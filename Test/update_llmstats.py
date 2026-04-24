"""
将llmstats来源的核实后新模型追加到Object-Models-Updated.xlsx。
"""
import pandas as pd
from datetime import date

OUTPUT = r"D:\yuwang\action\data\Object-Models-Updated.xlsx"
existing_df = pd.read_excel(OUTPUT)
print(f"当前模型数量: {len(existing_df)}")

TODAY = str(date.today())

NEW_MODELS = [
    # ==================== Video Generation ====================
    {
        "模型名称": "Grok Imagine Video",
        "公司": "xAI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "文生视频",
        "官网": "https://docs.x.ai/developers/model-capabilities/video/generation",
        "备注": "xAI视频生成模型；Video Arena排名第1；支持文本转视频和图像转视频；$0.05/s",
    },
    {
        "模型名称": "Gen-4 Aleph",
        "公司": "Runway",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "文生视频",
        "官网": "https://runwayml.com/research/introducing-runway-aleph",
        "备注": "Runway旗舰视频模型；in-context video model；支持多任务视觉生成；角色/场景一致性",
    },
    # ==================== Image Generation ====================
    {
        "模型名称": "Imagen 4 Standard",
        "公司": "Google",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://deepmind.google/models/imagen/",
        "备注": "Google最新图像生成模型；支持2K分辨率；$0.05/img",
    },
    {
        "模型名称": "Imagen 4 Ultra",
        "公司": "Google",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://deepmind.google/models/imagen/",
        "备注": "Google最高保真图像生成模型；超高画质；$0.10/img",
    },
    {
        "模型名称": "Seedream 4.5",
        "公司": "字节",
        "国内外": "国内",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://seed.bytedance.com/zh/seedream4_5",
        "备注": "字节Seed团队图像生成模型；多图组合一致性；海报排版+Logo设计；最高4K；支持最多14张参考图",
    },
    {
        "模型名称": "Flux 2 Max",
        "公司": "Black Forest Labs",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://bfl.ai/models/flux-2-max",
        "备注": "FLUX.2系列最高质量版；4MP输出；支持10张参考图；$0.06/img",
    },
    {
        "模型名称": "Flux 2 Pro",
        "公司": "Black Forest Labs",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://bfl.ai/models/flux-2",
        "备注": "FLUX.2系列专业版；$0.02/img",
    },
    {
        "模型名称": "Grok Imagine Image",
        "公司": "xAI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://grok.com/imagine",
        "备注": "xAI图像生成模型；Image Arena排名第5；$0.02/img；另有Pro版$0.07/img",
    },
    {
        "模型名称": "Qwen Image 2.0",
        "公司": "阿里",
        "国内外": "国内",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": None,
        "备注": "阿里通义图像生成模型；$0.03/img",
    },
    {
        "模型名称": "Reve",
        "公司": "Reve AI",
        "国内外": "国外",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "non-thinking",
        "任务类型": "图片编辑",
        "官网": "https://www.reve.com/",
        "备注": "Luma AI旗下图像生成+编辑模型；拖拽式编辑器；Image Arena排名第16；$0.18/img",
    },
    # ==================== LLM ====================
    {
        "模型名称": "MiMo-V2-Omni",
        "公司": "小米",
        "国内外": "国内",
        "开闭源": "闭源",
        "尺寸": None,
        "类型": "多模态",
        "能否推理": "thinking",
        "任务类型": "任意模态",
        "官网": None,
        "备注": "小米全模态Agent基座模型；262k上下文；与MiMo-V2-Pro同期发布",
    },
    {
        "模型名称": "mistral-small-4-119b-2603",
        "公司": "Mistral AI",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": "119B-A6.5B",
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": "任意模态",
        "官网": "https://mistral.ai/news/mistral-small-4",
        "备注": "Mistral Small 4；MoE 128专家4激活；256k上下文；统一instruct/reasoning/coding/多模态；Apache 2.0",
    },
    {
        "模型名称": "Sarvam-105B",
        "公司": "Sarvam AI",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": "105B",
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "印度AI实验室；GPQA 96.7%；MoE架构；超越DeepSeek R1和Gemini Flash",
    },
    {
        "模型名称": "Sarvam-30B",
        "公司": "Sarvam AI",
        "国内外": "国外",
        "开闭源": "开源",
        "尺寸": "30B",
        "类型": "基座",
        "能否推理": "thinking",
        "任务类型": None,
        "官网": None,
        "备注": "印度AI实验室；GPQA 96.7%；与105B同期发布",
    },
]

new_rows = []
for model in NEW_MODELS:
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

new_df = pd.DataFrame(new_rows)
combined_df = pd.concat([existing_df, new_df], ignore_index=True)
combined_df.to_excel(OUTPUT, index=False, engine="openpyxl")

print(f"新增模型数量: {len(new_rows)}")
print(f"合并后总数量: {len(combined_df)}")
print(f"结果已保存至: {OUTPUT}")

print("\n新增模型列表：")
for i, model in enumerate(NEW_MODELS, 1):
    company = model.get("公司") or "?"
    size = model.get("尺寸") or "-"
    url = "✅" if model.get("官网") else "⚠️"
    print(f"  {i:2d}. {model['模型名称']:<30s} | {company:<18s} | {model['开闭源']:<6s} | {size:<20s} {url}")
