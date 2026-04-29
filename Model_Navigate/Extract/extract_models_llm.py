"""
基于 LLM API 自动从腾讯研究院文章全文中提取模型信息。
===========================================================
次级方案：当用户无法在对话中让 AI 手动提取时，可通过本脚本自动提取。

用法:
    python extract_models_llm.py                          # 提取所有文章
    python extract_models_llm.py --since 20260417         # 只提取指定时间段
    python extract_models_llm.py --dry-run                # 预览，不调用 LLM

环境变量（或上级目录 .env 文件）:
    LLM_API_KEY=sk-xxx          # LLM API Key（默认用 DashScope 百炼）
    LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
    LLM_MODEL=qwen-plus         # 推荐 qwen-plus（便宜且够用）

依赖:
    pip install requests pandas openpyxl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ── 路径 ──
ROOT = Path(__file__).parent.parent  # action/
EXTRACT_DIR = Path(__file__).parent  # action/Extract/
ARTICLES_DIR = EXTRACT_DIR / "articles"
RESULT_XLSX = EXTRACT_DIR / "TXCrawl_result.xlsx"
EXISTING_XLSX = ROOT / "data" / "Object-Models-Updated.xlsx"

# ── LLM 提取 Prompt ──
EXTRACT_PROMPT = """你是一名 AI 模型追踪分析师。请从以下腾讯研究院 AI 速递文章中，提取所有**在本文报道时间窗口内新发布/新版本/新上线的具体 AI 模型**。

## 核心原则：只提取"新发布"，不提取"被提及"

AI 速递文章中会大量提及已有的模型/产品作为背景信息。你必须严格区分：
- ✅ 提取：文章报道的**新发布、新版本、新上线、新开源**的模型
- ❌ 不提取：文章中作为背景/对比/引用提及的**已有模型或产品**

## 排除清单（绝对不要提取以下类型）

1. **没有版本号的产品/平台泛称**：
   如"ChatGPT"、"Cursor"、"豆包"、"元宝"、"千问"、"即梦"、"Copilot"
   → 但如果有具体版本号，必须提取！例如：
     ✅ GPT-5.5、GPT-5.5 Pro、DeepSeek-V4-Pro-Max、DeepSeek-V4-Flash-Max、Cursor 3.0
     ❌ ChatGPT（泛称）、Cursor（泛称）、豆包（泛称）
2. **品牌名/公司名当模型名**：如"千问 (阿里巴巴)"→ 不是具体模型，应写"Qwen3.6-27B"
3. **纯硬件发布**、**纯算法论文**、**纯商业事件**（投融资/人事变动）、**benchmark/评测工具**
4. **发布时间明显不在文章日期附近**的旧模型（如文章是2026年4月但模型2025年发布）

## 关键提醒：有版本号 = 必须提取
只要模型名称中包含版本号/型号（如V4、5.5、3.0、27B等），就是具体模型，必须提取。
不要因为品牌名（如GPT、DeepSeek）看起来"很常见"就跳过——重点看有没有版本号。

## 模型名称规范

- 必须使用**官方名称 + 具体版本号/型号**，不能用泛称
- 正确：`DeepSeek-V4-Pro-Max`、`Claude Opus 4.7`、`Qwen3.6-27B`、`可灵AI视频3.0`
- 错误：`千问`、`豆包`、`元宝`、`ChatGPT`、`Cursor`、`Sora`（这些是产品泛称）
- 如果只有泛称没有版本号，**不要提取**

## 提取字段（不确定的留空字符串 ""）

- model_name: 模型名称（官方名称+版本号，不用泛称）
- company: 发布公司/组织
- domestic: 国内/国外
- open_source: 开源/闭源/未知
- size: 参数量/尺寸（如 "70B"、"1.8T"；不确定则留空）
- model_type: 基座/领域/微调/多模态/智能体/集成产品/代码/语音/视频/图像/具身
- can_reason: thinking/non-thinking/未知
- task_type: 任务类型（通用对话/代码生成/图像生成/视频生成/语音合成 等）
- release_date: 实际发布日期（YYYY-MM-DD）。从正文中找"X月X日发布""昨日上线"等时间锚点推算。如无明确时间则留空。
- website: 官网/GitHub/论文 URL（从文章中提取，不确定则留空）
- brief: 一句话描述（20字以内）

