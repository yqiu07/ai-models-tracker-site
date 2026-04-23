"""fetch 阶段：调度所有数据源，合并产出 fetch checkpoint。"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .persistence import save_fetch_checkpoint, now_cst_tag
from .sources import rss as rss_source
from .sources import zeroeval as zeroeval_source
from .sources import llmstats as llmstats_source
from .sources import txresearch as txresearch_source

CST = timezone(timedelta(hours=8))


async def run_fetch(
    *,
    opml_path: Path,
    output_dir: Path,
    cutoff_dt: Optional[datetime] = None,
    enable_zeroeval: bool = True,
    enable_rss: bool = True,
    enable_llmstats: bool = True,
    enable_txresearch: bool = True,
    proxy: Optional[str] = None,
) -> tuple[Path, dict[str, list[dict]]]:
    """并发抓取所有数据源，保存 fetch checkpoint。

    cutoff_dt: RSS 抓取的时间下限（早于此时间的文章不要）。None 表示不过滤。
    """
    proxy = proxy or os.getenv("TRACKER_PROXY") or None

    tasks = []
    task_names = []

    if enable_rss:
        tasks.append(rss_source.fetch(opml_path, cutoff=cutoff_dt, proxy=proxy))
        task_names.append("rss")

    if enable_zeroeval:
        tasks.append(zeroeval_source.fetch(proxy=proxy))
        task_names.append("zeroeval")

    if enable_llmstats:
        tasks.append(llmstats_source.fetch(proxy=proxy))
        task_names.append("llmstats")

    if enable_txresearch:
        tasks.append(txresearch_source.fetch(proxy=proxy))
        task_names.append("txresearch")

    if not tasks:
        raise ValueError("至少需要启用一个数据源")

    logging.info(f"[fetch] 启动 {len(tasks)} 个数据源: {task_names}")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    sources_data: dict[str, list[dict]] = {}
    for name, r in zip(task_names, results):
        if isinstance(r, Exception):
            logging.error(f"[fetch] 源 {name} 失败: {r}")
            sources_data[name] = []
        else:
            sources_data[name] = r

    total = sum(len(v) for v in sources_data.values())
    logging.info(f"[fetch] 总计: {total} 条 raw 记录")

    tag = now_cst_tag()
    path = save_fetch_checkpoint(sources_data, output_dir, tag)
    return path, sources_data
