"""
综合更新脚本：
1. 从STT.md/TTS.md/Open LLM Leaderboard.md中提取未追踪的新模型
2. 用llmstats的benchmark/参数/价格数据更新已有模型的备注
3. 加"是否新增"列：与Object-Models-Old.xlsx对比
"""
import pandas as pd
from datetime import date

UPDATED_PATH = r"D:\yuwang\action\Object-Models-Updated.xlsx"
OLD_PATH = r"D:\yuwang\action\Object-Models-Old.xlsx"
TODAY = str(date.today())

# 加载数据
updated_df = pd.read_excel(UPDATED_PATH)
old_df = pd.read_excel(OLD_PATH)

print(f"Updated表当前行数: {len(updated_df)}")
print(f"Old表行数: {len(old_df)}")


def normalize(name):
    if pd.isna(name):
        return ""
    return str(name).lower().strip().replace("-", "").replace("_", "").replace(" ", "")


# 构建已有模型名称集合
existing_names_raw = set(str(n).strip() for n in updated_df["模型名称"].dropna())
existing_normalized = {normalize(n) for n in existing_names_raw}

old_names_normalized = {normalize(str(n).strip()) for n in old_df["模型名称"].dropna()}


def is_tracked(model_name):
    n = normalize(model_name)
    if n in existing_normalized:
        return True
    for e in existing_normalized:
        if len(n) > 5 and len(e) > 5:
            if n in e or e in n:
                return True
    return False


# ============================================================
# 第一步：从三个新文件中提取未追踪的新模型
# ============================================================

# --- STT.md (实际是Code Arena排行榜) 中的新模型 ---
# 已追踪的：Claude Opus 4.6/4.5, Gemini 3.1 Pro/3 Pro/3 Flash, GPT-5.4/5.2/5.1,
#           GLM-5/5.1, Qwen3.5-397B, GPT-5.4 mini, Gemini 3.1 Flash-Lite, Claude Sonnet 4.6
# 需要检查的：Kimi K2.5, GLM-4.6, GPT-5.2 Codex, GPT-5.3 Codex, GPT-5.1 High, GPT-5 High

stt_new_models = [
    {
        "模型名称": "GPT-5.2 Codex",
        "公司": "OpenAI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "代码",
        "能否推理": "thinking",
        "任务类型": "代码生成",
        "官网": None,
        "备注": "OpenAI代码专用模型；Code Arena 1149；400K上下文；$1.75/$14.00 per M tokens",
    },
    {
        "模型名称": "GPT-5.3 Codex",
        "公司": "OpenAI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "代码",
        "能否推理": "thinking",
        "任务类型": "代码生成",
        "官网": None,
        "备注": "OpenAI代码专用模型；Code Arena 1105；400K上下文；$1.75/$14.00 per M tokens",
    },
    {
        "模型名称": "GPT-5 High",
        "公司": "OpenAI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "GPT-5高配版；Code Arena 1301；Chat Arena 1037；GPQA 87.3%；400K上下文；$1.25/$10.00 per M tokens",
    },
    {
        "模型名称": "GPT-5.1 High",
        "公司": "OpenAI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "GPT-5.1高配版；Code Arena 1137；Chat Arena 1132；GPQA 88.1%；400K上下文；$1.25/$10.00 per M tokens",
    },
    {
        "模型名称": "GLM-4.6",
        "公司": "智谱AI",
        "国内外": "国内",
        "开闭源": "开源",
        "尺寸": None,
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "智谱GLM-4.6；Code Arena 1139；Chat Arena 1079；GPQA 81.0%；SWE-bench 68.0%；131K上下文；$0.55/$2.19 per M tokens",
    },
]

# --- TTS.md (实际是STT语音转文字排行榜) 中的新模型 ---
# 语音模型，大部分是工具/API而非独立模型，但以下值得追踪：
tts_new_models = [
    {
        "模型名称": "Whisper Large V3 Turbo",
        "公司": "OpenAI",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": None,
        "类型": "语音",
        "能否推理": "non-thinking",
        "任务类型": "语音识别",
        "官网": None,
        "备注": "OpenAI语音转文字模型；STT Arena排名第1；ELO 2262；$0.35/min",
    },
    {
        "模型名称": "Deepgram Nova 3",
        "公司": "Deepgram",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "语音",
        "能否推理": "non-thinking",
        "任务类型": "语音识别",
        "官网": None,
        "备注": "Deepgram语音转文字模型；STT Arena排名第5；ELO 294",
    },
    {
        "模型名称": "Voxtral Mini",
        "公司": "Mistral AI",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": None,
        "类型": "语音",
        "能否推理": "non-thinking",
        "任务类型": "语音识别",
        "官网": None,
        "备注": "Mistral语音转文字模型；STT Arena排名第8；ELO -517",
    },
]

