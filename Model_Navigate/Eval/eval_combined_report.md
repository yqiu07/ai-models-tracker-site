# 合并评估报告

> 生成时间：2026-05-09 14:34

## 数据源概况

| 数据源 | 模型数 |
|--------|--------|
| 金标 | 116 |
| llmstats 流水线 | 41 |
| 腾讯研究院 LLM 提取 | 168 |
| 合并去重 | 189 |

## 覆盖率对比

| 数据源 | 精确匹配 | 模糊匹配 |
|--------|----------|----------|
| llmstats 单源 | 18/116 (15.5%) | 26/116 (22.4%) |
| 腾讯研究院单源 | 39/116 (33.6%) | 52/116 (44.8%) |
| **合并双源** | **45/116 (38.8%)** | **60/116 (51.7%)** |

## 交叉覆盖分析

| 覆盖情况 | 数量 |
|----------|------|
| 仅 llmstats | 8 |
| 仅腾讯研究院 | 34 |
| 两者都覆盖 | 18 |
| 两者都未覆盖 | 56 |

## 仅腾讯研究院覆盖的金标模型

- ABot-M0
- Abot-N0
- Ace-Step 1.5
- AutoClaw
- Baichuan-M3
- Emu3.5
- FireRed-Image-Edit-1.0
- FireRed-Image-Edit-1.1
- gemini-embedding-2-preview
- Genie 3
- GLM-OCR
- GPT 5.3-instant
- HY-1.8B-2Bit
- Intern-S1-Pro
- LabClaw
- lingbot-world-base-cam
- miclaw
- Ming-flash-omni-2.0
- MiniMax M2.1
- MiniMax Music 2.5
- MiniMax Music 2.5+
- MiroThinker-1.7
- Nano Banana 2/Gemini 3.1 Flash Image
- Protenix-v1
- Qwen3-Coder-Next
- qwen3-max-thinking
- Qwen-Image-2.0
- Seedance 2.0 Pro
- Seedream 5.0
- SkyReels-V3-A2V-19B
- Skyreels V4
- Solaris
- UniFolM-VLA-0
- Xiaomi-Robotics-0 series

## 两者都未覆盖的金标模型 (56)

- ArkClaw
- autoresearch
- Desktop App
- dola-seed-2.0-preview
- doubao-seed1.8
- doubao-seed-2.0
- DuMeta+DuClaw+RedClaw
- Fun-CosyVoice3-0.5B-2512
- Grok Imagine Image Pro
- K-EXAONE-236B-A23B
- Kling 3.0 series (video, image, etc.,)
- MiroThinker-H3
- PaperBanana
- qwen2.5-0.5b-instruct
- qwen2.5-0.5b-instruct-no-guard
- qwen2.5-14b-instruct
- qwen2.5-14b-instruct-1m
- qwen2.5-14b-instruct-1m-no-guard
- qwen2.5-1.5b-instruct
- qwen2.5-1.5b-instruct-no-guard
- qwen2.5-3b-instruct
- qwen2.5-3b-instruct-no-guard
- qwen2.5-7b-instruct
- qwen2.5-7b-instruct-1m
- qwen2.5-omni-7b
- qwen3-0.6b
- qwen3-1.7b
- qwen3-235b-a22b-instruct-2507
- qwen3-235b-a22b-thinking-2507
- qwen3-30b-a3b
- qwen3-30b-a3b-instruct-2507
- qwen3-30b-a3b-thinking-2507
- qwen3-4b
- qwen3-8b
- qwen3-max-preview
- qwen3-next-80b-a3b-instruct
- qwen3-next-80b-a3b-thinking
- qwen3-omni-flash
- qwen-flash
- qwen-flash-no-guard
- qwen-long
- qwen-long-no-guard
- qwen-plus
- qwen-plus-character-no-guard
- qwen-plus-no-guard
- qwen-turbo
- qwq-32b
- qwq-plus
- SkillHub
- stormcast-v1-era5-hrrr
- Tabbit
- UniScientist-30B-A3B
- WorkBuddy
- X2
- 大圣
- 悟空
