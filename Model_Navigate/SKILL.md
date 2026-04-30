---
name: model-navigate
description: "AI 模型导航与追踪系统（Model Navigate）。全自动化 AI 模型追踪流水线，覆盖采集→提取→校验→审核→推送全链路。当用户需要追踪最新 AI 模型发布动态、自动采集 llmstats.com / 腾讯研究院 / HuggingFace 的模型信息、用 LLM 从文章中提取模型数据、用 GPT-5.5 审核模型质量和重要性评级、生成钉钉日报并推送、批量补全模型字段（公司/尺寸/官网/发布时间/备注）时使用。触发关键词：模型追踪、模型导航、AI 模型采集、日报推送、模型审核、模型补全、llmstats、腾讯研究院。"
---

# Model Navigate — AI 操作手册

本文档是给 AI 的操作手册。项目说明和安装指南请见 `README.md`。

---

## 项目定位

Skill 工作目录为本文件所在目录。核心入口是 `main.py`，运行时需要 `.env` 配置 API Key。

### 配置管理（三层分离）

项目参数按**安全性和变化频率**分为三层：

| 层 | 文件 | 内容 | 修改频率 |
|----|------|------|----------|
| **脱敏参数** | `.env` | API Key、Webhook、Token、API Base URL | 部署时改一次 |
| **工程可变参数** | `config.py` | 数据源 URL、超时、UA、数据常量（CN_ORGS/HF_ORG_MAP）、阈值、模型名 | 随业务迭代 |
| **核心逻辑** | 各脚本内部 | CSS 选择器、去重算法、CLI 参数、步骤定义 | 几乎不变 |

**修改参数时**：先判断属于哪一层，改对应的文件，**不要在脚本里硬编码 URL 或 Key**。

- 新增中国公司？→ 改 `config.py` 的 `CN_ORGS`
- 换 API 提供商？→ 改 `.env` 的 `KUAI_API_BASE`
- 调超时阈值？→ 改 `config.py` 的 `SUBPROCESS_TIMEOUT_MINUTES` 等
- 换爬虫目标页？→ 改 `config.py` 的 `TXRESEARCH_SOHU_URL`

### 两套表格体系

- **流水线表** `data/Object-Models-*.xlsx`：`main.py` 自动更新，每轮从 `Old.xlsx` 复制基线、采集写入 `Updated.xlsx`
- **总表** `data/Models.xlsx`（如有）：全量模型信息，由 AI 在对话中手动维护

### 表格字段（14 列）

| 字段 | AI 可补全？ | 说明 |
|------|------------|------|
| 模型名称 | — | API 接口名，须含具体版本号 |
| 是否接入 | ❌ | 业务字段，AI 跳过 |
| workflow 接入进展 | ❌ | 业务字段，AI 跳过 |
| 公司 | ✅ L1 | 发布公司 |
| 国内外 | ✅ L1 | 根据公司推断 |
| 开闭源 | ✅ L1 | 开源/闭源/集成产品 |
| 尺寸 | ⚠️ L2 | 参数量（如 7B、235B(A22B)），需 web search |
| 类型 | ✅ L1 | 基座/多模态/智能体/代码/语音/视频/图像/具身等 |
| 是否推理 | ✅ L1 | thinking / non-thinking |
| 任务类型 | ✅ L1 | 主要任务 |
| 官网 | ⚠️ L2 | 需 web search |
| 备注 | ⚠️ L2 | 语义化描述，分号分隔，需 AI 创作 |
| 发布时间 | ⚠️ L2 | YYYY-MM-DD，需 web search 交叉验证 |
| 记录创建时间 | 自动 | 录入日期 |

AI 能力等级：**L0** 纯机械 / **L1** 规则判断 / **L2** 需 AI 创作或 web search。

---

## 三阶段工作流

### 首次运行（冷启动）

本 Skill 支持**从零冷启动**——无需提前准备基线文件或工作目录。

