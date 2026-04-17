"""
批量爬取TXCrawl.xlsx中的搜狐文章全文，保存为JSON文件。
"""
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import time
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

def fetch_article(url):
    """爬取单篇搜狐文章的正文内容"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 搜狐文章正文通常在 article 标签或特定 div 中
        article_tag = soup.find("article")
        if article_tag:
            paragraphs = article_tag.find_all("p")
        else:
            # 备选：查找 class 包含 article 的 div
            content_div = soup.find("div", class_=re.compile(r"article|content", re.I))
            if content_div:
                paragraphs = content_div.find_all("p")
            else:
                paragraphs = soup.find_all("p")
        
        text_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 5:
                text_parts.append(text)
        
        full_text = "\n".join(text_parts)
        return full_text if len(full_text) > 50 else f"[内容过短] {full_text}"
    except Exception as e:
        return f"[爬取失败] {str(e)}"


def main():
    df = pd.read_excel(r"D:\yuwang\action\Extract\TXCrawl.xlsx")
    results = []
    
    for idx, row in df.iterrows():
        url = row.iloc[3]  # 链接列
        title = row.iloc[1]  # 标题列
        seq = row.iloc[0]  # 序号列
        print(f"[{idx+1}/{len(df)}] 爬取: {title} -> {url}")
        
        content = fetch_article(url)
        results.append({
            "序号": int(seq),
            "标题": title,
            "链接": url,
            "全文": content
        })
        time.sleep(1)  # 礼貌爬取间隔
    
    output_path = r"D:\yuwang\action\Extract\articles_fulltext.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n完成！共爬取 {len(results)} 篇文章，保存至 {output_path}")
    
    # 打印每篇文章的字数统计
    for r in results:
        content_len = len(r["全文"])
        status = "✓" if content_len > 100 else "⚠"
        print(f"  {status} 序号{r['序号']}: {r['标题'][:30]}... ({content_len}字)")


if __name__ == "__main__":
    main()
