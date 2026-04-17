"""
从llmstats数据文件中提取模型列表，与Object-Models-Updated.xlsx对比，
找出未追踪的新模型。
"""
import pandas as pd
import re

# 加载已有模型
df = pd.read_excel(r"D:\yuwang\action\Object-Models-Updated.xlsx")
existing_names = set()
for name in df["模型名称"].dropna():
    existing_names.add(str(name).lower().strip())

print(f"已有模型数量: {len(existing_names)}")

# ============================================================
# 从llmstats文件中提取的所有模型（AI阅读后整理）
# ============================================================

# --- Video Generation Leaderboard ---
video_models = [
    ("Grok Imagine Video", "xAI", "闭源", None, "文生视频", "$0.05/s"),
    ("Veo 3.1", "Google", "闭源", None, "文生视频", "$0.40/s"),  # 已有veo-3.1-lite
    ("Sora 2 Pro", "OpenAI", "闭源", None, "文生视频", "$0.30/s"),
    ("WAN Video 2.6", "阿里", "闭源", None, "文生视频", "$0.05/s"),
    ("Sora 2", "OpenAI", "闭源", None, "文生视频", "$0.10/s"),
    ("Veo 3.0", "Google", "闭源", None, "文生视频", "$0.40/s"),
    ("Veo 2.0", "Google", "闭源", None, "文生视频", "$0.30/s"),
    ("Hailuo 02", "MiniMax", "闭源", None, "文生视频", "$0.08/s"),
    ("Gen-4 Aleph", "Runway", "闭源", None, "文生视频", None),
    ("Veo 3.1 Fast", "Google", "闭源", None, "文生视频", "$0.15/s"),
    ("Kling v2.5 Turbo Pro", "快手", "闭源", None, "文生视频", "$0.07/s"),
    ("Kling v2.6 Pro", "快手", "闭源", None, "文生视频", "$0.10/s"),
    ("WAN Video 2.5", "阿里", "闭源", None, "文生视频", None),
    ("WAN Video 2.6 I2V", "阿里", "闭源", None, "文生视频", "$0.05/s"),
    ("SeeDance 1 Pro", "字节", "闭源", None, "文生视频", "$0.06/s"),
    ("SeeDance 1 Lite", "字节", "闭源", None, "文生视频", "$0.04/s"),
    ("Hailuo 2.3", "MiniMax", "闭源", None, "文生视频", "$0.10/s"),
    ("Kling v2.1 Master", "快手", "闭源", None, "文生视频", "$0.07/s"),
    ("SeeDance 1 Pro Fast", "字节", "闭源", None, "文生视频", "$0.03/s"),
]

# --- Image Generation Leaderboard ---
image_models = [
    ("GPT Image 1.5", "OpenAI", "闭源", None, "图片编辑", "$0.05/img"),
    ("Gemini 3.1 Flash Image", "Google", "闭源", None, "图片编辑", "$0.02/img"),
    ("Gemini 3 Pro Image", "Google", "闭源", None, "图片编辑", "$0.13/img"),
    ("Gemini 2.5 Flash Image", "Google", "闭源", None, "图片编辑", "$0.04/img"),
    ("Grok Imagine Image", "xAI", "闭源", None, "图片编辑", "$0.02/img"),
    ("Imagen 4 Standard", "Google", "闭源", None, "图片编辑", "$0.05/img"),
    ("Seedream 4.5", "字节", "闭源", None, "图片编辑", "$0.04/img"),
    ("Flux 2 Max", "Black Forest Labs", "闭源", None, "图片编辑", "$0.06/img"),
    ("Flux 2 Pro", "Black Forest Labs", "闭源", None, "图片编辑", "$0.02/img"),
    ("Flux 2 Flex", "Black Forest Labs", "闭源", None, "图片编辑", "$0.06/img"),
    ("Imagen 4 Ultra", "Google", "闭源", None, "图片编辑", "$0.10/img"),
    ("Qwen Image 2.0", "阿里", "闭源", None, "图片编辑", "$0.03/img"),
    ("GPT Image 1 Mini", "OpenAI", "闭源", None, "图片编辑", "$0.01/img"),
    ("GPT Image 1", "OpenAI", "闭源", None, "图片编辑", "$0.04/img"),
    ("Grok Imagine Image Pro", "xAI", "闭源", None, "图片编辑", "$0.07/img"),
    ("Reve", "Reve AI", "闭源", None, "图片编辑", "$0.18/img"),
    ("Seedream 4", "字节", "闭源", None, "图片编辑", "$0.03/img"),
    ("Flux Kontext Max", "Black Forest Labs", "闭源", None, "图片编辑", "$0.08/img"),
    ("Flux 1.1 Pro Ultra", "Black Forest Labs", "闭源", None, "图片编辑", "$0.06/img"),
    ("Seedream 3", "字节", "闭源", None, "图片编辑", "$0.03/img"),
]

