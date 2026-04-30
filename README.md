# Model Navigate — AI 模型导航与追踪系统

> 全自动化 AI 模型追踪流水线，覆盖**采集→提取→校验→审核→推送**全链路。

多数据源自动采集（llmstats.com / 腾讯研究院 / HuggingFace），LLM 自动提取模型信息，GPT-5.5 智能审核 + 重要性评级，钉钉日报一键推送。

本项目同时是一个 AI Skill —— `Model_Navigate/SKILL.md` 是 AI 的操作手册，AI 可直接按流程执行完整的模型追踪任务。

---

## 功能亮点

- **多源自动采集**：llmstats.com HTTP 直连 + 腾讯研究院 Selenium 爬虫 + HuggingFace API 交叉校验
- **LLM 智能提取**：从文章全文中自动提取模型名称、公司、类型等字段
- **GPT-5.5 审核**：模型名称规范性审核 + 旧模型检测 + 字段补全 + 重要性评级（高/中/低）
- **钉钉日报推送**：自动生成日报并推送到钉钉群
- **AI 协作就绪**：内置 `SKILL.md` 操作手册，AI 可直接按流程执行

---

## 安装

### 1. 获取项目

```bash
git clone <repo-url>
cd model-navigate-skill
```

### 2. 安装依赖

```bash
cd Model_Navigate
pip install -r requirements.txt
```

需要 **Python 3.13+**，依赖包：`pandas`、`openpyxl`、`requests`、`selenium`、`python-dotenv`。

### 3. 配置 API Key

```bash
cp Model_Navigate/.env.example Model_Navigate/.env
# 编辑 .env，填入你的 API Key
```

| 配置项 | 用途 | 必需？ |
|--------|------|--------|
| `LLM_API_KEY` 或 `DASHSCOPE_API_KEY` | LLM 从文章中提取模型信息 | 推荐 |
| `KUAI_API_KEY` | GPT-5.5 模型审核 + 重要性评级 | 推荐 |
| `DINGTALK_WEBHOOK` + `DINGTALK_SECRET` | 钉钉日报推送 | 可选 |
| `HF_TOKEN` | HuggingFace 私有模型校验 | 可选 |

详细配置说明见 `Model_Navigate/.env.example`。

> ⚠️ **阿里内网用户**：以下外网域名可能被云壳安全策略拦截，需在 **云壳 → 防护记录 → 域名拦截** 中加白：
>
> | 域名 | 用途 | 必需？ |
> |------|------|--------|
> | `api.kuai.host` | 主 LLM API（GPT-5.5 审核 + LLM 提取） | 推荐 |
> | `llm-stats.com` | llmstats 数据源（模型排行榜抓取） | 推荐 |
> | `dashscope.aliyuncs.com` | 备选 LLM API（DashScope / Qwen） | 通常已加白 |
> | `huggingface.co` | HuggingFace 开源模型校验 | 可选 |
>
> 症状：`SSLError: self-signed certificate` 或 403 "网站不在安全策略允许范围内"，或抓取到的文件内容是"域名拦截"页面。

### 4. 首次运行（冷启动）

**无需提前准备数据文件**——本项目支持从零冷启动。首次运行时会自动创建空基线 Excel（含正确表头）。

所有过程性数据（爬虫结果、文章全文、JSON 缓存、报告等）都在 `Model_Navigate/` 目录内自动生成，不会额外创建工作目录。

### 5. 总表功能（可选）

在 `Model_Navigate/data/` 下放置 `Models.xlsx`（全量模型总表）即可启用总表功能。

每次流水线运行后，新增模型会自动增量合并到总表（标准化去重）。不放 `Models.xlsx` = 不启用，不影响流水线运行。

---

## 快速开始

所有命令在 `Model_Navigate/` 目录下执行：

```bash
cd Model_Navigate

# 一键运行全流水线
python main.py --since YYYYMMDD --until YYYYMMDD

# 含钉钉推送
python main.py --since YYYYMMDD --until YYYYMMDD --push

# 推送日报（预览加 --dry-run）
python push_dingtalk.py --since YYYYMMDD --until YYYYMMDD

# 模型审核（预览加 --dry-run）
python review_models.py

# LLM 自动提取
cd Extract; python extract_models_llm.py --since YYYYMMDD --until YYYYMMDD
```

---

## 工作流程

每轮模型追踪包含三个阶段：

### 阶段 A：自动采集

运行 `python main.py`，自动执行 9 个步骤：

```
Step 1    准备基线 → 从 Old.xlsx 复制
Step 2    数据采集 → llmstats + 腾讯研究院 + HuggingFace
Step 2.5  LLM 提取 → 从文章全文提取模型（可选）
Step 3    GPT-5.5 审核 → 名称规范 + 字段补全 + 重要性评级
Step 4    数据检查
Step 5    报告生成
Step 6    Case 格式化
Step 7    表格对比
Step 8    验收报告
Step 9    钉钉推送（需 --push）
```

