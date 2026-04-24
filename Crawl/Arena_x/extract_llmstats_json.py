"""
从 llm-stats.com 多个页面的 HTML 文件中提取内嵌的 Next.js RSC 数据，
并从 ZeroEval API 的网络响应文件中提取多模态排行榜数据。

支持两类数据源：
  A) HTML 内嵌 RSC 数据（LLM 排行榜）：
    - AI Leaderboard (首页)：基础字段
    - LLM Leaderboard：详细字段（参数量/benchmark/index 等）
    - Open LLM Leaderboard：仅开源模型的详细字段
    - LLM Updates：时间线视角

  B) ZeroEval API 响应文件（多模态排行榜）：
    - Image Generation: text-to-image + image-to-image
    - Video Generation: text-to-video + image-to-video
    - Text-to-Speech
    - Speech-to-Text
    - Embeddings（暂无数据）

用法:
    python extract_llmstats_json.py

输入 (同目录下):
    llm-stats-ai.com                    ← AI Leaderboard 首页源码
    llm-stats-LLM.com                   ← LLM Leaderboard 页源码
    llm-stats-open-llm.com              ← Open LLM Leaderboard 页源码
    llm-stats-updates.com               ← LLM Updates 页源码
    llm-stats.com                       ← 旧版首页源码 (fallback)
    api_text_to_image.network-response  ← ZeroEval API 响应
    api_image_to_image.network-response
    api_text_to_video.network-response
    api_image_to_video.network-response
    api_text_to_speech.network-response
    api_speech_to_text.network-response
    api_embeddings.network-response

输出:
    llmstats_models.json            ← 合并后的 LLM 结构化模型数据
    llmstats_leaderboard_auto.md    ← 自动生成的 LLM 排行榜 Markdown
    llmstats_multimodal.json        ← 多模态排行榜结构化数据
    llmstats_multimodal_auto.md     ← 自动生成的多模态排行榜 Markdown
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent

SOURCE_FILES = {
    "ai": {
        "file": SCRIPT_DIR / "llm-stats-ai.com",
        "label": "AI Leaderboard (首页)",
        "fallback": SCRIPT_DIR / "llm-stats.com",
    },
    "llm": {
        "file": SCRIPT_DIR / "llm-stats-LLM.com",
        "label": "LLM Leaderboard (详情页)",
    },
    "open": {
        "file": SCRIPT_DIR / "llm-stats-open-llm.com",
        "label": "Open LLM Leaderboard",
    },
    "updates": {
        "file": SCRIPT_DIR / "llm-stats-updates.com",
        "label": "LLM Updates (时间线)",
    },
}

JSON_OUTPUT = SCRIPT_DIR / "llmstats_models.json"
MD_OUTPUT = SCRIPT_DIR / "llmstats_leaderboard_auto.md"

# === B) ZeroEval API 响应文件（多模态排行榜） ===
ARENA_CATEGORIES = {
    "image_generation": {
        "label": "Image Generation",
        "subcategories": [
            {"key": "text_to_image", "file": "api_text_to_image.network-response", "label": "Text-to-Image"},
            {"key": "image_to_image", "file": "api_image_to_image.network-response", "label": "Image-to-Image"},
        ],
    },
    "video_generation": {
        "label": "Video Generation",
        "subcategories": [
            {"key": "text_to_video", "file": "api_text_to_video.network-response", "label": "Text-to-Video"},
            {"key": "image_to_video", "file": "api_image_to_video.network-response", "label": "Image-to-Video"},
        ],
    },
    "tts": {
        "label": "Text-to-Speech",
        "subcategories": [
            {"key": "text_to_speech", "file": "api_text_to_speech.network-response", "label": "Text-to-Speech"},
        ],
    },
    "stt": {
        "label": "Speech-to-Text",
        "subcategories": [
            {"key": "speech_to_text", "file": "api_speech_to_text.network-response", "label": "Speech-to-Text"},
        ],
    },
    "embeddings": {
        "label": "Embeddings",
        "subcategories": [
            {"key": "embeddings", "file": "api_embeddings.network-response", "label": "Embeddings"},
        ],
    },
}

MULTIMODAL_JSON_OUTPUT = SCRIPT_DIR / "llmstats_multimodal.json"
MULTIMODAL_MD_OUTPUT = SCRIPT_DIR / "llmstats_multimodal_auto.md"


def extract_models_from_next_f(html_content):
    """从 Next.js 的 self.__next_f.push 数据中提取模型列表。

    llm-stats.com 使用 Next.js RSC（React Server Components），
    数据通过 self.__next_f.push([1, "..."]) 的形式内嵌在 HTML 中，
    其中包含 "initialHomepageLLMModels" 字段。
    """
    pattern = r'self\.__next_f\.push\(\[1,"(.*?)"\]\)'
    chunks = re.findall(pattern, html_content, re.DOTALL)
    combined = "".join(chunks)
    combined = combined.replace('\\"', '"').replace('\\\\', '\\')

    # 查找模型数组的 key（不同页面使用不同的 key 名）
    # AI 首页: initialHomepageLLMModels
    # LLM/Open LLM 页: initialData
    # Updates 页: recentUpdates
    candidate_keys = ['"initialHomepageLLMModels":', '"initialData":', '"recentUpdates":']
    idx = -1
    for key in candidate_keys:
        idx = combined.find(key)
        if idx >= 0:
            break

    if idx < 0:
        return None

    # 从 key 后面开始找 [ ... ] 的 JSON 数组
    array_start = combined.find("[", idx)
    if array_start < 0:
        return None

    depth = 0
    array_end = array_start
    for i in range(array_start, len(combined)):
        if combined[i] == "[":
            depth += 1
        elif combined[i] == "]":
            depth -= 1
            if depth == 0:
                array_end = i + 1
                break

    json_str = combined[array_start:array_end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        model_pattern = r'\{"model_id":"[^"]+?".*?\}'
        model_matches = re.findall(model_pattern, json_str)
        models = []
        for match_str in model_matches:
            try:
                models.append(json.loads(match_str))
            except json.JSONDecodeError:
                continue
        return models if models else None


def read_html_file(source_config):
    """读取 HTML 文件，支持 fallback 路径。"""
    primary = source_config["file"]
    fallback = source_config.get("fallback")
    label = source_config["label"]

    if primary.exists():
        size_kb = primary.stat().st_size / 1024
        print(f"  [Read] {label}: {primary.name} ({size_kb:.0f} KB)")
        return primary.read_text(encoding="utf-8")

    if fallback and fallback.exists():
        size_kb = fallback.stat().st_size / 1024
        print(f"  [Read] {label} (fallback): {fallback.name} ({size_kb:.0f} KB)")
        return fallback.read_text(encoding="utf-8")

    print(f"  [Skip] {label}: 文件不存在")
    return None


def _merge_supplement(merged, models, page_key):
    """将一个页面的模型数据合并到已有的 merged 字典中（补充缺失字段）。"""
    for model in models:
        model_id = model.get("model_id", "")
        if not model_id:
            continue
        # 清理 $undefined 值（updates 页面特有）
        cleaned = {}
        for field_key, field_val in model.items():
            if field_val == "$undefined":
                continue
            cleaned[field_key] = field_val

        if model_id not in merged:
            merged[model_id] = dict(cleaned)
            merged[model_id]["_source_pages"] = [page_key]
        else:
            merged[model_id]["_source_pages"].append(page_key)
            for field_key, field_val in cleaned.items():
                if field_key not in merged[model_id] or merged[model_id][field_key] is None:
                    merged[model_id][field_key] = field_val


def extract_all_pages():
    """从多个页面中提取并合并模型数据。

    合并策略（按优先级）：
      1. LLM 详情页 — 字段最丰富（50+ 字段），作为基础
      2. AI 首页    — 补充 is_open_source 等字段
      3. Open LLM   — 补充缺失字段（不能用来判断开源）
      4. Updates     — 补充独有字段（description/source_paper/modality 等）
    """
    all_data = {}  # page_key → model list
    for page_key, config in SOURCE_FILES.items():
        html = read_html_file(config)
        if not html:
            continue
        models = extract_models_from_next_f(html)
        if models:
            print(f"  [OK] {config['label']}: {len(models)} 个模型")
            all_data[page_key] = models
        else:
            print(f"  [Warn] {config['label']}: 未提取到模型数据")

    if not all_data:
        return None, {}

    # 按优先级合并
    merged = {}

    # 第一轮：LLM 详情页（字段最丰富）
    for model in all_data.get("llm", []):
        model_id = model.get("model_id", "")
        if model_id:
            merged[model_id] = dict(model)
            merged[model_id]["_source_pages"] = ["llm"]

    # 第二轮：AI 首页（补充 is_open_source 等）
    _merge_supplement(merged, all_data.get("ai", []), "ai")

    # 第三轮：Open LLM 页（补充缺失字段，不标记开源）
    _merge_supplement(merged, all_data.get("open", []), "open")

    # 第四轮：Updates 页（补充 description/source_paper/modality 等独有字段）
    _merge_supplement(merged, all_data.get("updates", []), "updates")

    model_list = sorted(merged.values(), key=lambda m: m.get("announcement_date") or m.get("release_date") or "", reverse=True)

    page_stats = {k: len(v) for k, v in all_data.items()}
    return model_list, page_stats


def filter_recent_models(models, months_back=3):
    """筛选最近 N 个月内发布的模型。"""
    cutoff = datetime.now()
    cutoff = cutoff.replace(month=max(1, cutoff.month - months_back))

    recent = []
    for model in models:
        # 兼容两种日期字段名
        date_str = model.get("announcement_date") or model.get("release_date") or ""
        if not date_str:
            continue
        try:
            release_date = datetime.strptime(date_str, "%Y-%m-%d")
            if release_date >= cutoff:
                recent.append(model)
        except ValueError:
            continue

    return sorted(recent, key=lambda m: m.get("announcement_date") or m.get("release_date") or "", reverse=True)


def format_score(value, as_percent=True):
    """格式化分数值。"""
    if value is None:
        return "—"
    if as_percent:
        return f"{value:.1%}" if value <= 1 else f"{value:.1f}%"
    return str(value)


def format_params(params):
    """格式化参数量（如 236B）。"""
    if not params:
        return "—"
    if params >= 1_000_000_000_000:
        return f"{params / 1_000_000_000_000:.0f}T"
    if params >= 1_000_000_000:
        return f"{params / 1_000_000_000:.0f}B"
    if params >= 1_000_000:
        return f"{params / 1_000_000:.0f}M"
    return str(params)


def is_open_source(model):
    """判断模型是否开源。

    优先看 AI 首页的 is_open_source 字段（布尔值），
    其次看 LLM 页的 license 字段（非 proprietary 即为开源）。
    """
    if "is_open_source" in model:
        return bool(model["is_open_source"])
    license_val = model.get("license", "")
    if license_val and license_val != "proprietary":
        return True
    return False


def generate_markdown(models, page_stats):
    """生成完整的多页面合并排行榜 Markdown。"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# LLM 排行榜（自动提取 · 多页面合并）",
        "",
        f"> 自动提取自 `llm-stats.com` 三个导航页的 HTML 源码",
        f"> 提取时间：{now_str}",
        f"> 合并后模型总数：{len(models)}",
    ]

    # 数据来源统计
    if page_stats:
        source_parts = []
        for key, count in page_stats.items():
            label = SOURCE_FILES[key]["label"]
            source_parts.append(f"{label}: {count}")
        lines.append(f"> 数据来源：{' | '.join(source_parts)}")
    lines.append("")

    # === 近期模型（核心表格） ===
    recent = filter_recent_models(models, months_back=3)
    if recent:
        lines.append(f"## 近 3 个月发布的新模型 ({len(recent)} 个)")
        lines.append("")
        lines.append("| 模型 | 公司 | 参数 | 开源 | 日期 | GPQA | SWE | HLE | AIME | 上下文 | In$/M | Out$/M |")
        lines.append("|------|------|------|------|------|------|-----|-----|------|--------|-------|--------|")
        for model in recent:
            name = model.get("name", "?")
            org = model.get("organization", "?")
            params = format_params(model.get("params"))
            open_flag = "✅" if is_open_source(model) else "❌"
            date = model.get("announcement_date") or model.get("release_date") or "—"
            gpqa = format_score(model.get("gpqa_score"))
            swe = format_score(model.get("swe_bench_verified_score"))
            hle = format_score(model.get("hle_score"))
            aime = format_score(model.get("aime_2025_score"))
            ctx = f"{model['context']:,}" if model.get("context") else "—"
            inp = f"${model['input_price']}" if model.get("input_price") is not None else "—"
            out = f"${model['output_price']}" if model.get("output_price") is not None else "—"
            lines.append(f"| {name} | {org} | {params} | {open_flag} | {date} | {gpqa} | {swe} | {hle} | {aime} | {ctx} | {inp} | {out} |")
        lines.append("")

    # === 仅开源模型的 Top 20 ===
    open_models = [m for m in models if is_open_source(m)]
    open_with_gpqa = [m for m in open_models if m.get("gpqa_score")]
    open_top = sorted(open_with_gpqa, key=lambda m: m.get("gpqa_score", 0), reverse=True)[:20]
    if open_top:
        lines.append(f"## 开源模型 Top 20 (by GPQA, 共 {len(open_models)} 个开源)")
        lines.append("")
        lines.append("| # | 模型 | 公司 | 参数 | MoE | License | GPQA | SWE | HLE | AIME |")
        lines.append("|---|------|------|------|-----|---------|------|-----|-----|------|")
        for rank, model in enumerate(open_top, 1):
            name = model.get("name", "?")
            org = model.get("organization", "?")
            params = format_params(model.get("params"))
            moe = "✅" if model.get("is_moe") else "—"
            lic = model.get("license", "—")
            gpqa = format_score(model.get("gpqa_score"))
            swe = format_score(model.get("swe_bench_verified_score"))
            hle = format_score(model.get("hle_score"))
            aime = format_score(model.get("aime_2025_score"))
            lines.append(f"| {rank} | {name} | {org} | {params} | {moe} | {lic} | {gpqa} | {swe} | {hle} | {aime} |")
        lines.append("")

    # === 公司维度统计 ===
    lines.append("## 各公司模型数量统计")
    lines.append("")
    org_counts = {}
    for model in models:
        org = model.get("organization", "Unknown")
        org_counts[org] = org_counts.get(org, 0) + 1
    lines.append("| 公司 | 总模型 | 开源 | 近3月新发 |")
    lines.append("|------|--------|------|----------|")
    recent_ids = {m.get("model_id") for m in recent} if recent else set()
    for org, total in sorted(org_counts.items(), key=lambda x: -x[1])[:25]:
        org_open = sum(1 for m in models if m.get("organization") == org and is_open_source(m))
        org_recent = sum(1 for m in models if m.get("organization") == org and m.get("model_id") in recent_ids)
        lines.append(f"| {org} | {total} | {org_open} | {org_recent} |")
    lines.append("")

    # === 字段覆盖率 ===
    key_fields = ["gpqa_score", "swe_bench_verified_score", "hle_score", "aime_2025_score",
                  "params", "context", "input_price", "license", "is_moe", "multimodal"]
    lines.append("## 字段覆盖率")
    lines.append("")
    lines.append("| 字段 | 有值数 | 覆盖率 |")
    lines.append("|------|--------|--------|")
    for field in key_fields:
        count = sum(1 for m in models if m.get(field) is not None)
        rate = count / len(models) * 100 if models else 0
        lines.append(f"| {field} | {count} | {rate:.0f}% |")

    return "\n".join(lines)


