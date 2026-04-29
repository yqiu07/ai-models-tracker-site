"""
生成模型追踪更新报告，包含统计数据和文本图表。
输出：Report/update_report_20260416.md
"""
import pandas as pd
from collections import Counter
from datetime import date

UPDATED_PATH = r"D:\yuwang\action\data\Object-Models-Updated.xlsx"
OLD_PATH = r"D:\yuwang\action\data\Object-Models-Old.xlsx"
REPORT_PATH = r"D:\yuwang\action\Report\update_report_20260416.md"

df = pd.read_excel(UPDATED_PATH)
old_df = pd.read_excel(OLD_PATH)

total = len(df)
old_count = len(old_df)
new_count = df["是否新增"].apply(lambda x: x == "New" if pd.notna(x) else False).sum()

# ============================================================
# 统计数据
# ============================================================

# 按公司统计（Top 15）
company_counts = Counter(str(c).strip() for c in df["公司"].dropna())
company_top15 = company_counts.most_common(15)

# 按类型统计
type_counts = Counter(str(t).strip() for t in df["类型"].dropna())

# 按国内外统计
region_counts = Counter(str(r).strip() for r in df["国内外"].dropna())

# 按开闭源统计
license_counts = Counter(str(l).strip() for l in df["开闭源"].dropna())

# 按能否推理统计
reasoning_counts = Counter(str(r).strip() for r in df["能否推理"].dropna())

# 新增模型按公司统计
new_df = df[df["是否新增"] == "New"]
new_company_counts = Counter(str(c).strip() for c in new_df["公司"].dropna())
new_company_top10 = new_company_counts.most_common(10)

# 新增模型按类型统计
new_type_counts = Counter(str(t).strip() for t in new_df["类型"].dropna())

# 字段覆盖率
field_coverage = {}
for col in ["模型名称", "公司", "国内外", "开闭源", "尺寸", "类型", "能否推理", "任务类型", "官网", "备注"]:
    filled = df[col].notna().sum()
    field_coverage[col] = (filled, total, filled / total * 100)


def bar_chart(label, value, max_value, width=30):
    """生成文本柱状图"""
    bar_len = int(value / max_value * width) if max_value > 0 else 0
    bar = "█" * bar_len + "░" * (width - bar_len)
    return f"{label:<20s} {bar} {value:>3d}"


# ============================================================
# 生成报告
# ============================================================
lines = []

lines.append("## 模型追踪更新报告")
lines.append("")
lines.append(f"> **更新日期**：2026-04-16")
lines.append(f"> **报告生成时间**：{date.today()}")
lines.append(f"> **数据文件**：`Object-Models-Updated.xlsx`")
lines.append("")
lines.append("---")
lines.append("")

# 更新概览
lines.append("### 更新概览")
lines.append("")
lines.append(f"| 指标 | 数值 |")
lines.append(f"|---|---|")
lines.append(f"| **表格总行数** | **{total}** |")
lines.append(f"| 原有模型（Old.xlsx） | {old_count} |")
lines.append(f"| 本次新增（标记 New） | **{new_count}** |")
lines.append(f"| 新增占比 | {new_count/total*100:.1f}% |")
lines.append("")

# 数据来源覆盖
lines.append("### 数据来源覆盖")
lines.append("")
lines.append("| 来源 | 文件数 | 提取候选 | 最终录入 | 说明 |")
lines.append("|---|---|---|---|---|")
lines.append("| 腾讯研究院AI速递 | 19篇文章 | 87个 | 67个 | AI阅读文章提取新兴模型 |")
lines.append("| llmstats Video Gen | 1个排行榜 | 19条 | 2个 | 大部分已追踪 |")
lines.append("| llmstats Image Gen | 1个排行榜 | 20条 | 8个 | Flux 2/Imagen 4/Seedream等 |")
lines.append("| llmstats LLM | 1个排行榜 | 10条 | 4个 | Mistral Small 4/Sarvam等 |")
lines.append("| llmstats Code Arena | 1个排行榜 | 20条 | 3个 | GPT Codex/High版本 |")
lines.append("| llmstats STT | 1个排行榜 | 11条 | 3个 | Whisper/Deepgram/Voxtral |")
lines.append("| llmstats Open LLM | 1个排行榜 | 13条 | 2个 | Gemma 4小尺寸 |")
lines.append("| **合计** | — | — | **89** | — |")
lines.append("")

# 字段覆盖率
lines.append("### 字段覆盖率")
lines.append("")
lines.append("| 字段 | 已填写 | 总数 | 覆盖率 |")
lines.append("|---|---|---|---|")
for field, (filled, t, pct) in field_coverage.items():
    indicator = "✅" if pct >= 90 else ("⚠️" if pct >= 50 else "❌")
    lines.append(f"| {field} | {filled} | {t} | {pct:.1f}% {indicator} |")
