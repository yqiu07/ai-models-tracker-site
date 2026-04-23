"""AI 模型/智能体追踪器 - CLI 入口。

用法示例：
  python tracker.py                                    # 默认增量（last_published → now）
  python tracker.py --since 2026-04-15 --until 2026-04-23  # 时间窗口查询
  python tracker.py --stage fetch                      # 只跑抓取
  python tracker.py --stage diff --resume              # 从最近 fetch ckpt 续跑 diff
  python tracker.py --dry-run                          # 不推送、不写 Excel、不更新 state
  python tracker.py --check                            # 仅检查环境/数据源健康
  python tracker.py --verbose                          # 详细日志
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tracker.persistence import (
    CST,
    find_latest_checkpoint,
    load_diff_checkpoint,
    load_enrich_checkpoint,
    load_fetch_checkpoint,
    load_state,
    now_cst_iso,
    now_cst_tag,
    save_diff_checkpoint,
    save_enrich_checkpoint,
    save_state,
    today_cst_date,
    update_state_after_publish,
)

# ─────────────────────────────────────────────────────────────
# 路径常量
# ─────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
STATE_DIR = ROOT / "state"
CHECKPOINT_DIR = STATE_DIR / "checkpoints"

OPML_PATH = CONFIG_DIR / "ai-feeds.opml"
FIELD_PROMPT_PATH = CONFIG_DIR / "prompts" / "classify_field.txt"
NOTE_PROMPT_PATH = CONFIG_DIR / "prompts" / "distill_note.txt"
EXCEL_PATH = DATA_DIR / "Object-Models-Updated.xlsx"
STATE_FILE = STATE_DIR / "last_published.json"


# ─────────────────────────────────────────────────────────────
# Stage 调度
# ─────────────────────────────────────────────────────────────

async def stage_fetch(args, since_dt: Optional[datetime]):
    from tracker.fetch import run_fetch
    return await run_fetch(
        opml_path=OPML_PATH,
        output_dir=CHECKPOINT_DIR,
        cutoff_dt=since_dt,
        enable_zeroeval=True,
        enable_rss=True,
    )


def stage_diff(fetch_path: Path, since_dt: Optional[datetime], until_dt: Optional[datetime]):
    from tracker.diff import diff_against_history

    fetch_data = load_fetch_checkpoint(fetch_path)
    state = load_state(STATE_FILE)
    new_models, skipped = diff_against_history(
        fetch_data,
        history_xlsx=EXCEL_PATH,
        state_fingerprints=state.get("fingerprints", []),
        since_dt=since_dt,
        until_dt=until_dt,
    )
    window = (
        since_dt.isoformat() if since_dt else "(unbounded)",
        until_dt.isoformat() if until_dt else now_cst_iso(),
    )
    tag = now_cst_tag()
    save_diff_checkpoint(new_models, skipped, window, CHECKPOINT_DIR, tag)
    return new_models, skipped, window


async def stage_enrich(diff_path: Path):
    from tracker.enrich import enrich_records

    diff_data = load_diff_checkpoint(diff_path)
    new_models = diff_data["new_models"]
    if not new_models:
        logging.info("[enrich] 无新增模型，跳过 LLM 调用")
        enriched = []
    else:
        enriched = await enrich_records(
            new_models,
            field_prompt_path=FIELD_PROMPT_PATH,
            note_prompt_path=NOTE_PROMPT_PATH,
        )
    window = tuple(diff_data["window"])
    tag = now_cst_tag()
    save_enrich_checkpoint(enriched, window, CHECKPOINT_DIR, tag)
    return enriched, window


def stage_publish(enrich_path: Path, dry_run: bool, output_format: str = "html"):
    from tracker.publish import publish_all

    enrich_data = load_enrich_checkpoint(enrich_path)
    enriched = enrich_data["enriched_models"]
    window = tuple(enrich_data["window"])
    return publish_all(
        enriched,
        window=window,
        excel_path=EXCEL_PATH,
        docs_dir=DOCS_DIR,
        dry_run=dry_run,
        output_format=output_format,
    ), enriched, window


async def stage_notify(enriched, window, products, dry_run: bool):
    from tracker.notify import notify

    site_url = os.getenv("TRACKER_SITE_URL", "").rstrip("/")
    if site_url:
        daily_url = f"{site_url}/daily/{today_cst_date()}.html"
        excel_url = f"{site_url}/data/Object-Models-Updated.xlsx"
    else:
        daily_url = products["daily_html"].as_uri()
        excel_url = products["excel"].as_uri()

    return await notify(enriched, window, daily_url, excel_url, dry_run=dry_run)


# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────

def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # 支持 YYYY-MM-DD 或完整 ISO
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=CST)
        return datetime.fromisoformat(s)
    except Exception as e:
        raise SystemExit(f"无法解析日期: {s} ({e})")


async def run_pipeline(args):
    # 1. 计算时间窗口
    state = load_state(STATE_FILE)
    if args.since:
        since_dt = parse_dt(args.since)
    else:
        since_dt = parse_dt(state.get("last_published_at"))
    until_dt = parse_dt(args.until) if args.until else datetime.now(CST)
    logging.info(f"时间窗口: [{since_dt} ~ {until_dt}]")

    fetch_path = None
    diff_path = None
    enrich_path = None

    # 2. 阶段调度
    if args.stage in (None, "fetch"):
        fetch_path, _ = await stage_fetch(args, since_dt)
        if args.stage == "fetch":
            logging.info(f"✓ fetch 完成: {fetch_path}")
            return

    if args.stage == "diff" and args.resume:
        fetch_path = find_latest_checkpoint(CHECKPOINT_DIR, "fetch")
        if not fetch_path:
            raise SystemExit("找不到 fetch checkpoint，无法 resume")

    if args.stage in (None, "diff"):
        if fetch_path is None:
            fetch_path = find_latest_checkpoint(CHECKPOINT_DIR, "fetch")
            if not fetch_path:
                raise SystemExit("找不到 fetch checkpoint，请先运行 --stage fetch")
        new_models, skipped, window = stage_diff(fetch_path, since_dt, until_dt)
        diff_path = find_latest_checkpoint(CHECKPOINT_DIR, "diff")
        if args.stage == "diff":
            logging.info(
                f"✓ diff 完成: 新增={len(new_models)}, 已知跳过={len(skipped)}"
            )
            return

    if args.stage == "enrich" and args.resume:
        diff_path = find_latest_checkpoint(CHECKPOINT_DIR, "diff")
        if not diff_path:
            raise SystemExit("找不到 diff checkpoint，无法 resume")

    if args.stage in (None, "enrich"):
        if diff_path is None:
            diff_path = find_latest_checkpoint(CHECKPOINT_DIR, "diff")
            if not diff_path:
                raise SystemExit("找不到 diff checkpoint，请先运行 --stage diff")
        enriched, window = await stage_enrich(diff_path)
        enrich_path = find_latest_checkpoint(CHECKPOINT_DIR, "enrich")
        if args.stage == "enrich":
            logging.info(f"✓ enrich 完成: {len(enriched)} 条")
            return

    if args.stage == "publish" and args.resume:
        enrich_path = find_latest_checkpoint(CHECKPOINT_DIR, "enrich")
        if not enrich_path:
            raise SystemExit("找不到 enrich checkpoint，无法 resume")

    if args.stage in (None, "publish"):
        if enrich_path is None:
            enrich_path = find_latest_checkpoint(CHECKPOINT_DIR, "enrich")
            if not enrich_path:
                raise SystemExit("找不到 enrich checkpoint，请先运行 --stage enrich")
        products, enriched, window = stage_publish(
            enrich_path, dry_run=args.dry_run, output_format=args.output_format,
        )
        product_names = [f"{k}={v.name}" for k, v in products.items() if k != "excel"]
        logging.info(
            f"✓ publish 完成: {', '.join(product_names)}, Excel={products['excel'].name}"
        )
        if args.stage == "publish":
            return
    else:
        # 仅 notify 时也需要拿到产物路径
        products = None
        enriched = []
        window = ("", "")

    if args.stage == "notify" and args.resume:
        enrich_path = find_latest_checkpoint(CHECKPOINT_DIR, "enrich")
        if not enrich_path:
            raise SystemExit("找不到 enrich checkpoint，无法 resume")
        # notify 阶段 resume 需要 publish 产物，但产物路径可由约定推断
        products, enriched, window = stage_publish(
            enrich_path, dry_run=True, output_format=args.output_format,
        )

    # notify 阶段：默认跳过，需要 --notify 或 --stage notify 才执行
    should_notify = args.notify or args.stage == "notify"
    if not should_notify and args.stage is None:
        logging.info("[notify] 未指定 --notify，跳过钉钉推送。提示: 加 --notify 可推送到钉钉")

    if should_notify:
        if products is None or not enriched:
            logging.warning("[notify] 缺少 publish 产物，跳过")
            success = False
        else:
            success = await stage_notify(enriched, window, products, dry_run=args.dry_run)
    else:
        success = True  # 不推送也算成功，以便更新 state

    # 5. 成功后更新状态（增量模式 + 非 dry-run + 非自定义窗口）
    if (
        success
        and not args.dry_run
        and not args.since
        and args.stage in (None, "notify")
        and enriched
    ):
        new_state = update_state_after_publish(
            state,
            published_fingerprints=[r.fingerprint for r in enriched],
            published_count=len(enriched),
        )
        save_state(new_state, STATE_FILE)


# ─────────────────────────────────────────────────────────────
# --check 模式：环境与数据源健康检查
# ─────────────────────────────────────────────────────────────

async def run_check():
    """检查环境配置与数据源连通性。"""
    print("=" * 60)
    print("环境与数据源健康检查")
    print("=" * 60)

    # 1. 必要文件
    checks = [
        ("OPML 配置", OPML_PATH),
        ("字段分类 prompt", FIELD_PROMPT_PATH),
        ("备注浓缩 prompt", NOTE_PROMPT_PATH),
        ("历史 Excel", EXCEL_PATH),
    ]
    for name, path in checks:
        ok = path.exists()
        print(f"  [{'OK' if ok else '!!'}] {name}: {path}")

    # 2. 环境变量
    print("\n环境变量:")
    env_vars = [
        "TRACKER_FIELD_API_KEY", "TRACKER_FIELD_API_BASE", "TRACKER_FIELD_MODEL",
        "TRACKER_NOTE_MODEL", "DINGTALK_WEBHOOK", "TRACKER_PROXY", "TRACKER_SITE_URL",
    ]
    for v in env_vars:
        val = os.getenv(v, "")
        if val:
            shown = val[:20] + "..." if len(val) > 20 else val
            print(f"  [OK] {v} = {shown}")
        else:
            optional = v in ("DINGTALK_WEBHOOK", "TRACKER_PROXY", "TRACKER_SITE_URL", "TRACKER_NOTE_MODEL")
            print(f"  [{'--' if optional else '!!'}] {v} = (未配置{', 可选' if optional else ', 必填'})")

    # 3. RSS 源连通性（仅探测前 3 个）
    print("\nRSS 源探测（前 3 个）:")
    try:
        from tracker.sources.rss import parse_opml
        sources = parse_opml(OPML_PATH)
        for s in sources[:3]:
            print(f"  - {s['name']}: {s['xml_url']}")
        print(f"  ...共 {len(sources)} 个 RSS 源")
    except Exception as e:
        print(f"  [!!] OPML 解析失败: {e}")

    # 4. ZeroEval 端点列表
    print("\nZeroEval 端点:")
    from tracker.sources.zeroeval import ENDPOINTS, ZEROEVAL_BASE
    for name, path in ENDPOINTS.items():
        print(f"  - {name}: {ZEROEVAL_BASE}{path}")

    # 5. 状态文件
    print("\n状态文件:")
    if STATE_FILE.exists():
        state = load_state(STATE_FILE)
        print(f"  [OK] last_published_at = {state.get('last_published_at')}")
        print(f"  [OK] 已知指纹数 = {len(state.get('fingerprints', []))}")
        print(f"  [OK] 推送历史条数 = {len(state.get('history', []))}")
    else:
        print(f"  [--] 首次运行，状态文件将自动创建")

    print("=" * 60)


# ─────────────────────────────────────────────────────────────
# argparse + main
# ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tracker",
        description="AI 模型/智能体追踪器 - 增量抓取并推送到钉钉。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--stage",
        choices=["fetch", "diff", "enrich", "publish", "notify"],
        default=None,
        help="只跑指定阶段（不指定则完整跑）",
    )
    p.add_argument("--since", type=str, default=None, help="时间窗口起点 YYYY-MM-DD 或 ISO")
    p.add_argument("--until", type=str, default=None, help="时间窗口终点 YYYY-MM-DD 或 ISO")
    p.add_argument(
        "--resume",
        action="store_true",
        help="从最近的上一阶段 checkpoint 续跑（与 --stage 配合）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="不写真实 Excel、不推送钉钉、不更新 state",
    )
    p.add_argument(
        "--notify",
        action="store_true",
        help="启用钉钉推送（默认不推送，加此参数才推送）",
    )
    p.add_argument(
        "--output-format",
        choices=["html", "markdown", "both"],
        default="html",
        help="日报输出格式: html(默认) | markdown(Hugo兼容) | both",
    )
    p.add_argument("--check", action="store_true", help="仅检查环境与数据源健康")
    p.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    return p


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # aiohttp / asyncio 噪声压一下
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOCS_DIR, DOCS_DIR / "daily", STATE_DIR, CHECKPOINT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = build_parser().parse_args()
    setup_logging(args.verbose)
    ensure_dirs()

    if args.check:
        asyncio.run(run_check())
        return 0

    try:
        asyncio.run(run_pipeline(args))
        return 0
    except SystemExit:
        raise
    except Exception as e:
        logging.exception(f"流水线异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())