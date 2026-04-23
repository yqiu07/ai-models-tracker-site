# AI 模型/智能体追踪器 v0.2

> 从 llm-stats.com 排行榜、腾讯研究院、ZeroEval Arena API、RSS 等 4 大渠道并发抓取 AI 模型数据，经 LLM 14 字段富化，产出 Excel 增量 + HTML/Markdown 日报。可选推送钉钉。

## 一句话说明

在 Aone Agent 中说 **"跑一下模型追踪"** 或在命令行执行 `python tracker.py -v`，自动完成：

1. 从 4 个数据源并发抓取最新模型/智能体信息
2. 与历史 Excel 全库去重，识别真正新增的实体
3. LLM 双槽位富化：14 列字段分类 + 多源软信息浓缩成一句话备注
4. 增量更新 Excel + 生成 HTML/Markdown 日报
5. **可选**：钉钉群推送 ActionCard（需加 `--notify`）

---

## 数据源（4 个，按优先级排序）

| 优先级 | 数据源 | 类型 | 实现文件 | 说明 |
|--------|--------|------|---------|------|
| **P0** | llm-stats.com | 排行榜 | `tracker/sources/llmstats.py` | HTTP GET 4 个页面 HTML → 解析 Next.js RSC 内嵌数据，291+ LLM 模型 |
| **P0** | 腾讯研究院 | 文章 | `tracker/sources/txresearch.py` | 搜狐号 odin AJAX API（懒加载页面，直接调 API 绕过），默认 3 页 60 篇 |
| **P1** | ZeroEval Arena | API | `tracker/sources/zeroeval.py` | 多模态排行榜（图像/视频/音频生成、STT/TTS） |
| **P1** | RSS 订阅 | RSS | `tracker/sources/rss.py` | 8 个 AI 领域 RSS 源（OpenAI、Google AI、机器之心等） |

---

## 快速开始

```powershell
cd D:\yuwang\action\models-tracker

# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制环境变量模板并填入真实 Key
Copy-Item .env.example .env
notepad .env

# 3. 检查环境
python tracker.py --check

# 4. 试跑（不消耗 LLM API 的纯抓取阶段）
python tracker.py --stage fetch -v

# 5. 完整干跑（预览，不写真实文件）
python tracker.py --dry-run -v

# 6. 正式运行（不推送钉钉）
python tracker.py -v

# 7. 正式运行 + 推送钉钉
python tracker.py -v --notify
```

---

## CLI 参数完整表

| 参数 | 说明 | 示例 |
|------|------|------|
| (无) | 默认完整流水线，时间窗口 = `[last_published_at, now]` | `python tracker.py` |
| `--stage {fetch,diff,enrich,publish,notify}` | 只跑指定阶段 | `--stage fetch` |
| `--resume` | 与 `--stage` 配合，从上一阶段最近 checkpoint 续跑 | `--stage publish --resume` |
| `--dry-run` | 不写真实 Excel、不推送钉钉、不更新 state | `--dry-run` |
| `--notify` | 启用钉钉推送（**默认不推送**，必须显式加） | `--notify` |
| `--since YYYY-MM-DD` | 时间窗口起点 | `--since 2026-04-15` |
| `--until YYYY-MM-DD` | 时间窗口终点 | `--until 2026-04-20` |
| `--output-format {html,markdown,both}` | 日报输出格式 | `--output-format both` |
| `--check` | 仅检查环境与数据源健康 | `--check` |
| `-v, --verbose` | 详细日志 | `-v` |

---

## 输出文件说明

### 不推送钉钉时（默认）

运行 `python tracker.py -v` 后产出：

| 文件 | 路径 | 说明 |
|------|------|------|
| **HTML 日报** | `docs/daily/2026-04-23.html` | 卡片式日报，可在浏览器打开 |
| **Markdown 日报** | `docs/markdown/2026-04-23.md` | Hugo 兼容格式（需 `--output-format markdown` 或 `both`） |
| **Excel 增量** | `data/Object-Models-Updated.xlsx` | 14 列结构化数据，新增行追加到 Sheet2 |
| **日报归档** | `docs/index.html` | 所有日报的索引页 |
| **状态更新** | `state/last_published.json` | 时间戳 + 已发布指纹库 |
| **阶段 checkpoint** | `state/checkpoints/fetch-*.json` 等 | 每阶段的中间产物，支持断点续跑 |

### dry-run 模式

运行 `python tracker.py --dry-run -v` 后产出：

| 文件 | 路径 | 说明 |
|------|------|------|
| **预览 Excel** | `data/_dryrun_Object-Models-Updated.xlsx` | 带 `_dryrun_` 前缀，不覆盖正式文件 |
| **预览 HTML** | `docs/daily/2026-04-23.html` | 仍然生成，供预览 |
| 不更新 | `state/last_published.json` | **不更新**，不污染增量基线 |

