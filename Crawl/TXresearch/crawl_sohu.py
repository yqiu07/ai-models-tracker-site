"""
搜狐号文章列表爬虫
=================
使用 Selenium 模拟浏览器滚动加载，提取文章卡片信息并导出为 CSV/Excel。
支持两种文章卡片类型：纯文本 (TPLTextFeedItem) 和图文 (TPLImageTextFeedItem)。

用法:
    python crawl_sohu.py

输出:
    腾讯研究院文章列表.csv
    腾讯研究院文章列表.xlsx（蓝色表头、斑马纹、链接可点击）

依赖:
    pip install selenium pandas openpyxl
"""

import csv
import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ============================================================
#  配置区 - 修改以下变量即可适配不同搜狐号
# ============================================================

# 目标搜狐号主页 URL
TARGET_URL = (
    "https://mp.sohu.com/profile?xpt="
    "bGl1amluc29uZzIwMDBAMTI2LmNvbQ=="
    "&spm=smpc.content.author.1.1776311557025E5eBJ3T"
)

# 停止条件：至少抓取的文章数量
MIN_ARTICLES = 100

# 停止条件（备选）：遇到包含此关键词的标题时停止
STOP_KEYWORD = "AI速递 20260301"

# 输出目录
OUTPUT_DIR = Path(r"D:\yuwang\action\TXresearch")

# 滚动控制：连续多少次无新文章后放弃
MAX_SCROLL_RETRIES = 15

# 每次滚动后等待的秒数（太短可能加载不出来）
SCROLL_PAUSE_SECONDS = 2.5

# 文章卡片的 CSS 选择器（搜狐号页面的两种卡片类型）
CARD_SELECTORS = "div.TPLTextFeedItem, div.TPLImageTextFeedItem"
CARD_SELECTORS_FALLBACK = (
    "div.TPLPicFeedItem, div.TPLVideoFeedItem, "
    "div.TPLTextFeedItem, div.TPLImageTextFeedItem"
)

# ============================================================


def _ensure_dir(directory):
    """创建目录（兼容 Python 3.14 Windows 中文路径 bug）"""
    dir_str = str(directory)
    if not os.path.exists(dir_str):
        os.makedirs(dir_str)


def create_driver():
    """创建 Chrome WebDriver 实例"""
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _parse_single_card(element):
    """解析单个文章卡片，返回字段字典；解析失败返回 None。

    兼容两种卡片类型：
    - TPLTextFeedItem：纯文本，链接 class 为 tpl-text-feed-item-content
    - TPLImageTextFeedItem：图文，链接 class 为 tpl-image-text-feed-item-content
    两者内部的标题/摘要/额外信息选择器完全一致。
    """
    try:
        title_elem = element.find_element(By.CSS_SELECTOR, ".item-text-content-title")
        title = title_elem.text.strip()
    except Exception:
        return None

    if not title:
        return None

    link = ""
    try:
        link_elem = element.find_element(
            By.CSS_SELECTOR,
            "a.tpl-text-feed-item-content, a.tpl-image-text-feed-item-content, a[href*='/a/']",
        )
        href = link_elem.get_attribute("href") or ""
        if href.startswith("//"):
            href = "https:" + href
        link = href.split("?")[0]
    except Exception:
        pass

    summary = ""
    try:
        desc_elem = element.find_element(By.CSS_SELECTOR, ".item-text-content-description")
        summary = desc_elem.text.strip()
    except Exception:
        pass

    extra_items = []
    try:
        extra_elems = element.find_elements(By.CSS_SELECTOR, ".extra-info-item")
        extra_items = [e.text.strip() for e in extra_elems if e.text.strip()]
    except Exception:
        pass

    return {
        "title": title,
        "summary": summary,
        "link": link,
        "publish_time": extra_items[0] if len(extra_items) > 0 else "",
        "read_count": extra_items[1] if len(extra_items) > 1 else "",
        "comment_count": extra_items[2] if len(extra_items) > 2 else "",
    }


def extract_articles(driver):
    """从当前页面提取所有文章卡片信息，返回去重后的文章列表。"""
    article_elements = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTORS)

    if not article_elements:
        article_elements = driver.find_elements(By.CSS_SELECTOR, CARD_SELECTORS_FALLBACK)

    if article_elements:
        print(f"[Info] 找到 {len(article_elements)} 个文章卡片")

    articles = []
    seen_titles = set()
    for element in article_elements:
        parsed = _parse_single_card(element)
        if parsed and parsed["title"] not in seen_titles:
            seen_titles.add(parsed["title"])
            articles.append(parsed)

    return articles


def should_stop(articles):
    """检查是否已到达停止关键词对应的文章。"""
    return any(STOP_KEYWORD in article["title"] for article in articles)


