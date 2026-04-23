"""enrich 阶段：LLM 双槽位填充 14 个字段 + 浓缩备注。"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import aiohttp

from .ai import (
    ModelSlot,
    classify_fields,
    detect_system_proxy,
    distill_note,
    load_slots,
    make_ssl_context,
    should_skip_ssl_verify,
)
from .persistence import today_cst_date
from .schema import ModelRecord


def _build_evidence_summary(record: ModelRecord, max_evidence: int = 5) -> str:
    """把 evidence 列表浓缩成给 LLM 的摘要文本。"""
    lines = []
    for i, e in enumerate(record.evidence[:max_evidence], 1):
        parts = [f"[{i}] 来源: {e.source}"]
        if e.title:
            parts.append(f"标题: {e.title}")
        if e.description:
            parts.append(f"描述: {e.description[:300]}")
        if e.publish_time:
            parts.append(f"时间: {e.publish_time}")
        if e.url:
            parts.append(f"链接: {e.url}")
        lines.append("\n  ".join(parts))
    return "\n\n".join(lines)


def _pick_primary_url(record: ModelRecord) -> str:
    """选择"链接"列的代表 URL（优先级：官方/论文/RSS）。"""
    if not record.evidence:
        return ""
    # 优先级评分：官方域名 > 论文 > RSS
    def score(e):
        url = (e.url or "").lower()
        s = 0
        if any(d in url for d in ["openai.com", "anthropic.com", "google.com", "deepmind.com",
                                    "alibaba.com", "qwen.ai", "deepseek.com", "moonshot.ai",
                                    "huggingface.co", "github.com"]):
            s += 10
        if "arxiv.org" in url or "paper" in url:
            s += 5
        if e.source.startswith("zeroeval"):
            s += 3
        return -s  # min
    return sorted(record.evidence, key=score)[0].url or ""


async def _enrich_one(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    record: ModelRecord,
    field_slot: ModelSlot,
    note_slot: ModelSlot,
    field_prompt: str,
    note_prompt: str,
    proxy: Optional[str],
) -> ModelRecord:
    """对单个 ModelRecord 调用 LLM 填充字段。"""
    evidence_summary = _build_evidence_summary(record)
    async with sem:
        # 并发调用两个槽位
        fields_task = classify_fields(
            session, field_slot, field_prompt,
            record.raw_name, record.company, evidence_summary, proxy=proxy,
        )
        note_task = distill_note(
            session, note_slot, note_prompt,
            record.raw_name, record.company, evidence_summary, proxy=proxy,
        )
        fields, note = await asyncio.gather(fields_task, note_task)

    if fields:
        record.domestic_or_overseas = fields.get("国内外", "未知") or "未知"
        record.source_type = fields.get("来源", "未知") or "未知"
        record.size = fields.get("尺寸")
        record.category = fields.get("类型", "未知") or "未知"
        record.thinking_mode = fields.get("能否思考", "未知") or "未知"
        record.category2 = fields.get("类型2", "未知") or "未知"
        record.workflow_extensible = bool(fields.get("workflow编排拓展", False))
    else:
        logging.warning(f"[enrich] 字段分类失败: {record.fingerprint}")

    if note:
        record.note = note
    else:
        logging.warning(f"[enrich] 备注浓缩失败: {record.fingerprint}")
        # 兜底：拼第一条 evidence 的描述前 80 字
        if record.evidence:
            record.note = (record.evidence[0].description or record.evidence[0].title or "")[:80]

    record.primary_url = _pick_primary_url(record)
    record.recorded_date = today_cst_date()
    return record


async def enrich_records(
    records: list[ModelRecord],
    field_prompt_path: Path,
    note_prompt_path: Path,
    *,
    max_concurrent: int = 4,
) -> list[ModelRecord]:
    """对一批 ModelRecord 批量富化。"""
    if not records:
        return []
    field_slot, note_slot = load_slots()
    proxy = detect_system_proxy()
    if proxy:
        logging.info(f"[enrich] 使用代理: {proxy}")

    field_prompt = field_prompt_path.read_text(encoding="utf-8")
    note_prompt = note_prompt_path.read_text(encoding="utf-8")

    sem = asyncio.Semaphore(max_concurrent)
    skip_ssl = should_skip_ssl_verify()
    ssl_ctx = make_ssl_context(verify=not skip_ssl)
    connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=max_concurrent * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _enrich_one(session, sem, r, field_slot, note_slot,
                        field_prompt, note_prompt, proxy)
            for r in records
        ]
        enriched = await asyncio.gather(*tasks, return_exceptions=False)
    logging.info(f"[enrich] 完成 {len(enriched)} 条记录富化")
    return enriched
