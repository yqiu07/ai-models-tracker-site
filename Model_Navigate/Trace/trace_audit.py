# 2026/05/13/15:24
"""
name: trace_audit
description: 模型来源追溯与数据质量审计工具。
             支持按关键词/模型名追溯完整数据链路，
             支持按增量文件批量审计所有模型，
             支持数据质量评分和可疑项自动标记，
             辅助人工校验。

用法:
    # 按模型名追溯来源
    python trace_audit.py trace "pareto-code"
    python trace_audit.py trace "nemotron"

    # 审计指定增量文件
    python trace_audit.py audit 20260512_run1639.xlsx

    # 审计最近一个增量文件
    python trace_audit.py audit --latest

    # 审计所有增量文件并输出汇总报告
    python trace_audit.py audit --all

    # 总表数据质量概览
    python trace_audit.py quality

输出:
    Trace/reports/trace_{keyword}_{timestamp}.md     — 单模型追溯报告
    Trace/reports/audit_{filename}_{timestamp}.md    — 增量审计报告
    Trace/reports/quality_{timestamp}.md             — 总表质量报告

依赖:
    pip install pandas openpyxl
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows 终端编码修复：避免 emoji/中文输出 GBK 报错
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd

# ── 路径常量 ──
TRACE_DIR = Path(__file__).parent
ROOT = TRACE_DIR.parent
DATA_DIR = ROOT / "data"
TOTAL_XLSX = DATA_DIR / "Object-Models.xlsx"
UPDATED_XLSX = DATA_DIR / "Object-Models-Updated.xlsx"
INCREMENT_DIR = DATA_DIR / "increments"
CRAWL_DIR = ROOT / "Crawl" / "Arena_x"
ARTICLES_DIR = ROOT / "Extract" / "articles"
TX_RESULT = ROOT / "Extract" / "TXCrawl_result.xlsx"
REPORTS_DIR = TRACE_DIR / "reports"

# ── 关键字段 ──
KEY_FIELDS = ["官网", "备注", "模型发布时间"]
IDENTITY_FIELD = "模型名称"
CREATE_TIME_FIELD = "记录创建时间"
TRIGGER_TIME_FIELD = "触发时间"
IS_NEW_FIELD = "是否新增"

# ── 可疑项检测规则 ──
SUSPECT_PATTERNS = {
    "非LLM类模型": [
        r"classifier", r"fasttext", r"embedding", r"rerank",
        r"tts", r"asr", r"whisper", r"vocoder", r"wav2vec",
        r"detector", r"segmentat", r"yolo", r"sam\b",
    ],
    "疑似占卜/娱乐类": [
        r"占卜", r"算命", r"tarot", r"astro", r"horoscope",
        r"fortune", r"divination",
    ],
    "名称异常（含路由后缀）": [
        r":free$", r":extended$", r":nitro$", r":floor$",
    ],
    "名称异常（纯数字/过短）": [
        r"^[0-9.\-]+$",  # 纯数字
    ],
}


def timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def load_total() -> pd.DataFrame:
    """加载总表。"""
    if TOTAL_XLSX.exists():
        return pd.read_excel(TOTAL_XLSX, engine="openpyxl")
    return pd.DataFrame()


def load_increment(filename: str) -> pd.DataFrame | None:
    """加载指定增量文件。"""
    path = INCREMENT_DIR / filename
    if not path.exists():
        print(f"❌ 增量文件不存在: {path}")
        return None
    return pd.read_excel(path, engine="openpyxl")


def get_latest_increment() -> Path | None:
    """获取最新增量文件路径。"""
    xlsx_files = sorted(
        [f for f in INCREMENT_DIR.glob("*.xlsx") if not f.stem.endswith("_empty")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return xlsx_files[0] if xlsx_files else None


def detect_suspects(model_name: str, remarks: str = "") -> list[str]:
    """检测模型可疑项，返回可疑原因列表。"""
    flags = []
    combined = f"{model_name} {remarks}".lower()

    for category, patterns in SUSPECT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                flags.append(category)
                break

    # 模型名过短（<=3字符）
    if len(model_name.strip()) <= 3:
        flags.append("名称异常（过短）")

    return flags


def field_completeness(row: pd.Series) -> dict:
    """评估一行关键字段的填充情况。"""
    result = {}
    for field in KEY_FIELDS:
        value = row.get(field)
        filled = pd.notna(value) and str(value).strip() not in ("", "nan", "N/A", "未知")
        result[field] = filled
    return result


def find_in_increments(keyword: str) -> list[dict]:
    """在所有增量文件中搜索包含关键词的模型。"""
    results = []
    if not INCREMENT_DIR.exists():
        return results

    for xlsx_file in sorted(INCREMENT_DIR.glob("*.xlsx")):
        if xlsx_file.stem.endswith("_empty"):
            continue
        try:
            df = pd.read_excel(xlsx_file, engine="openpyxl")
        except Exception:
            continue

        mask = df.apply(
            lambda row: row.astype(str).str.contains(keyword, case=False).any(),
            axis=1,
        )
        matches = df[mask]
        for _, row in matches.iterrows():
            results.append({
                "increment_file": xlsx_file.name,
                "increment_path": str(xlsx_file),
                "row": row.to_dict(),
            })
    return results


def find_in_total(keyword: str) -> list[dict]:
    """在总表中搜索包含关键词的模型。"""
    df = load_total()
    if df.empty:
        return []

    mask = df.apply(
        lambda row: row.astype(str).str.contains(keyword, case=False).any(),
        axis=1,
    )
    matches = df[mask]
    results = []
    for idx, row in matches.iterrows():
        results.append({"row_index": idx, "row": row.to_dict()})
    return results


def infer_source(increment_filename: str, trigger_time: str = "") -> str:
    """推断增量文件的采集来源。"""
    # 从文件名推断：run{HHMM} 格式表示 auto_collect.py 定时任务
    if re.match(r"\d{8}_run\d{4}", increment_filename.replace(".xlsx", "")):
        return "auto_collect.py（定时采集）"

    # 从文件名推断其他模式
    if "txresearch" in increment_filename.lower() or "tx" in increment_filename.lower():
        return "腾讯研究院文章提取"

    if "llmstats" in increment_filename.lower():
        return "llm-stats.com 爬取"

    return "auto_collect.py（含 llm-stats + 腾讯研究院）"


def infer_data_source_detail(row: dict) -> str:
    """根据模型行数据推断更具体的数据来源。"""
    official_url = str(row.get("官网", ""))
    remarks = str(row.get("备注", ""))

    # 通过官网 URL 推断
    if "openrouter.ai" in official_url:
        return "llm-stats.com → OpenRouter 聚合平台"
    if "huggingface.co" in official_url:
        return "llm-stats.com → HuggingFace 开源社区"
    if "build.nvidia.com" in official_url or "developer.nvidia.com" in official_url:
        return "llm-stats.com → NVIDIA 官方"
    if "github.com" in official_url:
        return "llm-stats.com → GitHub 开源"

    # 通过备注推断
    if "HuggingFace" in remarks:
        return "llm-stats.com → HuggingFace"

    # 通过公司推断
    company = str(row.get("公司", ""))
    if company and company not in ("nan", "未知", "N/A"):
        return f"llm-stats.com → {company}"

    return "llm-stats.com（具体子来源不明）"


# ================================================================
#  命令 1: trace — 按关键词追溯模型来源
# ================================================================

def cmd_trace(keyword: str) -> str:
    """追溯指定关键词对应模型的完整数据链路。"""
    print(f"\n🔍 追溯模型来源: [{keyword}]")
    print("=" * 60)

    # 在总表中查找
    total_results = find_in_total(keyword)
    # 在增量中查找
    increment_results = find_in_increments(keyword)

    if not total_results and not increment_results:
        msg = f"❌ 未找到与 [{keyword}] 匹配的任何模型"
        print(msg)
        return msg

    # 构建报告
    lines = [
        f"# Trace 审计报告: {keyword}",
        f"",
        f"- **查询时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **关键词**: `{keyword}`",
        f"- **总表命中**: {len(total_results)} 条",
        f"- **增量命中**: {len(increment_results)} 条",
        f"",
        f"---",
        f"",
    ]

    # 总表结果
    if total_results:
        lines.append("## 总表中的记录\n")
        for item in total_results:
            row = item["row"]
            model_name = str(row.get(IDENTITY_FIELD, "N/A"))
            completeness = field_completeness(pd.Series(row))
            suspects = detect_suspects(model_name, str(row.get("备注", "")))

            lines.append(f"### `{model_name}` (行 {item['row_index']})\n")
            lines.append(f"| 字段 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 模型名称 | {model_name} |")
            lines.append(f"| 公司 | {row.get('公司', 'N/A')} |")
            lines.append(f"| 国内外 | {row.get('国内外', 'N/A')} |")
            lines.append(f"| 开闭源 | {row.get('开闭源', 'N/A')} |")
            lines.append(f"| 类型 | {row.get('类型', 'N/A')} |")
            lines.append(f"| 记录创建时间 | {row.get(CREATE_TIME_FIELD, 'N/A')} |")
            lines.append(f"| 触发时间 | {row.get(TRIGGER_TIME_FIELD, 'N/A')} |")
            lines.append(f"| 是否新增 | {row.get(IS_NEW_FIELD, 'N/A')} |")
            lines.append(f"")

            # 关键字段填充状态
            lines.append(f"**关键字段填充状态**:\n")
            for field, filled in completeness.items():
                icon = "✅" if filled else "❌"
                value = str(row.get(field, ""))[:80]
                lines.append(f"- {icon} **{field}**: {value if filled else '(空)'}")
            lines.append("")

            # 可疑项
            if suspects:
                lines.append(f"⚠️ **可疑项**: {', '.join(suspects)}\n")

            lines.append("")

    # 增量文件来源追溯
    if increment_results:
        lines.append("## 增量文件来源追溯\n")
        for item in increment_results:
            row = item["row"]
            model_name = str(row.get(IDENTITY_FIELD, "N/A"))
            inc_file = item["increment_file"]
            trigger = str(row.get(TRIGGER_TIME_FIELD, "N/A"))
            source = infer_source(inc_file, trigger)
            detail_source = infer_data_source_detail(row)

            lines.append(f"### `{model_name}` ← `{inc_file}`\n")
            lines.append(f"| 维度 | 信息 |")
            lines.append(f"|------|------|")
            lines.append(f"| 增量文件 | `{inc_file}` |")
            lines.append(f"| 采集脚本 | {source} |")
            lines.append(f"| 具体数据源 | {detail_source} |")
            lines.append(f"| 触发时间 | {trigger} |")
            lines.append(f"| 记录创建时间 | {row.get(CREATE_TIME_FIELD, 'N/A')} |")
            lines.append(f"")

            # 数据链路图
            lines.append(f"**数据链路**:")
            lines.append(f"```")
            lines.append(f"[{detail_source}]")
            lines.append(f"  → auto_collect.py (HTTP抓取 + LLM结构化提取)")
            lines.append(f"  → {inc_file} (增量文件)")
            lines.append(f"  → review_models.py (GPT-5.5 审核补全)")
            lines.append(f"  → verify_models.py (DashScope联网校验)")
            lines.append(f"  → Object-Models.xlsx (总表)")
            lines.append(f"```")
            lines.append(f"")

    # 写入报告
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_keyword = re.sub(r"[^\w\-]", "_", keyword)
    report_path = REPORTS_DIR / f"trace_{safe_keyword}_{timestamp_str()}.md"
    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\n📄 报告已保存: {report_path}")

    # 终端摘要
    print(f"\n{'─' * 60}")
    for item in total_results:
        row = item["row"]
        name = str(row.get(IDENTITY_FIELD, "?"))
        suspects = detect_suspects(name, str(row.get("备注", "")))
        flag = f" ⚠️ {suspects}" if suspects else ""
        print(f"  📌 {name}{flag}")
    print(f"{'─' * 60}")

    return report_content


# ================================================================
#  命令 2: audit — 增量文件批量审计
# ================================================================

def cmd_audit(filename: str = None, latest: bool = False, all_files: bool = False) -> str:
    """审计增量文件中的所有模型。"""
    targets: list[Path] = []

    if all_files:
        targets = sorted(
            [f for f in INCREMENT_DIR.glob("*.xlsx") if not f.stem.endswith("_empty")],
            key=lambda f: f.name,
        )
    elif latest:
        path = get_latest_increment()
        if path:
            targets = [path]
        else:
            print("❌ 无增量文件")
            return ""
    elif filename:
        path = INCREMENT_DIR / filename
        if not path.exists():
            print(f"❌ 文件不存在: {path}")
            return ""
        targets = [path]

    if not targets:
        print("❌ 未指定审计目标")
        return ""

    all_lines = [
        f"# 增量文件审计报告",
        f"",
        f"- **审计时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **审计范围**: {len(targets)} 个增量文件",
        f"",
    ]

    total_models = 0
    total_suspects = 0
    total_incomplete = 0

    for target_path in targets:
        try:
            df = pd.read_excel(target_path, engine="openpyxl")
        except Exception as exc:
            all_lines.append(f"## ❌ {target_path.name} — 读取失败: {exc}\n")
            continue

        source = infer_source(target_path.stem)
        all_lines.append(f"## 📁 `{target_path.name}`\n")
        all_lines.append(f"- **模型数**: {len(df)}")
        all_lines.append(f"- **采集来源**: {source}")
        all_lines.append(f"")

        # 字段填充率统计
        field_stats = {}
        for field in KEY_FIELDS:
            if field in df.columns:
                filled = df[field].apply(
                    lambda v: pd.notna(v) and str(v).strip() not in ("", "nan", "N/A")
                ).sum()
                field_stats[field] = (filled, len(df))

        all_lines.append(f"### 字段填充率\n")
        all_lines.append(f"| 字段 | 已填 | 总数 | 填充率 |")
        all_lines.append(f"|------|------|------|--------|")
        for field, (filled, total) in field_stats.items():
            rate = filled / total * 100 if total > 0 else 0
            icon = "🟢" if rate >= 80 else ("🟡" if rate >= 50 else "🔴")
            all_lines.append(f"| {field} | {filled} | {total} | {icon} {rate:.0f}% |")
        all_lines.append("")

        # 逐模型审计
        suspect_models = []
        incomplete_models = []

        for idx, row in df.iterrows():
            model_name = str(row.get(IDENTITY_FIELD, ""))
            if not model_name or model_name == "nan":
                continue

            total_models += 1
            suspects = detect_suspects(model_name, str(row.get("备注", "")))
            completeness = field_completeness(row)
            missing_fields = [f for f, filled in completeness.items() if not filled]

            if suspects:
                total_suspects += 1
                suspect_models.append((model_name, suspects))

            if missing_fields:
                total_incomplete += 1
                incomplete_models.append((model_name, missing_fields))

        # 可疑模型清单
        if suspect_models:
            all_lines.append(f"### ⚠️ 可疑模型 ({len(suspect_models)} 个)\n")
            all_lines.append(f"| 模型名 | 可疑原因 | 建议 |")
            all_lines.append(f"|--------|----------|------|")
            for name, flags in suspect_models:
                suggestion = "人工确认是否应纳入" if "非LLM" in str(flags) else "检查数据准确性"
                all_lines.append(f"| `{name}` | {', '.join(flags)} | {suggestion} |")
            all_lines.append("")

        # 字段缺失清单
        if incomplete_models:
            all_lines.append(f"### 🔴 字段缺失 ({len(incomplete_models)} 个)\n")
            # 只显示前 20 个
            display_list = incomplete_models[:20]
            all_lines.append(f"| 模型名 | 缺失字段 |")
            all_lines.append(f"|--------|----------|")
            for name, missing in display_list:
                all_lines.append(f"| `{name}` | {', '.join(missing)} |")
            if len(incomplete_models) > 20:
                all_lines.append(f"| ... | 还有 {len(incomplete_models) - 20} 个 |")
            all_lines.append("")

        all_lines.append("---\n")

    # 汇总
    all_lines.insert(4, f"- **总模型数**: {total_models}")
    all_lines.insert(5, f"- **可疑模型**: {total_suspects} ({total_suspects/max(total_models,1)*100:.1f}%)")
    all_lines.insert(6, f"- **字段缺失**: {total_incomplete} ({total_incomplete/max(total_models,1)*100:.1f}%)")
    all_lines.insert(7, "")

    # 写入报告
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if len(targets) == 1:
        report_name = f"audit_{targets[0].stem}_{timestamp_str()}.md"
    else:
        report_name = f"audit_all_{timestamp_str()}.md"
    report_path = REPORTS_DIR / report_name
    report_content = "\n".join(all_lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\n📄 报告已保存: {report_path}")

    # 终端摘要
    print(f"\n{'─' * 60}")
    print(f"  📊 总模型: {total_models} | ⚠️ 可疑: {total_suspects} | 🔴 缺失: {total_incomplete}")
    if suspect_models:
        print(f"\n  ⚠️ 可疑模型:")
        for name, flags in suspect_models[:10]:
            print(f"     • {name} — {', '.join(flags)}")
    print(f"{'─' * 60}")

    return report_content


# ================================================================
#  命令 3: quality — 总表数据质量概览
# ================================================================

def cmd_quality() -> str:
    """总表整体数据质量评估。"""
    print(f"\n📊 总表数据质量评估")
    print("=" * 60)

    df = load_total()
    if df.empty:
        msg = "❌ 总表为空或不存在"
        print(msg)
        return msg

    total_rows = len(df)
    lines = [
        f"# 总表数据质量报告",
        f"",
        f"- **评估时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **总表路径**: `{TOTAL_XLSX}`",
        f"- **总行数**: {total_rows}",
        f"",
        f"---",
        f"",
    ]

    # 1. 全字段填充率
    lines.append("## 字段填充率\n")
    lines.append(f"| 字段 | 已填 | 填充率 | 评级 |")
    lines.append(f"|------|------|--------|------|")

    all_columns = df.columns.tolist()
    for col in all_columns:
        filled = df[col].apply(
            lambda v: pd.notna(v) and str(v).strip() not in ("", "nan")
        ).sum()
        rate = filled / total_rows * 100
        if rate >= 90:
            grade = "🟢 优"
        elif rate >= 70:
            grade = "🟡 良"
        elif rate >= 50:
            grade = "🟠 中"
        else:
            grade = "🔴 差"
        lines.append(f"| {col} | {filled}/{total_rows} | {rate:.1f}% | {grade} |")
    lines.append("")

    # 2. 综合质量评分
    key_rates = []
    for field in KEY_FIELDS:
        if field in df.columns:
            filled = df[field].apply(
                lambda v: pd.notna(v) and str(v).strip() not in ("", "nan", "N/A")
            ).sum()
            key_rates.append(filled / total_rows)
    overall_score = sum(key_rates) / len(key_rates) * 100 if key_rates else 0

    lines.append(f"## 综合质量评分\n")
    lines.append(f"- **关键字段平均填充率**: {overall_score:.1f}%")
    if overall_score >= 80:
        lines.append(f"- **评级**: 🟢 **优秀** — 数据质量良好")
    elif overall_score >= 60:
        lines.append(f"- **评级**: 🟡 **良好** — 建议补全缺失字段")
    elif overall_score >= 40:
        lines.append(f"- **评级**: 🟠 **一般** — 存在较多缺失，需重点补全")
    else:
        lines.append(f"- **评级**: 🔴 **较差** — 大量关键字段缺失")
    lines.append("")

    # 3. 可疑模型扫描
    suspect_count = 0
    suspect_list = []
    for _, row in df.iterrows():
        model_name = str(row.get(IDENTITY_FIELD, ""))
        suspects = detect_suspects(model_name, str(row.get("备注", "")))
        if suspects:
            suspect_count += 1
            suspect_list.append((model_name, suspects))

    lines.append(f"## 可疑模型扫描\n")
    lines.append(f"- **可疑模型总数**: {suspect_count}/{total_rows} ({suspect_count/total_rows*100:.1f}%)")
    lines.append("")
    if suspect_list:
        lines.append(f"| 模型名 | 可疑原因 |")
        lines.append(f"|--------|----------|")
        for name, flags in suspect_list[:30]:
            lines.append(f"| `{name}` | {', '.join(flags)} |")
        if len(suspect_list) > 30:
            lines.append(f"| ... | 还有 {len(suspect_list) - 30} 个 |")
    lines.append("")

    # 4. 来源分布（基于增量文件）
    lines.append(f"## 数据来源分布\n")
    if INCREMENT_DIR.exists():
        inc_files = sorted(
            [f for f in INCREMENT_DIR.glob("*.xlsx") if not f.stem.endswith("_empty")]
        )
        lines.append(f"| 增量文件 | 模型数 | 采集来源 |")
        lines.append(f"|----------|--------|----------|")
        for inc_file in inc_files:
            try:
                df_inc = pd.read_excel(inc_file, engine="openpyxl")
                source = infer_source(inc_file.stem)
                lines.append(f"| `{inc_file.name}` | {len(df_inc)} | {source} |")
            except Exception:
                lines.append(f"| `{inc_file.name}` | ? | 读取失败 |")
    lines.append("")

    # 写入报告
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"quality_{timestamp_str()}.md"
    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\n📄 报告已保存: {report_path}")

    # 终端摘要
    print(f"\n{'─' * 60}")
    print(f"  📊 总行数: {total_rows}")
    print(f"  🎯 关键字段填充率: {overall_score:.1f}%")
    print(f"  ⚠️  可疑模型: {suspect_count}")
    print(f"{'─' * 60}")

    return report_content


# ================================================================
#  CLI 入口
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="模型来源追溯与数据质量审计工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python trace_audit.py trace "pareto-code"     追溯指定模型来源
  python trace_audit.py audit --latest          审计最新增量文件
  python trace_audit.py audit --all             审计所有增量文件
  python trace_audit.py quality                 总表质量概览
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # trace 子命令
    trace_parser = subparsers.add_parser("trace", help="按关键词追溯模型来源")
    trace_parser.add_argument("keyword", help="模型名称或关键词")

    # audit 子命令
    audit_parser = subparsers.add_parser("audit", help="增量文件批量审计")
    audit_group = audit_parser.add_mutually_exclusive_group(required=True)
    audit_group.add_argument("filename", nargs="?", help="增量文件名")
    audit_group.add_argument("--latest", action="store_true", help="审计最新增量文件")
    audit_group.add_argument("--all", action="store_true", help="审计所有增量文件")

    # quality 子命令
    subparsers.add_parser("quality", help="总表数据质量概览")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "trace":
        cmd_trace(args.keyword)
    elif args.command == "audit":
        if args.all:
            cmd_audit(all_files=True)
        elif args.latest:
            cmd_audit(latest=True)
        else:
            cmd_audit(filename=args.filename)
    elif args.command == "quality":
        cmd_quality()


if __name__ == "__main__":
    main()