# --- Open LLM Leaderboard 中的新模型 ---
# 大部分已追踪，检查小尺寸Qwen3.5和Nemotron 3 Super
open_llm_new_models = [
    {
        "模型名称": "Nemotron-3-Super-120B-A12B",
        "公司": "NVIDIA",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": "120B-A12B",
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "NVIDIA MoE模型；262.1K上下文；321 tok/s；GPQA 82.7%；AIME 90.2%；SWE-bench 53.7%；$0.10/$0.50 per M tokens",
    },
    {
        "模型名称": "Gemma-4-E2B",
        "公司": "Google",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": "2B",
        "类型": "基座",
        "能否推理": "non-thinking",
        "任务类型": None,
        "官网": None,
        "备注": "Google Gemma 4超小尺寸；GPQA 43.4%；MMMLU 67.4%",
    },
    {
        "模型名称": "Gemma-4-E4B",
        "公司": "Google",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": "4B",
        "类型": "基座",
        "能否推理": "non-thinking",
        "任务类型": None,
        "官网": None,
        "备注": "Google Gemma 4小尺寸；GPQA 58.6%；MMMLU 76.6%",
    },
    {
        "模型名称": "Qwen3.5-0.8B",
        "公司": "阿里",
        "国内外": "国内",
        "开闭源": "开源",
        "尺寸": "0.8B",
        "类型": "基座",
        "能否推理": "non-thinking",
        "任务类型": None,
        "官网": None,
        "备注": "Qwen3.5超小尺寸；端侧部署",
    },
    {
        "模型名称": "Qwen3.5-2B",
        "公司": "阿里",
        "国内外": "国内",
        "开闭源": "开源",
        "尺寸": "2B",
        "类型": "基座",
        "能否推理": "non-thinking",
        "任务类型": None,
        "官网": None,
        "备注": "Qwen3.5小尺寸；GPQA 51.6%；MMMLU 63.1%",
    },
    {
        "模型名称": "Qwen3.5-4B",
        "公司": "阿里",
        "国内外": "国内",
        "开闭源": "开源",
        "尺寸": "4B",
        "类型": "基座",
        "能否推理": "non-thinking",
        "任务类型": None,
        "官网": None,
        "备注": "Qwen3.5小尺寸；GPQA 76.2%；MMMLU 76.1%",
    },
    {
        "模型名称": "Qwen3.5-9B",
        "公司": "阿里",
        "国内外": "国内",
        "开闭源": "开源",
        "尺寸": "9B",
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "Qwen3.5中等尺寸；GPQA 81.7%；MMMLU 81.2%",
    },
]

# 合并所有新模型候选
all_candidates = stt_new_models + tts_new_models + open_llm_new_models

# 过滤已追踪的
new_models_to_add = []
for model in all_candidates:
    name = model["模型名称"]
    if not is_tracked(name):
        new_models_to_add.append(model)
    else:
        print(f"  [跳过-已追踪] {name}")

print(f"\n新增模型数量: {len(new_models_to_add)}")
for i, m in enumerate(new_models_to_add, 1):
    print(f"  {i:2d}. {m['模型名称']:<30s} | {m.get('公司', '?'):<12s} | {m.get('尺寸') or '-'}")

# ============================================================
# 第二步：追加新模型到表格
# ============================================================
new_rows = []
for model in new_models_to_add:
    row = {
        "模型名称": model["模型名称"],
        "是否接入": None,
        "workflow接入进展": False,
        "公司": model.get("公司"),
        "国内外": model.get("国内外"),
        "开闭源": model.get("开闭源"),
        "尺寸": model.get("尺寸"),
        "类型": model.get("类型"),
        "能否推理": model.get("能否推理"),
        "任务类型": model.get("任务类型"),
        "官网": model.get("官网"),
        "备注": model.get("备注"),
        "模型发布时间": model.get("模型发布时间"),
        "记录创建时间": TODAY,
    }
    new_rows.append(row)

if new_rows:
    new_df = pd.DataFrame(new_rows)
    combined_df = pd.concat([updated_df, new_df], ignore_index=True)
else:
    combined_df = updated_df.copy()

print(f"\n合并后总行数: {len(combined_df)}")

# ============================================================
# 第三步：用llmstats的benchmark数据更新已有模型的备注
# ============================================================

