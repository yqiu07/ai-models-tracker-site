"""
核实模型信息的脚本
1. 开源模型：爬取HuggingFace获取尺寸、类型等
2. 闭源模型：爬取发布页/平台入口
3. Qwen系列：阿里云百炼核实
"""
import requests
import json
import time
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

OUTPUT_DIR = r"D:\yuwang\action\Test"


def fetch_hf_model(model_id):
    """从HuggingFace API获取模型信息"""
    url = f"https://huggingface.co/api/models/{model_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}"}
    except Exception as exc:
        return {"error": str(exc)}


def fetch_hf_readme(model_id):
    """从HuggingFace获取模型README"""
    url = f"https://huggingface.co/{model_id}/raw/main/README.md"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text[:5000]
        else:
            return f"HTTP {response.status_code}"
    except Exception as exc:
        return str(exc)


# 需要在HuggingFace核实的开源模型及其可能的HF路径
HF_MODELS = {
    "Gemma 4": "google/gemma-4-27b-it",
    "Gemma 4 E2B": "google/gemma-4-e2b-it",
    "Mamba-3": "state-spaces/mamba3-2.8b-hf",
    "VoxCPM 2": "openbmb/VoxCPM2-2B",
    "MiniMax Music 2.6": "MiniMaxAI/MiniMax-Music-2.6",
    "LongCat-AudioDiT": "meituan/LongCat-AudioDiT",
    "HY-Embodied-0.5": "tencent/HY-Embodied-MoT-2B",
    "JoyAI-Image-Edit": "JD-AI/JoyAI-Image-Edit-240B",
    "MiMo-V2-Pro": "XiaomiMiMo/MiMo-V2-Pro-1T",
    "GLM-5.1": "THUDM/GLM-5.1",
    "GLM-5V-Turbo": "THUDM/GLM-5V-Turbo",
    "Hermes Agent": "NousResearch/Hermes-Agent",
    "Being-H 0.7": "zhizaiwujie/Being-H-0.7",
    "Wan2.7-Image": "Wan-AI/Wan2.7-Image",
    "CaP-X": "nvidia/CaP-X",
    "NemoClaw": "nvidia/NemoClaw",
    "Ising": "nvidia/Ising",
    "MuonClip": "MoonshotAI/MuonClip",
    "Psi-R2": "lingchu/Psi-R2",
    "AI Scientist": "SakanaAI/AI-Scientist",
    "JoyStreamer": "jd-research/JoyStreamer",
    "EchoZ-1.0": "UniPatAI/EchoZ-1.0",
    "Midjourney V8 Alpha": "midjourney/v8-alpha",
}

results = {}
for name, hf_id in HF_MODELS.items():
    print(f"正在查询 HuggingFace: {name} ({hf_id})...")
    info = fetch_hf_model(hf_id)
    readme = ""
    if "error" not in info:
        readme = fetch_hf_readme(hf_id)
    results[name] = {
        "hf_id": hf_id,
        "api_info": info,
        "readme_preview": readme[:3000] if isinstance(readme, str) else ""
    }
    time.sleep(0.5)

output_path = os.path.join(OUTPUT_DIR, "hf_verify_results.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)

print(f"\n结果已保存至: {output_path}")
print(f"共查询 {len(results)} 个模型")

# 打印摘要
for name, data in results.items():
    api = data["api_info"]
    if "error" in api:
        print(f"  ❌ {name}: {api['error']}")
    else:
        tags = api.get("tags", [])
        pipeline = api.get("pipeline_tag", "N/A")
        downloads = api.get("downloads", 0)
        print(f"  ✅ {name}: pipeline={pipeline}, downloads={downloads}, tags={tags[:5]}")
