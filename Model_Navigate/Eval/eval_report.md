# 流水线验收评估报告

> **评估时间**: 2026-05-09 12:01
> **金标文件**: gold_standard.xlsx (116 条)
> **流水线产出**: pipeline_llmstats.xlsx (41 条)
> **金标时间段**: 2026/01/01 ~ 2026/03/30
> **数据源**: llm-stats.com (4 个页面)

## 一、模型名称覆盖率 (Recall)

| 指标 | 数值 |
|------|------|
| 金标模型数 | 116 |
| 流水线采集数 | 41 |
| **匹配成功** | **23** |
| 未匹配（金标遗漏） | 93 |
| 流水线独有（金标未收录） | 18 |
| **覆盖率** | **19.8%** |

### 匹配成功的模型

| # | 金标名称 | 流水线名称 | 名称一致 |
|---|---------|-----------|---------|
| 1 | GLM-4.7-Flash | GLM-4.7-Flash | ✅ |
| 2 | GLM-5 | GLM-5 | ✅ |
| 3 | GPT-5.3-Codex-Spark | GPT-5.3 Codex | ⚠️ |
| 4 | GPT-5.4 | GPT-5.4 | ✅ |
| 5 | Gemini 3.1 Flash-Lite | Gemini 3.1 Flash-Lite | ✅ |
| 6 | Gemini 3.1 pro | Gemini 3.1 Pro | ⚠️ |
| 7 | Grok 4.20 Beta | Grok-4.20 Beta Non-Reasoning | ⚠️ |
| 8 | LongCat-Flash-Thinking-2601 | LongCat-Flash-Thinking-2601 | ✅ |
| 9 | Mercury 2 | Mercury 2 | ✅ |
| 10 | MiniMax M2.5 | MiniMax M2.5 | ✅ |
| 11 | Nemotron 3 Super | Nemotron 3 Super (120B A12B) | ⚠️ |
| 12 | claude-opus-4-6 | Claude Opus 4.6 | ⚠️ |
| 13 | claude-sonnet-4-6 | Claude Sonnet 4.6 | ⚠️ |
| 14 | ernie-5.0-0110 | ERNIE 5.0 | ⚠️ |
| 15 | kimi-k2.5-thinking | Kimi K2.5 | ⚠️ |
| 16 | qwen3.5-0.8B | Qwen3.5-0.8B | ⚠️ |
| 17 | qwen3.5-122b-a10b | Qwen3.5-122B-A10B | ⚠️ |
| 18 | qwen3.5-27b | Qwen3.5-27B | ⚠️ |
| 19 | qwen3.5-2B | Qwen3.5-2B | ⚠️ |
| 20 | qwen3.5-35b-a3b | Qwen3.5-35B-A3B | ⚠️ |
| 21 | qwen3.5-397b-a17b | Qwen3.5-397B-A17B | ⚠️ |
| 22 | qwen3.5-4B | Qwen3.5-4B | ⚠️ |
| 23 | qwen3.5-9B | Qwen3.5-9B | ⚠️ |

### 未匹配的金标模型（流水线遗漏）