### 阶段 B：AI 创作校验（推荐）

在 AI 对话中完成高质量校验：读取文章全文 → 提取新模型 → 生成语义化备注 → 核实发布时间 → 补全字段 → 去重写入 Excel。

AI 会自动加载 `Model_Navigate/SKILL.md` 并按规范执行。

### 阶段 C：推送与验收

数据质量检查 → 钉钉日报推送 → 人工终判。

---

## 数据源

| 渠道 | 自动化 | 说明 |
|------|--------|------|
| [llm-stats.com](https://llm-stats.com) | ✅ 全自动 | HTTP 直连 + Next.js RSC JSON 解析 |
| [腾讯研究院](https://mp.sohu.com/profile?xpt=bGl1amluc29uZzIwMDBAMTI2LmNvbQ==) | ✅ 全自动 | Selenium 爬虫抓取搜狐号文章全文 |
| [HuggingFace](https://huggingface.co) | ✅ 全自动 | API 交叉校验开源模型参数和日期 |
| [Arena](https://arena.ai/leaderboard) | ❌ 手动 | 需手动复制排行榜到 Case 文件 |

---

## 项目结构

```
model-navigate-skill/               ← 项目根目录（GitHub 仓库）
├── README.md                        ← 本文件（面向人的项目说明）
├── .gitignore
│
└── Model_Navigate/                  ← Skill 包（AI 操作手册 + 核心脚本）
    ├── SKILL.md                     ← AI 操作手册
    ├── package.json                 ← Skill 元数据
    ├── requirements.txt             ← Python 依赖
    ├── .env.example                 ← API Key 配置模板
    │
    ├── main.py                      ← 流水线入口（9步）
    ├── auto_collect.py              ← 自动化数据采集
    ├── review_models.py             ← GPT-5.5 模型审核 + 重要性评级
    ├── push_dingtalk.py             ← 钉钉日报生成与推送
    │
    ├── data/                        ← 运行时数据（用户自备）
    │
    ├── Crawl/
    │   ├── TXresearch/crawl_sohu.py ← 腾讯研究院爬虫（Selenium）
    │   └── Arena_x/
    │       ├── extract_llmstats_json.py  ← llmstats 数据提取
    │       └── format_cases.py           ← Case 文件格式化
    │
    ├── Extract/
    │   ├── extract_models_llm.py    ← LLM API 自动提取
    │   ├── Taxonomy.xlsx            ← 字段填写规范
    │   └── Focus.xlsx               ← 重点关注机构列表
    │
    ├── Report/
    │   └── generate_report.py       ← 更新报告生成
    │
    └── Test/
        └── check_result.py          ← 数据完整性检查
```

---

## 作为 AI Skill 使用

将 `Model_Navigate/` 文件夹复制到 `~/.agents/skills/model-navigate/`，AI 会自动发现并加载 `SKILL.md`。

在 AI 对话中说以下关键词即可触发：

- "帮我追踪最近一周的新模型"
- "运行模型追踪流水线"
- "补全 Models.xlsx 的发布时间"
- "生成钉钉日报"

AI 会按照 `SKILL.md` 中的三阶段工作流、数据质量标准和操作规范自动执行。

---

## 表格字段说明

| 字段 | 说明 | 填写规范 |
|------|------|----------|
| 模型名称 | API 接口名 | 具体版本号，非产品泛称 |
| 是否接入 | 是否已接入评测平台 | 业务字段 |
| workflow 接入进展 | 接入状态 | 业务字段 |
| 公司 | 发布公司 | 统一写法（如"OpenAI"而非"openai"） |
| 国内外 | 国内/国外 | 根据公司判断 |
| 开闭源 | 开源/闭源/集成产品 | — |
| 尺寸 | 参数量 | 如 7B、235B(A22B) |
| 类型 | 模型类型 | 基座/多模态/智能体/代码/语音/视频/图像/具身等 |
| 是否推理 | 推理能力 | thinking / non-thinking |
| 任务类型 | 主要任务 | 通用对话/代码生成/图像生成等 |
| 官网 | 官方页面链接 | — |
| 备注 | 语义化描述 | 分号分隔（如"MoE架构；1T参数；$0.95/4"） |
| 发布时间 | 模型发布日期 | YYYY-MM-DD |
| 记录创建时间 | 录入日期 | 自动填充 |

---

## 许可

MIT

---

## 贡献

欢迎 PR！请确保：

1. 新增的脚本使用 `Path(__file__).parent` 相对路径，不硬编码绝对路径
2. API Key 通过 `.env` 配置，不写死在代码中
3. 运行时生成的数据文件已加入 `.gitignore`
