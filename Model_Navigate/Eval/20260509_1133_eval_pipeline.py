# -*- coding: utf-8 -*-
"""
2026/05/09/11:33
name: eval_pipeline
description: 金标 vs 流水线产出 逐字段评估脚本。
             计算覆盖率(recall)、准确率(precision)、补全能力、纠错能力。
             输出 Markdown 评估报告。

用法:
    python eval_pipeline.py
输入:
    Eval/gold_standard.xlsx        — 金标文件（116条）
    Eval/pipeline_llmstats.xlsx    — 流水线产出（llmstats 采集）
输出:
    Eval/eval_report.md            — 评估报告
"""
import sys
import re
from pathlib import Path
from datetime import datetime

import pandas as pd

EVAL_DIR = Path(__file__).parent
GOLD_PATH = EVAL_DIR / "gold_standard.xlsx"
PIPE_PATH = EVAL_DIR / "pipeline_llmstats.xlsx"
REPORT_PATH = EVAL_DIR / "eval_report.md"

# 评估字段（排除业务字段：是否接入、workflow接入进展、是否新增、核实情况）
EVAL_FIELDS = [
    "公司", "国内外", "开闭源", "尺寸", "类型",
    "能否推理", "官网", "备注", "模型发布时间",
]

# ── 名称标准化 ──
def normalize_name(name):
    """标准化模型名称用于匹配。"""
    s = str(name).strip().lower()
    s = re.sub(r"[\s\-_\.]", "", s)
    return s


def build_name_index(df):
    """构建 normalized_name -> (original_name, row_index) 的索引。"""
    index = {}
    for idx, row in df.iterrows():
        raw = row["模型名称"]
        if pd.isna(raw):
            continue
        norm = normalize_name(raw)
        index[norm] = (str(raw).strip(), idx)
    return index


def fuzzy_match(gold_norm, pipe_norms):
    """尝试子串匹配。返回匹配到的 pipe_norm 或 None。"""
    for pn in pipe_norms:
        if gold_norm in pn or pn in gold_norm:
            return pn
    return None


# 中英文公司名双向映射
COMPANY_ALIASES = {
    "阿里": ["alibaba", "qwen", "alibaba cloud", "qwen team", "alibaba cloud / qwen team"],
    "百度": ["baidu"],
    "字节": ["bytedance", "byte dance"],
    "腾讯": ["tencent"],
    "智谱": ["zhipu", "zhipu ai", "thudm"],
    "月之暗面": ["moonshot", "moonshot ai", "kimi"],
    "minimax": ["minimax"],
    "深度求索": ["deepseek", "deepseek ai"],
    "科大讯飞": ["iflytek"],
    "小米": ["xiaomi"],
    "美团": ["meituan"],
    "商汤": ["sensetime"],
    "openai": ["openai"],
    "google": ["google", "google deepmind", "deepmind"],
    "anthropic": ["anthropic"],
    "meta": ["meta", "meta ai", "meta llama"],
    "xai": ["xai", "x.ai"],
    "nvidia": ["nvidia"],
    "mistral": ["mistral", "mistral ai"],
    "inception": ["inception", "inception ai"],
    "stepfun": ["stepfun", "阶跃星辰"],
}

def _normalize_company(name):
    """将公司名标准化到统一 key。"""
    s = str(name).strip().lower()
    s = re.sub(r"[\s\-_]", "", s)
    for canonical, aliases in COMPANY_ALIASES.items():
        canonical_norm = re.sub(r"[\s\-_]", "", canonical.lower())
        if s == canonical_norm:
            return canonical.lower()
        for alias in aliases:
            alias_norm = re.sub(r"[\s\-_]", "", alias.lower())
            if s == alias_norm or alias_norm in s or s in alias_norm:
                return canonical.lower()
    return s