| # | 模型名称 | 公司 | 国内外 | 类型 |
|---|---------|------|-------|------|
| 1 | ABot-M0 | 阿里 | 国内 | 领域 |
| 2 | Abot-N0 | 阿里 | 国内 | 领域 |
| 3 | Ace-Step 1.5 | ? | 国外 | 领域 |
| 4 | ArkClaw | 字节 | 国内 | 智能体 |
| 5 | AutoClaw | 智谱 | 国内 | 智能体 |
| 6 | Baichuan-M3 | 百度 | 国内 | 领域 |
| 7 | Desktop App | Meta | 国外 | 智能体 |
| 8 | DuMeta+DuClaw+RedClaw | 百度 | 国内 | 智能体 |
| 9 | ERNIE-5.0-Preview-1203 | 百度 | 国内 | 基座 |
| 10 | Emu3.5 | ? | 国内 | 多模态 |
| 11 | FireRed-Image-Edit-1.0 | ? | 国内 | 多模态 |
| 12 | FireRed-Image-Edit-1.1 | ? | 国内 | 多模态 |
| 13 | Fun-CosyVoice3-0.5B-2512 | 阿里 | 国内 | 领域 |
| 14 | GLM-5-Turbo | 智谱 | 国内 | 微调 |
| 15 | GLM-OCR | 智谱 | 国内 | 领域 |
| 16 | GPT 5.3-instant | Openai | 国外 | 基座 |
| 17 | Genie 3 | Google | 国外 | 多模态 |
| 18 | Grok Imagine Image Pro | xAI | 国外 | 多模态 |
| 19 | HY-1.8B-2Bit | ? | 国内 | 基座 |
| 20 | Intern-S1-Pro | ? | 国内 | 领域 |
| 21 | K-EXAONE-236B-A23B | 百度 | 国外 | 基座 |
| 22 | Kling 3.0 series (video, image, etc.,) | ? | 国内 | 多模态 |
| 23 | LabClaw | ? | 国外 | 智能体 |
| 24 | Ming-flash-omni-2.0 | ? | 国内 | 多模态 |
| 25 | MiniMax M2.1 | MiniMax | 国内 | 基座 |
| 26 | MiniMax Music 2.5 | MiniMax | 国内 | 多模态 |
| 27 | MiniMax Music 2.5+ | MiniMax | 国内 | 多模态 |
| 28 | MiroThinker-1.7 | ? | 国外 | 智能体 |
| 29 | MiroThinker-H3 | ? | 国外 | 智能体 |
| 30 | Nano Banana 2/Gemini 3.1 Flash Image | Google | 国外 | 多模态 |
| 31 | PaperBanana | Google | 国外 | 智能体 |
| 32 | Protenix-v1 | 字节 | 国内 | 领域 |
| 33 | Qwen-Image-2.0 | 阿里 | 国内 | 领域 |
| 34 | Qwen3-Coder-Next | 阿里 | 国内 | 领域 |
| 35 | Seedance 2.0 Pro | 字节 | 国内 | 领域 |
| 36 | Seedream 5.0 | 字节 | 国内 | 多模态 |
| 37 | SkillHub | 腾讯 | 国内 | 智能体 |
| 38 | SkyReels-V3-A2V-19B | ? | 国内 | 多模态 |
| 39 | Skyreels V4 | ? | 国内 | 多模态 |
| 40 | Solaris | ? | 国内 | 多模态 |
| 41 | Tabbit | 美团 | 国内 | 智能体 |
| 42 | UniFolM-VLA-0 | ? | 国内 | 领域 |
| 43 | UniScientist-30B-A3B | ? | 国外 | 领域 |
| 44 | WorkBuddy | ? | 国内 | 智能体 |
| 45 | X2 | 科大讯飞 | 国内 | 基座 |
| 46 | Xiaomi-Robotics-0 series | 小米 | 国内 | 领域 |
| 47 | autoresearch | ? | 国外 | 智能体 |
| 48 | claude-opus-4-6-thinking | Anthropic | 国外 | 基座 |
| 49 | dola-seed-2.0-preview | 字节 | 国内 | 基座 |
| 50 | doubao-seed-2.0 | 字节 | 国内 | 基座 |
| 51 | doubao-seed1.8 | 字节 | 国内 | 基座 |
| 52 | gemini-embedding-2-preview | Google | 国外 | 多模态 |
| 53 | lingbot-world-base-cam | ? | 国内 | 多模态 |
| 54 | miclaw | 小米 | 国内 | 智能体 |
| 55 | qwen-flash | 阿里 | 国内 | 基座 |
| 56 | qwen-flash-no-guard | 阿里 | 国内 | 基座 |
| 57 | qwen-long | 阿里 | 国内 | 基座 |
| 58 | qwen-long-no-guard | 阿里 | 国内 | 基座 |
| 59 | qwen-plus | 阿里 | 国内 | 基座 |
| 60 | qwen-plus-character-no-guard | 阿里 | 国内 | 领域 |
| 61 | qwen-plus-no-guard | 阿里 | 国内 | 领域 |
| 62 | qwen-turbo | 阿里 | 国内 | 基座 |
| 63 | qwen2.5-0.5b-instruct | 阿里 | 国内 | 微调 |
| 64 | qwen2.5-0.5b-instruct-no-guard | 阿里 | 国内 | 微调 |
| 65 | qwen2.5-1.5b-instruct | 阿里 | 国内 | 微调 |
| 66 | qwen2.5-1.5b-instruct-no-guard | 阿里 | 国内 | 微调 |
| 67 | qwen2.5-14b-instruct | 阿里 | 国内 | 微调 |
| 68 | qwen2.5-14b-instruct-1m | 阿里 | 国内 | 微调 |
| 69 | qwen2.5-14b-instruct-1m-no-guard | 阿里 | 国内 | 微调 |
| 70 | qwen2.5-3b-instruct | 阿里 | 国内 | 微调 |
| 71 | qwen2.5-3b-instruct-no-guard | 阿里 | 国内 | 微调 |
| 72 | qwen2.5-7b-instruct | 阿里 | 国内 | 微调 |
| 73 | qwen2.5-7b-instruct-1m | 阿里 | 国内 | 微调 |
| 74 | qwen2.5-omni-7b | 阿里 | 国内 | 基座 |
| 75 | qwen3-0.6b | 阿里 | 国内 | 基座 |
| 76 | qwen3-1.7b | 阿里 | 国内 | 基座 |
| 77 | qwen3-235b-a22b-instruct-2507 | 阿里 | 国内 | 微调 |
| 78 | qwen3-235b-a22b-thinking-2507 | 阿里 | 国内 | 微调 |
| 79 | qwen3-30b-a3b | 阿里 | 国内 | 基座 |
| 80 | qwen3-30b-a3b-instruct-2507 | 阿里 | 国内 | 微调 |
| 81 | qwen3-30b-a3b-thinking-2507 | 阿里 | 国内 | 微调 |
| 82 | qwen3-4b | 阿里 | 国内 | 基座 |
| 83 | qwen3-8b | 阿里 | 国内 | 基座 |
| 84 | qwen3-max-preview | 阿里 | 国内 | 基座 |
| 85 | qwen3-max-thinking | 阿里 | 国内 | 微调 |
| 86 | qwen3-next-80b-a3b-instruct | 阿里 | 国内 | 微调 |
| 87 | qwen3-next-80b-a3b-thinking | 阿里 | 国内 | 微调 |
| 88 | qwen3-omni-flash | 阿里 | 国内 | 领域 |
| 89 | qwq-32b | 阿里 | 国内 | 微调 |
| 90 | qwq-plus | 阿里 | 国内 | 微调 |
| 91 | stormcast-v1-era5-hrrr | ? | 国外 | 领域 |
| 92 | 大圣 | ? | 国内 | 领域 |
| 93 | 悟空 | 阿里 | 国内 | 智能体 |

