# 端到端测试报告

> **测试时间**：2026-04-17 11:15
> **测试环境**：Windows 11 + PowerShell + Python 3.14
> **测试命令**：`python main.py`（完整流水线）
> **测试结果**：✅ 8/8 步骤全部通过

---

## 测试概览

| 步骤 | 名称 | 状态 | 产出 |
|------|------|------|------|
| 1 | 准备基线 | ✅ SUCCESS | `Object-Models-Updated.xlsx`（158行基线） |
| 2 | 录入腾讯研究院模型 | ✅ SUCCESS | +67 个模型 → 225行 |
| 3 | 录入 llmstats 模型 | ✅ SUCCESS | +14 个模型 → 239行 |
| 4 | 综合更新 | ✅ SUCCESS | +8 个模型 + 13个benchmark更新 + "是否新增"列 → 247行 |
| 5 | 添加核实状态 | ✅ SUCCESS | "核实情况"列 + 2个尺寸更新（Whisper 809M, Voxtral 4.7B） |
| 6 | 数据完整性检查 | ✅ SUCCESS | 字段覆盖率统计输出 |
| 7 | 生成更新报告 | ✅ SUCCESS | `Report/update_report_20260416.md`（151行） |
| 8 | 整理 Case 文件 | ✅ SUCCESS | `Crawl/Arena_x/formatted_leaderboards.md`（7个文件解析） |

---

## 数据验证

### 最终表格统计

| 指标 | 数值 |
|------|------|
| 总行数 | 247 |
| 原有模型 | 158 |
| 新增模型 | 89（标记 New：85，未标记：4） |
| 总列数 | 15（含核实情况列） |

### 字段覆盖率（新增89个模型）

| 字段 | 覆盖率 | 说明 |
|------|--------|------|
| 模型名称 | 100% | ✅ |
| 公司 | 97% | 3个未知公司 |
| 国内外 | 100% | ✅ |
| 开闭源 | 100% | ✅ |
| 尺寸 | 17% | 闭源模型大多无公开参数量 |
| 类型 | 100% | ✅ |
| 能否推理 | 100% | ✅ |
| 任务类型 | 82% | 部分基座模型无特定任务 |
| 官网 | 43% | 51个待补充 |
| 备注 | 100% | ✅ |
| 核实情况 | 96% | 4个未标记New的模型无核实情况 |

### 核实情况统计

| 核实手段 | 已完成 | 未完成 |
|----------|--------|--------|
| web_search | 42 | 43 |
| HuggingFace 成功 | 4 | — |
| HuggingFace 401 | 6 | — |
| HuggingFace 未尝试 | — | 14 |
| 官网链接有 | 37 | — |
| 官网链接无 | — | 32 |

### 去重验证

- 步骤 4 正确跳过了 7 个已追踪模型：GPT-5.3 Codex、GLM-4.6、Nemotron-3-Super、Qwen3.5-0.8B/2B/4B/9B
- Benchmark 更新了 13 个已有模型（Gemini 3.1 Pro、GPT-5.4、GLM-5 等）
- 5 个模型因名称格式不匹配未找到（claude-opus-4.6 等），属于已知局限

---

## 命令行参数测试

| 命令 | 预期行为 | 实际结果 |
|------|---------|---------|
| `python main.py --dry-run` | 预览模式，不实际执行 | ✅ 8步全部显示 DRY_RUN |
| `python main.py --step 5` | 从步骤5开始 | ✅ 步骤1-4 SKIPPED，5-8执行 |
| `python main.py --skip-verify` | 跳过步骤5 | ✅ 步骤5 SKIPPED |
| `python main.py` | 完整流水线 | ✅ 8步全部 SUCCESS |

---

## 已知局限

1. **模型数据硬编码**：每次更新需要先由 AI 协作填入 `Test/` 下脚本中的模型列表
2. **报告日期硬编码**：`generate_report.py` 中报告路径固定为 `update_report_20260416.md`
3. **名称匹配不完美**：5 个模型因命名格式差异未匹配到（如 `claude-opus-4.6` vs `claude-opus-4-6`）
4. **HuggingFace 401**：6 个开源模型需在浏览器中同意 License 后才能 API 访问

---

## 产出文件清单

```
action/
├── Object-Models-Updated.xlsx        ← 最终表格（247行，15列）
├── Object-Models.xlsx                ← 步骤1创建的基线副本
├── Backup/                           ← 自动备份
│   └── Object-Models-Updated_*.xlsx
├── Report/
│   └── update_report_20260416.md     ← 更新报告
└── Crawl/Arena_x/
    └── formatted_leaderboards.md     ← 排行榜汇总
```
