"""
AI 模型/智能体追踪日报 —— 钉钉推送
====================================
从 Object-Models-Updated.xlsx 生成日报 Markdown 并推送到钉钉群。

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
EXCEL_PATH = DATA_DIR / "Object-Models-Updated.xlsx"

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
    hmac_code = hmac.new(
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


def load_models(excel_path: Path, since_int: int, until_int: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """从 Excel 加载数据，返回 (时间段内全部模型, 时间段内新增模型)。

    筛选逻辑：模型发布时间 或 记录创建时间（报道日期）任一落在时间窗口内即纳入。
    这样既覆盖"当天发布"的模型，也覆盖"当天被报道但实际更早发布"的模型。
    """
    df = pd.read_excel(excel_path, engine="openpyxl")

    all_in_range = []
    date_columns = ["模型发布时间", "记录创建时间"]
    for _, row in df.iterrows():
        matched = False
        for col in date_columns:
            if col in df.columns:
                date_int = _parse_date_int(row.get(col))
                if date_int is not None and since_int <= date_int <= until_int:
                    matched = True
                    break
        if matched:
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

        # 🟡 值得关注
        if mid_models:
            lines.append(f'<font color="#F59E0B">**🟡 值得关注 ({len(mid_models)})**</font>')
            lines.append("")
            for m in mid_models:
                line = f"- **{m['name']}**"
                if m["company"]:
                    line += f" ({m['company']})"
                lines.append(line)
                # 展示理由
                reason_text = m.get("reason", "")
                if not reason_text:
                    reason_text = _re.sub(r'\s*\[重要性[:：][高中低](?:\|[^]]*)?\]', '', m["note"]).strip()
                if reason_text:
                    reason_short = reason_text[:60] + "..." if len(reason_text) > 60 else reason_text
                    lines.append(f'  <font color="#999999" size="2">💡 {reason_short}</font>')
            lines.append("")

        # 🟢 其他新增
        if low_models:
            lines.append(f'<font color="#999999">**🟢 其他新增 ({len(low_models)})**</font>')
            lines.append("")
            for m in low_models:
                line = f"- {m['name']}"
                if m["company"]:
                    line += f" ({m['company']})"
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

    # 全部模型按公司分组展示
    df = df_all
    if "公司" in df.columns:
        company_groups = df.groupby("公司", sort=False)

        # 按模型数量排序
        sorted_groups = sorted(company_groups, key=lambda x: len(x[1]), reverse=True)

        for company, group in sorted_groups:
            company_str = str(company).strip()
            if not company_str or company_str == "nan":
                company_str = "未知"

            model_count = len(group)
            lines.append(f'<font color="#6366F1">**{company_str}**</font> ({model_count})')
            lines.append("")

            for _, row in group.iterrows():
                name = str(row.get("模型名称", "")).strip()
                model_type = str(row.get("类型", "")).strip()
                size = str(row.get("尺寸", "")).strip()
                open_closed = str(row.get("开闭源", "")).strip()
                note = str(row.get("备注", "")).strip()

                # 构造简洁的模型信息行
                info_parts = []
                if model_type and model_type != "nan":
                    info_parts.append(model_type)
                if size and size != "nan":
                    info_parts.append(size)
                if open_closed and open_closed != "nan":
                    info_parts.append(open_closed)

                info_str = " · ".join(info_parts)
                model_line = f"- **{name}**"
                if info_str:
                    model_line += f"  [{info_str}]"

                lines.append(model_line)

                # 备注（简化显示，去掉重要性标签）
                if note and note != "nan" and len(note) > 2:
                    import re as _re
                    note_clean = _re.sub(r'\s*\[重要性[:：][高中低]\]', '', note).strip()
                    if note_clean:
                        note_short = note_clean[:80] + "..." if len(note_clean) > 80 else note_clean
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

    print("📊 AI 模型追踪日报")
    print(f"  时间窗口: {since_int} ~ {until_int}")
    print(f"  Excel: {EXCEL_PATH}")
    if args.dry_run:
        print("  模式: 🔍 DRY-RUN")
    print()

    # 加载数据
    if not EXCEL_PATH.exists():
        print(f"  ❌ Excel 不存在: {EXCEL_PATH}")
        return

    df_all, df_new = load_models(EXCEL_PATH, since_int, until_int)
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
