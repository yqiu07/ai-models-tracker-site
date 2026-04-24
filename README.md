# AI 模型追踪项目（v2 自动化版）

> 目标：系统化追踪全球 AI 模型发布动态，明确各厂商旗舰模型版本号、对齐国内外趋势，按选型标准评估后接入评测链路。

---

## 项目概览

| 指标 | 数值 |
|---|---|
| 表格总模型数 | 161（持续增长中） |
| 数据源 | llm-stats.com · 腾讯研究院 · HuggingFace |
| 自动化程度 | v2.2（采集+校验+推送，L0/L1 全自动，L2 人机协作） |
| 输出格式 | Excel（.xlsx） + Markdown 日报 + 钉钉推送 |

---

## 核心理念：每轮校验

每次查阅新时间段时，都会经过一轮完整的数据质量校验流程：

```
┌─────────────────────────────────────────────────────────────┐
│                    一轮完整的时间段处理                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  阶段 A：自动采集（L0/L1，脚本自动完成）                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 1. 准备基线 → 2. llmstats 抓取 → 3. 腾讯研究院爬虫    │  │
│  │ → 4. HuggingFace 核实 → 5. 去重写入 Excel             │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  阶段 B：AI 创作校验（L2，人机协作完成）                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 6. 文章模型信息提取（web search + AI 知识）             │  │
│  │ 7. 语义化备注生成（web search + 多源综合）              │  │
│  │ 8. 发布时间核实/补充（web search 交叉验证）             │  │
│  │ 9. 公司/类型等字段补全                                  │  │
│  └───────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  阶段 C：检查 + 报告 + 推送（L0/L1，脚本自动完成）           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 10. 数据完整性检查 → 11. 生成报告 → 12. 钉钉推送       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ✅ 校验通过标准：公司100% · 备注100% · 发布时间100%         │
└─────────────────────────────────────────────────────────────┘
```

**关键**：阶段 B 是 L2 AI 创作任务，每轮都必须执行，不能跳过或用模板规则降级替代。

---

## 快速开始（面向人）

### 环境准备

```bash
pip install pandas openpyxl requests beautifulsoup4 selenium
```

### 一键运行

```bash
cd D:\yuwang\action

# 完整流水线（指定时间段）
python main.py --since 20260424 --until 20260430

# 完整流水线 + 钉钉推送
python main.py --since 20260424 --until 20260430 --push

# 预览模式（不实际执行）
python main.py --since 20260424 --until 20260430 --dry-run

# 只推送日报（不跑采集）
python push_dingtalk.py --since 20260424 --until 20260430
```

### 常用命令速查

| 命令 | 说明 |
|------|------|
| `python main.py --since YYYYMMDD --until YYYYMMDD` | 完整流水线 |
| `python main.py --dry-run` | 预览模式 |
| `python main.py --step 3` | 从第3步开始 |
| `python main.py --source llmstats` | 只跑 llmstats |
| `python main.py --push` | 含钉钉推送 |
| `python auto_collect.py --since YYYYMMDD --until YYYYMMDD` | 只跑数据采集 |
| `python push_dingtalk.py --since YYYYMMDD --until YYYYMMDD --dry-run` | 预览日报 |

---

## 流水线步骤详解

### 阶段 A：自动采集（L0/L1）

由 `main.py` 步骤 1-2 和 `auto_collect.py` 自动完成：

| 步骤 | 操作 | 等级 | 自动化方式 |
|------|------|------|-----------|
| 1 | 准备基线（备份 Updated→Medium，复制 Old→Updated） | L0 | 文件操作 |
| 2a | llmstats 抓取 | L0 | HTTP 直连 + Next.js RSC JSON 解析，4个页面，291+ 模型 |
| 2b | 腾讯研究院爬虫 | L0 | Selenium + 全文抓取，自动调用 `crawl_sohu.py` |
| 2c | HuggingFace 核实 | L0 | API 直连，交叉校验参数量、License、pipeline_tag |
| 2d | 去重与写入 | L1 | 模型名称归一化匹配，追加到 Excel |