### 流水线独有模型（金标未收录）

| # | 模型名称 | 公司 | 类型 |
|---|---------|------|------|
| 1 | GPT-5.2 Codex | OpenAI | 代码 |
| 2 | GPT-5.3 Chat | OpenAI | 多模态 |
| 3 | GPT-5.4 mini | OpenAI | 多模态 |
| 4 | GPT-5.4 nano | OpenAI | 多模态 |
| 5 | Grok-4.20 Beta Reasoning | xAI | 多模态 |
| 6 | Grok-4.20 Multi-Agent Beta | xAI | 多模态 |
| 7 | LongCat-Flash-Lite | Meituan | 基座 |
| 8 | MiMo-V2-Omni | Xiaomi | 多模态 |
| 9 | MiMo-V2-Pro | Xiaomi | 基座 |
| 10 | MiniCPM-SALA | OpenBMB | 基座 |
| 11 | MiniMax M2.7 | MiniMax | 基座 |
| 12 | Mistral Small 4 | Mistral AI | 多模态 |
| 13 | Sarvam-105B | Sarvam AI | 基座 |
| 14 | Sarvam-30B | Sarvam AI | 基座 |
| 15 | Seed 2.0 Lite | ByteDance | 多模态 |
| 16 | Seed 2.0 Pro | ByteDance | 多模态 |
| 17 | Step-3.5-Flash | StepFun | 基座 |
| 18 | Step3-VL-10B | StepFun | 多模态 |