### 推送钉钉时

运行 `python tracker.py -v --notify` 后，除上述产出外，还会：

| 推送内容 | 格式 | 说明 |
|---------|------|------|
| **ActionCard 消息** | 钉钉 Markdown | 新增模型列表 + 日报链接 + HMAC-SHA256 签名 |
| 推送目标 | 钉钉群 Webhook | 配置在 `.env` 的 `DINGTALK_WEBHOOK` + `DINGTALK_SECRET` |

---

## 常用操作速查

```powershell
# 🔍 只抓数据看看（不消耗 LLM API）
python tracker.py --stage fetch -v

# 👀 完整预览（消耗 API 但不写正式文件）
python tracker.py --dry-run -v

# ▶️ 正式运行
python tracker.py -v

# 📤 正式运行 + 推送钉钉
python tracker.py -v --notify

# 📅 查特定日期范围
python tracker.py --since 2026-04-15 --until 2026-04-20 -v

# 📄 生成 Hugo 格式日报
python tracker.py -v --output-format both

# 🔄 从 enrich 阶段续跑（跳过 fetch + diff）
python tracker.py --stage enrich --resume -v

# 🔄 重新生成日报（跳过 fetch + diff + enrich）
python tracker.py --stage publish --resume -v

# 📤 重新推送钉钉
python tracker.py --stage notify --resume -v --notify

# ❤️ 健康检查
python tracker.py --check
```

---

