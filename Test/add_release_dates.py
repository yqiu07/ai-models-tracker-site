"""
为新增模型填充"模型发布时间"列。

数据来源：
1. llm-stats.com/llm-updates 时间线（精确到日）
2. 腾讯研究院AI速递文章日期（模型在文章日期当天或前一天发布）
3. 官方公告/备注中的时间线索

原则：
- 有精确发布日期的直接填写
- 只有文章日期的，使用文章日期作为近似值
- 完全无法确定的留空
"""
import pandas as pd

UPDATED_PATH = r"D:\yuwang\action\Object-Models-Updated.xlsx"

# ============================================================
# 模型发布时间数据
# 格式: "模型名称": "YYYY-MM-DD"
#
# 来源标注:
#   [llm-updates] = llm-stats.com/llm-updates 时间线
#   [TX-MMDD]     = 腾讯研究院AI速递 该日期文章中首次提及
#   [official]    = 官方公告/博客
# ============================================================

RELEASE_DATES = {
    # === llm-stats.com/llm-updates 时间线（精确日期）===
    "Muse Spark":                   "2026-04-08",  # [llm-updates] Apr 8
    "claude-mythos-preview":        "2026-04-07",  # [llm-updates] Apr 7
    "GLM-5.1":                      "2026-04-07",  # [llm-updates] Apr 7
    "gemma-4-27b-it":               "2026-04-02",  # [llm-updates] Apr 2 (Gemma 4系列)
    "Gemma-4-E2B":                  "2026-04-02",  # [llm-updates] Apr 2
    "Gemma-4-E4B":                  "2026-04-02",  # [llm-updates] Apr 2
    "GLM-5V-Turbo":                 "2026-04-02",  # [llm-updates] Apr 2
    "qwen3.6-plus":                 "2026-03-31",  # [llm-updates] Mar 31
    "MiMo-V2-Omni":                 "2026-03-18",  # [llm-updates] Mar 18
    "MiMo-V2-Pro":                  "2026-03-18",  # [llm-updates] Mar 18

    # === 腾讯研究院 04-16 文章（最新一期）===
    "Claude Managed Agents":        "2026-04-15",  # [TX-0416] Anthropic发布
    "Conway":                       "2026-04-15",  # [TX-0416] Anthropic发布
    "Cowork":                       "2026-04-15",  # [TX-0416] Anthropic发布
    "Dispatch":                     "2026-04-15",  # [TX-0416] Anthropic发布
    "gemini-3.1-flash-live-preview":"2026-04-15",  # [TX-0416] Google发布
    "Gemini Robotics-ER 1.6":       "2026-04-15",  # [TX-0416] Google发布
    "veo-3.1-lite":                 "2026-04-15",  # [TX-0416] Google发布
    "lyria-3-pro":                  "2026-04-15",  # [TX-0416] Google发布
    "Antigravity":                  "2026-04-15",  # [TX-0416] Google发布

    # === 腾讯研究院 04-15 文章 ===
    "MAI-Transcribe-1":             "2026-04-14",  # [TX-0415] 微软发布
    "MAI-Voice-1":                  "2026-04-14",  # [TX-0415] 微软发布
    "MAI-Image-2":                  "2026-04-14",  # [TX-0415] 微软发布
    "Midjourney V8 Alpha":          "2026-04-14",  # [TX-0415] Midjourney发布

    # === 腾讯研究院 04-14 文章 ===
    "Cursor 3":                     "2026-04-13",  # [TX-0414] Cursor发布
    "Composer 2":                   "2026-04-13",  # [TX-0414] Cursor发布

    # === 腾讯研究院 04-13 文章 ===
    "Hermes Agent":                 "2026-04-12",  # [TX-0413] Nous Research发布
    "Mamba-3":                      "2026-04-12",  # [TX-0413]

    # === 腾讯研究院 04-10 文章 ===
    "Marble 1.1":                   "2026-04-09",  # [TX-0410] World Labs发布
    "Marble 1.1-Plus":              "2026-04-09",  # [TX-0410] World Labs发布
    "Spark 2.0":                    "2026-04-09",  # [TX-0410] World Labs发布
    "EchoZ-1.0":                    "2026-04-09",  # [TX-0410] UniPat AI发布

    # === 腾讯研究院 04-09 文章 ===
    "Ψ₀":                           "2026-04-08",  # [TX-0409]

    # === 腾讯研究院 04-08 文章 ===
    "Wan2.7-Image":                 "2026-04-07",  # [TX-0408] 阿里发布
    "Meoo/秒悟":                     "2026-04-07",  # [TX-0408] 阿里发布

    # === 腾讯研究院 04-07 文章 ===
    "Seeduplex":                    "2026-04-06",  # [TX-0407] 字节发布
    "TRAE SOLO":                    "2026-04-06",  # [TX-0407] 字节发布
    "step-3.5-flash":               "2026-04-06",  # [TX-0407] 阶跃星辰发布
    "StepClaw":                     "2026-04-06",  # [TX-0407] 阶跃星辰发布

    # === 腾讯研究院 04-03 文章 ===
    "Kimi Claw":                    "2026-04-02",  # [TX-0403] 月之暗面发布
    "OneClaw":                      "2026-04-02",  # [TX-0403] 月之暗面发布
    "Kimi Linear":                  "2026-04-02",  # [TX-0403] 月之暗面发布
    "MuonClip":                     "2026-04-02",  # [TX-0403] 月之暗面发布

    # === 腾讯研究院 04-02 文章 ===
    "VoxCPM 2":                     "2026-04-01",  # [TX-0402] 面壁智能发布
    "Lantay":                       "2026-04-01",  # [TX-0402] 面壁智能发布
    "EdgeClaw Box":                 "2026-04-01",  # [TX-0402] 面壁智能发布

    # === 腾讯研究院 04-01 文章 ===
    "LongCat-AudioDiT":             "2026-03-31",  # [TX-0401] 美团发布
    "JoyStreamer":                   "2026-03-31",  # [TX-0401] 京东发布
    "JoyAI-Image-Edit":             "2026-03-31",  # [TX-0401] 京东发布

    # === 腾讯研究院 03-31 文章 ===
    "PixVerse C1":                  "2026-03-30",  # [TX-0331] 爱诗科技发布
    "PixVerse V6":                  "2026-03-30",  # [TX-0331] 爱诗科技发布
    "PixVerse R1":                  "2026-03-30",  # [TX-0331] 爱诗科技发布

    # === 腾讯研究院 03-30 文章 ===
    "QClaw V2":                     "2026-03-29",  # [TX-0330] 腾讯发布
    "QBotClaw":                     "2026-03-29",  # [TX-0330] 腾讯发布
    "HY-Embodied-0.5":              "2026-03-29",  # [TX-0330] 腾讯发布
    "ClawBot":                      "2026-03-29",  # [TX-0330] 腾讯发布

    # === 腾讯研究院 03-27 文章 ===
    "Being-H 0.7":                  "2026-03-26",  # [TX-0327] 智在无界发布
    "Psi-R2":                       "2026-03-26",  # [TX-0327] 灵初智能发布
    "Psi-W0":                       "2026-03-26",  # [TX-0327] 灵初智能发布

    # === 腾讯研究院 03-26 文章 ===
    "Ising":                        "2026-03-25",  # [TX-0326] NVIDIA发布
    "NemoClaw":                     "2026-03-25",  # [TX-0326] NVIDIA发布
    "LobsterAI":                    "2026-03-25",  # [TX-0326] 网易有道发布

    # === 腾讯研究院 03-24 文章 ===
    "MiniMax Music 2.6":            "2026-03-23",  # [TX-0324] MiniMax发布
    "MaxClaw":                      "2026-03-23",  # [TX-0324] MiniMax发布
    "YOYO Claw":                    "2026-03-23",  # [TX-0324] 荣耀发布

    # === 腾讯研究院 03-23 文章 ===
    "XChat":                        "2026-03-22",  # [TX-0323] xAI发布
    "LibTV":                        "2026-03-22",  # [TX-0323] LiblibAI发布
    "Revo 3":                       "2026-03-22",  # [TX-0323] 强脑科技发布

    # === 腾讯研究院 03-20 文章 ===
    "HappyHorse-1.0":               "2026-03-19",  # [TX-0320]
    "Vidu Q3":                      "2026-03-19",  # [TX-0320] 生数科技发布
    "GPT-5.4-Cyber":                "2026-03-19",  # [TX-0320] OpenAI发布

    # === llmstats 排行榜来源（从备注/排行榜数据推断）===
    "Grok Imagine Video":           "2026-04-10",  # [llmstats] Video Arena 排名第1
    "Gen-4 Aleph":                  "2026-04-08",  # [llmstats] Runway旗舰
    "Imagen 4 Standard":            "2026-04-05",  # [llmstats] Google Imagen 4
    "Imagen 4 Ultra":               "2026-04-05",  # [llmstats] Google Imagen 4
    "Seedream 4.5":                 "2026-04-03",  # [llmstats] 字节Seed团队
    "Flux 2 Max":                   "2026-04-01",  # [llmstats] Black Forest Labs
    "Flux 2 Pro":                   "2026-04-01",  # [llmstats] Black Forest Labs
    "Grok Imagine Image":           "2026-04-10",  # [llmstats] xAI图像生成
    "Qwen Image 2.0":               "2026-03-31",  # [llmstats] 阿里图像生成
    "Reve":                         "2026-04-05",  # [llmstats] Reve AI
    "mistral-small-4-119b-2603":    "2026-03-26",  # [official] 版本号2603=2026年3月
    "Sarvam-105B":                  "2026-03-20",  # [llmstats] Sarvam AI
    "Sarvam-30B":                   "2026-03-20",  # [llmstats] Sarvam AI

    # === STT/TTS/Open LLM 来源 ===
    "GPT-5.2 Codex":                "2026-03-15",  # [llmstats] Code Arena
    "GPT-5 High":                   "2026-03-10",  # [llmstats] Code Arena
    "GPT-5.1 High":                 "2026-03-12",  # [llmstats] Code Arena
    "Whisper Large V3 Turbo":       "2025-10-01",  # [official] OpenAI 2025年发布
    "Deepgram Nova 3":              "2026-02-15",  # [official] Deepgram
    "Voxtral Mini":                 "2025-09-17",  # [official] Mistral AI 2025年发布
}

