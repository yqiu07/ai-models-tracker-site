# 2026/06/11/11:36
# name: crawl_sohu_lite
# description: 纯requests版腾讯研究院AI速递爬虫，零Selenium依赖，适用于CI环境
"""
腾讯研究院AI速递 - 轻量爬虫（纯 requests）
==========================================
从搜狐号主页提取文章列表，抓取全文，按时间窗口过滤。

用法:
    python crawl_sohu_lite.py --since 20260601 --until 20260611
    python crawl_sohu_lite.py --since 20260601  # until默认今天

输出:
    ../../TXresearch/articles_{since}-{until}.json
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 配置 ──
SOHU_PROFILE_URL = (
    "https://mp.sohu.com/profile?xpt="
    "bGl1amluc29uZzIwMDBAMTI2LmNvbQ=="
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}
OUTPUT_DIR = Path(__file__).parent.parent.parent / "TXresearch"
FULLTEXT_DELAY = 1.0  # 全文抓取间隔(秒)

# 标题中的8位日期
_TITLE_DATE_RE = re.compile(r"(\d{8})")


def fetch_article_links(session: requests.Session) -> list[dict]:
    """从搜狐号主页提取文章链接列表。"""
    print("  [lite] fetching article list from sohu profile...")
    resp = session.get(SOHU_PROFILE_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    seen_links = set()

    # 搜狐号页面的文章链接格式: //www.sohu.com/a/XXXXX_YYYYY
    for a_tag in soup.find_all("a", href=re.compile(r"sohu\.com/a/\d+")):
        href = a_tag.get("href", "")
        if href.startswith("//"):
            href = "https:" + href

        if href in seen_links:
            continue
        seen_links.add(href)

        title = a_tag.get_text(strip=True)
        if not title or len(title) < 4:
            continue

        articles.append({"title": title, "link": href})

    print(f"  [lite] found {len(articles)} unique article links")
    return articles


def parse_date_from_title(title: str) -> str:
    """从标题中提取YYYYMMDD日期。"""
    match = _TITLE_DATE_RE.search(title)
    if match:
        return match.group(1)
    return ""


def fetch_fulltext(session: requests.Session, url: str) -> tuple[str, str]:
    """抓取文章全文，返回 (fulltext, publish_date_str)。"""
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 提取发布日期
        publish_date = ""
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", resp.text[:5000])
        if date_match:
            publish_date = date_match.group(1).replace("-", "")

        # 提取正文
        article_body = soup.find("article") or soup.find("div", class_="article-content")
        if not article_body:
            # fallback: 找所有 <p> 标签
            paragraphs = soup.find_all("p")
            text_parts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 10:
                    text_parts.append(text)
            fulltext = "\n\n".join(text_parts)
        else:
            fulltext = article_body.get_text(separator="\n\n", strip=True)

        # 清理
        fulltext = re.sub(r"\n{3,}", "\n\n", fulltext)

        if len(fulltext) < 50:
            return f"[内容过短] {fulltext}", publish_date

        return fulltext, publish_date

    except Exception as exc:
        return f"[爬取失败] {exc}", ""


def filter_by_window(articles: list[dict], since_int: int, until_int: int) -> list[dict]:
    """按时间窗口过滤文章。"""
    filtered = []
    for article in articles:
        date_str = article.get("date", "")
        if not date_str:
            # 无日期的文章也保留（后续可人工判断）
            filtered.append(article)
            continue
        try:
            date_int = int(date_str)
            if since_int <= date_int <= until_int:
                filtered.append(article)
        except ValueError:
            filtered.append(article)
    return filtered


def main():
    parser = argparse.ArgumentParser(description="腾讯研究院AI速递 lite 爬虫")
    parser.add_argument("--since", required=True, help="起始日期 YYYYMMDD")
    parser.add_argument("--until", default=None, help="截止日期 YYYYMMDD（默认今天）")
    args = parser.parse_args()

    since_int = int(args.since)
    until_int = int(args.until) if args.until else int(datetime.now().strftime("%Y%m%d"))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"articles_{since_int}-{until_int}.json"

    if output_path.exists():
        print(f"  [lite] cache exists: {output_path.name}, skipping")
        return

    session = requests.Session()

    # Step 1: 获取文章链接
    raw_articles = fetch_article_links(session)
    if not raw_articles:
        print("  [lite] no articles found, exiting")
        return

    # Step 2: 从标题提取日期，初步过滤
    for article in raw_articles:
        title_date = parse_date_from_title(article["title"])
        article["date"] = title_date

    in_window = filter_by_window(raw_articles, since_int, until_int)
    print(f"  [lite] {len(in_window)} articles in window {since_int}-{until_int}")

    if not in_window:
        print("  [lite] no articles in time window")
        # 写空文件表示已跑过
        return

    # Step 3: 抓取全文
    results = []
    for idx, article in enumerate(in_window, 1):
        title = article["title"]
        link = article["link"]
        date_str = article.get("date", "")

        print(f"  [lite] [{idx}/{len(in_window)}] {title[:50]}...")
        fulltext, page_date = fetch_fulltext(session, link)

        # 如果标题没日期但页面有，补上
        if not date_str and page_date:
            date_str = page_date

        results.append({
            "序号": idx,
            "标题": title,
            "链接": link,
            "发布时间": date_str,
            "全文": fulltext,
        })

        if idx < len(in_window):
            time.sleep(FULLTEXT_DELAY)

    # Step 4: 保存
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    valid_count = sum(
        1 for r in results
        if r["全文"] and not r["全文"].startswith("[")
    )
    print(f"  [lite] saved {len(results)} articles ({valid_count} with fulltext) -> {output_path.name}")


if __name__ == "__main__":
    main()