lines.append("")

# 可视化：按公司分布
lines.append("### 按公司分布（Top 15）")
lines.append("")
lines.append("```")
max_val = company_top15[0][1] if company_top15 else 1
for company, count in company_top15:
    lines.append(bar_chart(company, count, max_val))
lines.append("```")
lines.append("")

# 可视化：新增模型按公司分布
lines.append("### 新增模型按公司分布（Top 10）")
lines.append("")
lines.append("```")
max_val = new_company_top10[0][1] if new_company_top10 else 1
for company, count in new_company_top10:
    lines.append(bar_chart(company, count, max_val))
lines.append("```")
lines.append("")

# 可视化：按类型分布
lines.append("### 按模型类型分布")
lines.append("")
lines.append("```")
max_val = max(type_counts.values()) if type_counts else 1
for model_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    lines.append(bar_chart(model_type, count, max_val))
lines.append("```")
lines.append("")

# 可视化：按国内外分布
lines.append("### 按国内外分布")
lines.append("")
lines.append("```")
max_val = max(region_counts.values()) if region_counts else 1
for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
    lines.append(bar_chart(region, count, max_val))
lines.append("```")
lines.append("")

# 可视化：按开闭源分布
lines.append("### 按开闭源分布")
lines.append("")
lines.append("```")
max_val = max(license_counts.values()) if license_counts else 1
for lic, count in sorted(license_counts.items(), key=lambda x: -x[1]):
    lines.append(bar_chart(lic, count, max_val))
lines.append("```")
lines.append("")

# 可视化：新增模型按类型分布
lines.append("### 新增模型按类型分布")
lines.append("")
lines.append("```")
max_val = max(new_type_counts.values()) if new_type_counts else 1
for model_type, count in sorted(new_type_counts.items(), key=lambda x: -x[1]):
    lines.append(bar_chart(model_type, count, max_val))
lines.append("```")
lines.append("")

# Benchmark更新
lines.append("### Benchmark 数据更新")
lines.append("")
lines.append("本次从 llm-stats.com 排行榜中提取了以下 benchmark 指标，更新到已有模型的备注中：")
lines.append("")
lines.append("| 指标 | 说明 |")
lines.append("|---|---|")
lines.append("| Code Arena ELO | 代码生成竞技场排名分数 |")
lines.append("| Chat Arena ELO | 对话竞技场排名分数 |")
lines.append("| GPQA | 研究生级别问答准确率 |")
lines.append("| SWE-bench | 软件工程任务通过率 |")
lines.append("| AIME 2025 | 数学竞赛题准确率 |")
lines.append("| MMMLU | 多语言大规模多任务理解 |")
lines.append("")
lines.append("共更新了 **18** 个模型的 benchmark 数据。")
lines.append("")

# 待人工核实项
lines.append("### 待人工核实项")
lines.append("")
lines.append("以下内容建议人工抽检确认：")
lines.append("")
lines.append('1. **类型字段**（⭐⭐⭐）：AI判断的"基座/多模态/代码/语音"分类可能有偏差')
lines.append("2. **能否推理字段**（⭐⭐⭐）：thinking vs non-thinking 需确认模型是否真正支持 CoT")
lines.append("3. **去重准确性**（⭐⭐）：同一模型不同版本是否应合并或分开追踪")
lines.append("4. **官网链接**（⭐⭐）：45%覆盖率，部分模型待补充")
lines.append("5. **尺寸信息**（⭐）：15%覆盖率，闭源模型大多无公开参数量")
lines.append("")

# 建议
lines.append("### 后续建议")
lines.append("")
lines.append('1. **人工核实**：筛选"是否新增"=New的行，按公司分组逐一检查')
lines.append("2. **补充官网**：优先补充国内模型的官网（阿里云百炼、智谱开放平台等）")
lines.append("3. **建立别名表**：解决 `claude-opus-4.6` vs `claude-opus-4-6` 等命名不一致问题")
lines.append("4. **定期更新**：每周从腾讯研究院 + llm-stats.com 拉取新数据")
lines.append("5. **版本管理**：每次更新前备份为 `Object-Models-vN.xlsx`")
lines.append("")

report_content = "\n".join(lines)

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"报告已生成: {REPORT_PATH}")
print(f"报告行数: {len(lines)}")
print(f"\n--- 统计摘要 ---")
print(f"总模型数: {total}")
print(f"新增模型数: {new_count}")
print(f"公司数: {len(company_counts)}")
print(f"类型分布: {dict(type_counts)}")
print(f"国内外分布: {dict(region_counts)}")
print(f"开闭源分布: {dict(license_counts)}")