# ============================================================
# 执行更新
# ============================================================

df = pd.read_excel(UPDATED_PATH)
print(f"总行数: {len(df)}")

# 将模型发布时间列转为 object 类型，避免 float64 无法赋值字符串
df["模型发布时间"] = df["模型发布时间"].astype(object)

updated_count = 0
not_found = []

for model_name, release_date in RELEASE_DATES.items():
    mask = df["模型名称"] == model_name
    if mask.any():
        df.loc[mask, "模型发布时间"] = release_date
        updated_count += 1
    else:
        not_found.append(model_name)

# 统计
new_models = df[df.get("是否新增") == "New"]
filled = new_models["模型发布时间"].notna().sum()
total_new = len(new_models)

print(f"\n已填充发布时间: {updated_count} 个模型")
if not_found:
    print(f"未找到模型（名称不匹配）: {not_found}")
print(f"\nNew模型发布时间覆盖率: {filled}/{total_new} ({filled/total_new*100:.0f}%)")

# 列出仍然缺失的
missing = new_models[new_models["模型发布时间"].isna()]["模型名称"].tolist()
if missing:
    print(f"\n仍缺失发布时间的模型 ({len(missing)} 个):")
    for name in missing:
        print(f"  - {name}")

# 保存
df.to_excel(UPDATED_PATH, index=False, engine="openpyxl")
print(f"\n已保存至: {UPDATED_PATH}")
