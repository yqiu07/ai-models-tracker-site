"""
给Object-Models-Updated.xlsx的New模型加"核实情况"列，
基于实际执行的核实操作，而非建议。
同时用HuggingFace核实结果更新尺寸。
"""
import pandas as pd

df = pd.read_excel(r"D:\yuwang\action\Object-Models-Updated.xlsx")

# HuggingFace实际核实结果
HF_SUCCESS = {
    "mistral-small-4-119b-2603": {
        "params": "119.4B",
        "license": "Apache-2.0",
        "pipeline": "N/A",
        "note": "MoE 128专家4激活; 多语言(en,fr,de,es,pt,it,ja)",
    },
    "Whisper Large V3 Turbo": {
        "params": "809M",
        "license": "MIT",
        "pipeline": "automatic-speech-recognition",
        "note": "多语言(en,zh,de,es,ru等)",
    },
    "Sarvam-105B": {
        "params": "未公开(MoE)",
        "license": "Apache-2.0",
        "pipeline": "text-generation",
        "note": "多语言(en,bn,hi,kn,gu等印度语言)",
    },
    "Voxtral Mini": {
        "params": "4.7B",
        "license": "Apache-2.0",
        "pipeline": "N/A",
        "note": "多语言(en,fr,de,es)",
    },
}

HF_FAILED = {
    "gemma-4-27b-it": "401 Unauthorized(需同意License)",
    "Gemma-4-E2B": "401 Unauthorized(需同意License)",
    "Gemma-4-E4B": "401 Unauthorized(需同意License)",
    "GLM-5.1": "401 Unauthorized(需同意License)",
    "Sarvam-30B": "401 Unauthorized(需同意License)",
    "Mamba-3": "401 Unauthorized(需同意License)",
}

# web_search实际执行过的模型
WEBSEARCHED = {
    # llmstats来源 - 全部做了web_search
    "Grok Imagine Video", "Gen-4 Aleph", "Imagen 4 Standard", "Imagen 4 Ultra",
    "Seedream 4.5", "Flux 2 Max", "Flux 2 Pro", "Grok Imagine Image",
    "Qwen Image 2.0", "Reve", "MiMo-V2-Omni", "mistral-small-4-119b-2603",
    "Sarvam-105B", "Sarvam-30B",
    "GPT-5.2 Codex", "GPT-5 High", "GPT-5.1 High",
    "Whisper Large V3 Turbo", "Deepgram Nova 3", "Voxtral Mini",
    "Gemma-4-E2B", "Gemma-4-E4B",
    # 腾讯研究院来源 - 做了web_search的
    "claude-mythos-preview", "Claude Managed Agents",
    "gemma-4-27b-it", "Muse Spark",
    "Midjourney V8 Alpha", "Cursor 3",
    "GLM-5.1", "GLM-5V-Turbo",
    "qwen3.6-plus", "MiMo-V2-Pro",
    "step-3.5-flash", "Kimi Linear",
    "veo-3.1-lite", "lyria-3-pro",
    "gemini-3.1-flash-live-preview", "Gemini Robotics-ER 1.6",
    "MAI-Transcribe-1", "MAI-Voice-1", "MAI-Image-2",
    "Hermes Agent", "Marble 1.1",
    "MiniMax Music 2.6",
}

# 构建核实情况列
verify_status = []
for idx, row in df.iterrows():
    is_new = row.get("是否新增")
    if is_new != "New":
        verify_status.append(None)
        continue

    name = str(row.get("模型名称", ""))
    source = str(row.get("数据来源", ""))
    oc = str(row.get("开闭源", ""))
    has_url = pd.notna(row.get("官网")) and str(row.get("官网", "")).startswith("http")

    statuses = []

    # 1. 数据来源核实
    if source == "llmstats":
        statuses.append("榜单数据直接引用:已完成")
    elif source == "腾讯研究院":
        statuses.append("文章AI阅读提取:已完成")

    # 2. web_search核实
    if name in WEBSEARCHED:
        statuses.append("web_search:已执行")
    else:
        statuses.append("web_search:未执行")

    # 3. HuggingFace核实
    if name in HF_SUCCESS:
        r = HF_SUCCESS[name]
        statuses.append(
            "HuggingFace:已成功(params={},license={})".format(r["params"], r["license"])
        )
    elif name in HF_FAILED:
        statuses.append("HuggingFace:访问失败({})".format(HF_FAILED[name]))
    elif oc == "开源":
        statuses.append("HuggingFace:未尝试")

    # 4. 官网链接
    if has_url:
        statuses.append("官网链接:有(未逐个验证可用性)")
    elif oc in ("闭源", "集成产品"):
        statuses.append("官网链接:无")

    verify_status.append(" | ".join(statuses))

df["核实情况"] = verify_status

# 用HF数据更新尺寸
update_count = 0
for idx, row in df.iterrows():
    name = str(row.get("模型名称", ""))
    if name in HF_SUCCESS and pd.isna(row.get("尺寸")):
        params = HF_SUCCESS[name]["params"]
        if params != "未公开(MoE)":
            df.at[idx, "尺寸"] = params
            update_count += 1
            print("  [更新尺寸] {}: {}".format(name, params))

df.to_excel(r"D:\yuwang\action\Object-Models-Updated.xlsx", index=False, engine="openpyxl")

print("\n总行数: {}".format(len(df)))
print("列名: {}".format(list(df.columns)))
print("尺寸更新: {}个".format(update_count))

# 统计
new_df = df[df["是否新增"] == "New"]
from collections import Counter

parts = []
for v in new_df["核实情况"].dropna():
    for p in str(v).split(" | "):
        key = p.split(":")[0].strip() if ":" in p else p
        val = p.split(":", 1)[1].strip() if ":" in p else ""
        parts.append("{}: {}".format(key, val))

print("\nNew模型核实情况统计:")
for k, c in Counter(parts).most_common():
    print("  {}: {}".format(k, c))

print("\n已保存")
