# Re 2026/05/19/18:01
# name: generate_site_data
# description: 从总表生成静态站所需的 JSON 数据文件，供 GitHub Pages 前端展示日报和仪表盘

"""
从 Object-Models.xlsx 总表生成前端展示所需的 JSON 数据。

输出到 docs/data/ 目录：
  - daily_report.json     — 最新日报数据（按发布时间筛选）
  - dashboard.json        — 仪表盘统计数据（趋势、分布等）
  - all_models.json       — 全量模型数据（含所有Excel列，供前端交互表格）
  - history_index.json    — 历史日报文件列表（供前端切换）
  - site_meta.json        — 站点元信息（数据源列表、README内容等）
  - history/YYYYMMDD.json — 历史日报归档

用法:
    python generate_site_data.py --since 20260518 --until 20260519
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 过滤 & 去重常量
# ---------------------------------------------------------------------------
GAP_MAX_DAYS = 7  # release_date 与 created_date 最大允许间隔
GAP_FILTER_SINCE = "2026-05-28"  # gap 过滤仅对此日期及之后创建的模型生效
LLM_DEDUP_BATCH_SIZE = 40  # 每批送 LLM 查重的模型数
DEDUP_LOOKBACK_DAYS = 30   # 去重时回看总表最近N天的模型

ROOT = Path(__file__).parent
EXCEL_PATH = ROOT / "data" / "Object-Models.xlsx"
README_PATH = ROOT.parent / "README.md"
DOCS_DIR = ROOT.parent / "docs"
DATA_DIR = DOCS_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
DROPOUT_PATH = DATA_DIR / "dropout.json"

# 当前启用的数据源（与 auto_collect.py 同步维护）
ACTIVE_DATA_SOURCES = [
    {
        "name": "llm-stats.com",
        "url": "https://llm-stats.com",
        "status": "active",
        "description": "HTTP 直连 + Next.js RSC JSON 解析，有可靠时间戳",
        "sub_sources": [
            {"name": "llm-stats-LLM.com", "url": "https://llm-stats.com", "description": "主站 LLM 模型列表"},
            {"name": "llm-stats-ai.com", "url": "https://ai.llm-stats.com", "description": "AI 综合模型数据"},
            {"name": "llm-stats-open-llm.com", "url": "https://open-llm.llm-stats.com", "description": "开源 LLM 排行"},
            {"name": "llm-stats-updates.com", "url": "https://updates.llm-stats.com", "description": "模型更新动态"},
        ],
    },
    {
        "name": "腾讯研究院AI速递",
        "url": "https://mp.sohu.com/profile?xpt=bGl1amluc29uZzIwMDBAMTI2LmNvbQ==",
        "status": "active",
        "description": "双模式爬虫 + LLM 提取，文章自带日期天然时间锚定",
    },
    {
        "name": "HuggingFace",
        "url": "https://huggingface.co",
        "status": "active",
        "description": "API createdAt 字段精确到秒，时间过滤可靠",
    },
    {
        "name": "平台模型目录（12平台）",
        "url": "",
        "status": "suspended",
        "description": "灌入旧模型根因未解决（created=0 + LLM降级查错）",
        "sub_sources": [
            {"name": "火山引擎（字节/豆包）", "url": "https://ark.cn-beijing.volces.com/api/v3"},
            {"name": "OpenRouter（聚合平台）", "url": "https://openrouter.ai/api/v1"},
            {"name": "Moonshot / Kimi", "url": "https://api.moonshot.cn/v1"},
            {"name": "智谱 BigModel（GLM）", "url": "https://open.bigmodel.cn/api/paas/v4"},
            {"name": "MiniMax（海螺AI）", "url": "https://api.minimaxi.com/v1"},
            {"name": "MIMO（小米）", "url": "https://api.xiaomimimo.com/v1"},
            {"name": "百度千帆（ERNIE）", "url": "https://qianfan.baidubce.com"},
            {"name": "硅基流动 SiliconFlow", "url": "https://api.siliconflow.cn/v1"},
            {"name": "DeepSeek 官方", "url": "https://api.deepseek.com"},
            {"name": "阶跃星辰 StepFun", "url": "https://api.stepfun.com/v1"},
            {"name": "DashScope（通义千问）", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
            {"name": "腾讯混元", "url": "https://api.hunyuan.cloud.tencent.com/v1"},
        ],
    },
    {
        "name": "LM Arena 排行榜",
        "url": "https://lmarena.ai",
        "status": "suspended",
        "description": "排行榜无发布时间，全量灌入无法过滤",
    },
]


def _clean_value(value) -> str:
    """将 pandas 单元格值转为干净的字符串（处理 NaN、NaT、None）。"""
    if value is None:
        return ""
    s = str(value)
    if s in ("nan", "NaN", "NaT", "None", "nat"):
        return ""
    return s.strip()


def _normalize_date(value) -> str:
    """将日期值统一为 YYYY-MM-DD 格式（去掉时间部分）。"""
    if value is None:
        return ""
    # pandas NaT
    if pd.isna(value):
        return ""
    # pandas Timestamp / datetime
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if s in ("nan", "NaN", "NaT", "None", "nat", ""):
        return ""
    # 已经是 YYYY-MM-DD 格式
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # YYYY-MM-DD HH:MM:SS 格式，截取日期部分
    if re.match(r"^\d{4}-\d{2}-\d{2}\s", s):
        return s[:10]
    # 尝试解析其他格式
    try:
        dt = pd.to_datetime(s)
        if pd.notna(dt):
            return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    return s


def _normalize_name(name: str) -> str:
    """归一化模型名称用于去重比较。"""
    return re.sub(r"[-_\s.()\u3000]", "", (name or "")).lower()


def _is_substring_match(name_a: str, name_b: str) -> bool:
    """检查两个归一化名称是否存在子串包含关系（语义重复）。

    例如 "fable5" 是 "claudefable5" 的子串 → 视为重复。

    排除规则（避免误杀同系列不同规格的模型）：
      - 短名称至少4字符才触发
      - 差异部分若仅是参数量后缀（如 235b、7b）则不算重复
      - 短名占长名比例 < 50% 时不匹配（避免公共前缀误伤）
    """
    if not name_a or not name_b or name_a == name_b:
        return name_a == name_b
    short, long = (name_a, name_b) if len(name_a) <= len(name_b) else (name_b, name_a)
    if len(short) < 4:
        return False
    if short not in long:
        return False
    # 差异部分（去掉匹配后的残余）
    residue = long.replace(short, "", 1)
    # 若残余仅为参数量后缀（数字+b/m/k），视为不同规格而非重复
    if re.fullmatch(r"\d+[bmk]?", residue):
        return False
    # 短名占比过低（<50%）不匹配，避免 "qwen" 匹配 "qwen3turbo235b" 这种
    if len(short) / len(long) < 0.5:
        return False
    return True


def _calc_gap(release_date: str, created_date: str) -> int | None:
    """计算 created_date - release_date 天数差。"""
    rd = (release_date or "").strip()
    cd = (created_date or "").strip()
    if not rd or len(rd) < 10 or "XX" in rd:
        return None
    try:
        rd_dt = datetime.strptime(rd[:10], "%Y-%m-%d")
        cd_dt = datetime.strptime(cd[:10], "%Y-%m-%d")
        return (cd_dt - rd_dt).days
    except (ValueError, TypeError):
        return None


def filter_stale_models(models: list[dict]) -> tuple[list[dict], list[dict]]:
    """过滤 gap > GAP_MAX_DAYS 的过时模型。

    仅对 created_date >= GAP_FILTER_SINCE 的模型生效，更早的历史数据不动。

    Returns:
        (kept, removed) 两个列表。
    """
    kept, removed = [], []
    for m in models:
        created = m.get("created_date") or ""
        if created < GAP_FILTER_SINCE:
            kept.append(m)
            continue
        gap = _calc_gap(m.get("release_date"), created)
        if gap is not None and gap > GAP_MAX_DAYS:
            removed.append(m)
        else:
            kept.append(m)
    if removed:
        print(f"  [filter] stale removed: {len(removed)} (gap>{GAP_MAX_DAYS}d, since {GAP_FILTER_SINCE})")
    return kept, removed


def dedup_models_by_name(models: list[dict], existing: list[dict] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """基于名称归一化+子串包含关系去重。保留 created_date 最早的。

    两层检查：
      1. 精确匹配：归一化名称完全相同
      2. 子串匹配：短名称是长名称的子串（≥4字符）

    Args:
        models: 待去重列表。
        existing: 已有模型（用于跨批次查重），不会被删除。
    Returns:
        (kept, removed, dropout_records) 三个列表。
        dropout_records: 包含 {name, reason, matched_with, removed_at} 的记录。
    """
    seen: dict[str, str] = {}  # normalized_name → original_name
    if existing:
        for m in existing:
            norm = _normalize_name(m.get("name", ""))
            if norm:
                seen[norm] = m.get("name", "")

    kept, removed = [], []
    dropout_records = []
    sorted_models = sorted(models, key=lambda x: (x.get("created_date") or "9999"))

    for m in sorted_models:
        name = m.get("name", "")
        key = _normalize_name(name)
        if not key:
            kept.append(m)
            continue

        # 层1：精确匹配
        if key in seen:
            removed.append(m)
            dropout_records.append({
                "name": name,
                "reason": f"name_exact_match: '{seen[key]}'",
                "matched_with": seen[key],
                "removed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            continue

        # 层2：子串包含关系
        substring_match = None
        for existing_key, existing_name in seen.items():
            if _is_substring_match(key, existing_key):
                substring_match = existing_name
                break

        if substring_match:
            removed.append(m)
            dropout_records.append({
                "name": name,
                "reason": f"name_substring_match: '{substring_match}'",
                "matched_with": substring_match,
                "removed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            continue

        seen[key] = name
        kept.append(m)

    if removed:
        print(f"  [dedup] name-based removed: {len(removed)}")
        for d in dropout_records:
            print(f"    - drop '{d['name']}' : {d['reason']}")
    return kept, removed, dropout_records


def _append_dropout_records(dedup_records: list[dict], stale_removed: list[dict]):
    """将去重/过滤丢弃的模型追加到 dropout.json（范例学习库）。

    dropout.json 结构：
    {
      "description": "采集过程中被丢弃的模型记录，作为未来去重/过滤的范例学习库",
      "total": N,
      "records": [...]
    }
    """
    new_records = list(dedup_records)  # dedup已有完整记录

    # stale过滤的也记录
    for m in stale_removed:
        new_records.append({
            "name": m.get("name", ""),
            "reason": f"stale_gap: release={m.get('release_date', '')} created={m.get('created_date', '')}",
            "matched_with": "",
            "removed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    if not new_records:
        return

    # 读取已有记录
    existing = {"description": "采集过程中被丢弃的模型记录，作为去重/过滤的范例学习库", "total": 0, "records": []}
    if DROPOUT_PATH.exists():
        try:
            with open(DROPOUT_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, Exception):
            pass

    records = existing.get("records", [])
    records.extend(new_records)

    # 保留最近500条，避免无限增长
    if len(records) > 500:
        records = records[-500:]

    existing["records"] = records
    existing["total"] = len(records)
    existing["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(DROPOUT_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"  [dropout] appended {len(new_records)} records → {DROPOUT_PATH.name} (total: {len(records)})")


def dedup_models_by_llm(models: list[dict]) -> tuple[list[dict], list[dict]]:
    """调用 LLM 做语义级查重（名称/公司相近但不完全相同的模型）。

    Returns:
        (kept, removed) 两个列表。
    """
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        print("  [llm-dedup] LLM_API_KEY not set, skipping LLM dedup")
        return models, []

    api_base = os.environ.get("LLM_API_BASE", "https://api.kuai.host/v1")
    model = os.environ.get("LLM_MODEL_REVIEW", "gpt-5.5")

    # 构建简洁的模型列表供 LLM 判断
    entries = []
    for i, m in enumerate(models):
        entries.append({
            "idx": i,
            "name": m.get("name", ""),
            "company": m.get("company", ""),
            "type": m.get("type", ""),
            "release_date": m.get("release_date", ""),
        })

    all_remove_indices = set()

    # 分批处理
    for batch_start in range(0, len(entries), LLM_DEDUP_BATCH_SIZE):
        batch = entries[batch_start:batch_start + LLM_DEDUP_BATCH_SIZE]
        prompt = (
            "以下是一批 AI 模型记录，请找出语义上重复的模型组（同一模型的不同名称写法、"
            "不同版本后缀但本质相同的条目）。\n\n"
            "对每组重复，保留 idx 最小的（最早采集），标记其他为移除。\n"
            "只输出 JSON：{\"remove_indices\": [idx1, idx2, ...]}\n"
            "如果没有重复，输出 {\"remove_indices\": []}\n\n"
            f"模型列表：\n{json.dumps(batch, ensure_ascii=False, indent=1)}"
        )

        try:
            import urllib.request
            url = f"{api_base.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }).encode()
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content)
            remove_ids = parsed.get("remove_indices", [])
            all_remove_indices.update(remove_ids)
            if remove_ids:
                removed_names = [entries[i]["name"] for i in remove_ids if i < len(entries)]
                print(f"  [llm-dedup] batch {batch_start}: remove {len(remove_ids)} → {removed_names}")
        except Exception as e:
            print(f"  [llm-dedup] batch {batch_start} error: {e}")
        time.sleep(1)  # 限流

    kept = [m for i, m in enumerate(models) if i not in all_remove_indices]
    removed = [m for i, m in enumerate(models) if i in all_remove_indices]
    if removed:
        print(f"  [llm-dedup] total removed: {len(removed)}")
    return kept, removed


def load_master_table() -> pd.DataFrame:
    """加载总表。"""
    if not EXCEL_PATH.exists():
        print(f"[ERROR] master table not found: {EXCEL_PATH}")
        return pd.DataFrame()
    return pd.read_excel(EXCEL_PATH, engine="openpyxl")


def _row_to_model(row) -> dict:
    """将 DataFrame 行转为标准模型字典（15列，去掉是否新增和核实情况）。"""
    return {
        "name": _clean_value(row.get("模型名称")),
        "connected": _clean_value(row.get("是否接入")),
        "workflow_progress": _clean_value(row.get("workflow接入进展")),
        "company": _clean_value(row.get("公司")),
        "domestic": _clean_value(row.get("国内外")),
        "open_source": _clean_value(row.get("开闭源")),
        "size": _clean_value(row.get("尺寸")),
        "type": _clean_value(row.get("类型")),
        "reasoning": _clean_value(row.get("能否推理")),
        "task_type": _clean_value(row.get("任务类型")),
        "website": _clean_value(row.get("官网")),
        "note": _clean_value(row.get("备注")),
        "release_date": _normalize_date(row.get("模型发布时间")),
        "created_date": _normalize_date(row.get("记录创建时间")),
        "data_source": _clean_value(row.get("data_source")),
    }


def extract_daily_from_total(total_models: list[dict], since: str, until: str) -> dict:
    """从已过滤去重的总表中提取日报：created_date 在 [since, until] 范围内的模型。

    总表增量了什么，日报就增量什么——日报是总表的子集，不独立过滤。
    """
    since_dash = f"{since[:4]}-{since[4:6]}-{since[6:8]}"
    until_dash = f"{until[:4]}-{until[4:6]}-{until[6:8]}"

    daily_models = [
        m for m in total_models
        if since_dash <= (m.get("created_date") or "") <= until_dash
    ]

    return {
        "models": daily_models,
        "meta": {
            "since": since_dash,
            "until": until_dash,
            "count": len(daily_models),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def generate_dashboard(dataframe: pd.DataFrame) -> dict:
    """生成仪表盘统计 JSON 数据。"""
    total = len(dataframe)
    if total == 0:
        return {"total": 0, "by_type": {}, "by_domestic": {}, "by_open_source": {}, "trend": []}

    by_type = Counter(dataframe.get("类型", pd.Series(dtype=str)).fillna("未知"))
    by_domestic = Counter(dataframe.get("国内外", pd.Series(dtype=str)).fillna("未知"))
    by_open_source = Counter(dataframe.get("开闭源", pd.Series(dtype=str)).fillna("未知"))

    # 按月趋势（模型发布时间）
    trend = []
    if "模型发布时间" in dataframe.columns:
        dates = pd.to_datetime(dataframe["模型发布时间"], errors="coerce")
        monthly = dates.dt.to_period("M").value_counts().sort_index()
        for period, count in monthly.items():
            if pd.notna(period):
                trend.append({"month": str(period), "count": int(count)})

    # 最近7天新增
    recent_count = 0
    if "记录创建时间" in dataframe.columns:
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        created_col = dataframe["记录创建时间"].astype(str)
        recent_count = int(((created_col >= week_ago) & (created_col <= today + "z")).sum())

    return {
        "total": total,
        "recent_7d": recent_count,
        "by_type": dict(by_type.most_common()),
        "by_domestic": dict(by_domestic),
        "by_open_source": dict(by_open_source),
        "trend": trend,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    parser = argparse.ArgumentParser(description="生成静态站 JSON 数据")
    parser.add_argument("--since", required=True, help="起始日期 YYYYMMDD")
    parser.add_argument("--until", required=True, help="截止日期 YYYYMMDD")
    args = parser.parse_args()

    # 确保目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # 加载总表
    dataframe = load_master_table()
    if dataframe.empty:
        print("[WARN] master table is empty, generating empty data")

    # ── 第一步：生成总表（过滤 + 去重）──
    # 读取回收站文件，排除其中的模型
    recycle_path = DATA_DIR / "recycle.json"
    recycled_names = set()
    if recycle_path.exists():
        with open(recycle_path, "r", encoding="utf-8") as f:
            recycle_data = json.load(f)
            for item in recycle_data.get("models", []):
                recycled_names.add(item.get("name", ""))

    all_models_list = [_row_to_model(row) for _, row in dataframe.iterrows()]
    active_models = [m for m in all_models_list if m.get("name", "") not in recycled_names]

    print("[FILTER] applying stale + dedup to all_models...")
    active_models, stale_rm = filter_stale_models(active_models)
    active_models, dedup_rm, dropout_records = dedup_models_by_name(active_models)

    # 写入 dropout.json（追加模式，保留历史记录作为范例学习库）
    _append_dropout_records(dropout_records, stale_rm)

    all_models_data = {
        "models": active_models,
        "meta": {
            "total": len(active_models),
            "recycled": len(recycled_names),
            "stale_filtered": len(stale_rm),
            "dedup_filtered": len(dedup_rm),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
    all_models_path = DATA_DIR / "all_models.json"
    with open(all_models_path, "w", encoding="utf-8") as f:
        json.dump(all_models_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] all_models: {all_models_path.name} ({len(active_models)} models, {len(recycled_names)} recycled)")

    # ── 第二步：日报 = 总表中 created_date 在范围内的子集 ──
    # 总表增量了什么，日报就增量什么
    report = extract_daily_from_total(active_models, args.since, args.until)
    report_path = DATA_DIR / "daily_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] daily_report: {report_path.name} ({report['meta']['count']} models)")

    # 归档历史
    history_path = HISTORY_DIR / f"{args.since}_{args.until}.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] history: {history_path.name}")

    # ── 第三步：仪表盘 ──
    dashboard = generate_dashboard(dataframe)
    dashboard_path = DATA_DIR / "dashboard.json"
    with open(dashboard_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    print(f"[OK] dashboard: {dashboard_path.name} (total {dashboard['total']} models)")

    # 3.5 接入站数据（workflow接入进展=1 的模型）
    connected_path = DATA_DIR / "connected.json"
    # 如果 connected.json 已存在且有手动维护的数据，保留它；否则从 Excel 生成
    if not connected_path.exists():
        connected_models = [m for m in all_models_list if m.get("workflow_progress") == "1.0" or m.get("workflow_progress") == "1"]
        connected_data = {
            "models": connected_models,
            "meta": {
                "total": len(connected_models),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
        with open(connected_path, "w", encoding="utf-8") as f:
            json.dump(connected_data, f, ensure_ascii=False, indent=2)
        print(f"[OK] connected: {connected_path.name} ({len(connected_models)} models, initial generation)")
    else:
        print(f"[SKIP] connected: {connected_path.name} already exists (manually maintained)")

    # 4. 历史日报索引
    # 同步 Report/ 下的 JSON 日报到 history/
    report_dir = ROOT / "Report"
    if report_dir.exists():
        import shutil
        for rpt_file in report_dir.glob("*.json"):
            if rpt_file.name == "review_results.json":
                continue
            dest = HISTORY_DIR / rpt_file.name
            if not dest.exists():
                shutil.copy2(rpt_file, dest)
                print(f"[OK] synced Report/{rpt_file.name} -> history/")

    # 列出 history/ 下所有 JSON 文件供前端切换
    history_files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    history_index = []
    for hf in history_files:
        if hf.name == ".gitkeep":
            continue
        stem = hf.stem
        parts = stem.split("_")
        if len(parts) == 2:
            since_str = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]}"
            until_str = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}"
            history_index.append({
                "file": f"history/{hf.name}",
                "since": since_str,
                "until": until_str,
                "label": f"{since_str} ~ {until_str}",
            })

    # 同时扫描 Report/ 下的 daily_report_*.md，复制到 history/ 并加入索引
    if report_dir.exists():
        import shutil as _shutil
        for md_file in sorted(report_dir.glob("daily_report_*.md"), reverse=True):
            match = re.search(r"daily_report_(\d{8})-(\d{8})", md_file.name)
            if match:
                s, u = match.group(1), match.group(2)
                since_str = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
                until_str = f"{u[:4]}-{u[4:6]}-{u[6:8]}"
                label = f"{since_str} ~ {until_str}"
                # 复制到 history/ 目录
                dest = HISTORY_DIR / md_file.name
                if not dest.exists():
                    _shutil.copy2(md_file, dest)
                # 避免重复
                if not any(h["label"] == label for h in history_index):
                    history_index.append({
                        "file": f"history/{md_file.name}",
                        "since": since_str,
                        "until": until_str,
                        "label": label,
                        "format": "md",
                    })

    # 按 since 降序排列
    history_index.sort(key=lambda x: x.get("since", ""), reverse=True)

    history_index_path = DATA_DIR / "history_index.json"
    with open(history_index_path, "w", encoding="utf-8") as f:
        json.dump(history_index, f, ensure_ascii=False, indent=2)
    print(f"[OK] history_index: {history_index_path.name} ({len(history_index)} entries)")

    # 5. 站点元信息（数据源列表 + README 内容）
    readme_content = ""
    if README_PATH.exists():
        readme_content = README_PATH.read_text(encoding="utf-8")

    site_meta = {
        "data_sources": ACTIVE_DATA_SOURCES,
        "readme": readme_content,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    site_meta_path = DATA_DIR / "site_meta.json"
    with open(site_meta_path, "w", encoding="utf-8") as f:
        json.dump(site_meta, f, ensure_ascii=False, indent=2)
    print(f"[OK] site_meta: {site_meta_path.name} (readme {len(readme_content)} chars)")

    # 6. Pipeline 日志（从 pipeline_trace.json 转换为前端可消费格式）
    _generate_pipeline_log()


def _generate_pipeline_log():
    """将 Model_Navigate/data/pipeline_trace.json 转换为 docs/data/pipeline_log.json。

    前端日志Tab读取 pipeline_log.json 按日期展示pipeline执行记录。
    """
    trace_path = ROOT / "data" / "pipeline_trace.json"
    log_path = DATA_DIR / "pipeline_log.json"

    # 读取已有日志（追加模式）
    existing_runs = []
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                existing_runs = existing_data.get("runs", [])
        except (json.JSONDecodeError, Exception):
            pass

    existing_run_ids = {r.get("run_id") for r in existing_runs}

    # 读取最新trace
    if trace_path.exists():
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                trace = json.load(f)
            run_id = trace.get("run_id", "")
            if run_id and run_id not in existing_run_ids:
                run_entry = {
                    "run_id": run_id,
                    "date": trace.get("trigger_time", "")[:10],
                    "trigger_time": trace.get("trigger_time", ""),
                    "trigger_type": trace.get("trigger_type", ""),
                    "status": trace.get("status", ""),
                    "new_count": trace.get("new_count", 0),
                    "duration_seconds": trace.get("duration_seconds", 0),
                    "since": trace.get("since", ""),
                    "until": trace.get("until", ""),
                    "steps": trace.get("steps", []),
                }
                existing_runs.insert(0, run_entry)  # 最新的排前面
                print(f"  [pipeline_log] added run: {run_id}")
        except (json.JSONDecodeError, Exception) as exc:
            print(f"  [pipeline_log] failed to read trace: {exc}")

    # 保留最近90条
    if len(existing_runs) > 90:
        existing_runs = existing_runs[:90]

    log_data = {
        "description": "Pipeline 执行日志，供前端日志Tab展示",
        "total": len(existing_runs),
        "runs": existing_runs,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] pipeline_log: {log_path.name} ({len(existing_runs)} runs)")


if __name__ == "__main__":
    main()
