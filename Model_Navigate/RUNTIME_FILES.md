2026/05/11/17:04
name: 运行时数据文件分类说明
description: 区分项目中哪些是源码/配置（必须版本管理），哪些是运行时产出（可按需 gitignore），方便随时切换

# 运行时数据文件分类说明

> 本文档将项目文件分为**源码层**和**运行时数据层**，当你需要启用 `.gitignore` 排除运行时文件时，直接复制下方对应的规则即可。

---

## 一、源码层（必须版本管理，不可 gitignore）

这些是项目的核心逻辑、配置和文档，删了就跑不起来。

```
Model_Navigate/
├── .env.example              # API Key 配置模板
├── config.py                 # 全局配置（路径、超时、常量）
├── main.py                   # 流水线入口
├── auto_collect.py           # 数据采集脚本
├── review_models.py          # GPT-5.5 审核脚本
├── push_dingtalk.py          # 钉钉推送脚本
├── SKILL.md                  # AI 操作手册
├── package.json              # Skill 元数据
├── requirements.txt          # Python 依赖
├── Crawl/
│   ├── Arena_x/extract_llmstats_json.py
│   ├── Arena_x/format_cases.py
│   └── TXresearch/crawl_sohu.py
├── Extract/
│   ├── extract_models_llm.py
│   ├── Taxonomy.xlsx         # 字段填写规范（静态参考）
│   └── Focus.xlsx            # 重点关注机构列表（静态参考）
├── Report/
│   └── generate_report.py
├── Test/
│   └── check_result.py
├── Eval/
│   ├── 20260509_*.py         # 评估脚本
│   └── gold_standard.xlsx    # 金标文件（静态参考）
└── data/
    └── .gitkeep
```

---

## 二、运行时数据层（可 gitignore 的产出文件）

这些是每次流水线运行自动生成的，删了可以重新跑出来。

### 2.1 核心数据（建议保留在 git 中，因为是业务资产）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `data/Object-Models.xlsx` | **总表（唯一真相源）** | ❌ 不可重建，是累积资产 |
| `data/increments/*.xlsx` | 增量归档 | ⚠️ 可从总表 diff 推算，但建议保留 |
| `data/Backup/*.xlsx` | 总表备份 | ✅ 可重建，但保留更安全 |
| `data/run_log.csv` | 运行记录 | ✅ 可重建 |

### 2.2 采集缓存（可安全 gitignore）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `Crawl/Arena_x/llm-stats-*.com` | llmstats HTML 本地缓存 | ✅ 重新抓取即可 |
| `Crawl/Arena_x/llmstats_models.json` | llmstats 模型 JSON | ✅ 重新抓取即可 |
| `Crawl/Arena_x/formatted_leaderboards.md` | 排行榜格式化 | ✅ 重新生成 |
| `TXresearch/articles_*.json` | 腾讯研究院文章列表缓存 | ✅ 重新爬取即可 |
| `TXresearch/腾讯研究院文章列表.csv` | 文章列表 CSV | ✅ 重新爬取 |
| `TXresearch/腾讯研究院文章列表.xlsx` | 文章列表 Excel | ✅ 重新爬取 |

### 2.3 提取产出（可安全 gitignore）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `Extract/articles/*.txt` | 文章全文（爬虫抓取） | ✅ 重新爬取 |
| `Extract/TXCrawl.xlsx` | 爬取结果中间表 | ✅ 重新生成 |
| `Extract/TXCrawl_result.xlsx` | 提取结果中间表 | ✅ 重新生成 |
| `Extract/extracted_models_llm.json` | LLM 提取结果 | ✅ 重新跑 LLM 提取 |

### 2.4 报告产出（可安全 gitignore）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `Report/daily_report_*.md` | 日报文件 | ✅ 重新生成 |
| `Report/diff_result.md` | 对比结果 | ✅ 重新生成 |
| `Report/E2E-Test-Report.md` | 端到端测试报告 | ✅ 重新生成 |
| `Report/Update-Log.md` | 更新日志 | ✅ 重新生成 |
| `Report/update_report_*.md` | 更新报告 | ✅ 重新生成 |
| `Report/review_report.md` | 审核报告 | ✅ 重新生成 |
| `Report/review_results.json` | 审核结果 JSON | ✅ 重新生成 |

