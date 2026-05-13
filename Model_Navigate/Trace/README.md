# 2026/05/13/15:34
name: trace-audit
description: 模型来源追溯与数据质量审计工具。支持按关键词追溯模型完整数据链路，按增量文件批量审计，数据质量评分和可疑项自动标记，辅助人工校验。

# Trace — 模型来源追溯与数据质量审计

> 追溯每个模型的完整数据链路，标记可疑项，辅助人工校验。

---

## 功能定位

流水线每次跑完都会产出几十上百个模型记录，但人工不可能逐一确认每条数据。Trace 审计工具的核心价值是：

1. **来源可追溯**：给定模型名，追溯从哪个数据源采集、经过哪些处理步骤、当前字段填充状态
2. **批量审计**：对整个增量文件的所有模型做自动化质量扫描
3. **可疑项标记**：自动检测不属于 LLM 的模型混入（TTS/ASR/分类器等）、名称异常、字段缺失
4. **质量评分**：总表级别的数据健康度评估

---

## 快速使用

```bash
cd D:\yuwang\model-navigate-skill\Model_Navigate\Trace

# 按模型名追溯来源（支持模糊匹配）
python trace_audit.py trace "pareto-code"
python trace_audit.py trace "nemotron"

# 审计指定增量文件
python trace_audit.py audit 20260512_run1639.xlsx

# 审计最新增量文件
python trace_audit.py audit --latest

# 审计所有增量文件
python trace_audit.py audit --all

# 总表数据质量概览
python trace_audit.py quality
```

---

## 三个子命令

### `trace <关键词>` — 模型来源追溯

输入模型名称或关键词，输出：
- 总表中的完整记录（含所有字段值）
- 关键字段填充状态（官网/备注/发布时间 ✅/❌）
- 增量文件归属（来自哪个 `increments/*.xlsx`）
- 采集脚本推断（auto_collect.py 定时采集）
- 具体数据源推断（llm-stats.com → OpenRouter / HuggingFace / NVIDIA 等）
- 完整数据链路图

**示例输出**：
```
[llm-stats.com → OpenRouter 聚合平台]
  → auto_collect.py (HTTP抓取 + LLM结构化提取)
  → 20260512_run1639.xlsx (增量文件)
  → review_models.py (GPT-5.5 审核补全)
  → verify_models.py (DashScope联网校验)
  → Object-Models.xlsx (总表)
```

### `audit <文件/--latest/--all>` — 增量文件批量审计

对增量文件中的所有模型做批量质量检查：
- **字段填充率**：官网/备注/发布时间的填充比例，红黄绿分级
- **可疑模型标记**：自动检测非 LLM 类混入、名称异常、来源不明
- **字段缺失清单**：列出所有关键字段为空的模型

**可疑项检测规则**：

| 类别 | 匹配模式 | 建议 |
|------|----------|------|
| 非LLM类模型 | classifier, fasttext, embedding, tts, asr, whisper 等 | 人工确认是否应纳入 |
| 占卜/娱乐类 | 占卜, tarot, fortune 等 | 检查是否误采 |
| 名称异常（路由后缀） | `:free`, `:extended`, `:nitro` | 确认是否为独立模型 |
| 名称异常（过短） | 长度 ≤ 3 字符 | 可能是采集错误 |

### `quality` — 总表数据质量概览

对总表做全局健康度评估：
- 所有字段的填充率统计（🟢优 / 🟡良 / 🟠中 / 🔴差）
- 关键字段（官网/备注/发布时间）平均填充率 → 综合评分
- 全表可疑模型扫描
- 增量文件来源分布

---

## 输出报告

所有报告自动保存到 `Trace/reports/` 目录：

```
Trace/reports/
├── trace_{keyword}_{timestamp}.md    — 单模型追溯报告
├── audit_{filename}_{timestamp}.md   — 增量审计报告
├── audit_all_{timestamp}.md          — 全量审计报告
└── quality_{timestamp}.md            — 总表质量报告
```

报告格式为 Markdown，适合直接在编辑器中查看或作为人工校验的工作底稿。

---

## 与流水线的关系

```
auto_collect.py → increments/*.xlsx → review_models.py → verify_models.py → Object-Models.xlsx
                                                                                    ↓
                                                            trace_audit.py (事后审计，辅助人工校验)
```

Trace 是**事后审计工具**，不参与流水线主流程，不修改任何数据。它的输入是流水线的产出（增量文件和总表），输出是可读的审计报告。

---

## 依赖

```
pandas
openpyxl
```

无额外依赖，使用与主流水线相同的环境即可。