# --- LLM Leaderboard (从文件中提取的新模型，已有的跳过) ---
llm_models = [
    # 已在Updated中的跳过: Muse Spark, GLM-5.1, Gemma 4系列, GLM-5V-Turbo,
    # Qwen3.6 Plus, MiMo-V2-Pro, MiniMax M2.7, GPT-5.4 mini/nano, step-3.5-flash
    ("MiMo-V2-Omni", "小米", "闭源", "262k上下文", "任意模态", "小米全模态Agent基座"),
    ("Mistral Small 4", "Mistral AI", "开源", "119B; 256k上下文", "基座", "法国；多语言"),
    ("Nemotron 3 Super", "NVIDIA", "开源", "120B-A12B; 262.1k上下文", "基座", "MoE架构"),
    ("Grok-4.20 Beta", "xAI", "闭源", "2M上下文", "基座", "Non-Reasoning/Reasoning/Multi-Agent三模式"),
    ("Sarvam-105B", "Sarvam AI", "开源", "105B", "基座", "印度；GPQA 96.7%"),
    ("Sarvam-30B", "Sarvam AI", "开源", "30B", "基座", "印度；GPQA 96.7%"),
    ("GPT-5.3 Chat", "OpenAI", "闭源", "128k上下文", "基座", None),
    ("Gemini 3.1 Flash-Lite", "Google", "闭源", "1M上下文", "基座", "轻量版"),
    ("Mercury 2", "Inception", "闭源", "128k上下文; 1020 tok/s", "基座", "阿联酋；超快推理速度"),
    ("Qwen3.5-122B-A10B", "阿里", "开源", "122B-A10B; 262.1k上下文", "基座", "MoE架构"),
]


def normalize(name):
    return name.lower().strip().replace("-", "").replace("_", "").replace(" ", "")


def is_tracked(model_name):
    n = normalize(model_name)
    for existing in existing_names:
        e = normalize(existing)
        if n == e:
            return True
        # 模糊匹配：核心名称包含
        if len(n) > 5 and len(e) > 5:
            if n in e or e in n:
                return True
    return False


# 手动标记已追踪的（名称不同但实际已追踪）
ALREADY_TRACKED = {
    normalize(n) for n in [
        "Veo 3.1",        # veo-3.1-lite 已追踪
        "Veo 3.0",        # Veo 3 系列已追踪
        "Veo 2.0",        # 旧版
        "Veo 3.1 Fast",   # 同系列
        "Veo 3.0 Fast",   # 同系列
        "Sora 2",         # Sora 2 系列
        "Sora 2 Pro",     # Sora 2 系列
        "WAN Video 2.5",  # 旧版
        "WAN Video 2.6",  # Wan2.6 已追踪
        "WAN Video 2.6 I2V",
        "Kling v2.5 Turbo Pro",  # Kling 系列已追踪
        "Kling v2.6 Pro",
        "Kling v2.1 Master",
        "SeeDance 1 Pro",  # Seedance 已追踪
        "SeeDance 1 Lite",
        "SeeDance 1 Pro Fast",
        "Hailuo 2.3",     # Hailuo/海螺 已追踪
        "Hailuo 02",
        "GPT Image 1.5",  # GPT Image 系列
        "GPT Image 1",
        "GPT Image 1 Mini",
        "Gemini 3.1 Flash Image",  # Gemini 系列
        "Gemini 3 Pro Image",
        "Gemini 2.5 Flash Image",
        "Flux 1.1 Pro Ultra",  # Flux 旧版
        "Seedream 3",     # 旧版
        "Seedream 4",     # 旧版
        "Qwen3.5-122B-A10B",  # Qwen3.5系列已追踪
        "GPT-5.3 Chat",   # GPT-5.3 已追踪
    ]
}


print("\n" + "=" * 80)
print("未追踪的新模型（来自llmstats）")
print("=" * 80)

new_models = []

for source, models in [("Video Gen", video_models), ("Image Gen", image_models)]:
    for name, company, oc, size, task, price in models:
        n = normalize(name)
        if n in ALREADY_TRACKED:
            continue
        if is_tracked(name):
            continue
        new_models.append({
            "name": name,
            "company": company,
            "oc": oc,
            "size": size,
            "task": task,
            "price": price,
            "source": source,
        })

for name, company, oc, size_ctx, model_type, note in llm_models:
    n = normalize(name)
    if n in ALREADY_TRACKED:
        continue
    if is_tracked(name):
        continue
    new_models.append({
        "name": name,
        "company": company,
        "oc": oc,
        "size": size_ctx,
        "task": model_type,
        "price": None,
        "source": "LLM",
        "note": note,
    })

# 去重
seen = set()
unique = []
for m in new_models:
    key = normalize(m["name"])
    if key not in seen:
        seen.add(key)
        unique.append(m)

for i, m in enumerate(unique, 1):
    price_info = f" | {m['price']}" if m.get('price') else ""
    note_info = f" | {m.get('note', '')}" if m.get('note') else ""
    print(f"  {i:2d}. [{m['source']:<9s}] {m['name']:<30s} | {m['company']:<18s} | {m['oc']:<6s} | {m.get('size') or '-'}{price_info}{note_info}")

print(f"\n共发现 {len(unique)} 个未追踪的新模型")