def field_equal(gold_val, pipe_val, field_name):
    """判断两个字段值是否"等价"。"""
    if pd.isna(gold_val) or pd.isna(pipe_val):
        return None  # 无法比较
    g = str(gold_val).strip().lower()
    p = str(pipe_val).strip().lower()
    if not g or not p:
        return None

    # 国内外：直接比较
    if field_name == "国内外":
        return g == p

    # 开闭源：同义映射
    if field_name == "开闭源":
        open_synonyms = {"开源", "open", "open source", "open-source"}
        closed_synonyms = {"闭源", "closed", "proprietary", "closed source"}
        g_is_open = g in open_synonyms
        p_is_open = p in open_synonyms
        g_is_closed = g in closed_synonyms
        p_is_closed = p in closed_synonyms
        if g_is_open and p_is_open:
            return True
        if g_is_closed and p_is_closed:
            return True
        if (g_is_open or g_is_closed) and (p_is_open or p_is_closed):
            return g_is_open == p_is_open
        return g == p

    # 类型：同义映射 + "基座"与"多模态"兼容处理
    if field_name == "类型":
        type_map = {
            "基座": {"基座", "foundation"},
            "多模态": {"多模态", "multimodal"},
            "代码": {"代码", "code"},
            "语音": {"语音", "speech", "audio", "tts", "stt"},
            "图像": {"图像", "image"},
            "视频": {"视频", "video"},
            "微调": {"微调", "finetune", "fine-tune"},
            "智能体": {"智能体", "agent"},
            "领域": {"领域", "domain"},
            "未知": {"未知", "unknown"},
        }
        g_type = None
        p_type = None
        for canonical, synonyms in type_map.items():
            if g in synonyms:
                g_type = canonical
            if p in synonyms:
                p_type = canonical
        if g_type and p_type and g_type == p_type:
            return True
        # 基座模型同时支持多模态时，"基座"和"多模态"都算正确
        if {g_type, p_type} == {"基座", "多模态"}:
            return True
        # 代码是领域的一种，也兼容
        if {g_type, p_type} == {"代码", "领域"}:
            return True
        if g_type and p_type:
            return False
        return g == p

    # 能否推理
    if field_name == "能否推理":
        thinking_kw = {"thinking", "yes", "是", "支持"}
        non_thinking_kw = {"non-thinking", "no", "否", "不支持"}
        g_think = g in thinking_kw
        p_think = p in thinking_kw
        g_non = g in non_thinking_kw
        p_non = p in non_thinking_kw
        if g_think and p_think:
            return True
        if g_non and p_non:
            return True
        if (g_think or g_non) and (p_think or p_non):
            return g_think == p_think
        return g == p

    # 公司：中英文同义映射
    if field_name == "公司":
        return _normalize_company(g) == _normalize_company(p)

    # 尺寸：提取数字部分比较
    if field_name == "尺寸":
        g_nums = re.findall(r"[\d.]+", g)
        p_nums = re.findall(r"[\d.]+", p)
        if g_nums and p_nums:
            try:
                return abs(float(g_nums[0]) - float(p_nums[0])) < 0.1
            except ValueError:
                pass
        return g == p

    # 官网：只要都有 URL 就算"都提供了"，不比较具体值
    # （排行榜链接 vs 官方链接是不同含义，不应判为不一致）
    if field_name == "官网":
        return None  # 跳过比较，不计入准确率

    # 备注：风格不同不应判为不一致，跳过比较
    if field_name == "备注":
        return None  # 跳过比较，不计入准确率

    # 模型发布时间：日期比较（容忍 ±3 天）
    if field_name == "模型发布时间":
        try:
            g_date = pd.to_datetime(g)
            p_date = pd.to_datetime(p)
            return abs((g_date - p_date).days) <= 3
        except Exception:
            return g == p

    return g == p