### 阶段 B：AI 创作校验（L2，每轮必须执行）

**这是每轮校验的核心**。以下任务需要 AI 理解、搜索、综合生成，不可用简单规则替代：

| 任务 | 方式 | 说明 |
|------|------|------|
| **文章模型信息提取** | AI 读取全文 + web search | 从腾讯研究院 AI 速递中提取新模型信息 |
| **语义化备注生成** | web search + AI 知识综合 | 为每个新模型生成"定位;特性;对标"格式的备注 |
| **发布时间核实/补充** | web search 交叉验证 | 核实 llmstats 回填的时间，补充缺失的时间 |
| **公司/类型等字段补全** | 名称推断(L1) + web search(L2) | 简单映射为 L1，需搜索核实时升级为 L2 |

**主方案**：在 AI Copilot 对话中，AI 使用 web search + 自身知识综合完成（推荐）

**次级方案**：通过 LLM API（`extract_models_llm.py`）自动提取，需配置 API Key

> ⚠️ **核心认知**：L2 任务必须使用 AI 能力（web search + AI 知识综合），绝不能用模板规则降级替代。
> 模板规则生成的备注（如"Qwen系列模型"）质量极低，无法替代 AI 结合公开资料生成的语义化备注。

### 阶段 C：检查 + 报告 + 推送（L0/L1）

由 `main.py` 步骤 3-9 自动完成：

| 步骤 | 操作 | 等级 |
|------|------|------|
| 3 | 数据完整性检查（`Test/check_result.py`） | L1 |
| 4 | 生成更新报告（`Report/generate_report.py`） | L1 |
| 5 | 整理 Case 文件 | L0 |
| 6 | 对比新旧表格（Updated vs Medium） | L1 |
| 7 | 同步新增模型（写入 only.xlsx） | L0 |
| 8 | 生成验收报告 | L1 |
| 9 | 钉钉推送日报（需 `--push` 参数） | L0 |

---

## AI 能力依赖等级

| 等级 | 含义 | 典型操作 |
|------|------|----------|
| **L0** 纯机械 | 无需 AI，脚本/规则即可完成 | 文件移动、路径替换、Excel 读写、目录整理、备份 |
| **L1** 规则判断 | 基于确定性规则的推断，可用代码实现 | 模型名称→公司映射、llmstats 精确匹配回填、去重、字段校验 |
| **L2** AI 创作 | 需要 AI 理解、搜索、综合生成，不可用简单规则替代 | 语义化备注生成、发布时间核实、文章模型信息提取、数据质量改进 |

---

## 腾讯研究院模型提取

腾讯研究院 AI 速递文章中包含大量模型信息，需要从全文中提取。这是每轮校验阶段 B 的重要输入。

### 主方案：AI 对话提取（推荐）

在 AI Copilot 对话中让 AI 直接读取文章并提取模型信息。

**优点**：更准确、可交互追问、能结合 web search 交叉校验

**适用**：日常更新、需要高质量备注时

使用方式：
1. 运行流水线步骤 2，全文会自动保存到 `Extract/articles/` 目录
2. 在对话中告诉 AI："请读取 Extract/articles/ 下 MMDD-MMDD 的文章，提取模型信息"
3. AI 会逐篇阅读并提取模型名称、公司、类型等字段
4. AI 同时为每个模型生成语义化备注、核实发布时间（L2 任务）
5. 确认后由 AI 写入 Excel

### 次级方案：LLM API 自动提取

通过 LLM API（DashScope 百炼 qwen-plus）自动从全文中提取模型信息。

**优点**：全自动、批量处理、无需人工干预

**适用**：批量补录、时间紧迫时

