---
name: model-navigate
description: "AI 模型导航与追踪系统（Model Navigate）。全自动化 AI 模型追踪流水线，覆盖采集→提取→校验→审核→推送全链路。当用户需要追踪最新 AI 模型发布动态、自动采集 llmstats.com / 腾讯研究院 / HuggingFace 的模型信息、用 LLM 从文章中提取模型数据、用 GPT-5.5 审核模型质量和重要性评级、生成钉钉日报并推送、批量补全模型字段（公司/尺寸/官网/发布时间/备注）时使用。触发关键词：模型追踪、模型导航、AI 模型采集、日报推送、模型审核、模型补全、llmstats、腾讯研究院。"
---

# Model Navigate — AI 操作手册

本文档是给 AI 的操作手册。项目说明和安装指南请见 `README.md`。

---

## 项目定位

Skill 工作目录为本文件所在目录。核心入口是 `main.py`，运行时需要 `.env` 配置 API Key。

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

### 阶段 A：自动采集

运行 `python main.py --since YYYYMMDD --until YYYYMMDD`，自动完成：

1. 从 `Object-Models-Old.xlsx` 复制基线
2. `auto_collect.py`：llmstats HTTP 直连 + 腾讯研究院 Selenium 爬虫 + HuggingFace API 校验
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
