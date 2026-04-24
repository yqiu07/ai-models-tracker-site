# Arena_x — llm-stats.com 数据采集与结构化

> 从 [llm-stats.com](https://llm-stats.com) 多个导航页自动提取 AI 模型排行榜数据，输出结构化 JSON 和 Markdown 排行榜。

## 数据全景

llm-stats.com 的导航结构与数据关系：

```
llm-stats.com 数据全景
├─ A) LLM 排行榜（HTML 内嵌 Next.js RSC 数据）
│   ├── AI Leaderboard (首页) ─── 291 个 LLM 模型 ← 同一份数据
│   ├── LLM Leaderboard ──────── 291 个 LLM 模型 ← 同一份数据（更多字段）
│   ├── Open LLM Leaderboard ─── 291 个 LLM 模型 ← 同一份数据（前端默认筛选开源）
│   └── LLM Updates ──────────── 50 个近期发布模型 ← 子集（时间线视角）
│
└─ B) 多模态排行榜（ZeroEval Arena API 动态加载）
    ├── Image Generation ─── text-to-image (34) + image-to-image (32) = 44 去重
    ├── Video Generation ─── text-to-video (29) + image-to-video (71) = 100 条目
    ├── Text-to-Speech ──── 23 个模型
    ├── Speech-to-Text ──── 11 个模型
    └── Embeddings ──────── 暂无数据（API 返回空数组）
```

### 关键架构发现

1. **AI/LLM/Open LLM 三页共享同一份数据集**，只是展示列和默认筛选不同
2. **Image/Video/TTS/STT 等多模态数据不在 HTML 源码中**，而是通过 [ZeroEval Arena API](https://api.zeroeval.com) 动态加载
3. **API 模式统一**: `https://api.zeroeval.com/magia/arenas/{category}/leaderboard?limit=100&offset=0`
4. **Embeddings 使用不同 API**: `/leaderboard/models?output_modalities=vector`（目前返回空数组）

## 文件说明

### 核心脚本

| 文件 | 说明 |
|------|------|
| `extract_llmstats_json.py` | **自动提取** — 从 HTML 源码提取 LLM 数据 + 从 API 响应提取多模态数据，合并输出 JSON + Markdown |
| `format_cases.py` | 将手动复制的 Case 文件整理为标准 Markdown 表格 |

### 自动生成的输出

| 文件 | 说明 |
|------|------|
| `llmstats_models.json` | LLM 模型数据（291 个模型 × 50+ 字段） |
| `llmstats_leaderboard_auto.md` | LLM 排行榜（近期新发 + 开源 Top20 + 公司统计） |
| `llmstats_multimodal.json` | 多模态模型数据（200 个模型条目 × Arena 评分字段） |
| `llmstats_multimodal_auto.md` | 多模态排行榜（Image/Video/TTS/STT 按 ELO Rating 排名） |
| `formatted_leaderboards.md` | 手动 Case 文件的整理版 |

### 数据源文件

#### A) HTML 源码（LLM 排行榜）

| 文件 | 页面 | 数据 key | 大小 |
|------|------|---------|------|
| `llm-stats-ai.com` | AI Leaderboard 首页 | `initialHomepageLLMModels` | ~242 KB |
| `llm-stats-LLM.com` | LLM Leaderboard 详情 | `initialData` | ~1.2 MB |
| `llm-stats-open-llm.com` | Open LLM Leaderboard | `initialData` | ~1.2 MB |
| `llm-stats-updates.com` | LLM Updates 时间线 | `recentUpdates` | ~465 KB |

#### B) ZeroEval API 响应（多模态排行榜）

| 文件 | 类别 | 模型数 | API 端点 |
|------|------|--------|----------|
| `api_text_to_image.network-response` | Image Gen (文生图) | 34 | `magia/arenas/text-to-image/leaderboard` |
| `api_image_to_image.network-response` | Image Gen (图编辑) | 32 | `magia/arenas/image-to-image/leaderboard` |
| `api_text_to_video.network-response` | Video Gen (文生视频) | 29 | `magia/arenas/text-to-video/leaderboard` |
| `api_image_to_video.network-response` | Video Gen (图转视频) | 71 | `magia/arenas/image-to-video/leaderboard` |
| `api_text_to_speech.network-response` | TTS | 23 | `magia/arenas/text-to-speech/leaderboard` |
| `api_speech_to_text.network-response` | STT | 11 | `magia/arenas/speech-to-text/leaderboard` |
| `api_embeddings.network-response` | Embeddings | 0 | `leaderboard/models?output_modalities=vector` |

> **如何获取 API 数据**: 在浏览器中打开 llm-stats.com → 依次点击 Image Generation / Video Generation / TTS / STT / Embeddings 导航标签 → 使用 DevTools Network 面板截获 `api.zeroeval.com` 的 XHR 请求 → 保存响应 JSON 到对应文件

### 手动采集的 Case 文件

| 文件 | 内容 |
|------|------|
| `Case-llmstats-LLM Leaderboards.md` | LLM 排行榜手动复制 |
| `Case-llmstats-AI leaderboards-image generation.md` | 图像生成排行榜 |
| `Case-llmstats-AI leaderboards video generation.md` | 视频生成排行榜 |
| `Case-llmstats-AI leaderboards STT.md` | 语音识别排行榜 |
| `Case-llmstats-AI leaderboards TTS.md` | 语音合成排行榜 |
| `LLM-updates-byllmstats.md` | 手动复制的更新时间线 |
| `Open LLM Leaderboard.md` | 开源模型排行榜（待完善） |

## 使用方式

### 一键提取

```bash
python extract_llmstats_json.py
```

脚本会自动：
1. **Phase 1-2**: 从 4 个 HTML 源码提取 LLM 数据 → `llmstats_models.json` + `llmstats_leaderboard_auto.md`
2. **Phase 3-4**: 从 7 个 API 响应文件提取多模态数据 → `llmstats_multimodal.json` + `llmstats_multimodal_auto.md`

### 数据流

```
A) HTML 源码 (4个页面)                    B) API 响应 (7个文件)
  ↓ Phase 1: 提取 Next.js RSC              ↓ Phase 3: 解析 JSON
  ↓ Phase 2: 合并去重                      ↓ Phase 4: 分类汇总
  ↓                                        ↓
llmstats_models.json                    llmstats_multimodal.json
  ↓                                        ↓
llmstats_leaderboard_auto.md            llmstats_multimodal_auto.md
  ↓                                        ↓
  └──────────────→ action/main.py 流水线 ←──┘
```

## 合并策略

### LLM 排行榜

| 优先级 | 页面 | 字段丰富度 | 独有字段 |
|--------|------|-----------|---------|
| 1 | LLM Leaderboard | ★★★★★ | params, training_tokens, multimodal, license, is_moe, 20+ benchmark, index_* |
| 2 | AI Leaderboard | ★★★ | is_open_source (布尔值) |
| 3 | Open LLM | ★★★★★ | 同 LLM 页 |
| 4 | LLM Updates | ★★ | description, source_paper, source_api_ref (目前全部为空) |

### 多模态排行榜

ZeroEval Arena API 的每个模型条目包含以下核心字段：

| 字段 | 说明 |
|------|------|
| `model_id` / `model_name` | 模型标识 |
| `organization` | 开发公司 |
| `mu` / `sigma` | ELO 评分的均值/标准差 |
| `conservative_rating` | 保守评分（= μ - 3σ） |
| `matches_played` / `wins` / `win_rate` | Arena 对战统计 |
| `avg_generation_price` | 单次生成平均价格 |
| `license` / `is_open_source` | 授权信息 |

## 待办

- [ ] 完善 `Open LLM Leaderboard.md` 内容
- [ ] 探索 ZeroEval API 其他端点，获取更多数据维度
