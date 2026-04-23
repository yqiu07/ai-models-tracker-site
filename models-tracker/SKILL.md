---
name: ai-models-tracker
description: >
  AI 模型/智能体追踪 Pipeline。从 llm-stats.com 排行榜、腾讯研究院搜狐号、
  ZeroEval Arena API、RSS 订阅等多渠道抓取模型数据，经 LLM 14 字段富化，
  产出 Excel 增量 + Markdown/HTML 日报。可选推送钉钉。
  当用户提到 "跑一下模型追踪"、"今天有什么新模型"、"查 X 月到 Y 月发布的模型"、
  "试跑一下"、"推送到钉钉"、"检查数据源" 时使用此技能。
version: 0.2.0
author: yinpan
category: ai-tracking
tags: [ai, models, tracker, leaderboard, llmstats, zeroeval, rss, dingtalk]
---

# AI 模型/智能体追踪器

从 llm-stats.com、腾讯研究院、ZeroEval Arena、RSS 等多渠道抓取 AI 模型数据，经 LLM 富化后产出结构化日报。

> 4 大数据源并发抓取，LLM 双槽位（字段分类 + 备注浓缩），支持 Excel 增量 + Markdown/HTML 日报 + 可选钉钉推送。

## 数据源（优先级排序）

| 优先级 | 数据源 | 类型 | 说明 |
|--------|--------|------|------|
| **P0** | llm-stats.com | 排行榜 | 4 个页面 HTML 解析，291+ LLM 模型 |
| **P0** | 腾讯研究院 | 文章 | 搜狐号主页文章列表 |
| **P1** | ZeroEval Arena | API | 多模态排行榜（图像/视频/音频） |
| **P1** | RSS 订阅 | RSS | 8 个 AI 领域 RSS 源 |

---

## 安全规则

- **严禁**泄露 `.env` 中的 API Key / Secret
- **严禁**未经用户确认执行 `--notify`（推送钉钉）
- **严禁**跳过阶段顺序直接运行下游阶段（除非上游 checkpoint 已存在）

---

## 意图路由

| 用户说 | 类型 | Agent 操作 | 额外提示 |
|--------|------|-----------|---------|
| "跑一下" / "今天有什么新模型" | 运行 | `python tracker.py -v` | 💡 加 `--notify` 可推送钉钉 |
| "跑一下并推送钉钉" | 运行 | `python tracker.py -v --notify` | |
| "查 X 月 X 日到 Y 月 Y 日" | 查询 | `python tracker.py --since YYYY-MM-DD --until YYYY-MM-DD -v` | 💡 加 `--notify` 可推送结果 |
| "试跑一下" / "先看看" | 预览 | `python tracker.py --dry-run -v` | 💡 不会写文件、不推送 |
| "只抓数据" | 阶段 | `python tracker.py --stage fetch -v` | 💡 不消耗 LLM API |
| "重新生成日报" | 阶段 | `python tracker.py --stage publish --resume -v` | 💡 加 `--output-format markdown` 可生成 Hugo 格式 |
| "推送到钉钉" | 阶段 | `python tracker.py --stage notify --resume -v --notify` | ⚠️ 需用户确认 |
| "检查环境" / "源是否健康" | 检查 | `python tracker.py --check` | |
| "帮我配置" / "初始化" | 引导 | 进入引导式配置 | |
| "看看历史日报" | 查看 | 打开 `docs/index.html` 或 Hugo 站点 | |

### 每次运行后的主动提示

Agent 在运行命令后，应根据实际情况提示用户：
- 未加 `--notify` → 提示："加 `--notify` 可以推送到钉钉"
- 未加 `--output-format markdown` → 提示："加 `--output-format markdown` 可生成 Hugo 站点格式"
- 使用了 `--dry-run` → 提示："去掉 `--dry-run` 后将写入真实 Excel 并更新状态"
- 使用了 `--since/--until` → 提示："时间窗口模式不会更新增量基线"

---

## 快速开始

```bash
# 1. 配置环境变量
Copy-Item .env.example .env
# 编辑 .env，填入 TRACKER_FIELD_API_KEY 等

# 2. 安装依赖
pip install -r requirements.txt

# 3. 检查环境
python tracker.py --check

# 4. 试跑（不消耗 API 的抓取阶段）
python tracker.py --stage fetch -v

# 5. 完整运行（不推送钉钉）
python tracker.py -v

# 6. 完整运行 + 推送钉钉
python tracker.py -v --notify
```

如果你更喜欢对话式，告诉我"帮我配置"即可。

---

## 引导式配置

共 5 步，每步独立，支持从任意步骤开始。

```
Step 1           Step 2            Step 3          Step 4          Step 5
选定数据源  →  配置 LLM API  →  检查环境    →  试跑          → 配置钉钉
(OPML/源)      (Field+Note)      (--check)     (--dry-run)     (可选 --notify)
```

### Step 1：选定数据源
- 默认启用全部 4 个数据源（llmstats + txresearch + zeroeval + rss）
- RSS 源通过 `config/ai-feeds.opml` 配置
- 无需额外配置，开箱即用

### Step 2：配置 LLM API
- 必填：`TRACKER_FIELD_API_KEY` + `TRACKER_FIELD_API_BASE` + `TRACKER_FIELD_MODEL`
- 可选：`TRACKER_NOTE_MODEL`（备注浓缩用更强的模型，默认复用 FIELD 模型）

### Step 3：检查环境
```bash
python tracker.py --check
```

### Step 4：试跑
```bash
python tracker.py --dry-run -v
```

### Step 5：配置钉钉推送（可选）
- 填入 `DINGTALK_WEBHOOK` + `DINGTALK_SECRET`
- 运行时加 `--notify` 才推送

---

## Pipeline 架构

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: FETCH（并发抓取 4 个数据源）                       │
│  llm-stats.com → ZeroEval API → 腾讯研究院 → RSS           │
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

---

## 完整参数表

| 参数 | 说明 | 示例 |
|------|------|------|
| `--stage {fetch,diff,enrich,publish,notify}` | 仅运行指定阶段 | `--stage fetch` |
| `--resume` | 从上一次 checkpoint 恢复 | `--stage publish --resume` |
| `--dry-run` | 预览模式，不写文件 | `--dry-run` |
| `--notify` | 启用钉钉推送（默认不推送） | `--notify` |
| `--since YYYY-MM-DD` | 时间窗口起点 | `--since 2026-04-15` |
| `--until YYYY-MM-DD` | 时间窗口终点 | `--until 2026-04-20` |
| `--output-format {html,markdown,both}` | 日报格式 | `--output-format both` |
| `--check` | 检查环境与数据源健康 | `--check` |
| `-v, --verbose` | 详细日志 | `-v` |

---

## 重要约束

- **钉钉推送默认关闭**：必须显式加 `--notify` 才推送，防止误发
- **dry-run 默认行为**：不写真实 Excel、不推送钉钉、不更新 state，但仍会生成预览文件
- **状态自动管理**：默认增量模式成功后会更新 `state/last_published.json`
- **时间窗口不更新状态**：`--since/--until` 是查询行为，不污染增量基线
- **失败降级**：单个数据源失败不中断整个流水线
- **AI 字段标 🤖**：`国内外/来源/类型/能否思考/类型2` 由 LLM 分类，需余网在 Excel 中复核