1. 创建 `.env` 文件（参考 `.env.example`），填入 API Key、Webhook 等脱敏参数
2. 运行 `python main.py --since YYYYMMDD --until YYYYMMDD`

冷启动时 `main.py` 会自动创建空基线 Excel（含正确表头），无需手动准备。

**所有过程性数据**（爬虫结果、文章全文、JSON 缓存、报告等）都在 Skill 自身目录内生成（`data/`、`TXresearch/`、`Extract/articles/`、`Report/`、`Crawl/` 等），**不会额外创建工作目录**，对用户零负担。

### ⚠️ 网络环境要求

如果你在**阿里巴巴内网**（办公电脑 + 阿里郎）环境中使用，以下外网域名可能被**云壳安全策略**拦截，需要在云壳后台加白。

**需要加白的域名**：

| 域名 | 用途 | 必需？ |
|------|------|--------|
| `api.kuai.host` | 主 LLM API（GPT-5.5 审核 + LLM 提取） | 推荐 |
| `llm-stats.com` | llmstats 数据源（模型排行榜抓取） | 推荐 |
| `dashscope.aliyuncs.com` | 备选 LLM API（DashScope / Qwen） | 通常已加白 |
| `huggingface.co` | HuggingFace 开源模型校验 | 可选 |

**加白步骤**：
1. 打开 **云壳 → 防护记录 → 域名拦截**
2. 找到被拦截的域名，点击右侧按钮申请加白
3. 加白后重新运行即可

**症状**：`SSLError: certificate verify failed: self-signed certificate in certificate chain`，或 403 返回"网站不在安全策略默认允许的范围内"。抓取到的文件内容是"域名拦截"HTML 页面而非真实数据。

> 如果主 API（kuai）不可用，`extract_models_llm.py` 会自动 fallback 到备选 API（DashScope）。但 `review_models.py`（GPT-5.5 审核）目前没有 fallback，需确保主 API 可达。

### 总表功能

在 `data/` 下放置 `Models.xlsx`（全量模型总表）即可启用总表功能。

**行为**：每次流水线运行（步骤 7）时，自动将新增模型增量合并到总表。去重标准：`name.strip().lower().replace('-','').replace('_','').replace(' ','')`。

**不放 Models.xlsx** = 不启用总表功能，不影响流水线正常运行。

### 阶段 A：自动采集

**数据源 1：llm-stats.com**（排行榜抓取，4 个页面）

| 页面 | URL | 说明 |
|------|-----|------|
| AI Leaderboard 首页 | `https://llm-stats.com` | LLM / Image / Video / TTS / STT / Embeddings 全量排行 |
| LLM Leaderboard | `https://llm-stats.com/leaderboards/llm-leaderboard` | LLM 详情（参数量 / benchmark / index） |
| Open LLM Leaderboard | `https://llm-stats.com/leaderboards/open-llm-leaderboard` | 仅开源模型 |
| LLM Updates | `https://llm-stats.com/llm-updates` | 模型更新时间线 |

抓取后由 `Crawl/Arena_x/extract_llmstats_json.py` 解析 Next.js RSC 数据，输出 `llmstats_models.json`。

**数据源 2：腾讯研究院 AI 速递**（Selenium 爬虫 → LLM 提取模型）

**数据源 3：HuggingFace API**（交叉校验开源模型）

运行 `python main.py --since YYYYMMDD --until YYYYMMDD`，自动完成：

1. 从 `Object-Models-Old.xlsx` 复制基线（冷启动时自动创建空基线）
2. `auto_collect.py`：llmstats HTTP 直连（4 页面）+ 腾讯研究院 Selenium 爬虫 + HuggingFace API 校验
3. `Extract/extract_models_llm.py`（可选）：LLM 从文章全文提取模型
4. `review_models.py`：GPT-5.5 审核（名称规范性 + 旧模型检测 + 字段补全 + 重要性评级）
5. `Test/check_result.py`：数据检查
6. `Report/generate_report.py`：报告生成
7. `Crawl/Arena_x/format_cases.py`：Case 格式化
8. 表格对比 + 验收报告
9. `push_dingtalk.py`：钉钉推送（需 `--push` 参数）