## 二、逐字段准确率与补全能力

基于匹配成功的 **23** 个模型进行字段对比：

| 字段 | 双方都有 | 一致 | 不一致 | 准确率 | 金标独有 | 流水线补全 | 补全能力 |
|------|---------|------|--------|--------|---------|-----------|---------|
| 公司 | 21 | 21 | 0 | 100% | 0 | 2 | ✅ |
| 国内外 | 23 | 23 | 0 | 100% | 0 | 0 | — |
| 开闭源 | 23 | 23 | 0 | 100% | 0 | 0 | — |
| 尺寸 | 4 | 4 | 0 | 100% | 0 | 10 | ✅ |
| 类型 | 23 | 22 | 1 | 95% | 0 | 0 | — |
| 能否推理 | 22 | 21 | 1 | 95% | 0 | 1 | ✅ |
| 官网 | 4 | 0 | 0 | 0% | 0 | 19 | ✅ |
| 备注 | 9 | 0 | 0 | 0% | 0 | 14 | ✅ |
| 模型发布时间 | 0 | 0 | 0 | N/A | 0 | 23 | ✅ |

## 三、不一致项详情（待人工判定谁对谁错）

### 类型

| 模型 | 金标值 | 流水线值 | 判定 |
|------|--------|---------|------|
| Grok 4.20 Beta | 智能体 | 多模态 | 待定 |

### 能否推理

| 模型 | 金标值 | 流水线值 | 判定 |
|------|--------|---------|------|
| Grok 4.20 Beta | thinking | non-thinking | 待定 |

## 四、流水线补全能力（金标缺失，流水线补充）

### 公司（补全 2 项）

| 模型 | 流水线补全值 |
|------|-----------|
| Mercury 2 | Inception |
| Nemotron 3 Super | NVIDIA |

### 尺寸（补全 10 项）

| 模型 | 流水线补全值 |
|------|-----------|
| GLM-5 | 744B |
| MiniMax M2.5 | 230B |
| qwen3.5-0.8B | 800M |
| qwen3.5-2B | 2B |
| qwen3.5-4B | 4B |
| qwen3.5-9B | 9B |
| qwen3.5-27b | 27B |
| qwen3.5-35b-a3b | 35B |
| qwen3.5-122b-a10b | 122B |
| qwen3.5-397b-a17b | 397B |

### 能否推理（补全 1 项）

| 模型 | 流水线补全值 |
|------|-----------|
| claude-sonnet-4-6 | thinking |

### 官网（补全 19 项）