## 5 阶段 Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: FETCH（并发抓取 4 个数据源）                       │
│  llm-stats.com → 腾讯研究院 → ZeroEval API → RSS           │
│  → checkpoint: fetch-{timestamp}.json                       │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: DIFF（去重 + 增量筛选）                            │
│  指纹去重 normalize(公司)::normalize(模型名)                 │
│  与历史 Excel 对比，筛出新增/更新                            │
│  → checkpoint: diff-{timestamp}.json                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: ENRICH（LLM 双槽位富化）                           │
│  FIELD 槽位：14 字段分类（便宜模型，高并发）                  │
│  NOTE 槽位：备注浓缩（强推理模型，低频）                     │
│  → checkpoint: enrich-{timestamp}.json                      │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: PUBLISH（生成产物）                                │
│  Excel 增量写入 + HTML 卡片日报 + Markdown 日报              │
│  → docs/daily/*.html + data/*.xlsx + docs/markdown/*.md     │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 5: NOTIFY（可选，需 --notify）                        │
│  推送到钉钉（ActionCard 格式 + HMAC-SHA256 签名）           │
└─────────────────────────────────────────────────────────────┘
```

每阶段独立 checkpoint，支持 `--stage X --resume` 断点续跑。

---

## 14 列输出 schema

严格对齐 `D:\yuwang\action\Object-Models-Updated - only.xlsx` Sheet2：

| # | 列 | 来源 | 说明 |
|---|----|------|------|
| 1 | 模型名称 | 数据源原值 | |
| 2 | 是否新增 | diff 阶段 | 与历史 Excel 对比 |
| 3 | workflow编排拓展 | LLM 🤖 | |
| 4 | 公司 | 数据源 + LLM 兜底 | |
| 5 | 国内外 | LLM 🤖 | |
| 6 | 来源 | LLM 🤖 | 开源/闭源/集成产品 |
| 7 | 尺寸 | LLM 🤖 | 参数量 |
| 8 | 类型 | LLM 🤖 | 语言/多模态/图像/视频/音频 |
| 9 | 能否思考 | LLM 🤖 | thinking/non-thinking |
| 10 | 类型2 | LLM 🤖 | 工具调用/任务规划 |
| 11 | 链接 | evidence 最权威 URL | |
| 12 | 备注 | LLM 🤖 | 多源信息浓缩一句话 |
| 13 | 模型发布时间 | evidence 最早时间 | |
| 14 | 收录日期 | 当日 | |

> 🤖 标注的列由 LLM 分类，需余网在 Excel 中复核。

---

## 环境变量配置

| 变量 | 必填 | 说明 |
|------|------|------|
| `TRACKER_FIELD_API_KEY` | ✅ | LLM API Key（字段分类槽位） |
| `TRACKER_FIELD_API_BASE` | ✅ | LLM API Base URL |
| `TRACKER_FIELD_MODEL` | ✅ | 字段分类模型（推荐便宜的） |
| `TRACKER_NOTE_MODEL` | 可选 | 备注浓缩模型（推荐强推理的，默认复用 FIELD） |
| `DINGTALK_WEBHOOK` | 可选 | 钉钉群 Webhook URL |
| `DINGTALK_SECRET` | 可选 | 钉钉群签名密钥 |
| `TRACKER_PROXY` | 可选 | 显式代理（如 `http://127.0.0.1:13658`） |
| `TRACKER_SKIP_SSL_VERIFY` | 可选 | 跳过 SSL 验证（`true`/`false`） |

---

## 项目结构

```
models-tracker/
├── tracker.py                  # CLI 入口 + Pipeline 编排
├── SKILL.md                    # Skill 封装（自然语言意图路由）
├── tracker/                    # 核心包
│   ├── ai.py                   # LLM 双槽位 + 代理检测 + 403 智能判断
│   ├── fetch.py                # Stage 1：调度 4 个数据源
│   ├── diff.py                 # Stage 2：去重 + 时间窗口
│   ├── enrich.py               # Stage 3：LLM 14 字段填充
│   ├── publish.py              # Stage 4：HTML + Excel + Markdown
│   ├── notify.py               # Stage 5：钉钉推送
│   ├── persistence.py          # checkpoint + state 读写
│   ├── fingerprint.py          # 模型指纹规范化
│   ├── schema.py               # 14 列 schema 定义
│   └── sources/                # 数据源适配器
│       ├── llmstats.py         # P0：llm-stats.com 排行榜
│       ├── txresearch.py       # P0：腾讯研究院搜狐号
│       ├── zeroeval.py         # P1：ZeroEval Arena API
│       └── rss.py              # P1：RSS 订阅源
├── config/
│   ├── ai-feeds.opml           # RSS 订阅源配置
│   └── prompts/                # LLM prompt 模板
├── data/                       # 数据产出
│   └── Object-Models-Updated.xlsx
├── docs/                       # 日报产出
│   ├── index.html              # 归档列表
│   ├── daily/                  # HTML 日报
│   └── markdown/               # Markdown 日报
├── state/                      # 状态管理
│   ├── last_published.json     # 增量基线
│   └── checkpoints/            # 阶段 checkpoint
├── site/                       # Hugo 站点（GitHub Pages）
│   ├── hugo.yaml
│   └── content/cn/
├── scripts/
│   └── validate_env.py         # 环境检查脚本
├── .env.example                # 环境变量模板
├── requirements.txt            # Python 依赖
└── README.md                   # 本文件
```

---

## 与 news-digest 的关系

本项目**架构对标** `D:\yuwang\action\news-digest-0.1.0\`，复用了：
- 钉钉签名 + Markdown 渲染逻辑
- LLM 双槽位思想（高频便宜 + 高推理最强）
- checkpoint 断点续跑机制
- RSS OPML 解析与并发抓取
- SKILL.md 封装规范（自然语言意图路由）

但**追踪单位不同**：news-digest 追新闻文章，models-tracker 追模型/智能体实体。

---

## GitHub 仓库

- **仓库**：`https://github.com/yqiu07/ai-models-tracker-site`
- **GitHub Actions**：
  - `Daily Tracker Run`：每天 UTC 22:00（北京时间 06:00）自动运行，支持手动触发
  - `Deploy Hugo site to Pages`：tracker 完成后自动部署 Hugo 站点

---

## 版本历史

### v0.2（当前）
- ✅ 4 数据源并发：llm-stats.com + 腾讯研究院 + ZeroEval + RSS
- ✅ 钉钉推送改为可选（`--notify`）
- ✅ SKILL.md 完整封装（自然语言交互）
- ✅ 搜狐号 odin AJAX API 适配（绕过懒加载）
- ✅ 通用代理检测 + 403 智能判断
- ✅ Markdown 输出格式 + Hugo 站点

### v0.1（M1）
- ✅ 5 阶段流水线（fetch/diff/enrich/publish/notify）
- ✅ ZeroEval API + RSS 双数据源
- ✅ 模型指纹去重 + 14 列 schema
- ✅ HTML 卡片日报 + Excel 增量
- ✅ 钉钉 ActionCard 推送
- ✅ CLI 时间窗口查询 + dry-run

---

## 会话续接 Prompt

下次和 AI 继续工作时，发送以下 prompt 即可恢复上下文：

```
我们在做 AI 模型追踪器项目（D:\yuwang\action\models-tracker）。
当前版本 v0.2，4 数据源（llmstats/txresearch/zeroeval/rss）并发抓取，
5 阶段 Pipeline（fetch→diff→enrich→publish→notify），
钉钉推送需 --notify 显式启用。
请先读取 SKILL.md 和 README.md 恢复完整上下文，然后我们继续。
```