### 阶段 B：AI 创作校验（你的核心任务）

在对话中完成以下步骤：

1. **读取文章全文**：`Extract/articles/` 下的 TXT 文件
2. **提取新模型信息**：模型名称、公司、类型等
3. **生成语义化备注**：web search + AI 知识综合，分号分隔
4. **核实发布时间**：web search 交叉验证，不可只用未验证数据
5. **补全缺失字段**：公司/类型/开闭源/尺寸/官网等
6. **去重**：标准化后对比 `s.strip().lower().replace('-','').replace('_','').replace(' ','')`
7. **写入 Excel**：需用户确认，提醒关闭已打开的 Excel

### 阶段 C：推送与验收

1. 数据质量检查（公司 100%、备注 100%、发布时间 100%）
2. 钉钉日报推送
3. 人工终判

---

## 操作规范

### 读写规范

| 操作 | 规范 |
|------|------|
| 读取 Excel | 必须用 `pd.read_excel()` 读取，不要凭记忆猜测 |
| 写入 Excel | 运行前提醒用户关闭 Excel |
| 去重 | 填入前必须与已有模型对比 |
| "是否新增"列 | 新写入一律用 `New`，不是"是"或 True |

### 备注风格

语义化标签式，分号分隔，中文为主、技术术语保留英文。

示例：
- `MoE架构；1T参数；262k上下文；GPQA 90.5%；$0.95/4；MIT (modified)`
- `视频生成；成本减半；Lite版本`
- `开源Agent；内置学习循环`

备注和发布时间是 L2 任务，**必须 web search + AI 知识综合**，禁止模板批量生成。

### 数据质量标准

进入推送前必须达到：

| 字段 | 目标 |
|------|------|
| 公司 | 100% |
| 备注 | 100%（AI 创作质量） |
| 发布时间 | 100%（web search 交叉验证） |

---

## ⚠️ 时效性校验机制（三重校验，强制执行）

**核心原则："被报道" ≠ "当天发布"**

腾讯研究院 AI 速递是新闻汇编，一篇 04-27 的速递可能报道过去一周内发布的模型。因此 LLM 从文章中提取的模型，**不能直接假定其发布日期等于文章日期**。必须经过三层校验。

### 第一层：LLM 提取时 Prompt 约束

`extract_models_llm.py` 的 Prompt 必须强调：
- 从文章正文中找到明确的发布时间锚点（"X月X日发布"、"昨日上线"、"今天宣布"等）
- **如果找不到明确发布时间，`release_date` 留空**，不要用文章日期填充
- 输出字段增加 `release_date_source`：标注日期来源是"文中明确提及"还是"推断"

### 第二层：自动化交叉核实（代码层）

LLM 提取完成后，`extract_models_llm.py` 或 `review_models.py` 自动执行：

1. **llmstats 交叉核实**（已有）：匹配 llmstats JSON 中的发布日期
2. **时间窗口过滤**（已有）：剔除发布日期明确在 `since-until` 窗口外的模型
3. **无日期模型标记**：`release_date` 为空的模型标记为"待人工确认"，不自动写入主表

### 第三层：AI 对话中 Web Search 验证（人机协作层，必须执行）

**在钉钉推送前**，AI 必须对每个新增模型执行 `web_search`，验证：

1. 该模型的**实际发布日期**是否在时间窗口内
2. 如果 Web Search 确认发布日期在窗口外 → **剔除该模型**
3. 如果 Web Search 无法确认 → 标记为"低置信"，提醒用户人工判断

```
校验流程：
LLM提取 → llmstats交叉核实 → 时间窗口过滤 → Web Search验证 → 人工终判 → 推送
                                                    ↑
                                              这一步之前经常被跳过！
                                              必须在推送前完成！
```

