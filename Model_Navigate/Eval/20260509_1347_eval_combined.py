# -*- coding: utf-8 -*-
"""
2026/05/09/13:47
name: eval_combined
description: 合并 llmstats + 腾讯研究院 LLM 提取结果，与金标对比评估覆盖率。
             对比单源 vs 双源的覆盖率提升。

用法:
    python eval_combined.py
输入:
    Eval/gold_standard.xlsx              — 金标（116条）
    Eval/pipeline_llmstats.xlsx          — llmstats 流水线产出
    Extract/extracted_models_llm.json    — 腾讯研究院 LLM 提取结果
输出:
    Eval/eval_combined_report.md         — 合并评估报告
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

EVAL_DIR = Path(__file__).parent
ROOT = EVAL_DIR.parent
GOLD_PATH = EVAL_DIR / "gold_standard.xlsx"
LLMSTATS_PATH = EVAL_DIR / "pipeline_llmstats.xlsx"
TX_EXTRACT_PATH = ROOT / "Extract" / "extracted_models_llm.json"
REPORT_PATH = EVAL_DIR / "eval_combined_report.md"


def normalize_name(name: str) -> str:
    """标准化模型名称用于匹配。"""
    s = str(name).strip().lower()
    s = re.sub(r"[\s\-_\.]", "", s)
    return s


def fuzzy_match(target_norm: str, candidates: set[str]) -> str | None:
    """子串匹配：target 包含 candidate 或反过来。"""
    for candidate in candidates:
        if len(target_norm) > 3 and len(candidate) > 3:
            if target_norm in candidate or candidate in target_norm:
                return candidate
    return None


def main():
    # 加载金标
    gold_df = pd.read_excel(GOLD_PATH)
    gold_names_raw = gold_df["模型名称"].dropna().astype(str).str.strip().tolist()
    gold_names_norm = {normalize_name(n): n for n in gold_names_raw}
    print(f"金标模型: {len(gold_names_norm)}")

    # 加载 llmstats 流水线产出
    llmstats_df = pd.read_excel(LLMSTATS_PATH)
    llmstats_names_raw = llmstats_df["模型名称"].dropna().astype(str).str.strip().tolist()
    llmstats_names_norm = {normalize_name(n): n for n in llmstats_names_raw}
    print(f"llmstats 模型: {len(llmstats_names_norm)}")

    # 加载腾讯研究院 LLM 提取结果
    with open(TX_EXTRACT_PATH, "r", encoding="utf-8") as f:
        tx_models = json.load(f)
    tx_names_raw = [m.get("model_name", "") for m in tx_models if m.get("model_name")]
    tx_names_norm = {normalize_name(n): n for n in tx_names_raw}
    # 去重
    tx_unique = set(tx_names_norm.keys())
    print(f"腾讯研究院 LLM 提取: {len(tx_unique)} 个唯一模型")

    # 合并两个数据源
    combined_norm = set(llmstats_names_norm.keys()) | tx_unique
    print(f"合并后唯一模型: {len(combined_norm)}")

    # === 覆盖率评估 ===
    # 精确匹配
    llmstats_exact = set(gold_names_norm.keys()) & set(llmstats_names_norm.keys())
    tx_exact = set(gold_names_norm.keys()) & tx_unique
    combined_exact = set(gold_names_norm.keys()) & combined_norm

    # 模糊匹配（子串）
    llmstats_fuzzy = set()
    tx_fuzzy = set()
    combined_fuzzy = set()

    for gold_norm in gold_names_norm:
        if gold_norm in llmstats_exact:
            llmstats_fuzzy.add(gold_norm)
        elif fuzzy_match(gold_norm, set(llmstats_names_norm.keys())):
            llmstats_fuzzy.add(gold_norm)

        if gold_norm in tx_exact:
            tx_fuzzy.add(gold_norm)
        elif fuzzy_match(gold_norm, tx_unique):
            tx_fuzzy.add(gold_norm)

        if gold_norm in combined_exact:
            combined_fuzzy.add(gold_norm)
        elif fuzzy_match(gold_norm, combined_norm):
            combined_fuzzy.add(gold_norm)

    total_gold = len(gold_names_norm)

    print(f"\n{'='*60}")
    print(f"覆盖率评估（金标 {total_gold} 个模型）")
    print(f"{'='*60}")
    print(f"  llmstats 精确: {len(llmstats_exact)}/{total_gold} = {len(llmstats_exact)/total_gold*100:.1f}%")
    print(f"  llmstats 模糊: {len(llmstats_fuzzy)}/{total_gold} = {len(llmstats_fuzzy)/total_gold*100:.1f}%")
    print(f"  腾讯研究院 精确: {len(tx_exact)}/{total_gold} = {len(tx_exact)/total_gold*100:.1f}%")
    print(f"  腾讯研究院 模糊: {len(tx_fuzzy)}/{total_gold} = {len(tx_fuzzy)/total_gold*100:.1f}%")
    print(f"  合并后 精确: {len(combined_exact)}/{total_gold} = {len(combined_exact)/total_gold*100:.1f}%")
    print(f"  合并后 模糊: {len(combined_fuzzy)}/{total_gold} = {len(combined_fuzzy)/total_gold*100:.1f}%")

    # 仅腾讯研究院覆盖的（llmstats 覆盖不到的）
    tx_only = tx_fuzzy - llmstats_fuzzy
    llmstats_only = llmstats_fuzzy - tx_fuzzy
    both = llmstats_fuzzy & tx_fuzzy
    neither = set(gold_names_norm.keys()) - combined_fuzzy

    print(f"\n  仅 llmstats 覆盖: {len(llmstats_only)}")
    print(f"  仅腾讯研究院覆盖: {len(tx_only)}")
    print(f"  两者都覆盖: {len(both)}")
    print(f"  两者都未覆盖: {len(neither)}")

    # 列出仅腾讯研究院覆盖的
    if tx_only:
        print(f"\n  仅腾讯研究院覆盖的金标模型:")
        for norm in sorted(tx_only):
            print(f"    {gold_names_norm[norm]}")

    # 列出两者都未覆盖的
    if neither:
        print(f"\n  两者都未覆盖的金标模型 ({len(neither)}):")
        for norm in sorted(neither):
            print(f"    {gold_names_norm[norm]}")

    # === 生成报告 ===
    report_lines = [
        f"# 合并评估报告",
        f"",
        f"> 生成时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## 数据源概况",
        f"",
        f"| 数据源 | 模型数 |",
        f"|--------|--------|",
        f"| 金标 | {total_gold} |",
        f"| llmstats 流水线 | {len(llmstats_names_norm)} |",
        f"| 腾讯研究院 LLM 提取 | {len(tx_unique)} |",
        f"| 合并去重 | {len(combined_norm)} |",
        f"",
        f"## 覆盖率对比",
        f"",
        f"| 数据源 | 精确匹配 | 模糊匹配 |",
        f"|--------|----------|----------|",
        f"| llmstats 单源 | {len(llmstats_exact)}/{total_gold} ({len(llmstats_exact)/total_gold*100:.1f}%) | {len(llmstats_fuzzy)}/{total_gold} ({len(llmstats_fuzzy)/total_gold*100:.1f}%) |",
        f"| 腾讯研究院单源 | {len(tx_exact)}/{total_gold} ({len(tx_exact)/total_gold*100:.1f}%) | {len(tx_fuzzy)}/{total_gold} ({len(tx_fuzzy)/total_gold*100:.1f}%) |",
        f"| **合并双源** | **{len(combined_exact)}/{total_gold} ({len(combined_exact)/total_gold*100:.1f}%)** | **{len(combined_fuzzy)}/{total_gold} ({len(combined_fuzzy)/total_gold*100:.1f}%)** |",
        f"",
        f"## 交叉覆盖分析",
        f"",
        f"| 覆盖情况 | 数量 |",
        f"|----------|------|",
        f"| 仅 llmstats | {len(llmstats_only)} |",
        f"| 仅腾讯研究院 | {len(tx_only)} |",
        f"| 两者都覆盖 | {len(both)} |",
        f"| 两者都未覆盖 | {len(neither)} |",
        f"",
    ]

    if tx_only:
        report_lines.append("## 仅腾讯研究院覆盖的金标模型")
        report_lines.append("")
        for norm in sorted(tx_only):
            report_lines.append(f"- {gold_names_norm[norm]}")
        report_lines.append("")

    if neither:
        report_lines.append(f"## 两者都未覆盖的金标模型 ({len(neither)})")
        report_lines.append("")
        for norm in sorted(neither):
            report_lines.append(f"- {gold_names_norm[norm]}")
        report_lines.append("")

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    main()
