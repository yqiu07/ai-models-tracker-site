"""腾讯研究院（搜狐号）数据源适配器（重点源）。

从搜狐号主页抓取文章列表 HTML，解析文章卡片信息。
搜狐号的 SSR 页面在初始 HTML 中就包含了前 N 篇文章的数据，
后续文章需要滚动加载（AJAX），这里只抓初始页的文章。

对于需要更多文章的场景，可在本地手动运行 Crawl/TXresearch/crawl_sohu.py。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp

from ..ai import detect_system_proxy, make_ssl_context, should_skip_ssl_verify

# 搜狐号主页 URL
SOHU_PROFILE_URL = (
    "https://mp.sohu.com/profile?xpt="
    "bGl1amluc29uZzIwMDBAMTI2LmNvbQ=="
)

# 搜狐号 AJAX 文章列表 API（用于获取更多文章）
# xpt 是搜狐号 ID 的 base64 编码
SOHU_FEED_API = "https://v2.sohu.com/public-api/feed"

CST = timezone(timedelta(hours=8))


def _parse_html_articles(html: str) -> list[dict]:
    """从搜狐号主页 HTML 中解析文章列表。

    搜狐号的 SSR HTML 中，文章数据以 JSON 形式嵌入在 window.__INITIAL_STATE__ 或
    类似的 script 标签中。如果找不到结构化数据，则降级为正则解析。
    """
    articles = []

    # 方案 1：尝试提取 window.__INITIAL_STATE__ 或 window.globalData
    for pattern in [
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>',
        r'window\.globalData\s*=\s*({.*?});?\s*</script>',
    ]:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                feed_list = _extract_feed_from_state(data)
                if feed_list:
                    return feed_list
            except (json.JSONDecodeError, KeyError):
                pass

    # 方案 2：正则解析 HTML 中的文章卡片
    card_pattern = re.compile(
        r'<a[^>]*href="(https?://(?:www\.)?sohu\.com/a/\d+[^"]*)"[^>]*>'
        r'.*?class="[^"]*title[^"]*"[^>]*>([^<]+)</a>',
        re.DOTALL,
    )
    for link_match in card_pattern.finditer(html):
        url = link_match.group(1).split("?")[0]
        title = link_match.group(2).strip()
        if title and url:
            articles.append({
                "title": title,
                "url": url,
                "summary": "",
                "publish_time": None,
            })

    # 方案 3：更宽松的标题 + 链接提取
    if not articles:
        title_pattern = re.compile(
            r'<(?:h[1-6]|div|span)[^>]*class="[^"]*(?:title|item-text)[^"]*"[^>]*>'
            r'\s*([^<]{5,100})\s*</(?:h[1-6]|div|span)>',
            re.DOTALL,
        )
        for title_match in title_pattern.finditer(html):
            title = title_match.group(1).strip()
            if title and len(title) > 5:
                articles.append({
                    "title": title,
                    "url": "",
                    "summary": "",
                    "publish_time": None,
                })

    # 去重
    seen_titles = set()
    deduped = []
    for article in articles:
        if article["title"] not in seen_titles:
            seen_titles.add(article["title"])
            deduped.append(article)

    return deduped


def _extract_feed_from_state(state: dict) -> list[dict]:
    """从 __INITIAL_STATE__ 结构中提取文章列表。"""
    articles = []

    # 搜狐号 SSR 数据结构可能嵌套在不同的 key 下
    feed_data = None
    for key_path in [
        ("feedData", "data"),
        ("articleList", "list"),
        ("data", "list"),
        ("feedList",),
    ]:
        current = state
        for key in key_path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                current = None
                break
        if current and isinstance(current, list):
            feed_data = current
            break

    if not feed_data:
        return []

    for item in feed_data:
        title = (item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        url = item.get("url") or item.get("link") or ""
        if url and url.startswith("//"):
            url = "https:" + url
        summary = item.get("brief") or item.get("digest") or item.get("summary") or ""
        publish_time = item.get("publicTime") or item.get("createTime") or item.get("time")
        articles.append({
            "title": title,
            "url": url,
            "summary": summary,
            "publish_time": publish_time,
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
            "fetched_at": fetched_at_iso,
        },
    }


async def fetch(
    *,
    proxy: Optional[str] = None,
    profile_url: Optional[str] = None,
) -> list[dict]:
    """抓取搜狐号主页文章列表，返回标准化 record 列表。"""
    target_url = profile_url or SOHU_PROFILE_URL
    if not proxy:
        proxy = detect_system_proxy()
    skip_ssl = should_skip_ssl_verify()
    connector = aiohttp.TCPConnector(
        ssl=make_ssl_context(verify=not skip_ssl), limit=4,
    )
    fetched_at_iso = datetime.now(timezone.utc).isoformat()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    html = None
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        # 先直连
        try:
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    logging.debug(f"[txresearch] 直连成功 ({len(html)} bytes)")
        except Exception as exc:
            logging.debug(f"[txresearch] 直连失败: {exc}")

        # 失败则走代理
        if not html and proxy:
            try:
                async with session.get(target_url, proxy=proxy, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        logging.debug(f"[txresearch] 代理成功 ({len(html)} bytes)")
            except Exception as exc:
                logging.debug(f"[txresearch] 代理失败: {exc}")

    if not html:
        logging.warning("[txresearch] 搜狐号主页抓取失败")
        return []

    articles = _parse_html_articles(html)
    if not articles:
        logging.warning("[txresearch] 未解析到文章（搜狐号可能需要 JS 渲染）")
        return []

    records = [_article_to_record(a, fetched_at_iso) for a in articles]
    logging.info(f"[txresearch] 共抓到 {len(records)} 篇文章")
    return records