def scroll_and_collect(driver):
    """滚动页面并收集所有文章"""
    all_articles = []
    seen_titles = set()
    no_new_count = 0

    print(f"[Start] 开始爬取，目标: 至少抓取 {MIN_ARTICLES} 篇文章")

    while no_new_count < MAX_SCROLL_RETRIES:
        current_articles = extract_articles(driver)
        new_count = 0

        for article in current_articles:
            if article["title"] not in seen_titles:
                seen_titles.add(article["title"])
                all_articles.append(article)
                new_count += 1

        if new_count > 0:
            print(f"[Progress] 新增 {new_count} 篇，累计 {len(all_articles)} 篇")
            no_new_count = 0
        else:
            no_new_count += 1
            print(f"[Wait] 未发现新文章 ({no_new_count}/{MAX_SCROLL_RETRIES})")

        # 检查是否已达到目标数量
        if len(all_articles) >= MIN_ARTICLES:
            print(f"[Found] 已抓取 {len(all_articles)} 篇文章（超过 {MIN_ARTICLES}），停止爬取")
            return all_articles[:MIN_ARTICLES]

        # 检查是否到达目标关键词（备选停止条件）
        if should_stop(all_articles):
            print(f"[Found] 已找到目标文章 '{STOP_KEYWORD}'，停止爬取")
            filtered = []
            for article in all_articles:
                filtered.append(article)
                if STOP_KEYWORD in article["title"]:
                    break
            return filtered

        # 滚动到页面底部
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_SECONDS)

        # 尝试点击"加载更多"按钮
        load_more_selectors = [
            "button.load-more", "a.load-more", "div.load-more",
            "[class*='load-more']", "[class*='loadmore']",
        ]
        for load_sel in load_more_selectors:
            try:
                load_btn = driver.find_element(By.CSS_SELECTOR, load_sel)
                if load_btn.is_displayed():
                    load_btn.click()
                    print("[Info] 点击了'加载更多'按钮")
                    time.sleep(SCROLL_PAUSE_SECONDS)
                    break
            except Exception:
                continue

    print(f"[Done] 滚动结束，共收集 {len(all_articles)} 篇文章")
    return all_articles


def save_results(articles, output_dir):
    """保存结果为 CSV 和 Excel（带格式美化）"""
    _ensure_dir(output_dir)

    csv_path = output_dir / "腾讯研究院文章列表.csv"
    xlsx_path = output_dir / "腾讯研究院文章列表.xlsx"

    # 添加序号
    for index, article in enumerate(articles, 1):
        article["序号"] = index

    fieldnames = ["序号", "title", "summary", "link", "publish_time", "read_count", "comment_count"]
    header_names = ["序号", "标题", "简介", "链接", "发布时间", "阅读数", "评论数"]

    # 保存 CSV
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header_names)
        for article in articles:
            writer.writerow([article.get(field, "") for field in fieldnames])
    print(f"[Save] CSV 已保存: {csv_path}")

    # 保存 Excel（带格式美化）
    try:
        import pandas as pd
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl import load_workbook

        data_for_df = []
        for article in articles:
            data_for_df.append({
                "序号": article["序号"],
                "标题": article["title"],
                "简介": article["summary"],
                "链接": article["link"],
                "发布时间": article.get("publish_time", ""),
                "阅读数": article.get("read_count", ""),
                "评论数": article.get("comment_count", ""),
            })
        df = pd.DataFrame(data_for_df)
        df.to_excel(xlsx_path, index=False, engine="openpyxl")

        # 美化 Excel
        workbook = load_workbook(xlsx_path)
        worksheet = workbook.active

        header_font = Font(name="微软雅黑", bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        data_font = Font(name="微软雅黑", size=10)
        data_alignment = Alignment(vertical="center", wrap_text=True)
        link_font = Font(name="微软雅黑", size=10, color="0563C1", underline="single")

        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        column_widths = {"A": 6, "B": 40, "C": 60, "D": 50, "E": 14, "F": 10, "G": 10}
        for col_letter, width in column_widths.items():
            worksheet.column_dimensions[col_letter].width = width

        for cell in worksheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        for row_idx in range(2, worksheet.max_row + 1):
            for col_idx in range(1, worksheet.max_column + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.font = data_font
                cell.alignment = data_alignment
                cell.border = thin_border
                if col_idx == 4 and cell.value:
                    cell.font = link_font
                    cell.hyperlink = str(cell.value)
            if row_idx % 2 == 0:
                for col_idx in range(1, worksheet.max_column + 1):
                    worksheet.cell(row=row_idx, column=col_idx).fill = PatternFill(
                        start_color="F2F2F2", end_color="F2F2F2", fill_type="solid"
                    )

        worksheet.freeze_panes = "A2"
        workbook.save(xlsx_path)
        print(f"[Save] Excel 已保存（含格式美化）: {xlsx_path}")
    except ImportError:
        print("[Warn] pandas/openpyxl 未安装，跳过 Excel 导出")


def main():
    print("=" * 60)
    print("  搜狐号文章爬虫")
    print("=" * 60)

    driver = create_driver()
    try:
        print(f"[Open] 正在打开页面: {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(5)
        print(f"[Info] 页面标题: {driver.title}")

        _ensure_dir(OUTPUT_DIR)

        articles = scroll_and_collect(driver)

        if articles:
            save_results(articles, OUTPUT_DIR)
            print(f"\n[Result] 共爬取 {len(articles)} 篇文章")
            print(f"[Result] 第一篇: {articles[0]['title']}")
            print(f"[Result] 最后一篇: {articles[-1]['title']}")
        else:
            print("[Error] 未能爬取到任何文章")
            print("[Hint] 可能原因：页面结构变化、网络问题、反爬机制")
            print("[Hint] 建议：保存页面源码到 Case 文件，对比 HTML 结构")

    finally:
        driver.quit()
        print("[Done] 浏览器已关闭")


if __name__ == "__main__":
    main()