| 模型 | 流水线补全值 |
|------|-----------|
| claude-opus-4-6 | https://llm-stats.com/models/claude-opus-4-6 |
| claude-sonnet-4-6 | https://llm-stats.com/models/claude-sonnet-4-6 |
| ernie-5.0-0110 | https://llm-stats.com/models/ernie-5.0 |
| Gemini 3.1 pro | https://llm-stats.com/models/gemini-3.1-pro-preview |
| GLM-4.7-Flash | https://llm-stats.com/models/glm-4.7-flash |
| GLM-5 | https://llm-stats.com/models/glm-5 |
| GPT-5.3-Codex-Spark | https://llm-stats.com/models/gpt-5.3-codex |
| GPT-5.4 | https://llm-stats.com/models/gpt-5.4 |
| Grok 4.20 Beta | https://llm-stats.com/models/grok-4.20-beta-0309-non-reasoning |
| kimi-k2.5-thinking | https://llm-stats.com/models/kimi-k2.5 |
| LongCat-Flash-Thinking-2601 | https://llm-stats.com/models/longcat-flash-thinking-2601 |
| Mercury 2 | https://llm-stats.com/models/mercury-2 |
| qwen3.5-2B | https://llm-stats.com/models/qwen3.5-2b |
| qwen3.5-4B | https://llm-stats.com/models/qwen3.5-4b |
| qwen3.5-9B | https://llm-stats.com/models/qwen3.5-9b |
| qwen3.5-27b | https://llm-stats.com/models/qwen3.5-27b |
| qwen3.5-35b-a3b | https://llm-stats.com/models/qwen3.5-35b-a3b |
| qwen3.5-122b-a10b | https://llm-stats.com/models/qwen3.5-122b-a10b |
| qwen3.5-397b-a17b | https://llm-stats.com/models/qwen3.5-397b-a17b |

### 备注（补全 14 项）

| 模型 | 流水线补全值 |
|------|-----------|
| claude-opus-4-6 | 1000k上下文；顶级推理能力；顶级编码能力；高端定价 |
| ernie-5.0-0110 | 强推理能力 |
| Gemini 3.1 pro | 1048k上下文；顶级推理能力；顶级编码能力 |
| GLM-4.7-Flash | 128k上下文；强编码能力；低成本；MIT |
| GLM-5 | MoE架构；744B参数；200k上下文；顶级编码能力；MIT |
| GPT-5.3-Codex-Spark | 400k上下文 |
| GPT-5.4 | 1000k上下文；顶级推理能力 |
| kimi-k2.5-thinking | MoE架构；1T参数；262k上下文；强推理能力；顶级编码能力；MIT |
| LongCat-Flash-Thinking-2601 | MoE架构；560B参数；强推理能力；顶级编码能力；MIT |
| MiniMax M2.5 | MoE架构；230B参数；1000k上下文；顶级编码能力；MIT |
| qwen3.5-0.8B | Apache 2.0 |
| qwen3.5-2B | Apache 2.0 |
| qwen3.5-4B | Apache 2.0 |
| qwen3.5-9B | 强推理能力；Apache 2.0 |

### 模型发布时间（补全 23 项）

| 模型 | 流水线补全值 |
|------|-----------|
| claude-opus-4-6 | 2026-02-05 |
| claude-sonnet-4-6 | 2026-02-17 |
| ernie-5.0-0110 | 2026-01-22 |
| Gemini 3.1 Flash-Lite | 2026-03-03 |
| Gemini 3.1 pro | 2026-02-19 |
| GLM-4.7-Flash | 2026-01-19 |
| GLM-5 | 2026-02-11 |
| GPT-5.3-Codex-Spark | 2026-02-05 |
| GPT-5.4 | 2026-03-05 |
| Grok 4.20 Beta | 2026-03-09 |
| kimi-k2.5-thinking | 2026-01-27 |
| LongCat-Flash-Thinking-2601 | 2026-01-14 |
| Mercury 2 | 2026-02-24 |
| MiniMax M2.5 | 2026-02-12 |
| Nemotron 3 Super | 2026-03-11 |
| qwen3.5-0.8B | 2026-03-02 |
| qwen3.5-2B | 2026-03-02 |
| qwen3.5-4B | 2026-03-02 |
| qwen3.5-9B | 2026-03-02 |
| qwen3.5-27b | 2026-02-24 |
| qwen3.5-35b-a3b | 2026-02-24 |
| qwen3.5-122b-a10b | 2026-02-24 |
| qwen3.5-397b-a17b | 2026-02-16 |

## 五、总结

- **模型覆盖率**: 19.8% (23/116)
- **字段总准确率**: 88% (114/129)
- **补全数据项**: 69 项（金标缺失但流水线可补充）
- **不一致项**: 2 项（需人工判定）
- **金标遗漏模型**: 93 个
- **流水线独有模型**: 18 个
