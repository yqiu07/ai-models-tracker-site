"""RSS 数据源适配器（精简版，复用 news-digest 思路）。"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

import aiohttp
import certifi
import feedparser

from ..ai import detect_system_proxy, make_ssl_context, should_skip_ssl_verify


def parse_opml(path: Path) -> list[dict]:
    """解析 OPML，返回 [{name, category, xml_url, html_url}, ...]"""
    tree = ET.parse(path)
    root = tree.getroot()
    body = root.find("body")
    if body is None:
        raise ValueError(f"OPML 格式错误（无 <body>）: {path}")
    sources = []
    for cat in body.findall("outline"):
        cat_name = cat.get("text") or cat.get("title") or "未分类"
        for feed in cat.findall("outline"):
            url = feed.get("xmlUrl")
            if not url:
                continue
            sources.append({
                "name": feed.get("text") or feed.get("title") or "未知源",
                "category": cat_name,
                "xml_url": url,
                "html_url": feed.get("htmlUrl") or "",
            })
    return sources


def _parse_entry_date(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        tp = getattr(entry, attr, None)
        if tp:
            try:
                return datetime(*tp[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
    for attr in ("published", "updated", "created"):
        s = getattr(entry, attr, None)
        if s:
            try:
                return parsedate_to_datetime(s).astimezone(timezone.utc)
            except (ValueError, TypeError):
                continue
    return None


async def _fetch_one(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    src: dict,
    cutoff: Optional[datetime],
    max_per_feed: int,
    proxy: Optional[str],
) -> list[dict]:
    """抓取单个 RSS 源，返回标准化 record 列表。"""
    async with sem:
        content = None
        try:
            async with session.get(src["xml_url"], timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    content = await resp.text()
        except Exception as e:
            logging.debug(f"[RSS] {src['name']} 直连失败: {e}")

        if not content and proxy:
            try:
                async with session.get(src["xml_url"], proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        content = await resp.text()
            except Exception as e:
                logging.debug(f"[RSS] {src['name']} 代理失败: {e}")

        if not content:
            logging.warning(f"[RSS] {src['name']} 抓取失败")
            return []

    try:
        feed = feedparser.parse(content)
    except Exception as e:
        logging.warning(f"[RSS] {src['name']} 解析失败: {e}")
        return []

    records = []
    for entry in (feed.entries or [])[:max_per_feed]:
        pub_dt = _parse_entry_date(entry)
        if cutoff and pub_dt and pub_dt < cutoff:
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        desc = entry.get("summary") or entry.get("description") or ""
        url = entry.get("link", "")
        records.append({
            "source": f"rss/{src['name']}",
            "raw_name": title,           # RSS 阶段无法直接知道"模型名"，先用文章标题占位
            "company": "",               # 由 LLM 后续推断
            "title": title,
            "description": desc[:500],
            "url": url,
            "publish_time": pub_dt.isoformat() if pub_dt else None,
            "raw": {
                "feed_name": src["name"],
                "category": src["category"],
            },
        })
    return records


async def fetch(
    opml_path: Path,
    *,
    max_concurrent: int = 8,
    max_per_feed: int = 30,
    cutoff: Optional[datetime] = None,
    proxy: Optional[str] = None,
) -> list[dict]:
    """抓取 OPML 中所有 RSS 源。"""
    sources = parse_opml(opml_path)
    logging.info(f"[RSS] 共 {len(sources)} 个源")
    if not proxy:
        proxy = detect_system_proxy()
    sem = asyncio.Semaphore(max_concurrent)
    skip_ssl = should_skip_ssl_verify()
    connector = aiohttp.TCPConnector(ssl=make_ssl_context(verify=not skip_ssl), limit=max_concurrent * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_fetch_one(session, sem, s, cutoff, max_per_feed, proxy) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    all_records = []
    for r in results:
        if isinstance(r, list):
            all_records.extend(r)
    logging.info(f"[RSS] 共抓到 {len(all_records)} 篇文章")
    return all_records
