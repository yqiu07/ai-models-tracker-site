"""
AI 模型/智能体追踪日报 —— 钉钉推送
====================================
从总表按"模型发布时间"精确筛选窗口内的模型，生成日报 Markdown 并推送到钉钉群。
等同于在 Excel 中对"模型发布时间"列做筛选器勾选目标日期范围。

用法:
    python push_dingtalk.py --since 20260417 --until 20260423
    python push_dingtalk.py --since 20260417 --until 20260423 --dry-run
    python push_dingtalk.py --since 20260417 --until 20260423 --webhook https://oapi.dingtalk.com/robot/send?access_token=xxx

环境变量（或 .env 文件）:
    DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=your-token
    DINGTALK_SECRET=SECyour-secret  (可选，加签模式)

依赖:
    pip install pandas openpyxl requests python-dotenv
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests

# ── 路径常量 ──
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "Report"
# v6: 日报直接从总表按"模型发布时间"筛选，简单直接
# 等同于在 Excel 中对"模型发布时间"列做筛选器勾选目标日期
MASTER_PATH = DATA_DIR / "Object-Models.xlsx"
UPDATED_PATH = DATA_DIR / "Object-Models-Updated.xlsx"

# ── 钉钉 Markdown 最大长度 ──
DINGTALK_MAX_LENGTH = 18000


def load_env():
    """加载 .env 文件（如果存在）。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file = ROOT.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                value = value.strip()
                # 去掉引号包裹（如 WEBHOOK="https://..."）
                if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)