def extract_arena_api_data():
    """从 ZeroEval API 的 .network-response 文件中提取多模态排行榜数据。

    返回: {category_key: {label, subcategories: [{key, label, models: [...]}]}}
    """
    result = {}
    total_models = 0

    for category_key, category_config in ARENA_CATEGORIES.items():
        category_label = category_config["label"]
        subcategory_results = []

        for sub_config in category_config["subcategories"]:
            filepath = SCRIPT_DIR / sub_config["file"]
            sub_label = sub_config["label"]

            if not filepath.exists():
                print(f"  [Skip] {sub_label}: 文件不存在 ({sub_config['file']})")
                continue

            try:
                raw = json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                print(f"  [Error] {sub_label}: JSON 解析失败 - {error}")
                continue

            if isinstance(raw, list):
                models = raw
            elif isinstance(raw, dict) and "leaderboard" in raw:
                models = raw["leaderboard"]
            else:
                print(f"  [Warn] {sub_label}: 未识别的数据结构")
                continue

            if not models:
                print(f"  [Skip] {sub_label}: 无模型数据")
                continue

            for model in models:
                model["_arena_category"] = category_key
                model["_arena_subcategory"] = sub_config["key"]

            subcategory_results.append({
                "key": sub_config["key"],
                "label": sub_label,
                "models": models,
            })
            total_models += len(models)
            print(f"  [OK] {sub_label}: {len(models)} 个模型")

        if subcategory_results:
            result[category_key] = {
                "label": category_label,
                "subcategories": subcategory_results,
            }

    return result, total_models