```bash
# 需要先配置 LLM API Key（在 .env 文件中添加，三选一）：
#   LLM_API_KEY=sk-xxx                      ← 专用 Key
#   TRACKER_FIELD_API_KEY=sk-xxx             ← 复用 models-tracker 的
#   DASHSCOPE_API_KEY=sk-xxx                 ← 复用 DashScope 的
#
# API Base（可选，默认百炼）：
#   LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
#   LLM_MODEL=qwen-plus

# 运行提取
cd Extract
python extract_models_llm.py --since YYYYMMDD --until YYYYMMDD

# 预览模式（不调用 LLM）
python extract_models_llm.py --since YYYYMMDD --until YYYYMMDD --dry-run
```

输出：
- `Extract/TXCrawl_result.xlsx` — 文章级结果（提及的模型 / 未追踪到的模型）
- `Extract/extracted_models_llm.json` — 完整提取结果（含字段信息）

---

## 数据源

| 渠道 | 地址 | 自动化程度 | 说明 |
|------|------|-----------|------|
| **llm-stats.com** | [AI首页](https://llm-stats.com) / [LLM榜](https://llm-stats.com/leaderboards/llm-leaderboard) / [Open LLM榜](https://llm-stats.com/leaderboards/open-llm-leaderboard) / [Updates](https://llm-stats.com/llm-updates) | ✅ 全自动 | HTTP 直连 + Next.js RSC JSON 解析 |
| **腾讯研究院** | [搜狐号主页](https://mp.sohu.com/profile?xpt=bGl1amluc29uZzIwMDBAMTI2LmNvbQ==) | ✅ 全自动 | Selenium 爬虫 + 全文抓取 |
| **HuggingFace** | `https://huggingface.co/api/models/` | ✅ 全自动 | API 交叉校验开源模型 |
| **Arena** | [arena.ai/leaderboard](https://arena.ai/leaderboard) | ❌ 手动 | 需手动复制排行榜到 Case 文件 |
| **X 账号** | @rowancheung 等 | ❌ 手动 | 关注官方发布动态 |

---

## 表格字段说明

| 字段 | 说明 | 填写规范 |
|---|---|---|
| 模型名称 | 用 API 接口名 | 参考 `Taxonomy.xlsx` |
| 是否接入 | 是否已接入评测 | — |
| workflow接入进展 | 接入状态 | — |
| 公司 | 发布公司 | — |
| 国内外 | 国内/国外 | — |
| 开闭源 | 开源/闭源/集成产品 | — |
| 尺寸 | 参数量 | HuggingFace 核实或留空 |
| 类型 | 基座/领域/微调/多模态/智能体/代码/语音/视频/图像/具身 | — |
| 能否推理 | thinking/non-thinking | 无 CoT/diffusion 一律 non-thinking |
| 任务类型 | 主要任务 | — |
| 官网 | 官方页面链接 | — |
| 备注 | 语义化描述 | 模型定位;技术特性;对标信息（分号分隔） |
| 记录创建时间 | 录入日期 | 自动填充 |
| 模型发布时间 | YYYYMMDD | 自动从数据源映射 |
| 是否新增 | New/空 | 自动与 Old.xlsx 对比 |
| 核实情况 | 核实渠道和结果 | HuggingFace/官网/公开榜单 |

### 备注风格规范

语义化标签式，分号分隔，中文为主技术术语保留英文。重在模型定位/能力/对标/技术特性，不堆积 benchmark 数字。

**生成方式**：必须由 AI 结合 web search + 公开资料综合生成（L2），禁止用模板规则批量生成。

示例：
- `MoE架构；1T参数；262k上下文；GPQA 90.5%；$0.95/4；MIT (modified)`
- `视频生成；成本减半；Lite版本`
- `开源Agent；内置学习循环`

---

## 钉钉推送

### 配置

在 `action/.env` 文件中配置：

```env
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_SECRET=SECxxx
```

### 使用

```bash
# 通过流水线推送
python main.py --since YYYYMMDD --until YYYYMMDD --push

# 单独推送
python push_dingtalk.py --since YYYYMMDD --until YYYYMMDD

# 预览日报内容
python push_dingtalk.py --since YYYYMMDD --until YYYYMMDD --dry-run
```

日报格式：AI 模型/智能体追踪日报，包含时间窗口内的总模型数、新增数、国内外/开闭源统计、按公司分组的模型列表。

---

## 文件结构

```
action/
├── main.py                          ← 主流水线入口（阶段A+C）
├── auto_collect.py                  ← 自动化数据采集（阶段A核心）
├── push_dingtalk.py                 ← 钉钉推送（阶段C）
├── .env                             ← 钉钉/LLM API 配置
│
├── data/                            ← 数据文件
│   ├── Object-Models-Updated.xlsx   ← 最终输出表格
│   ├── Object-Models-Old.xlsx       ← 基线表格
│   ├── Object-Models.xlsx           ← 基线副本
│   ├── Object-Models-Medium.xlsx    ← 更新前备份
│   └── Object-Models-Updated - only.xlsx ← 仅新增模型
│
├── Report/                          ← 报告与日报
│   ├── generate_report.py           ← 更新报告生成脚本
│   ├── daily_report_*.md            ← 钉钉日报 Markdown
│   ├── diff_result.md               ← 新旧对比报告
│   ├── E2E-Test-Report.md           ← 端到端测试报告
│   ├── Update-Log.md                ← 更新日志
│   └── update_report_*.md           ← 详细更新报告
│
├── Crawl/
│   ├── TXresearch/
│   │   └── crawl_sohu.py            ← 腾讯研究院爬虫（Selenium）
│   └── Arena_x/
│       ├── extract_llmstats_json.py ← llmstats HTML→JSON 提取
│       └── llmstats_models.json     ← llmstats 结构化数据（291模型）
│
├── Extract/
│   ├── articles/                    ← 腾讯研究院文章全文（TXT）
│   ├── crawl_articles.py            ← 文章全文爬取
│   ├── extract_models.py            ← 模型提取（手动版，硬编码）
│   ├── extract_models_llm.py        ← 模型提取（LLM API 自动版）
│   ├── TXCrawl_result.xlsx          ← 文章级提取结果
│   ├── Taxonomy.xlsx                ← 字段填写规范
│   └── Focus.xlsx                   ← 重点关注机构列表
│
├── TXresearch/                      ← 爬虫 JSON 输出缓存
├── Test/                            ← 数据完整性检查
├── Backup/                          ← 历史备份
└── README.md                        ← 本文件
```

---

## AI 使用指南（给 AI 协作者看的）

> 如果你是一个 AI（Claude、GPT、Qwen 等），正在被用户要求协助完成模型追踪任务，请先阅读本节。

### 你的角色

你是用户的**模型追踪协作者**，每轮新时间段的处理都需要你参与阶段 B（AI 创作校验）：

- **提取新模型信息**（读取文章全文 + web search 交叉校验）
- **生成语义化备注**（web search + AI 知识综合，L2 任务）
- **核实发布时间**（web search 交叉验证，L2 任务）
- **补全缺失字段**（公司、类型等，L1→L2）
- 运行自动化流水线（阶段 A + C）
- 生成日报并推送到钉钉

### 每轮完整操作流程

```
阶段 A：一键采集（L0/L1，自动）
  1. 运行 python main.py --since YYYYMMDD --until YYYYMMDD
  2. 步骤 2 自动完成：
     a. llmstats 抓取 → 新模型写入 data/Object-Models-Updated.xlsx
     b. 腾讯研究院爬虫 → 全文保存到 Extract/articles/
        → 元数据追加到 Extract/TXCrawl.xlsx 和 TXCrawl_result.xlsx
     c. HuggingFace 交叉核实开源模型
  3. 步骤 3-8 自动完成：检查 + 报告 + 对比 + 验收

阶段 B：AI 创作校验（L2，人机协作，每轮必须执行）
  4. 读取 Extract/articles/ 下的文章全文
  5. 逐篇提取模型名称、公司、类型等字段
  6. 为每个新模型生成语义化备注（web search + AI 知识）
  7. 核实/补充发布时间（web search 交叉验证）
  8. 补全缺失的公司/类型等字段
  9. 与已有 Excel 去重，标注未追踪的新模型
  10. 将结果写入 Excel（需用户确认）

阶段 C：推送与验收（L0/L1，自动 + 人工终判）
  11. 数据质量检查：公司100% · 备注100% · 发布时间100%
  12. 运行 python push_dingtalk.py 推送日报
  13. 用户检查钉钉群中的日报内容
```

### 关键操作规范

| 操作 | 规范 |
|------|------|
| 读取 Excel | 必须用 `pd.read_excel()` 读取，不要凭记忆猜测 |
| 写入 Excel | 运行前提醒用户关闭 Excel |
| 去重 | 填入前必须与 Updated.xlsx 中已有模型对比 |
| 备注生成 | **必须** web search + AI 知识综合生成（L2）；兜底：`_build_llmstats_note()` 规则生成 |
| 发布时间 | **必须** web search 交叉验证（L2）；不可只用 llmstats 未经验证的数据 |
| HuggingFace 核实 | 直连 API，部分模型需登录（401）属已知限制 |
| 腾讯研究院提取 | 主方案：对话中 AI 读取全文提取；次级方案：`extract_models_llm.py` |

### 数据质量校验标准

每轮处理完成后，必须达到以下质量标准才能进入推送阶段：

| 字段 | 目标 | 校验方式 |
|------|------|----------|
| 公司 | 100% | `pd.read_excel()` 统计非空比例 |
| 备注 | 100%（AI 创作质量） | 人工抽检语义化程度，禁止模板备注 |
| 模型发布时间 | 100% | web search 交叉验证准确性 |

### 常见陷阱

1. **不要假设 Excel 内容** — 必须先 `pd.read_excel()` 读取
2. **不要在 Excel 被占用时写入** — 提醒用户关闭
3. **不要把"可以核实"说成"已核实"** — 区分"已做"和"可做"
4. **不要用模板规则替代 AI 创作** — 备注生成、发布时间核实是 L2 任务
5. **sub agent 统计结果需二次验证** — 用磁盘数据核实 sub agent 的断言
6. **PowerShell 注意事项** — 不支持 `&&`，用 `;` 分隔；内联多行 Python 用临时脚本更可靠

### LLM API 配置（次级方案）

当用户无法在对话中让你提取模型信息时，可使用 LLM API 自动提取：

```bash
# .env 配置（优先级从高到低）
LLM_API_KEY=sk-xxx                                          # 专用 Key
TRACKER_FIELD_API_KEY=sk-xxx                                 # 复用 models-tracker 的
DASHSCOPE_API_KEY=sk-xxx                                     # 复用 DashScope 的

LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus

# 运行
cd Extract
python extract_models_llm.py --since YYYYMMDD --until YYYYMMDD
```

---

## 前置文件要求

| 文件 | 说明 | 必须存在 |
|------|------|----------|
| `data/Object-Models-Old.xlsx` | 原始基线表格 | ✅ |
| `Crawl/TXresearch/crawl_sohu.py` | 腾讯研究院爬虫 | ✅（步骤2自动调用） |
| `Crawl/Arena_x/extract_llmstats_json.py` | llmstats 提取 | ✅（步骤2自动调用） |
| `.env` | 钉钉/LLM 配置 | ⚠️（推送和 LLM 提取需要） |

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.2 | 2026-04-23 | 数据质量全面提升至100%（备注/公司/发布时间）；新增AI能力依赖等级（L0/L1/L2）；确立"每轮校验"常态化流程；README 全面重构 |
| v2.1 | 2026-04-23 | 目录整理（data/ + Report/）、备注语义化改造、腾讯研究院抓取修复与自动化集成、TXCrawl Excel 自动同步 |
| v2.0 | 2026-04-23 | 全自动化改造：9步流水线、llmstats HTTP直连、腾讯研究院自动爬虫、HuggingFace交叉校验、钉钉推送、LLM自动提取次级方案 |
| v1.0 | 2026-03-19 | 初版：12步半自动流水线，手动采集+硬编码模型列表 |
