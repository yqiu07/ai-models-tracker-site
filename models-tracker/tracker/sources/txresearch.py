"""腾讯研究院（搜狐号）数据源适配器（重点源）。

搜狐号主页是懒加载的（JS 动态渲染 + 滚动触发 AJAX），纯 HTTP GET 拿不到文章。
本适配器直接调用搜狐内部 AJAX API（odin blockdata）获取文章列表，
无需 Selenium，轻量级 aiohttp 即可完成。

API 端点: POST https://odin.sohu.com/odin/api/blockdata
关键参数: mkey=455313 (腾讯研究院搜狐号 authorId)
"""

from __future__ import annotations

import logging
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from ..ai import detect_system_proxy, make_ssl_context, should_skip_ssl_verify

# 搜狐号 odin AJAX API
ODIN_API_URL = "https://odin.sohu.com/odin/api/blockdata"

# 腾讯研究院搜狐号 authorId
AUTHOR_MKEY = "455313"

CST = timezone(timedelta(hours=8))


def _build_request_body(page: int = 1, page_size: int = 20) -> dict:
    """构造 odin blockdata API 的请求体。

    参数来自浏览器实际抓包，关键字段：
    - mainContent.authorId: 搜狐号作者 ID
    - resourceList[0].content.page: 页码
    - resourceList[0].context.mkey: 搜狐号 ID（与 authorId 对应）
    """
    timestamp_ms = int(time.time() * 1000)
    random_suffix = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    pv_id = f"{timestamp_ms}_{random_suffix}"
    page_id = f"{timestamp_ms}_{timestamp_ms}odi_{random_suffix[:3]}"
    request_id = f"{timestamp_ms}{random_suffix}_324"

    return {
        "pvId": pv_id,
        "pageId": page_id,
        "mainContent": {
            "productType": "13",
            "productId": "324",
            "secureScore": "5",
            "categoryId": "47",
            "adTags": "11111111",
            "authorId": 121135924,
        },
        "resourceList": [
            {
                "tplCompKey": "FeedSlideloadAuthor_2_0_pc_1655965929143_data2",
                "isServerRender": True,
                "isSingleAd": False,
                "configSource": "mp",
                "content": {
                    "productId": "325",
                    "productType": "13",
                    "size": page_size,
                    "pro": "0,1,3,4,5",
                    "feedType": "XTOPIC_SYNTHETICAL",
                    "view": "operateFeedMode",
                    "innerTag": "work",
                    "spm": "smpc.channel_248.block3_308_hHsK47_2_fd",
                    "page": page,
                    "requestId": request_id,
                },
                "adInfo": {},
                "context": {"mkey": AUTHOR_MKEY},
            }
        ],
    }


def _parse_api_response(payload: dict) -> list[dict]:
    """从 odin API 响应中提取文章列表。"""
    articles = []
    if not isinstance(payload, dict):
        return articles

    data = payload.get("data", {})
    if not data:
        return articles

    # API 返回的 key 是动态的 tplCompKey，遍历所有值找 list
    for block in data.values():
        if not isinstance(block, dict):
            continue
        article_list = block.get("list")
        if not article_list or not isinstance(article_list, list):
            continue

        for item in article_list:
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # URL 处理
            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.sohu.com{url}"
            # 去掉 scm 追踪参数
            if "?" in url:
                url = url.split("?")[0]

            # 摘要
            summary = (item.get("brief") or "").strip()

            # extraInfoList: [{"text": "2026.04.09"}, {"text": "517阅读"}, {"text": "0评论"}]
            extra_info = item.get("extraInfoList", [])
            publish_time = None
            read_count = ""
            if extra_info and len(extra_info) > 0:
                publish_time = extra_info[0].get("text", "")
            if extra_info and len(extra_info) > 1:
                read_count = extra_info[1].get("text", "")

            articles.append({
                "title": title,
                "url": url,
                "summary": summary,
                "publish_time": publish_time,
                "article_id": item.get("id"),
                "read_count": read_count,
            })

    return articles


def _article_to_record(article: dict, fetched_at_iso: str) -> dict:
    """将文章转换为标准 record 格式。

    腾讯研究院的文章是信息源（不是模型数据），
    raw_name 使用文章标题，由后续 LLM 阶段从中提取模型信息。
    """
    return {
        "source": "txresearch",
        "raw_name": article["title"],
        "company": "",
        "title": article["title"],
        "description": article.get("summary", "")[:500],
        "url": article.get("url", ""),
        "publish_time": article.get("publish_time"),
        "raw": {
            "origin": "腾讯研究院（搜狐号）",
            "article_id": article.get("article_id"),
            "read_count": article.get("read_count", ""),
            "fetched_at": fetched_at_iso,
        },
    }


async def _fetch_page(
    session: aiohttp.ClientSession,
    page: int,
    proxy: Optional[str],
) -> list[dict]:
    """请求单页文章数据。先直连，失败则走代理。"""
    body = _build_request_body(page=page)
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": "https://mp.sohu.com",
        "Referer": "https://mp.sohu.com/profile?xpt=bGl1amluc29uZzIwMDBAMTI2LmNvbQ==",
    }

    for attempt_proxy in (None, proxy):
        if attempt_proxy is None and proxy is not None:
            label = "直连"
        elif attempt_proxy:
            label = "代理"
        else:
            label = "直连"
        try:
            kwargs = {"timeout": aiohttp.ClientTimeout(total=30)}
            if attempt_proxy:
                kwargs["proxy"] = attempt_proxy
            async with session.post(
                ODIN_API_URL,
                json=body,
                headers=headers,
                **kwargs,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    articles = _parse_api_response(data)
                    if articles:
                        logging.debug(f"[txresearch] page {page} {label}成功: {len(articles)} 篇")
                        return articles
                logging.debug(f"[txresearch] page {page} {label} HTTP {resp.status}")
        except Exception as exc:
            logging.debug(f"[txresearch] page {page} {label}失败: {exc}")

    return []


async def fetch(
    *,
    proxy: Optional[str] = None,
    max_pages: int = 3,
) -> list[dict]:
    """通过搜狐 odin API 获取腾讯研究院文章列表，返回标准化 record 列表。

    Args:
        proxy: HTTP 代理地址
        max_pages: 最多抓取的页数（每页 20 条），默认 3 页 = 60 篇
    """
    if not proxy:
        proxy = detect_system_proxy()
    skip_ssl = should_skip_ssl_verify()
    connector = aiohttp.TCPConnector(
        ssl=make_ssl_context(verify=not skip_ssl), limit=4,
    )
    fetched_at_iso = datetime.now(timezone.utc).isoformat()

    all_articles: list[dict] = []
    seen_titles: set[str] = set()

    async with aiohttp.ClientSession(connector=connector) as session:
        for page_num in range(1, max_pages + 1):
            articles = await _fetch_page(session, page_num, proxy)
            if not articles:
                logging.debug(f"[txresearch] page {page_num} 无数据，停止翻页")
                break
            for article in articles:
                if article["title"] not in seen_titles:
                    seen_titles.add(article["title"])
                    all_articles.append(article)

    if not all_articles:
        logging.warning("[txresearch] 未获取到任何文章")
        return []

    records = [_article_to_record(a, fetched_at_iso) for a in all_articles]
    logging.info(f"[txresearch] 共抓到 {len(records)} 篇文章（{max_pages} 页）")
    return records