def generate_multimodal_markdown(arena_data):
    """为多模态排行榜生成 Markdown 文档。"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    total_models = sum(
        len(sub["models"])
        for cat in arena_data.values()
        for sub in cat["subcategories"]
    )

    lines = [
        "# 多模态 AI 排行榜（自动提取 · ZeroEval Arena API）",
        "",
        f"> 数据源: ZeroEval Arena API (`api.zeroeval.com`)",
        f"> 提取时间: {now_str}",
        f"> 覆盖类别: {len(arena_data)} 大类, 共 {total_models} 个模型条目",
        "",
    ]

    # 数据概览表
    lines.append("## 数据概览")
    lines.append("")
    lines.append("| 类别 | 子类别 | 模型数 | API 端点 |")
    lines.append("|------|--------|--------|----------|")
    for category_key, category_data in arena_data.items():
        for sub in category_data["subcategories"]:
            endpoint = f"`magia/arenas/{sub['key'].replace('_', '-')}/leaderboard`"
            lines.append(f"| {category_data['label']} | {sub['label']} | {len(sub['models'])} | {endpoint} |")
    lines.append("")

    # 按类别生成排行榜
    for category_key, category_data in arena_data.items():
        lines.append(f"## {category_data['label']}")
        lines.append("")

        for sub in category_data["subcategories"]:
            models = sub["models"]
            # 按 conservative_rating 降序排序（ELO rating）
            sorted_models = sorted(
                models,
                key=lambda m: m.get("conservative_rating") or 0,
                reverse=True,
            )

            # 过滤掉没有实际比赛数据的模型（matches_played == 0）
            active_models = [m for m in sorted_models if m.get("matches_played", 0) > 0]
            inactive_models = [m for m in sorted_models if m.get("matches_played", 0) == 0]

            lines.append(f"### {sub['label']} ({len(active_models)} 活跃 / {len(inactive_models)} 待评)")
            lines.append("")
            lines.append("| # | 模型 | 公司 | Rating | 对战 | 胜率 | $/次 | 开源 |")
            lines.append("|---|------|------|--------|------|------|------|------|")

            for rank, model in enumerate(active_models[:30], 1):
                name = model.get("model_name", model.get("model_id", "?"))
                org = model.get("organization", "?")
                rating = model.get("conservative_rating")
                rating_str = f"{rating:.0f}" if rating is not None else "—"
                matches = model.get("matches_played", 0)
                win_rate = model.get("win_rate")
                win_rate_str = f"{win_rate:.1f}%" if win_rate is not None else "—"
                avg_price = model.get("avg_generation_price")
                price_str = f"${avg_price:.2f}" if avg_price else "—"
                open_flag = "✅" if model.get("is_open_source") else "❌"
                lines.append(
                    f"| {rank} | {name} | {org} | {rating_str} "
                    f"| {matches} | {win_rate_str} | {price_str} | {open_flag} |"
                )

            if len(active_models) > 30:
                lines.append(f"| ... | *还有 {len(active_models) - 30} 个活跃模型* | | | | | | |")
            lines.append("")

    # 跨类别统计
    lines.append("## 跨类别统计")
    lines.append("")

    org_stats = {}
    for category_data in arena_data.values():
        for sub in category_data["subcategories"]:
            for model in sub["models"]:
                org = model.get("organization", "unknown")
                if org not in org_stats:
                    org_stats[org] = {"total": 0, "categories": set()}
                org_stats[org]["total"] += 1
                org_stats[org]["categories"].add(category_data["label"])

    lines.append("| 公司 | 模型总数 | 覆盖类别 |")
    lines.append("|------|----------|----------|")
    for org, stats in sorted(org_stats.items(), key=lambda x: -x[1]["total"])[:20]:
        categories_str = ", ".join(sorted(stats["categories"]))
        lines.append(f"| {org} | {stats['total']} | {categories_str} |")
    lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("llm-stats.com 多页面数据提取")
    print("=" * 60)
    print()

    # 提取并合并三个页面的数据
    print("[Phase 1] 读取并提取各页面数据...")
    models, page_stats = extract_all_pages()

    if not models:
        print("\n[Error] 未从任何页面提取到模型数据")
        print("[Hint] 请确保以下文件至少存在一个：")
        for config in SOURCE_FILES.values():
            print(f"  - {config['file']}")
        sys.exit(1)

    print(f"\n[Phase 2] 合并完成：共 {len(models)} 个唯一模型")

    # 保存 JSON
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(models, f, ensure_ascii=False, indent=2)
    print(f"[Save] JSON: {JSON_OUTPUT}")

    # 生成 Markdown 排行榜
    markdown = generate_markdown(models, page_stats)
    with open(MD_OUTPUT, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"[Save] Markdown: {MD_OUTPUT}")

    # 打印 LLM 摘要
    recent = filter_recent_models(models, months_back=3)
    open_count = sum(1 for m in models if is_open_source(m))
    print(f"\n[Summary - LLM]")
    print(f"  总模型数: {len(models)}")
    print(f"  开源模型: {open_count}")
    print(f"  近3月新发: {len(recent)}")
    print()
    for model in recent[:8]:
        gpqa = f"GPQA={model['gpqa_score']:.1%}" if model.get("gpqa_score") else ""
        params = f"({format_params(model.get('params'))})" if model.get("params") else ""
        print(f"  {model.get('announcement_date', '?')} | {model['name']} {params} [{model.get('organization', '?')}] {gpqa}")
    if len(recent) > 8:
        print(f"  ... 还有 {len(recent) - 8} 个")

    # === 多模态排行榜（ZeroEval Arena API） ===
    print()
    print("=" * 60)
    print("[Phase 3] 提取多模态排行榜 (ZeroEval Arena API)...")
    arena_data, arena_total = extract_arena_api_data()

    if arena_data:
        print(f"\n[Phase 4] 多模态数据提取完成：{len(arena_data)} 大类, {arena_total} 个模型条目")

        # 保存多模态 JSON（扁平化为列表）
        all_arena_models = []
        for category_data in arena_data.values():
            for sub in category_data["subcategories"]:
                all_arena_models.extend(sub["models"])

        with open(MULTIMODAL_JSON_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(all_arena_models, f, ensure_ascii=False, indent=2)
        print(f"[Save] JSON: {MULTIMODAL_JSON_OUTPUT}")

        # 生成多模态 Markdown
        multimodal_md = generate_multimodal_markdown(arena_data)
        with open(MULTIMODAL_MD_OUTPUT, "w", encoding="utf-8") as f:
            f.write(multimodal_md)
        print(f"[Save] Markdown: {MULTIMODAL_MD_OUTPUT}")

        # 打印多模态摘要
        print(f"\n[Summary - Multimodal]")
        for category_key, category_data in arena_data.items():
            for sub in category_data["subcategories"]:
                active = sum(1 for m in sub["models"] if m.get("matches_played", 0) > 0)
                print(f"  {sub['label']}: {len(sub['models'])} 总 / {active} 活跃")
    else:
        print("\n[Info] 未找到多模态 API 响应文件，跳过")


if __name__ == "__main__":
    main()