### 校验结果处理

| 场景 | 处理 |
|------|------|
| Web Search 确认在窗口内 | ✅ 保留，更新 `模型发布时间` 为 Web Search 确认的实际日期 |
| Web Search 确认在窗口外 | ✅ 保留模型，**修正 `模型发布时间` 为实际日期**，`记录创建时间` 保留报道日期 |
| Web Search 无法确认 | ⚠️ 标记"低置信"，保留但在日报中注明"发布时间待确认" |
| 多个来源日期不一致 | 取最早的官方发布日期（官网 > 新闻稿 > 社区讨论） |

### 双时间线机制

Excel 中维护两条独立时间线：

| 列 | 含义 | 示例 |
|----|------|------|
| `模型发布时间` | 模型的**实际发布日期**（Web Search 验证后） | 2026-04-23 |
| `记录创建时间` | 模型被**报道/录入的日期** | 2026-04-29 |

`push_dingtalk.py` 的 `load_models()` 会同时检查两列：只要任一日期落在 `--since ~ --until` 窗口内，该模型就纳入日报。这样确保：
- 按报道日期推送日报时，能包含当天报道但更早发布的模型
- 按发布日期查询时，能追溯到模型的真实发布时间

### 教训案例

2026-04-29 日报推送了 6 个模型，Web Search 事后验证发现其中 4 个（Vision Banana 04-22、StepAudio 2.5 ASR 04-24、uAI Nexus MedVLM 04-24、GPT Image 2 04-21）**实际发布日期都早于 04-27**，只有 HappyHorse 1.0 和 GenFlow 4.0 是真正在 04-27 发布的。根因：腾讯研究院速递汇编了过去一周的模型发布，LLM 提取时未区分"被报道"和"当天发布"。

---

## 常见陷阱

1. **不要假设 Excel 内容** — 必须先 `pd.read_excel()` 读取
2. **不要在 Excel 被占用时写入** — 提醒用户关闭
3. **区分"已做"和"可做"** — 严禁把"可以核实"说成"已核实"
4. **备注和发布时间是 L2 任务** — 不要用模板规则替代 AI 创作
5. **sub agent 统计需二次验证** — 用磁盘数据核实
6. **`str.format()` 含 JSON 时花括号须转义** — `{}` → `{{}}`
7. **脚本创建后必须立即运行** — 不要假设"创建=已执行"
8. **模型名可能含隐藏换行符** — 写入前 `replace('\n',' ').strip()`
9. **多源写入同一张表时先对齐字段规范** — 关键字段取值必须统一
10. **PowerShell 不支持 `&&`** — 用 `;` 分隔；复杂 Python 逻辑写临时 `_*.py` 脚本
11. **"被报道" ≠ "当天发布"** — 腾讯研究院速递是汇编，文章日期不等于模型发布日期；推送前必须 Web Search 逐个验证

---

## 执行环境与进度输出规范

### ⚠️ IDE Shell 有 300 秒硬限制（前台/后台均适用）

IDE 的 shell 工具有 **300 秒不可修改的硬限制**（前台和后台模式均受限）。这是平台层面的约束，代码无法绕过。

### 执行策略：拆步执行

**禁止一次性跑全流水线**。必须按以下方式拆步：

```
# ✅ 正确：拆步执行，每步 < 4 分钟
shell("cd D:\yuwang\action; python -X utf8 main.py --step 1 --since ... --until ... --force")  # 步骤1 ~10s
# 步骤 2 含爬虫，通常超时 → 提示用户手动在终端执行，或跳过依赖缓存
shell("cd D:\yuwang\action; python -X utf8 main.py --step 3 --since ... --until ...")  # 步骤3 ~30s
# ... 逐步执行其余步骤

# ❌ 错误：一次跑全流水线
shell("cd D:\yuwang\action; python -X utf8 main.py --since ... --until ... --push --force")
```

### 步骤 2 特殊处理