请严格以 JSON 数组格式输出，不要输出其他内容。如果文章中没有新发布的模型，输出空数组 []。

示例：
[
  {{"model_name": "Claude Opus 4.7", "company": "Anthropic", "domestic": "国外", "open_source": "闭源", "size": "", "model_type": "基座", "can_reason": "thinking", "task_type": "通用对话", "release_date": "2026-04-15", "website": "https://claude.ai", "brief": "Anthropic旗舰模型"}},
  {{"model_name": "Qwen3.6-27B", "company": "阿里", "domestic": "国内", "open_source": "开源", "size": "27B", "model_type": "基座", "can_reason": "thinking", "task_type": "通用对话,代码生成", "release_date": "", "website": "https://github.com/QwenLM/Qwen3", "brief": "阿里开源27B推理模型"}}
]

---
文章日期（仅作参考锚点）：{article_date}
文章内容：
{article_text}
"""


def load_env():
    """加载 .env 文件。"""
    for env_path in [EXTRACT_DIR / ".env", ROOT / ".env", ROOT.parent / "models-tracker" / ".env"]:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), value)


def get_llm_config() -> tuple[str, str, str]:
    """获取主 LLM API 配置（kuai API — Claude Opus 4.6）。"""
    api_key = os.environ.get("KUAI_API_KEY", "")
    api_base = os.environ.get("KUAI_API_BASE", "https://api.kuai.host/v1")
    model = os.environ.get("KUAI_MODEL", "claude-opus-4-6")
    return api_key, api_base, model

def get_fallback_llm_config() -> tuple[str, str, str]:
    """获取备选 LLM API 配置（DashScope 百炼 — Qwen）。"""
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("TRACKER_FIELD_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or ""
    )
    api_base = (
        os.environ.get("LLM_API_BASE")
        or os.environ.get("TRACKER_FIELD_API_BASE")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model = os.environ.get("LLM_MODEL") or "qwen-plus"
    return api_key, api_base, model


def _call_llm_once(article_text: str, api_key: str, api_base: str, model: str,
                   article_date: str = "") -> list[dict]:
    """调用单个 LLM API 端点提取模型信息。"""
    prompt = EXTRACT_PROMPT.format(
        article_text=article_text[:8000],
        article_date=article_date or "未知",
    )

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4000,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()

    resp_json = resp.json()

    # 兼容多种 API 返回格式（OpenAI / DashScope / kuai）
    content = ""
    if "choices" in resp_json and resp_json["choices"]:
        choice = resp_json["choices"][0]
        if isinstance(choice, dict) and "message" in choice:
            content = choice["message"].get("content", "")
        elif isinstance(choice, dict) and "text" in choice:
            content = choice["text"]
    elif "output" in resp_json:
        # DashScope 老版本格式
        output = resp_json["output"]
        if isinstance(output, dict):
            content = output.get("text", "") or output.get("content", "")
        elif isinstance(output, str):
            content = output

    if not content:
        raise ValueError(f"无法从 API 响应中提取内容，响应结构: {list(resp_json.keys())}")

    # 从 LLM 回复中提取 JSON 数组
    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if json_match:
        models = json.loads(json_match.group())
        # 校验并标准化每个模型对象
        validated = []
        for item in models:
            if not isinstance(item, dict):
                continue
            # 容错：LLM 可能返回 "name" 而非 "model_name"
            if "model_name" not in item:
                for alt_key in ("name", "模型名称", "model", "modelName"):
                    if alt_key in item:
                        item["model_name"] = item[alt_key]
                        break
            if item.get("model_name"):
                validated.append(item)
        return validated
    return []

def call_llm(article_text: str, api_key: str, api_base: str, model: str,
             article_date: str = "") -> list[dict]:
    """调用 LLM API 提取模型信息，主 API 失败时自动 fallback 到备选 API。"""
    # 主 API 调用（kuai — Claude Opus 4.6）
    start = time.time()
    try:
        result = _call_llm_once(article_text, api_key, api_base, model, article_date)
        elapsed = time.time() - start
        if result:
            print(f"    ✅ {model} 提取到 {len(result)} 个模型（{elapsed:.1f}s）")
            return result
    except requests.exceptions.HTTPError as exc:
        elapsed = time.time() - start
        print(f"    ⚠️ 主 API ({model}) 失败（{elapsed:.1f}s）: {exc}")
        if exc.response is not None:
            print(f"    响应: {exc.response.text[:200]}")
    except json.JSONDecodeError as exc:
        elapsed = time.time() - start
        print(f"    ⚠️ 主 API ({model}) 输出非法 JSON（{elapsed:.1f}s）: {exc}")
    except Exception as exc:
        elapsed = time.time() - start
        print(f"    ⚠️ 主 API ({model}) 调用失败（{elapsed:.1f}s）: {exc}")

    # Fallback 到备选 API（DashScope — Qwen）
    fb_key, fb_base, fb_model = get_fallback_llm_config()
    if fb_key and fb_key != api_key:
        print(f"    🔄 Fallback 到备选 API ({fb_model})...")
        fb_start = time.time()
        try:
            result = _call_llm_once(article_text, fb_key, fb_base, fb_model, article_date)
            fb_elapsed = time.time() - fb_start
            if result:
                print(f"    ✅ {fb_model} 提取到 {len(result)} 个模型（{fb_elapsed:.1f}s）")
            return result
        except Exception as exc:
            fb_elapsed = time.time() - fb_start
            print(f"    ❌ 备选 API ({fb_model}) 也失败（{fb_elapsed:.1f}s）: {exc}")

    return []


def load_articles(since_int: int | None = None, until_int: int | None = None) -> list[dict]:
    """从 Extract/articles/ 目录加载文章。"""
    articles = []
    if not ARTICLES_DIR.exists():
        return articles

    for txt_file in sorted(ARTICLES_DIR.glob("*.txt")):
        content = txt_file.read_text(encoding="utf-8")

        # 解析文件头
        title = ""
        link = ""
        seq = 0
        body_lines = []
        header_done = False
        for line in content.split("\n"):
            if not header_done:
                if line.startswith("标题:"):
                    title = line[3:].strip()
                elif line.startswith("链接:"):
                    link = line[3:].strip()
                elif line.startswith("序号:"):
                    try:
                        seq = int(line[3:].strip())
                    except ValueError:
                        pass
                elif line.startswith("=" * 10):
                    header_done = True
            else:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()
        if not body or len(body) < 50:
            continue

        # 从标题中提取日期
        date_match = re.search(r'(\d{8})', title)
        article_date_int = int(date_match.group(1)) if date_match else 0

        # 时间筛选
        if since_int and article_date_int and article_date_int < since_int:
            continue
        if until_int and article_date_int and article_date_int > until_int:
            continue

        articles.append({
            "序号": seq,
            "标题": title,
            "链接": link,
            "日期": article_date_int,
            "全文": body,
            "文件": txt_file.name,
        })

    return articles


def normalize_name(name: str) -> str:
    """标准化模型名称用于去重匹配。"""
    name_lower = name.lower().strip()
    name_lower = re.sub(r'\s*[\(（].*?[\)）]', '', name_lower)
    name_lower = re.sub(r'\s+', ' ', name_lower).strip()
    return name_lower


def load_existing_models() -> set[str]:
    """加载已追踪的模型名称。"""
    existing = set()
    if EXISTING_XLSX.exists():
        df = pd.read_excel(EXISTING_XLSX, engine="openpyxl")
        name_col = "模型名称"
        if name_col in df.columns:
            for name in df[name_col].dropna():
                existing.add(normalize_name(str(name)))
    return existing


def _normalize_for_match(name: str) -> str:
    """更宽松的标准化，用于交叉核实匹配。"""
    name = name.lower().strip()
    name = re.sub(r'[\s\-_\.]+', '', name)
    name = re.sub(r'[\(（].*?[\)）]', '', name)
    return name


def cross_verify_with_llmstats(models: list[dict]) -> list[dict]:
    """将 LLM 提取的模型与 llmstats JSON 交叉核实，补全缺失字段。

    对于匹配到的模型：
    - 补全缺失的 size（从 params 字段）
    - 补全缺失的 release_date（从 release_date/announcement_date）
    - 补全缺失的 website（构造 llm-stats.com 链接）
    - 核实情况升级为 "腾讯研究院+llmstats交叉核实"
    """
    llmstats_json = ROOT / "Crawl" / "Arena_x" / "llmstats_models.json"
    if not llmstats_json.exists():
        print("\n  ⚠️ llmstats JSON 不存在，跳过交叉核实")
        return models

    with open(llmstats_json, "r", encoding="utf-8") as f:
        llmstats_data = json.load(f)

    # 构建 llmstats 索引（标准化名称 → 模型数据）
    llmstats_index: dict[str, dict] = {}
    for item in llmstats_data:
        name = item.get("name", "")
        if name:
            llmstats_index[_normalize_for_match(name)] = item
        model_id = item.get("model_id", "")
        if model_id:
            llmstats_index[_normalize_for_match(model_id)] = item

    matched_count = 0
    for model_info in models:
        model_name = model_info.get("model_name", "")
        if not model_name:
            continue

        norm_name = _normalize_for_match(model_name)

        # 精确匹配
        matched = llmstats_index.get(norm_name)

        # 子串匹配（一方包含另一方）
        if not matched:
            for ls_name, ls_data in llmstats_index.items():
                if len(norm_name) > 4 and len(ls_name) > 4:
                    if norm_name in ls_name or ls_name in norm_name:
                        matched = ls_data
                        break

        if not matched:
            continue

        matched_count += 1

        # 补全缺失的 size
        if not model_info.get("size"):
            params = matched.get("params")
            if params:
                if params >= 1_000_000_000_000:
                    model_info["size"] = f"{params / 1_000_000_000_000:.0f}T"
                elif params >= 1_000_000_000:
                    model_info["size"] = f"{params / 1_000_000_000:.0f}B"
                elif params >= 1_000_000:
                    model_info["size"] = f"{params / 1_000_000:.0f}M"

        # 补全缺失的 release_date
        if not model_info.get("release_date"):
            ls_date = matched.get("release_date") or matched.get("announcement_date") or ""
            if ls_date:
                model_info["release_date"] = ls_date

        # 补全缺失的 website
        if not model_info.get("website"):
            model_id = matched.get("model_id", "")
            if model_id:
                model_info["website"] = f"https://llm-stats.com/models/{model_id}"

        # 升级核实情况
        model_info["_verified_by"] = "腾讯研究院+llmstats交叉核实"

    print(f"\n  🔗 交叉核实: {matched_count}/{len(models)} 个模型匹配到 llmstats 数据")
    return models


# ── 已知产品/平台泛称黑名单（不应被录入，除非有具体新版本号）──
_GENERIC_PRODUCT_NAMES = {
    "chatgpt", "cursor", "copilot", "豆包", "元宝", "千问", "即梦",
    "manus", "codebuddy", "sora", "claude code", "devin", "replit",
    "钉钉悟空", "飞书aily", "通义千问", "文心一言", "kimi", "智谱清言",
    "openai codex", "github copilot", "base44", "快乐小马", "龙虾",
    "chatgpt images", "deep research",
}


def _is_generic_product_name(name: str) -> bool:
    """检查模型名称是否为不含版本号的产品泛称。"""
    normalized = name.lower().strip()
    # 精确匹配泛称黑名单
    if normalized in _GENERIC_PRODUCT_NAMES:
        return True
    # 检查是否有版本号特征（数字+点、vN、数字后缀等）
    # 如果完全没有任何数字，且在黑名单的模糊匹配范围内，也视为泛称
    has_version = bool(re.search(r'\d', normalized))
    if not has_version:
        for generic in _GENERIC_PRODUCT_NAMES:
            if normalized == generic or (len(normalized) > 3 and normalized in generic):
                return True
    return False


def write_to_main_excel(untracked_models: list[dict], existing_names: set[str],
                        since_int: int | None = None, until_int: int | None = None):
    """将未追踪的新模型回写到主表格 Object-Models-Updated.xlsx。

    增强过滤：
    1. 排除已知产品泛称（无版本号的 ChatGPT/Cursor/豆包 等）
    2. 排除 release_date 不在时间窗口内的旧模型
    3. 与已有模型名称去重
    """
    from datetime import datetime as _dt

    if not untracked_models:
        print("\n  📭 无新模型需要写入主表格")
        return 0

    if not EXISTING_XLSX.exists():
        print(f"\n  ❌ 主表格不存在: {EXISTING_XLSX}")
        return 0

    df = pd.read_excel(EXISTING_XLSX, engine="openpyxl")
    now_str = _dt.now().strftime("%Y-%m-%d")

    new_rows = []
    merge_updates = []  # (normalized_name, model_info, release_date) — 已存在但需要补全字段的模型
    filtered_generic = []
    filtered_date = []

    for model_info in untracked_models:
        model_name = model_info.get("model_name", "").strip()
        if not model_name:
            continue

        # 过滤 1：排除产品泛称
        if _is_generic_product_name(model_name):
            filtered_generic.append(model_name)
            continue

        normalized = normalize_name(model_name)
        is_existing = normalized in existing_names
        existing_names.add(normalized)

        # 发布日期：优先取 LLM 从正文提取的 release_date，fallback 到文章日期
        release_date = model_info.get("release_date", "").strip()
        if not release_date:
            source_date = model_info.get("source_date", "")
            if source_date and len(str(source_date)) == 8:
                date_str = str(source_date)
                release_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

        # 过滤 2：如果有明确的 release_date 且不在时间窗口内，则跳过
        if release_date and since_int and until_int:
            try:
                release_int = int(release_date.replace("-", "").replace("/", "")[:8])
                if release_int < since_int or release_int > until_int:
                    filtered_date.append(f"{model_name} ({release_date})")
                    continue
            except (ValueError, TypeError):
                pass

        if is_existing:
            # 已存在的模型：合并更新空字段（覆盖而非跳过）
            merge_updates.append((normalized, model_info, release_date))
        else:
            row = {
                "模型名称": model_name,
                "公司": model_info.get("company", ""),
                "国内外": model_info.get("domestic", ""),
                "开闭源": model_info.get("open_source", ""),
                "尺寸": model_info.get("size", ""),
                "类型": model_info.get("model_type", ""),
                "能否推理": model_info.get("can_reason", ""),
                "任务类型": model_info.get("task_type", ""),
                "官网": model_info.get("website", ""),
                "备注": model_info.get("brief", ""),
                "模型发布时间": release_date,
                "记录创建时间": now_str,
                "是否新增": "New",
                "核实情况": model_info.get("_verified_by", "腾讯研究院AI速递LLM自动提取"),
            }
            new_rows.append(row)

    # 打印过滤日志
    if filtered_generic:
        print(f"\n  🚫 过滤掉 {len(filtered_generic)} 个产品泛称: {', '.join(filtered_generic[:10])}")
    if filtered_date:
        print(f"  🚫 过滤掉 {len(filtered_date)} 个时间窗口外模型: {', '.join(filtered_date[:10])}")

    # 处理已存在模型的字段合并更新（覆盖空字段）
    merged_count = 0
    if merge_updates and "模型名称" in df.columns:
        # 构建标准化名称 → 行索引的映射
        name_to_idx: dict[str, int] = {}
        for idx, row in df.iterrows():
            raw_name = str(row.get("模型名称", ""))
            if raw_name and raw_name != "nan":
                name_to_idx[normalize_name(raw_name)] = idx

        # 定义可覆盖的字段映射（LLM 字段 → Excel 列名）
        field_map = {
            "company": "公司", "domestic": "国内外", "open_source": "开闭源",
            "size": "尺寸", "model_type": "类型", "can_reason": "能否推理",
            "task_type": "任务类型", "website": "官网", "brief": "备注",
        }

        for norm_name, model_info, release_date in merge_updates:
            row_idx = name_to_idx.get(norm_name)
            if row_idx is None:
                continue
            updated_fields = []
            for llm_key, col_name in field_map.items():
                new_val = model_info.get(llm_key, "").strip()
                if not new_val:
                    continue
                if col_name not in df.columns:
                    continue
                old_val = str(df.at[row_idx, col_name]).strip()
                if old_val in ("", "nan", "None", "未知"):
                    df.at[row_idx, col_name] = new_val
                    updated_fields.append(col_name)
            # 补全发布时间
            if release_date:
                if "模型发布时间" in df.columns:
                    old_date = str(df.at[row_idx, "模型发布时间"]).strip()
                    if old_date in ("", "nan", "None"):
                        df.at[row_idx, "模型发布时间"] = release_date
                        updated_fields.append("模型发布时间")
            if updated_fields:
                merged_count += 1
                model_name = model_info.get("model_name", norm_name)
                print(f"  🔄 合并更新: {model_name} ← {', '.join(updated_fields)}")

    if merged_count > 0:
        print(f"\n  🔄 合并更新了 {merged_count} 个已有模型的空字段")

    if not new_rows and merged_count == 0:
        print("\n  📭 无新模型需要写入，也无已有模型需要更新")
        return 0

    try:
        if new_rows:
            df_new = pd.DataFrame(new_rows)
            df = pd.concat([df, df_new], ignore_index=True)
        df.to_excel(EXISTING_XLSX, index=False, engine="openpyxl")
        print(f"\n  📊 主表格已更新: {EXISTING_XLSX}")
        print(f"     原有: {len(df) - len(new_rows)} 行")
        if new_rows:
            print(f"     新增: {len(new_rows)} 行")
        if merged_count:
            print(f"     合并更新: {merged_count} 行")
        print(f"     合计: {len(df)} 行")
        for row in new_rows:
            print(f"     + [{row['公司']}] {row['模型名称']} — {row['备注'][:30]}")
        return len(new_rows) + merged_count
    except PermissionError:
        print(f"\n  ❌ 主表格被占用（请关闭 Excel）: {EXISTING_XLSX}")
        return 0
    except Exception as exc:
        print(f"\n  ❌ 写入主表格失败: {exc}")
        return 0

def main():
    parser = argparse.ArgumentParser(description="LLM 自动提取腾讯研究院文章中的模型信息")
    parser.add_argument("--since", type=str, help="起始日期 (YYYYMMDD)")
    parser.add_argument("--until", type=str, help="截止日期 (YYYYMMDD)")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不调用 LLM")
    parser.add_argument("--write-excel", action="store_true",
                        help="将未追踪的新模型回写到 Object-Models-Updated.xlsx")
    parser.add_argument("--list", action="store_true", dest="list_only",
                        help="仅列出符合条件的文章（不调用 LLM）")
    parser.add_argument("--index", type=int, default=None,
                        help="仅处理第 N 篇文章（从 1 开始），配合 --list 使用")
    args = parser.parse_args()

    since_int = int(args.since) if args.since else None
    until_int = int(args.until) if args.until else None

    load_env()
    api_key, api_base, model = get_llm_config()

    print("📚 LLM 自动提取腾讯研究院模型信息")
    print(f"  API: {api_base}")
    print(f"  模型: {model}")
    print(f"  时间: {since_int or '全部'} ~ {until_int or '全部'}")
    if args.dry_run:
        print("  模式: 🔍 DRY-RUN")
    print()

    if not api_key and not args.dry_run:
        print("  ❌ 未配置 LLM API Key")
        print("  💡 请设置环境变量 LLM_API_KEY 或在 .env 中配置")
        print("  💡 也可使用 TRACKER_FIELD_API_KEY 或 DASHSCOPE_API_KEY")
        return

    # 加载文章
    articles = load_articles(since_int, until_int)
    if not articles:
        print("  📭 未找到符合条件的文章")
        print(f"  💡 请确认 {ARTICLES_DIR} 目录下有 .txt 文件")
        return

    print(f"  📄 找到 {len(articles)} 篇文章")

    # --list 模式：仅列出文章
    if args.list_only:
        for i, a in enumerate(articles, 1):
            print(f"  [{i}] {a['标题']}（{len(a['全文'])} 字）")
        print(f"\n  💡 使用 --index N 处理单篇文章")
        return

    # --index 模式：仅处理指定文章
    if args.index is not None:
        if args.index < 1 or args.index > len(articles):
            print(f"  ❌ --index {args.index} 超出范围（共 {len(articles)} 篇）")
            return
        articles = [articles[args.index - 1]]
        print(f"  🎯 仅处理第 {args.index} 篇")

    # 加载已追踪模型
    existing_models = load_existing_models()
    print(f"  📊 已追踪 {len(existing_models)} 个模型")
    print()

    # 逐篇提取
    all_extracted = []
    article_results = []
    total_start = time.time()
    elapsed_per_article = []

    for idx, article in enumerate(articles, 1):
        title = article["标题"]
        body = article["全文"]
        date_int = article["日期"]
        article_start = time.time()

        # 进度条
        done_ratio = (idx - 1) / len(articles)
        bar_filled = int(done_ratio * 20)
        bar_str = f"[{'#' * bar_filled}{'.' * (20 - bar_filled)}]"
        eta_str = ""
        if elapsed_per_article:
            avg_sec = sum(elapsed_per_article) / len(elapsed_per_article)
            remaining = avg_sec * (len(articles) - idx + 1)
            eta_str = f" ETA ~{remaining:.0f}s"

        print(f"\n  {bar_str} [{idx}/{len(articles)}]{eta_str}")
        print(f"  {title}（{len(body)} 字）")

        if args.dry_run:
            print(f"    🔍 DRY-RUN: 跳过 LLM 调用")
            article_results.append({
                "序号": article["序号"],
                "标题": title,
                "提及的模型": "(dry-run)",
                "未追踪到的模型": "(dry-run)",
            })
            elapsed_per_article.append(time.time() - article_start)
            continue

        # 调用 LLM（传入文章日期作为锚点参考）
        article_date_str = ""
        if date_int and len(str(date_int)) == 8:
            d = str(date_int)
            article_date_str = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        models = call_llm(body, api_key, api_base, model, article_date=article_date_str)

        if not models:
            print(f"    ⚠️ 未提取到模型")
            article_results.append({
                "序号": article["序号"],
                "标题": title,
                "提及的模型": "无明确新模型",
                "未追踪到的模型": "",
            })
            elapsed_per_article.append(time.time() - article_start)
            continue

        # 分类：已追踪 vs 未追踪
        mentioned_names = []
        untracked_names = []

        for model_info in models:
            model_name = model_info.get("model_name", "")
            if not model_name:
                continue

            mentioned_names.append(model_name)
            normalized = normalize_name(model_name)

            is_tracked = normalized in existing_models
            if not is_tracked:
                # 模糊匹配
                for existing in existing_models:
                    if len(normalized) > 4 and len(existing) > 4:
                        if normalized in existing or existing in normalized:
                            is_tracked = True
                            break

            if not is_tracked:
                untracked_names.append(model_name)
                model_info["_untracked"] = True

            all_extracted.append({
                **model_info,
                "source_article": title,
                "source_date": date_int,
            })

        tracked_count = len(mentioned_names) - len(untracked_names)
        print(f"    ✅ 提取 {len(mentioned_names)} 个模型（已追踪 {tracked_count}，未追踪 {len(untracked_names)}）")

        article_results.append({
            "序号": article["序号"],
            "标题": title,
            "提及的模型": "\n".join(mentioned_names),
            "未追踪到的模型": "\n".join(untracked_names) if untracked_names else "均已追踪",
        })

        elapsed_per_article.append(time.time() - article_start)

        # 礼貌调用间隔
        if idx < len(articles):
            time.sleep(1)

    # ── 保存结果 ──
    if not args.dry_run and article_results:
        # 保存文章级结果到 TXCrawl_result.xlsx
        df_result = pd.DataFrame(article_results)
        df_result.to_excel(RESULT_XLSX, index=False, engine="openpyxl")
        print(f"\n  💾 文章级结果: {RESULT_XLSX}")

        # 保存完整提取结果到 JSON
        extracted_json_path = EXTRACT_DIR / "extracted_models_llm.json"
        with open(extracted_json_path, "w", encoding="utf-8") as f:
            json.dump(all_extracted, f, ensure_ascii=False, indent=2)
        print(f"  💾 完整提取结果: {extracted_json_path}")

    # ── 汇总 ──
    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  汇总（总耗时 {total_elapsed:.1f}s）")
    print(f"{'='*60}")

    if args.dry_run:
        print(f"  📄 文章数: {len(articles)}")
        print(f"  🔍 DRY-RUN 模式，未调用 LLM")
        return

    untracked_all = {}
    for model_info in all_extracted:
        if model_info.get("_untracked"):
            key = normalize_name(model_info["model_name"])
            if key not in untracked_all:
                untracked_all[key] = model_info

    print(f"  📄 文章数: {len(articles)}")
    print(f"  🤖 提取到的模型总数: {len(all_extracted)}")
    print(f"  🆕 未追踪的新模型: {len(untracked_all)}")

    if untracked_all:
        print(f"\n  未追踪模型列表:")
        for idx, (_, info) in enumerate(sorted(untracked_all.items()), 1):
            name = info["model_name"]
            company = info.get("company", "")
            brief = info.get("brief", "")
            mtype = info.get("model_type", "")
            print(f"    {idx}. {name} ({company}) [{mtype}] — {brief}")

    # ── 交叉核实（与 llmstats 数据匹配，补全缺失字段）──
    if untracked_all:
        untracked_list = list(untracked_all.values())
        untracked_list = cross_verify_with_llmstats(untracked_list)
    else:
        untracked_list = []

    # ── 回写主表格（需 --write-excel 参数）──
    if args.write_excel and untracked_list:
        written = write_to_main_excel(untracked_list, existing_models, since_int, until_int)
        if written > 0:
            print(f"\n  ✅ 已将 {written} 个新模型写入主表格")
        else:
            print(f"\n  ⚠️ 未能写入主表格（可能已存在或文件被占用）")
    elif args.write_excel and not untracked_all:
        print(f"\n  📭 无未追踪模型，无需写入主表格")
    elif not args.write_excel and untracked_all:
        print(f"\n  💡 使用 --write-excel 参数可将 {len(untracked_all)} 个新模型自动写入主表格")

    print(f"\n  💡 主方案：在对话中让 AI Copilot 读取文章并提取（更准确）")
    print(f"  💡 次级方案：本脚本通过 LLM API 自动提取（更快速）")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