# llmstats中的benchmark数据（仅更新那些备注中还没有benchmark信息的模型）
BENCHMARK_DATA = {
    # 从STT.md (Code Arena排行榜)
    "claude-opus-4.6": "Code Arena 1998；Chat Arena 1491；GPQA 91.3%；SWE-bench 80.8%；1M上下文；$5/$25 per M tokens",
    "gemini-3.1-pro": "Code Arena 1941；Chat Arena 1222；GPQA 94.3%；SWE-bench 80.6%；1M上下文；$2.5/$15 per M tokens",
    "gpt-5.4": "Code Arena 1638；Chat Arena 1146；GPQA 92.8%；1M上下文；$2.5/$15 per M tokens",
    "claude-opus-4.5": "Code Arena 1590；Chat Arena 1345；GPQA 87.0%；SWE-bench 80.9%；200K上下文；$5/$25 per M tokens",
    "glm-5": "Code Arena 1588；Chat Arena 1158；SWE-bench 77.8%；200K上下文；$1/$3.2 per M tokens",
    "gemini-3-pro": "Code Arena 1579；Chat Arena 1045；GPQA 91.9%；SWE-bench 76.2%",
    "gemini-3-flash": "Code Arena 1579；Chat Arena 1172；GPQA 90.4%；SWE-bench 78.0%；1M上下文；$0.5/$3 per M tokens",
    "gpt-5.2": "Code Arena 1500；Chat Arena 1180；GPQA 92.4%；SWE-bench 80.0%；400K上下文；$1.75/$14 per M tokens",
    "kimi-k2.5": "Code Arena 1468；Chat Arena 1003；GPQA 87.6%；SWE-bench 76.8%；262K上下文；$0.6/$2.5 per M tokens",
    "claude-sonnet-4.6": "Code Arena 1365；Chat Arena 941；GPQA 89.9%；SWE-bench 79.6%；200K上下文；$3/$15 per M tokens",
    "gpt-5.1": "Code Arena 1234；Chat Arena 1018；GPQA 88.1%；SWE-bench 76.3%；400K上下文；$1.25/$10 per M tokens",
    "glm-5.1": "Code Arena 1234；GPQA 86.2%；200K上下文；$1.4/$4.4 per M tokens；754B参数",
    "qwen3.5-397b-a17b": "Code Arena 1212；Chat Arena 1067；GPQA 88.4%；SWE-bench 76.4%；262K上下文；$0.6/$3.6 per M tokens",
    "gpt-5.4-mini": "Code Arena 1100；Chat Arena 821；GPQA 88.0%；400K上下文；$0.75/$4.5 per M tokens",
    "gemini-3.1-flash-lite": "Code Arena 1146；Chat Arena 328；GPQA 86.9%；1M上下文；$0.25/$1.5 per M tokens",
    # 从Open LLM Leaderboard
    "gemma-4-26b-a4b": "Code Arena 978；GPQA 82.3%；MMMLU 86.3%；262.1K上下文；$0.13/$0.4 per M tokens；135 tok/s",
    "gemma-4-31b": "Code Arena 387；GPQA 84.3%；MMMLU 88.4%；262.1K上下文；$0.14/$0.4 per M tokens",
    "minimax-m2.7": "Code Arena 1008；204.8K上下文；$0.3/$1.2 per M tokens；43 tok/s",
    "mistral-small-4": "GPQA 71.2%；AIME 83.8%；MMMLU 60.0%；256K上下文；$0.15/$0.6 per M tokens；119B参数",
    "qwen3.6-plus": "GPQA 90.4%；AIME 78.8%；MMMLU 89.5%",
}


def find_model_row(df, search_name):
    """在df中查找模型名称匹配的行索引"""
    n = normalize(search_name)
    for idx, row in df.iterrows():
        model_name = str(row.get("模型名称", ""))
        if normalize(model_name) == n:
            return idx
        # 模糊匹配
        mn = normalize(model_name)
        if len(n) > 5 and len(mn) > 5:
            if n in mn or mn in n:
                return idx
    return None


benchmark_update_count = 0
for model_key, benchmark_info in BENCHMARK_DATA.items():
    idx = find_model_row(combined_df, model_key)
    if idx is not None:
        current_note = str(combined_df.at[idx, "备注"]) if pd.notna(combined_df.at[idx, "备注"]) else ""
        # 只在备注中没有Arena/GPQA信息时才追加
        if "Arena" not in current_note and "GPQA" not in current_note:
            if current_note:
                combined_df.at[idx, "备注"] = current_note + "；" + benchmark_info
            else:
                combined_df.at[idx, "备注"] = benchmark_info
            benchmark_update_count += 1
            print(f"  [更新benchmark] {combined_df.at[idx, '模型名称']}")
        else:
            pass  # 已有benchmark信息，跳过
    else:
        print(f"  [未找到模型] {model_key}")

print(f"\n更新了 {benchmark_update_count} 个模型的benchmark数据")

# ============================================================
# 第四步：加"是否新增"列
# ============================================================
is_new_column = []
for _, row in combined_df.iterrows():
    model_name = str(row.get("模型名称", ""))
    n = normalize(model_name)
    if n in old_names_normalized:
        is_new_column.append(None)
    else:
        # 模糊匹配Old表
        found_in_old = False
        for old_n in old_names_normalized:
            if len(n) > 5 and len(old_n) > 5:
                if n in old_n or old_n in n:
                    found_in_old = True
                    break
        if found_in_old:
            is_new_column.append(None)
        else:
            is_new_column.append("New")

combined_df["是否新增"] = is_new_column

new_count = sum(1 for v in is_new_column if v == "New")
print(f"\n标记为New的模型数量: {new_count}")
print(f"未标记（Old中已有）的数量: {len(is_new_column) - new_count}")

# ============================================================
# 保存
# ============================================================
combined_df.to_excel(UPDATED_PATH, index=False, engine="openpyxl")
print(f"\n最终表格已保存至: {UPDATED_PATH}")
print(f"最终总行数: {len(combined_df)}")
print(f"列名: {list(combined_df.columns)}")
