"""ZeroEval Arena API 数据源适配器。

ZeroEval 是 llm-stats.com 的多模态排行榜后端，公开 API 端点：
  - /api/text-to-image
  - /api/image-to-image
  - /api/text-to-video
  - /api/embeddings
  - /api/text-to-speech
  - /api/speech-to-text

返回的 JSON 包含模型在各项任务的 ELO 评分、参与对战次数、模型元数据。
本适配器从这些响应中提取"模型实体"，作为模型/智能体追踪的硬数据源。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from ..ai import detect_system_proxy, make_ssl_context, should_skip_ssl_verify

ZEROEVAL_BASE = "https://api.zeroeval.com"

ENDPOINTS = {
    "text-to-image": "/v1/leaderboards/text-to-image",
    "image-to-image": "/v1/leaderboards/image-to-image",
    "text-to-video": "/v1/leaderboards/text-to-video",
    "embeddings": "/v1/leaderboards/embeddings",
    "text-to-speech": "/v1/leaderboards/text-to-speech",
    "speech-to-text": "/v1/leaderboards/speech-to-text",
}

# modality 到统一类目的映射
MODALITY_CATEGORY = {
    "text-to-image": "图像",
    "image-to-image": "图像",
    "text-to-video": "视频",
    "embeddings": "多任务",
    "text-to-speech": "音频",
    "speech-to-text": "音频",
}


async def _fetch_endpoint(
    session: aiohttp.ClientSession,
    name: str,
    path: str,
    proxy: Optional[str] = None,
) -> Optional[dict]:
    """抓取单个 ZeroEval API 端点。"""
    url = f"{ZEROEVAL_BASE}{path}"
    try:
        async with session.get(url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logging.warning(f"[ZeroEval] {name} HTTP {resp.status}")
                return None
            return await resp.json()
    except Exception as e:
        logging.warning(f"[ZeroEval] {name} 抓取异常: {e}")
        return None


def _normalize_model_entry(entry: dict, modality: str, fetched_at_iso: str) -> Optional[dict]:
    """将 ZeroEval 单条模型条目规范化为 record。"""
    name = (
        entry.get("display_name")
        or entry.get("name")
        or entry.get("model")
        or entry.get("model_name")
        or ""
    ).strip()
    if not name:
        return None
    company = (
        entry.get("organization")
        or entry.get("provider")
        or entry.get("company")
        or entry.get("creator")
        or ""
    ).strip()
    # 发布时间字段（不同接口名字可能不同）
    publish = (
        entry.get("release_date")
        or entry.get("released_at")
        or entry.get("created_at")
        or entry.get("publish_date")
        or None
    )
    # 链接（官网/论文）
    link = (
        entry.get("url")
        or entry.get("homepage")
        or entry.get("paper_url")
        or f"https://llm-stats.com/{modality}"
    )
    description_parts = []
    if entry.get("elo") is not None:
        description_parts.append(f"ELO {entry['elo']}")
    if entry.get("votes") is not None:
        description_parts.append(f"{entry['votes']} 票")
    if entry.get("rank") is not None:
        description_parts.append(f"排名 #{entry['rank']}")
    description = " · ".join(description_parts) or f"{modality} 排行榜模型"

    return {
        "source": f"zeroeval/{modality}",
        "raw_name": name,
        "company": company,
        "title": f"[{modality}] {name}",
        "description": description,
        "url": link,
        "publish_time": publish,  # 可能为 None，后续 diff 阶段降级到 fetched_at
        "raw": {
            "modality": modality,
            "category_hint": MODALITY_CATEGORY.get(modality, "多任务"),
            "elo": entry.get("elo"),
            "votes": entry.get("votes"),
            "rank": entry.get("rank"),
            "fetched_at": fetched_at_iso,
        },
    }


def _extract_model_list(payload: dict) -> list[dict]:
    """从 ZeroEval 响应中提取模型列表。
    不同端点结构可能不一样，做容错处理。"""
    if not isinstance(payload, dict):
        return []
    for key in ("models", "leaderboard", "data", "results", "items"):
        if key in payload and isinstance(payload[key], list):
            return payload[key]
    # 顶层就是 list 的情况
    if "rankings" in payload and isinstance(payload["rankings"], list):
        return payload["rankings"]
    return []


async def fetch(
    *,
    proxy: Optional[str] = None,
    enabled_modalities: Optional[list[str]] = None,
) -> list[dict]:
    """抓取所有启用的 ZeroEval 排行榜，返回标准化 record 列表。"""
    modalities = enabled_modalities or list(ENDPOINTS.keys())
    fetched_at_iso = datetime.utcnow().isoformat() + "Z"
    if not proxy:
        proxy = detect_system_proxy()
    skip_ssl = should_skip_ssl_verify()
    connector = aiohttp.TCPConnector(ssl=make_ssl_context(verify=not skip_ssl), limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_fetch_endpoint(session, m, ENDPOINTS[m], proxy) for m in modalities]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    records = []
    for modality, payload in zip(modalities, results):
        if isinstance(payload, Exception) or not payload:
            continue
        entries = _extract_model_list(payload)
        for e in entries:
            r = _normalize_model_entry(e, modality, fetched_at_iso)
            if r:
                records.append(r)
    logging.info(f"[ZeroEval] 共抓到 {len(records)} 条模型记录")
    return records