def dingtalk_sign(secret: str, timestamp: str) -> str:
    """计算钉钉加签模式的签名。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.HMAC(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return quote_plus(base64.b64encode(hmac_code))


def build_webhook_url(webhook: str, secret: str | None = None) -> str:
    """构建钉钉 Webhook URL（含可选签名参数）。"""
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    sign = dingtalk_sign(secret, timestamp)
    return f"{webhook}&timestamp={timestamp}&sign={sign}"


def format_date_range(since_int: int, until_int: int) -> str:
    """将 YYYYMMDD 格式化为可读日期范围。"""
    since_str = f"{str(since_int)[:4]}.{str(since_int)[4:6]}.{str(since_int)[6:]}"
    until_str = f"{str(until_int)[:4]}.{str(until_int)[4:6]}.{str(until_int)[6:]}"
    return f"{since_str} ~ {until_str}"


def _parse_date_int(raw_date) -> int | None:
    """将各种日期格式统一解析为 YYYYMMDD 整数。"""
    if pd.isna(raw_date):
        return None
    pub_str = str(raw_date).strip()
    if not pub_str or pub_str == "nan":
        return None
    # 去掉时间部分（如 "2026-04-20 00:00:00"）
    pub_str = pub_str.split(" ")[0].split("T")[0]
    try:
        return int(pub_str.replace("-", "").replace("/", "")[:8])
    except (ValueError, TypeError):
        return None


def load_models(excel_path: Path, since_int: int, until_int: int,
                created_date: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """从 Excel 加载数据，返回 (时间段内全部模型, 时间段内新增模型)。

    筛选逻辑：
      - 必选：模型发布时间精确落在 [since, until] 窗口内
      - 可选：若指定 created_date，则同时要求记录创建时间匹配（AND 关系）

    等同于在 Excel 中对"模型发布时间"列做筛选器（可选加"记录创建时间"筛选）。
    总表必须事先保证唯一性（合并前去重），这样日报不会出现重复模型。
    """
    df = pd.read_excel(excel_path, engine="openpyxl")

    release_col = "模型发布时间"
    create_col = "记录创建时间"

    all_in_range = []
    for _, row in df.iterrows():
        # 条件 1（必选）：发布时间在 [since, until]
        release_date_int = _parse_date_int(row.get(release_col)) if release_col in df.columns else None
        if release_date_int is None or not (since_int <= release_date_int <= until_int):
            continue

        # 条件 2（可选）：记录创建时间匹配
        if created_date is not None and create_col in df.columns:
            create_val = str(row.get(create_col, "")).strip()
            create_day = create_val.replace("/", "-")[:10]
            if create_day != created_date:
                continue

        all_in_range.append(row)

    df_all = pd.DataFrame(all_in_range) if all_in_range else pd.DataFrame(columns=df.columns)

    # 从全部模型中筛选新增（"是否新增"为 New / 是）
    if not df_all.empty and "是否新增" in df_all.columns:
        df_new = df_all[df_all["是否新增"].astype(str).str.strip().str.lower().isin(["new", "是"])].copy()
    else:
        df_new = df_all.copy()

    return df_all, df_new


def generate_daily_report(
    df_all: pd.DataFrame, df_new: pd.DataFrame,
    since_int: int, until_int: int,
) -> str:
    """从 DataFrame 生成 AI 模型/智能体追踪日报 Markdown。

    Args:
        df_all: 时间段内的全部模型
        df_new: 时间段内的新增模型（子集）
    """
    date_range = format_date_range(since_int, until_int)
    now = datetime.now()
    total_all = len(df_all)
    total_new = len(df_new)

    lines = [
        f'<font color="#6366F1">**📊 AI 模型/智能体追踪日报**</font>',
        f'<font color="#999999" size="2">{date_range}</font>',
        "",
        f"---",
        "",
    ]

    if total_all == 0:
        lines.append("本期时间窗口内无模型数据。")
        return "\n".join(lines)

    # 统计摘要（基于全部模型）
    domestic_count = len(df_all[df_all["国内外"].astype(str) == "国内"]) if "国内外" in df_all.columns else 0
    foreign_count = total_all - domestic_count
    open_count = len(df_all[df_all["开闭源"].astype(str) == "开源"]) if "开闭源" in df_all.columns else 0
    closed_count = len(df_all[df_all["开闭源"].astype(str) == "闭源"]) if "开闭源" in df_all.columns else 0

    lines.append(f"###### 📈 本期追踪 **{total_all}** 个模型/智能体，其中新增 **{total_new}** 个")
    lines.append(f"###### 国内 {domestic_count} · 国外 {foreign_count} · 开源 {open_count} · 闭源 {closed_count}")
    lines.append("")

    # 新增模型高亮区（按重要性分组）
    if total_new > 0:
        # 从备注中提取重要性标签（由 review_models.py 写入）
        high_models = []
        mid_models = []
        low_models = []
        for _, row in df_new.iterrows():
            name = str(row.get("模型名称", "")).strip()
            company = str(row.get("公司", "")).strip()
            note = str(row.get("备注", "")).strip()
            model_type = str(row.get("类型", "")).strip()
            size = str(row.get("尺寸", "")).strip()
            if company == "nan":
                company = ""
            if model_type == "nan":
                model_type = ""
            if size == "nan":
                size = ""
            if note == "nan":
                note = ""

            # 解析重要性标签和理由
            # 新格式: [重要性:高|理由文本]  旧格式: [重要性:高]
            import re as _re
            importance_match = _re.search(r'\[重要性[:：](高|中|低)(?:\|([^]]*))?\]', note)
            importance_level = importance_match.group(1) if importance_match else ""
            importance_reason = importance_match.group(2).strip() if importance_match and importance_match.group(2) else ""

            info = {"name": name, "company": company, "note": note,
                    "type": model_type, "size": size, "reason": importance_reason}

            if importance_level == "高":
                high_models.append(info)
            elif importance_level == "低":
                low_models.append(info)
            else:
                mid_models.append(info)

        # 🔴 最值得关注
        if high_models:
            lines.append(f'<font color="#EF4444">**🔴 最值得关注 ({len(high_models)})**</font>')
            lines.append("")
            for m in high_models:
                tag_parts = [p for p in [m["type"], m["size"]] if p]
                tag = f"  [{' · '.join(tag_parts)}]" if tag_parts else ""
                line = f"- **{m['name']}**"
                if m["company"]:
                    line += f" ({m['company']})"
                line += tag
                lines.append(line)
                # 优先展示理由，无理由时回退到备注
                reason_text = m.get("reason", "")
                if not reason_text:
                    reason_text = _re.sub(r'\s*\[重要性[:：][高中低](?:\|[^]]*)?\]', '', m["note"]).strip()
                if reason_text:
                    reason_short = reason_text[:60] + "..." if len(reason_text) > 60 else reason_text
                    lines.append(f'  <font color="#999999" size="2">💡 {reason_short}</font>')
            lines.append("")

        # 🟡 值得关注（变体合并防刷屏）
        if mid_models:
            def _base_name_for_highlight(name):
                """高亮区变体合并用的基座名提取"""
                n = str(name).strip()
                n = _re.sub(r'[-_]\d{4}-\d{2}-\d{2}$', '', n)
                n = _re.sub(r'[-_]\d{8}$', '', n)
                n = _re.sub(r'[-_]\d+\.?\d*[BbMm]$', '', n)
                n = _re.sub(r'[-_](preview|latest|fast|exp|beta|alpha)$', '', n, flags=_re.IGNORECASE)
                n = _re.sub(r'[-_](v\d+|[\d]{4,})$', '', n, flags=_re.IGNORECASE)
                return n.lower().strip()

            mid_groups = {}
            for m in mid_models:
                base = _base_name_for_highlight(m["name"])
                mid_groups.setdefault(base, []).append(m)

            lines.append(f'<font color="#F59E0B">**🟡 值得关注 ({len(mid_models)})**</font>')
            lines.append("")
            for base, members in mid_groups.items():
                if len(members) == 1:
                    m = members[0]
                    line = f"- **{m['name']}**"
                    if m["company"]:
                        line += f" ({m['company']})"
                    lines.append(line)
                    reason_text = m.get("reason", "")
                    if not reason_text:
                        reason_text = _re.sub(r'\s*\[重要性[:：][高中低](?:\|[^]]*)?\]', '', m["note"]).strip()
                    if reason_text:
                        reason_short = reason_text[:60] + "..." if len(reason_text) > 60 else reason_text
                        lines.append(f'  <font color="#999999" size="2">💡 {reason_short}</font>')
                else:
                    first = members[0]
                    names = [m["name"] for m in members]
                    line = f"- **{first['name']}** 等 {len(members)} 个变体"
                    if first["company"]:
                        line += f" ({first['company']})"
                    lines.append(line)
                    reason_text = first.get("reason", "")
                    if not reason_text:
                        reason_text = _re.sub(r'\s*\[重要性[:：][高中低](?:\|[^]]*)?\]', '', first["note"]).strip()
                    if reason_text:
                        reason_short = reason_text[:60] + "..." if len(reason_text) > 60 else reason_text
                        lines.append(f'  <font color="#999999" size="2">💡 {reason_short}</font>')
            lines.append("")

        # 🟢 其他新增（变体合并）
        if low_models:
            low_groups = {}
            for m in low_models:
                base = _base_name_for_highlight(m["name"])
                low_groups.setdefault(base, []).append(m)

            lines.append(f'<font color="#999999">**🟢 其他新增 ({len(low_models)})**</font>')
            lines.append("")
            for base, members in low_groups.items():
                if len(members) == 1:
                    m = members[0]
                    line = f"- {m['name']}"
                    if m["company"]:
                        line += f" ({m['company']})"
                    lines.append(line)
                else:
                    first = members[0]
                    line = f"- {first['name']} 等 {len(members)} 个变体"
                    if first["company"]:
                        line += f" ({first['company']})"
                    lines.append(line)
            lines.append("")

        # 如果没有重要性标签（review_models.py 未执行），回退到原始列表
        if not high_models and not mid_models and not low_models:
            lines.append(f'<font color="#10B981">**🆕 新增模型 ({total_new})**</font>')
            lines.append("")
            for _, row in df_new.iterrows():
                name = str(row.get("模型名称", "")).strip()
                company = str(row.get("公司", "")).strip()
                if company == "nan":
                    company = ""
                lines.append(f"- **{name}**" + (f" ({company})" if company else ""))
            lines.append("")

    lines.append("---")
    lines.append("")

    # 全部模型按公司分组展示（同系列变体合并为一个单元防刷屏）
    df = df_all
    if "公司" in df.columns:
        import re as _re
        company_groups = df.groupby("公司", sort=False)

        # 按模型数量排序
        sorted_groups = sorted(company_groups, key=lambda x: len(x[1]), reverse=True)

        for company, group in sorted_groups:
            company_str = str(company).strip()
            if not company_str or company_str == "nan":
                company_str = "未知"

            # 变体合并：同公司下，相同基座名的模型合并为一个单元
            # 基座名提取：去掉尾部的 -size/-variant（如 Qwen3-7B, Qwen3-14B → Qwen3）
            def _extract_base_name(name):
                """提取模型基座名（去掉尺寸/变体/日期后缀）"""
                n = str(name).strip()
                # 去掉日期后缀：-2026-04-16, -20260416, -0416
                n = _re.sub(r'[-_]\d{4}-\d{2}-\d{2}$', '', n)
                n = _re.sub(r'[-_]\d{8}$', '', n)
                # 去掉常见的尺寸后缀：-7B, -14B, -0.5B, -A3B
                n = _re.sub(r'[-_]\d+\.?\d*[BbMm]$', '', n)
                # 去掉变体标记：-preview, -latest, -fast
                n = _re.sub(r'[-_](preview|latest|fast|exp|beta|alpha)$', '', n, flags=_re.IGNORECASE)
                # 去掉末尾版本号如 -v1, -0711
                n = _re.sub(r'[-_](v\d+|[\d]{4,})$', '', n, flags=_re.IGNORECASE)
                # 注意：不去掉 turbo/flash/pro/max/mini 等，因为它们代表不同的模型线
                return n.lower().strip()

            base_groups = {}
            for _, row in group.iterrows():
                name = str(row.get("模型名称", "")).strip()
                base = _extract_base_name(name)
                if base not in base_groups:
                    base_groups[base] = []
                base_groups[base].append(row)

            model_count = len(group)
            unit_count = len(base_groups)
            lines.append(f'<font color="#6366F1">**{company_str}**</font> ({model_count})')
            lines.append("")

            for base, rows in base_groups.items():
                if len(rows) == 1:
                    # 单个模型，正常展示
                    row = rows[0]
                    name = str(row.get("模型名称", "")).strip()
                    model_type = str(row.get("类型", "")).strip()
                    note = str(row.get("备注", "")).strip()
                    if model_type == "nan":
                        model_type = ""
                    if note == "nan":
                        note = ""

                    model_line = f"- **{name}**"
                    if model_type:
                        model_line += f"  [{model_type}]"
                    lines.append(model_line)

                    if note and len(note) > 2:
                        note_clean = _re.sub(r'\s*\[重要性[:：][高中低](?:\|[^]]*)?\]', '', note).strip()
                        if note_clean:
                            note_short = note_clean[:80] + "..." if len(note_clean) > 80 else note_clean
                            lines.append(f'  <font color="#999999" size="2">{note_short}</font>')
                else:
                    # 多个变体，合并展示
                    variant_names = [str(r.get("模型名称", "")).strip() for r in rows]
                    first_row = rows[0]
                    model_type = str(first_row.get("类型", "")).strip()
                    note = str(first_row.get("备注", "")).strip()
                    if model_type == "nan":
                        model_type = ""
                    if note == "nan":
                        note = ""

                    # 用第一个名称作为系列标题，列出所有变体
                    series_label = variant_names[0]
                    model_line = f"- **{series_label}** 等 {len(rows)} 个变体"
                    if model_type:
                        model_line += f"  [{model_type}]"
                    lines.append(model_line)

                    # 变体列表简短展示
                    variants_str = "、".join(variant_names[1:4])
                    if len(variant_names) > 4:
                        variants_str += f" 等"
                    lines.append(f'  <font color="#999999" size="2">含: {variants_str}</font>')

                    if note and len(note) > 2:
                        note_clean = _re.sub(r'\s*\[重要性[:：][高中低](?:\|[^]]*)?\]', '', note).strip()
                        if note_clean:
                            note_short = note_clean[:60] + "..." if len(note_clean) > 60 else note_clean
                            lines.append(f'  <font color="#999999" size="2">{note_short}</font>')

            lines.append("")
    else:
        # 无公司列时简单列出
        for _, row in df.iterrows():
            name = str(row.get("模型名称", "")).strip()
            lines.append(f"- {name}")

    # 尾部
    lines.append("---")
    lines.append(
        f'###### <font color="#999999">数据来源：llm-stats.com · 腾讯研究院 · HuggingFace</font>'
    )
    lines.append(
        f'###### <font color="#999999">生成时间：{now.strftime("%Y-%m-%d %H:%M")}</font>'
    )

    text = "\n".join(lines)

    # 截断保护
    if len(text) > DINGTALK_MAX_LENGTH:
        text = text[:DINGTALK_MAX_LENGTH - 50] + "\n\n...(内容过长已截断)"

    return text


def push_to_dingtalk(markdown_text: str, webhook: str, secret: str | None = None) -> bool:
    """将 Markdown 推送到钉钉群。"""
    url = build_webhook_url(webhook, secret)

    title_match = markdown_text[:100]
    title = "AI 模型追踪日报"

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown_text,
        },
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        result = resp.json()
        if result.get("errcode") == 0:
            print(f"  ✅ 钉钉推送成功")
            return True
        else:
            print(f"  ❌ 钉钉推送失败: {result}")
            return False
    except Exception as exc:
        print(f"  ❌ 钉钉推送异常: {exc}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI 模型追踪日报 —— 钉钉推送",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python push_dingtalk.py --since 20260417 --until 20260423\n"
            "  python push_dingtalk.py --since 20260417 --until 20260423 --dry-run\n"
        ),
    )
    parser.add_argument("--since", type=str, help="起始日期 (YYYYMMDD)")
    parser.add_argument("--until", type=str, help="截止日期 (YYYYMMDD)")
    parser.add_argument("--created-date", type=str,
                        help="记录创建日期 (YYYY-MM-DD)，默认今天。用于筛选'本次入库'的模型")
    parser.add_argument("--webhook", type=str, help="钉钉 Webhook URL（覆盖环境变量）")
    parser.add_argument("--secret", type=str, help="钉钉加签密钥（覆盖环境变量）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不推送")
    parser.add_argument("--save-md", action="store_true", help="同时保存 Markdown 文件")
    return parser.parse_args()


def main():
    args = parse_args()
    load_env()

    today = datetime.now()
    if args.until:
        until_int = int(args.until)
    else:
        until_int = int(today.strftime("%Y%m%d"))
    if args.since:
        since_int = int(args.since)
    else:
        since_int = int((today - timedelta(days=7)).strftime("%Y%m%d"))

    webhook = args.webhook or os.environ.get("DINGTALK_WEBHOOK", "")
    secret = args.secret or os.environ.get("DINGTALK_SECRET", "")

    # 记录创建日期（可选，不指定则只按发布时间筛选）
    created_date = args.created_date if args.created_date else None

    # 日报数据源：总表
    data_source = MASTER_PATH
    source_label = "总表（按发布时间筛选）"
    if created_date:
        source_label += f" + 创建日期={created_date}"

    print("📊 AI 模型追踪日报")
    print(f"  时间窗口: {since_int} ~ {until_int}")
    if created_date:
        print(f"  记录创建日期: {created_date}")
    print(f"  数据源: {data_source.name} ← {source_label}")
    if args.dry_run:
        print("  模式: 🔍 DRY-RUN")
    print()

    # 加载数据
    if not data_source.exists():
        print(f"  ❌ 数据源不存在: {data_source}")
        return

    df_all, df_new = load_models(data_source, since_int, until_int, created_date=created_date)
    print(f"  📋 时间窗口内共 {len(df_all)} 个模型，其中新增 {len(df_new)} 个")

    if df_all.empty:
        print("  📭 时间窗口内无模型数据")
        return

    # 生成日报
    report = generate_daily_report(df_all, df_new, since_int, until_int)
    print(f"  📝 日报长度: {len(report)} 字符")

    # 保存 Markdown
    if args.save_md or args.dry_run:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        md_path = REPORT_DIR / f"daily_report_{since_int}-{until_int}.md"
        md_path.write_text(report, encoding="utf-8")
        print(f"  💾 已保存: {md_path}")

    # DRY-RUN 模式：打印预览
    if args.dry_run:
        print(f"\n{'='*50}")
        print("  预览日报内容:")
        print(f"{'='*50}")
        print(report[:2000])
        if len(report) > 2000:
            print(f"\n... (还有 {len(report) - 2000} 字符)")
        return

    # 推送到钉钉
    if not webhook:
        print("  ⚠️ 未配置钉钉 Webhook")
        print("  💡 请设置环境变量 DINGTALK_WEBHOOK 或使用 --webhook 参数")
        print("  💡 或在 .env 文件中配置")
        # 即使没有 webhook 也保存文件
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        md_path = REPORT_DIR / f"daily_report_{since_int}-{until_int}.md"
        md_path.write_text(report, encoding="utf-8")
        print(f"  💾 已保存 Markdown: {md_path}")
        return

    push_to_dingtalk(report, webhook, secret or None)


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
