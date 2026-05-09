# 2026/05/09/17:00
# name: eval_full_pipeline
# description: 评估完整流水线产出（Object-Models-Updated.xlsx）对比金标覆盖率

import re
from pathlib import Path
import pandas as pd

EVAL_DIR = Path(__file__).parent
ROOT = EVAL_DIR.parent
GOLD_PATH = EVAL_DIR / "gold_standard.xlsx"
PIPELINE_PATH = ROOT / "data" / "Object-Models-Updated.xlsx"
REPORT_PATH = EVAL_DIR / "eval_full_pipeline_report.md"


def normalize_name(name: str) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[\s\-_\.]", "", s)
    return s


def fuzzy_match(target_norm: str, candidates: set[str]) -> str | None:
    for candidate in candidates:
        if len(target_norm) > 3 and len(candidate) > 3:
            if target_norm in candidate or candidate in target_norm:
                return candidate
    return None


def main():
    gold_df = pd.read_excel(GOLD_PATH)
    pipeline_df = pd.read_excel(PIPELINE_PATH)

    gold_names_raw = gold_df["模型名称"].dropna().astype(str).str.strip().tolist()
    gold_names_norm = {normalize_name(n): n for n in gold_names_raw}

    pipeline_names_raw = pipeline_df["模型名称"].dropna().astype(str).str.strip().tolist()
    pipeline_names_norm = {normalize_name(n): n for n in pipeline_names_raw}

    total_gold = len(gold_names_norm)
    total_pipeline = len(pipeline_names_norm)

    print(f"金标模型: {total_gold}")
    print(f"流水线产出: {total_pipeline}")

    # 精确匹配
    exact_matches = set(gold_names_norm.keys()) & set(pipeline_names_norm.keys())

    # 模糊匹配
    fuzzy_matches = set()
    fuzzy_mapping = {}
    for gold_norm, gold_raw in gold_names_norm.items():
        if gold_norm in exact_matches:
            fuzzy_matches.add(gold_norm)
            fuzzy_mapping[gold_raw] = pipeline_names_norm.get(gold_norm, gold_raw)
        else:
            matched = fuzzy_match(gold_norm, set(pipeline_names_norm.keys()))
            if matched:
                fuzzy_matches.add(gold_norm)
                fuzzy_mapping[gold_raw] = pipeline_names_norm[matched]

    not_covered = set(gold_names_norm.keys()) - fuzzy_matches

    print(f"\n{'='*60}")
    print(f"覆盖率评估（金标 {total_gold} 个模型）")
    print(f"{'='*60}")
    print(f"  精确匹配: {len(exact_matches)}/{total_gold} = {len(exact_matches)/total_gold*100:.1f}%")
    print(f"  模糊匹配: {len(fuzzy_matches)}/{total_gold} = {len(fuzzy_matches)/total_gold*100:.1f}%")
    print(f"  未覆盖:   {len(not_covered)}/{total_gold}")

    # 列出匹配详情
    print(f"\n匹配成功的模型 ({len(fuzzy_matches)}):")
    for gold_raw, pipe_raw in sorted(fuzzy_mapping.items()):
        match_type = "精确" if normalize_name(gold_raw) in exact_matches else "模糊"
        print(f"  [{match_type}] {gold_raw}  ←→  {pipe_raw}")

    print(f"\n未覆盖的金标模型 ({len(not_covered)}):")
    for norm in sorted(not_covered):
        raw = gold_names_norm[norm]
        row = gold_df[gold_df["模型名称"].astype(str).str.strip() == raw].iloc[0]
        company = row.get("公司", "?") if "公司" in row.index else "?"
        model_type = row.get("类型", "?") if "类型" in row.index else "?"
        print(f"  {raw} ({company}, {model_type})")

    # 生成报告
    report_lines = [
        "# 完整流水线评估报告",
        "",
        f"> 生成时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 流水线产出：Object-Models-Updated.xlsx ({total_pipeline} 条)",
        f"> 金标：gold_standard.xlsx ({total_gold} 条)",
        "",
        "## 覆盖率",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 精确匹配 | {len(exact_matches)}/{total_gold} ({len(exact_matches)/total_gold*100:.1f}%) |",
        f"| 模糊匹配 | {len(fuzzy_matches)}/{total_gold} ({len(fuzzy_matches)/total_gold*100:.1f}%) |",
        f"| 未覆盖 | {len(not_covered)}/{total_gold} ({len(not_covered)/total_gold*100:.1f}%) |",
        "",
    ]

    if not_covered:
        report_lines.append(f"## 未覆盖的金标模型 ({len(not_covered)})")
        report_lines.append("")
        report_lines.append("| 模型 | 公司 | 类型 |")
        report_lines.append("|------|------|------|")
        for norm in sorted(not_covered):
            raw = gold_names_norm[norm]
            row = gold_df[gold_df["模型名称"].astype(str).str.strip() == raw].iloc[0]
            company = row.get("公司", "?") if "公司" in row.index else "?"
            model_type = row.get("类型", "?") if "类型" in row.index else "?"
            report_lines.append(f"| {raw} | {company} | {model_type} |")
        report_lines.append("")

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    main()
