"""llm-stats.com 数据源适配器（重点源）。

从 llm-stats.com 的多个页面抓取 HTML 源码，解析 Next.js RSC 内嵌数据，
提取 LLM 模型排行榜的结构化信息。

数据来源页面：
  - https://llm-stats.com              (AI Leaderboard 首页)
  - https://llm-stats.com/llm-leaderboard  (LLM 详情)
  - https://llm-stats.com/open-llm-leaderboard (Open LLM)
  - https://llm-stats.com/llm-updates   (时间线)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from ..ai import detect_system_proxy, make_ssl_context, should_skip_ssl_verify

PAGES = {
    "ai": {
        "url": "https://llm-stats.com",
        "label": "AI Leaderboard (首页)",
    },
    "llm": {
        "url": "https://llm-stats.com/llm-leaderboard",
        "label": "LLM Leaderboard (详情)",
    },
    "open": {
        "url": "https://llm-stats.com/open-llm-leaderboard",
        "label": "Open LLM Leaderboard",
    },
    "updates": {
        "url": "https://llm-stats.com/llm-updates",
        "label": "LLM Updates (时间线)",
    },
}

# ── Next.js RSC 数据解析 ──────────────────────────────────────

def _extract_models_from_next_f(html_content: str) -> Optional[list[dict]]:
    """从 Next.js self.__next_f.push 数据中提取模型列表。

    llm-stats.com 将数据通过 self.__next_f.push([1, "..."]) 内嵌在 HTML 中，
    其中包含 initialHomepageLLMModels / initialData / recentUpdates 字段。
    """
    pattern = r'self\.__next_f\.push\(\[1,"(.*?)"\]\)'
    chunks = re.findall(pattern, html_content, re.DOTALL)
    combined = "".join(chunks)
    combined = combined.replace('\\"', '"').replace('\\\\', '\\')

    candidate_keys = ['"initialHomepageLLMModels":', '"initialData":', '"recentUpdates":']
    idx = -1
    for key in candidate_keys:
        idx = combined.find(key)
        if idx >= 0:
            break

    if idx < 0:
        return None

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


def _merge_supplement(merged: dict, models: list[dict], page_key: str) -> None:
    """将一个页面的模型数据合并到已有字典中（补充缺失字段）。"""
    for model in models:
        model_id = model.get("model_id", "")
        if not model_id:
            continue
        cleaned = {k: v for k, v in model.items() if v != "$undefined"}
        if model_id not in merged:
            merged[model_id] = dict(cleaned)
            merged[model_id]["_source_pages"] = [page_key]
        else:
            merged[model_id]["_source_pages"].append(page_key)
            for field_key, field_val in cleaned.items():
                if field_key not in merged[model_id] or merged[model_id][field_key] is None:
                    merged[model_id][field_key] = field_val


def _format_params(params) -> str:
    """格式化参数量（如 236B）。"""
    if not params:
        return ""
    if params >= 1_000_000_000_000:
        return f"{params / 1_000_000_000_000:.0f}T"
    if params >= 1_000_000_000:
        return f"{params / 1_000_000_000:.0f}B"
    if params >= 1_000_000:
        return f"{params / 1_000_000:.0f}M"
    return str(params)


# ── HTTP 抓取 ─────────────────────────────────────────────────

async def _fetch_page(
    session: aiohttp.ClientSession,
    page_key: str,
    url: str,
    proxy: Optional[str],
) -> Optional[str]:
    """抓取单个页面 HTML。先直连，失败则走代理。"""
    for attempt_proxy in (None, proxy):
        if attempt_proxy is None:
            label = "直连"
        else:
            label = "代理"
        try:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=45)}
            if attempt_proxy:
                kwargs["proxy"] = attempt_proxy
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    logging.debug(f"[llmstats] {page_key} {label}成功 ({len(html)} bytes)")
                    return html
                logging.debug(f"[llmstats] {page_key} {label} HTTP {resp.status}")
        except Exception as exc:
            logging.debug(f"[llmstats] {page_key} {label}失败: {exc}")
    return None


# ── 模型 → record 转换 ───────────────────────────────────────

_CN_ORGS = {
    "alibaba", "qwen", "baidu", "bytedance", "tencent", "deepseek",
    "zhipu", "minimax", "moonshot", "stepfun", "sensetime", "01.ai",
    "iflytek", "kuaishou", "huawei", "xiaomi", "vivo",
}

def _is_domestic(org_id: str, org_country: str) -> bool:
    org_lower = (org_id or "").lower()
    if org_country:
        return org_country.upper() == "CN"
    return any(cn in org_lower for cn in _CN_ORGS)


def _model_to_record(model: dict, fetched_at_iso: str) -> dict:
    """将合并后的 llmstats 模型转换为标准 record 格式。"""
    name = model.get("name", "")
    company = model.get("organization", "")
    model_id = model.get("model_id", "")
    org_id = model.get("organization_id", "")
    org_country = model.get("organization_country", "")
    publish_time = model.get("announcement_date") or model.get("release_date")

    description_parts = []
    params = model.get("params")
    if params:
        description_parts.append(f"参数量: {_format_params(params)}")
    gpqa = model.get("gpqa_score")
    if gpqa is not None:
        description_parts.append(f"GPQA: {gpqa:.1%}" if gpqa <= 1 else f"GPQA: {gpqa}")
    swe = model.get("swe_bench_verified_score")
    if swe is not None:
        description_parts.append(f"SWE: {swe:.1%}" if swe <= 1 else f"SWE: {swe}")
    hle = model.get("hle_score")
    if hle is not None:
        description_parts.append(f"HLE: {hle:.1%}" if hle <= 1 else f"HLE: {hle}")
    description = " · ".join(description_parts) or f"{company} 的 {name}"

    return {
        "source": "llmstats",
        "raw_name": name,
        "company": company,
        "title": name,
        "description": description,
        "url": f"https://llm-stats.com/models/{model_id}" if model_id else "https://llm-stats.com",
        "publish_time": publish_time,
        "raw": {
            "model_id": model_id,
            "organization_id": org_id,
            "organization_country": org_country,
            "params": params,
            "context": model.get("context"),
            "input_price": model.get("input_price"),
            "output_price": model.get("output_price"),
            "is_open_source": model.get("is_open_source"),
            "multimodal": model.get("multimodal"),
            "license": model.get("license"),
            "is_moe": model.get("is_moe"),
            "gpqa_score": gpqa,
            "swe_bench_verified_score": swe,
            "hle_score": hle,
            "source_pages": model.get("_source_pages", []),
            "domestic": _is_domestic(org_id, org_country),
            "fetched_at": fetched_at_iso,
        },
    }


# ── 公开接口 ──────────────────────────────────────────────────

async def fetch(
    *,
    proxy: Optional[str] = None,
    recent_months: int = 3,
) -> list[dict]:
    """抓取 llm-stats.com 所有页面，合并后返回标准化 record 列表。

    Args:
        proxy: HTTP 代理地址
        recent_months: 只返回最近 N 个月发布的模型（0 表示全部）
    """
    if not proxy:
        proxy = detect_system_proxy()
    skip_ssl = should_skip_ssl_verify()
    connector = aiohttp.TCPConnector(
        ssl=make_ssl_context(verify=not skip_ssl), limit=8,
    )
    fetched_at_iso = datetime.now(timezone.utc).isoformat()

    # 并发抓取 4 个页面
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = {
            key: _fetch_page(session, key, cfg["url"], proxy)
            for key, cfg in PAGES.items()
        }
        results = {}
        for key, coro in tasks.items():
            results[key] = await coro

    # 解析每个页面
    page_models: dict[str, list[dict]] = {}
    for key, html in results.items():
        if not html:
            logging.warning(f"[llmstats] {PAGES[key]['label']} 抓取失败，跳过")
            continue
        models = _extract_models_from_next_f(html)
        if models:
            logging.info(f"[llmstats] {PAGES[key]['label']}: {len(models)} 个模型")
            page_models[key] = models
        else:
            logging.warning(f"[llmstats] {PAGES[key]['label']}: 未提取到模型数据")

    if not page_models:
        logging.error("[llmstats] 所有页面均未提取到数据")
        return []

    # 按优先级合并（LLM 详情页字段最丰富 → AI 首页 → Open LLM → Updates）
    merged: dict[str, dict] = {}
    for model in page_models.get("llm", []):
        model_id = model.get("model_id", "")
        if model_id:
            merged[model_id] = dict(model)
            merged[model_id]["_source_pages"] = ["llm"]
    _merge_supplement(merged, page_models.get("ai", []), "ai")
    _merge_supplement(merged, page_models.get("open", []), "open")
    _merge_supplement(merged, page_models.get("updates", []), "updates")

    # 时间过滤
    all_models = sorted(
        merged.values(),
        key=lambda m: m.get("announcement_date") or m.get("release_date") or "",
        reverse=True,
    )

    if recent_months > 0:
        now = datetime.now()
        cutoff_year = now.year
        cutoff_month = now.month - recent_months
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        cutoff_str = f"{cutoff_year:04d}-{cutoff_month:02d}-01"

        filtered = []
        for model in all_models:
            date_str = model.get("announcement_date") or model.get("release_date") or ""
            if date_str >= cutoff_str:
                filtered.append(model)
        all_models = filtered

    # 转换为标准 record 格式
    records = [_model_to_record(m, fetched_at_iso) for m in all_models]
    logging.info(f"[llmstats] 共产出 {len(records)} 条模型记录（近 {recent_months} 个月）")
    return records