### 2.5 Trace 运行记录（可选 gitignore）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `Trace/trace_*.md` | 流水线运行记录 | ✅ 重新跑流水线生成 |

### 2.6 评估产出（可选 gitignore）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `Eval/eval_report.md` | 评估报告 | ✅ 重新跑评估脚本 |
| `Eval/eval_combined_report.md` | 联合评估报告 | ✅ 重新跑 |
| `Eval/eval_full_pipeline_report.md` | 完整流水线评估 | ✅ 重新跑 |
| `Eval/pipeline_llmstats.xlsx` | 流水线产出快照 | ✅ 重新跑 |

### 2.7 备份文件（可选 gitignore）

| 路径 | 说明 | 能否重建 |
|------|------|----------|
| `Backup/*.xlsx` | 旧的根目录备份 | ✅ 历史遗留，可删 |
| `data/Backup/*.xlsx` | v3 合并前备份 | ✅ 可重建但保留更安全 |
| `data/_backup/*.xlsx` | 旧架构备份 | ✅ 过渡期遗留，可清理 |

---

## 三、推荐的 .gitignore 规则（按需复制启用）

当你想排除运行时文件时，将以下内容追加到 `.gitignore`：

```gitignore
# ===== 运行时数据文件（按需启用） =====

# 采集缓存
Model_Navigate/Crawl/Arena_x/llm-stats-*.com
Model_Navigate/Crawl/Arena_x/llmstats_models.json
Model_Navigate/Crawl/Arena_x/formatted_leaderboards.md
Model_Navigate/TXresearch/articles_*.json
Model_Navigate/TXresearch/腾讯研究院文章列表.csv
Model_Navigate/TXresearch/腾讯研究院文章列表.xlsx

# 提取产出
Model_Navigate/Extract/articles/
Model_Navigate/Extract/TXCrawl.xlsx
Model_Navigate/Extract/TXCrawl_result.xlsx
Model_Navigate/Extract/extracted_models_llm.json

# 报告产出
Model_Navigate/Report/daily_report_*.md
Model_Navigate/Report/diff_result.md
Model_Navigate/Report/E2E-Test-Report.md
Model_Navigate/Report/Update-Log.md
Model_Navigate/Report/update_report_*.md
Model_Navigate/Report/review_report.md
Model_Navigate/Report/review_results.json

# Trace 运行记录
Model_Navigate/Trace/trace_*.md

# 评估产出
Model_Navigate/Eval/eval_report.md
Model_Navigate/Eval/eval_combined_report.md
Model_Navigate/Eval/eval_full_pipeline_report.md
Model_Navigate/Eval/pipeline_llmstats.xlsx

# 备份
Model_Navigate/Backup/
Model_Navigate/data/Backup/
Model_Navigate/data/_backup/
Model_Navigate/data/run_log.csv
```

### 最小化 gitignore（只排除大体积可重建文件）

如果只想排除最占空间的，用这个最小版：

```gitignore
# 最小化：只排除大体积可重建文件
Model_Navigate/Extract/articles/
Model_Navigate/Crawl/Arena_x/llm-stats-*.com
Model_Navigate/Backup/
Model_Navigate/data/_backup/
```

---

## 四、决策指南

| 你的场景 | 建议 |
|----------|------|
| 想保留完整历史可追溯性 | 全部纳入 git（当前状态） |
| 仓库太大想瘦身 | 启用"推荐规则"，保留总表和增量 |
| 只想保留源码+总表 | 启用"推荐规则" + 排除 `data/increments/` |
| 迁移到新机器冷启动 | 只需源码层 + `data/Object-Models.xlsx`，其余重新跑即可 |