步骤 2（auto_collect.py）含 Selenium 爬虫，通常 5-20 分钟，必超 IDE 300 秒限制。处理策略：

1. **如果 JSON 缓存已存在**（`TXresearch/articles_SINCE-UNTIL.json`）→ 步骤 2 会自动使用缓存，可在 IDE 中执行
2. **如果需要爬虫** → 告知用户在独立终端（PowerShell/CMD）手动运行：
   ```
   cd D:\yuwang\action; python -X utf8 auto_collect.py --since YYYYMMDD --until YYYYMMDD
   ```
3. **阶段 B（AI 创作校验）不依赖步骤 2** → 可直接读取 `Extract/articles/` 下的 TXT 文件在对话中完成

### 心跳探测机制

所有子进程调用统一使用 `run_subprocess_heartbeat()` 函数：

- **30 分钟上限**：超时自动终止
- **每 60 秒心跳**：检查子进程是否存活
- **5 分钟静默 = 不健康**：超过 300 秒无输出则判定为卡死并终止
- **实时输出**：子进程的 stdout 实时转发到终端/日志

### 长耗时步骤提醒

执行前主动告知用户哪些步骤耗时较长：

| 步骤 | 预估耗时 | 超时上限 |
|------|----------|----------|
| 步骤 2（腾讯研究院爬虫） | 5-20 分钟 | 30 分钟 |
| 步骤 2.5（LLM 提取） | 每篇 30-60 秒 | 每篇 10 分钟 |
| 步骤 2.7（GPT-5.5 审核） | 2-5 分钟 | 10 分钟 |
| 步骤 9（钉钉推送） | < 30 秒 | 5 分钟 |
| 其他步骤 | < 30 秒 | 30 分钟（默认） |

### 超时配置

| 组件 | 超时模式 | 位置 |
|------|----------|------|
| main.py 所有子进程 | 心跳探测（30min/60s/300s静默） | `run_subprocess_heartbeat()` |
| Selenium 爬虫（auto_collect 内部） | 心跳探测（30min/60s/300s静默） | `auto_collect.py` Popen 循环 |
| LLM API 请求 | HTTP 超时 300 秒 | `extract_models_llm.py` |
| GPT-5.5 审核请求 | HTTP 超时 180 秒 | `review_models.py` |
| 钉钉推送 | HTTP 超时 15 秒 | `push_dingtalk.py` |

### 执行失败处理

- 爬虫超时/卡死 → 心跳探测自动终止，检查已有文章缓存 `TXresearch/articles_*.json`
- LLM 提取失败 → 记录失败篇数，不阻塞流水线
- 任何步骤失败 → 终端输出恢复提示：`修复问题后，可用 --step N 从失败步骤重新开始`

### `--log` 参数

```bash
python main.py --since YYYYMMDD --until YYYYMMDD --push --force --log pipeline.log
```

所有输出同时写入终端 + 指定日志文件，适用于后台运行时 AI 轮询监控。

---

## 命令速查

```bash
# 全流水线
python main.py --since YYYYMMDD --until YYYYMMDD

# 含推送
python main.py --since YYYYMMDD --until YYYYMMDD --push

# 单独推送（预览加 --dry-run）
python push_dingtalk.py --since YYYYMMDD --until YYYYMMDD

# 模型审核
python review_models.py

# LLM 提取
cd Extract; python extract_models_llm.py --since YYYYMMDD --until YYYYMMDD
```

---

## GPT-5.5 模型审核详情

`review_models.py` 对新增模型执行四项任务：

1. **模型名称规范性审核**：检测产品泛称（无版本号），标记 `should_remove`
2. **旧模型检测**：2024 年或更早的模型
3. **缺失字段补全**：尺寸/发布时间/官网（高置信度自动应用，低置信度写入核实列）
4. **重要性评级**：高/中/低 + 理由，输出格式 `[重要性:高|理由文本]`

三层过滤：Prompt 指令层 + 代码黑名单层 + GPT-5.5 审核层。