def run_evaluation():
    """执行评估，返回报告文本。"""
    gold_df = pd.read_excel(GOLD_PATH)
    pipe_df = pd.read_excel(PIPE_PATH)

    gold_index = build_name_index(gold_df)
    pipe_index = build_name_index(pipe_df)

    # ── 第一步：名称匹配 ──
    matched_pairs = []       # (gold_name, pipe_name, gold_idx, pipe_idx)
    unmatched_gold = []      # (gold_name, gold_idx)
    extra_pipeline = []      # (pipe_name, pipe_idx)

    used_pipe_norms = set()
    pipe_norms_list = list(pipe_index.keys())

    for g_norm, (g_name, g_idx) in gold_index.items():
        if g_norm in pipe_index:
            p_name, p_idx = pipe_index[g_norm]
            matched_pairs.append((g_name, p_name, g_idx, p_idx))
            used_pipe_norms.add(g_norm)
        else:
            fuzzy = fuzzy_match(g_norm, [pn for pn in pipe_norms_list if pn not in used_pipe_norms])
            if fuzzy:
                p_name, p_idx = pipe_index[fuzzy]
                matched_pairs.append((g_name, p_name, g_idx, p_idx))
                used_pipe_norms.add(fuzzy)
            else:
                unmatched_gold.append((g_name, g_idx))

    for p_norm, (p_name, p_idx) in pipe_index.items():
        if p_norm not in used_pipe_norms:
            extra_pipeline.append((p_name, p_idx))

    # ── 第二步：逐字段评估 ──
    field_stats = {}
    field_details = {}  # field -> list of (gold_name, gold_val, pipe_val, result)

    for field in EVAL_FIELDS:
        stats = {
            "both_filled": 0,     # 双方都有值
            "agree": 0,           # 一致
            "disagree": 0,        # 不一致
            "gold_only": 0,       # 只有金标有
            "pipe_only": 0,       # 只有流水线有（补全能力）
            "both_empty": 0,      # 都没有
        }
        details = []

        for g_name, p_name, g_idx, p_idx in matched_pairs:
            g_val = gold_df.at[g_idx, field] if field in gold_df.columns else None
            p_val = pipe_df.at[p_idx, field] if field in pipe_df.columns else None

            g_has = pd.notna(g_val) and str(g_val).strip() != ""
            p_has = pd.notna(p_val) and str(p_val).strip() != ""

            if g_has and p_has:
                eq = field_equal(g_val, p_val, field)
                if eq is True:
                    stats["both_filled"] += 1
                    stats["agree"] += 1
                    details.append((g_name, g_val, p_val, "AGREE"))
                elif eq is False:
                    stats["both_filled"] += 1
                    stats["disagree"] += 1
                    details.append((g_name, g_val, p_val, "DISAGREE"))
                else:
                    stats["both_filled"] += 1
                    details.append((g_name, g_val, p_val, "UNKNOWN"))
            elif g_has and not p_has:
                stats["gold_only"] += 1
                details.append((g_name, g_val, "", "GOLD_ONLY"))
            elif not g_has and p_has:
                stats["pipe_only"] += 1
                details.append((g_name, "", p_val, "PIPE_ONLY"))
            else:
                stats["both_empty"] += 1

        field_stats[field] = stats
        field_details[field] = details

    # ── 第三步：生成报告 ──
    lines = []
    lines.append("# 流水线验收评估报告")
    lines.append("")
    lines.append(f"> **评估时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> **金标文件**: gold_standard.xlsx ({len(gold_index)} 条)")
    lines.append(f"> **流水线产出**: pipeline_llmstats.xlsx ({len(pipe_index)} 条)")
    lines.append(f"> **金标时间段**: 2026/01/01 ~ 2026/03/30")
    lines.append(f"> **数据源**: llm-stats.com (4 个页面)")
    lines.append("")

    # 覆盖率
    recall = len(matched_pairs) / len(gold_index) * 100 if gold_index else 0
    lines.append("## 一、模型名称覆盖率 (Recall)")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 金标模型数 | {len(gold_index)} |")
    lines.append(f"| 流水线采集数 | {len(pipe_index)} |")
    lines.append(f"| **匹配成功** | **{len(matched_pairs)}** |")
    lines.append(f"| 未匹配（金标遗漏） | {len(unmatched_gold)} |")
    lines.append(f"| 流水线独有（金标未收录） | {len(extra_pipeline)} |")
    lines.append(f"| **覆盖率** | **{recall:.1f}%** |")
    lines.append("")

    # 匹配详情
    if matched_pairs:
        lines.append("### 匹配成功的模型")
        lines.append("")
        lines.append("| # | 金标名称 | 流水线名称 | 名称一致 |")
        lines.append("|---|---------|-----------|---------|")
        for i, (g, p, _, _) in enumerate(sorted(matched_pairs), 1):
            same = "✅" if g == p else "⚠️"
            lines.append(f"| {i} | {g} | {p} | {same} |")
        lines.append("")

    if unmatched_gold:
        lines.append("### 未匹配的金标模型（流水线遗漏）")
        lines.append("")
        lines.append("| # | 模型名称 | 公司 | 国内外 | 类型 |")
        lines.append("|---|---------|------|-------|------|")
        for i, (name, idx) in enumerate(sorted(unmatched_gold), 1):
            row = gold_df.iloc[idx] if idx < len(gold_df) else {}
            company = row.get("公司", "?") if not pd.isna(row.get("公司", float("nan"))) else "?"
            domestic = row.get("国内外", "?") if not pd.isna(row.get("国内外", float("nan"))) else "?"
            mtype = row.get("类型", "?") if not pd.isna(row.get("类型", float("nan"))) else "?"
            lines.append(f"| {i} | {name} | {company} | {domestic} | {mtype} |")
        lines.append("")

    if extra_pipeline:
        lines.append("### 流水线独有模型（金标未收录）")
        lines.append("")
        lines.append("| # | 模型名称 | 公司 | 类型 |")
        lines.append("|---|---------|------|------|")
        for i, (name, idx) in enumerate(sorted(extra_pipeline), 1):
            row = pipe_df.iloc[idx] if idx < len(pipe_df) else {}
            company = row.get("公司", "?") if not pd.isna(row.get("公司", float("nan"))) else "?"
            mtype = row.get("类型", "?") if not pd.isna(row.get("类型", float("nan"))) else "?"
            lines.append(f"| {i} | {name} | {company} | {mtype} |")
        lines.append("")

    # 逐字段评估
    lines.append("## 二、逐字段准确率与补全能力")
    lines.append("")
    lines.append("基于匹配成功的 **{}** 个模型进行字段对比：".format(len(matched_pairs)))
    lines.append("")
    lines.append("| 字段 | 双方都有 | 一致 | 不一致 | 准确率 | 金标独有 | 流水线补全 | 补全能力 |")
    lines.append("|------|---------|------|--------|--------|---------|-----------|---------|")

    for field in EVAL_FIELDS:
        s = field_stats[field]
        accuracy = f"{s['agree']*100//s['both_filled']}%" if s["both_filled"] > 0 else "N/A"
        complement = s["pipe_only"]
        complement_pct = f"{complement}" if complement > 0 else "0"
        lines.append(
            f"| {field} | {s['both_filled']} | {s['agree']} | {s['disagree']} | {accuracy} "
            f"| {s['gold_only']} | {complement_pct} | "
            f"{'✅' if complement > 0 else '—'} |"
        )
    lines.append("")

    # 不一致详情
    has_disagree = False
    for field in EVAL_FIELDS:
        disagrees = [(g, gv, pv, r) for g, gv, pv, r in field_details[field] if r == "DISAGREE"]
        if disagrees:
            if not has_disagree:
                lines.append("## 三、不一致项详情（待人工判定谁对谁错）")
                lines.append("")
                has_disagree = True
            lines.append(f"### {field}")
            lines.append("")
            lines.append("| 模型 | 金标值 | 流水线值 | 判定 |")
            lines.append("|------|--------|---------|------|")
            for g_name, g_val, p_val, _ in disagrees:
                lines.append(f"| {g_name} | {g_val} | {p_val} | 待定 |")
            lines.append("")

    if not has_disagree:
        lines.append("## 三、不一致项详情")
        lines.append("")
        lines.append("无不一致项。")
        lines.append("")

    # 补全详情
    has_complement = False
    for field in EVAL_FIELDS:
        complements = [(g, gv, pv, r) for g, gv, pv, r in field_details[field] if r == "PIPE_ONLY"]
        if complements:
            if not has_complement:
                lines.append("## 四、流水线补全能力（金标缺失，流水线补充）")
                lines.append("")
                has_complement = True
            lines.append(f"### {field}（补全 {len(complements)} 项）")
            lines.append("")
            lines.append("| 模型 | 流水线补全值 |")
            lines.append("|------|-----------|")
            for g_name, _, p_val, _ in complements[:30]:
                lines.append(f"| {g_name} | {p_val} |")
            if len(complements) > 30:
                lines.append(f"| ... | 共 {len(complements)} 项 |")
            lines.append("")

    if not has_complement:
        lines.append("## 四、流水线补全能力")
        lines.append("")
        lines.append("无补全项。")
        lines.append("")

    # 总结
    lines.append("## 五、总结")
    lines.append("")
    lines.append(f"- **模型覆盖率**: {recall:.1f}% ({len(matched_pairs)}/{len(gold_index)})")
    total_agree = sum(s["agree"] for s in field_stats.values())
    total_both = sum(s["both_filled"] for s in field_stats.values())
    total_accuracy = f"{total_agree*100//total_both}%" if total_both > 0 else "N/A"
    lines.append(f"- **字段总准确率**: {total_accuracy} ({total_agree}/{total_both})")
    total_complement = sum(s["pipe_only"] for s in field_stats.values())
    lines.append(f"- **补全数据项**: {total_complement} 项（金标缺失但流水线可补充）")
    total_disagree = sum(s["disagree"] for s in field_stats.values())
    lines.append(f"- **不一致项**: {total_disagree} 项（需人工判定）")
    lines.append(f"- **金标遗漏模型**: {len(unmatched_gold)} 个")
    lines.append(f"- **流水线独有模型**: {len(extra_pipeline)} 个")
    lines.append("")

    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    return report_text, len(matched_pairs), len(gold_index), len(unmatched_gold)


if __name__ == "__main__":
    report, matched, total_gold, unmatched = run_evaluation()
    print(f"评估完成: {matched}/{total_gold} 模型匹配, {unmatched} 个金标遗漏")
    print(f"报告已写入: {REPORT_PATH}")
