# 2026/06/11/12:17
# name: _backfill_tx
# description: 从 Selenium 爬取的 JSON 中过滤 AI 速递文章，保存 TXT 到 Extract/articles/，供 LLM 提取
"""
从 TXresearch/articles_*.json 中过滤"腾讯研究院AI速递"文章，
将全文保存到 Extract/articles/ 目录，供 extract_models_llm.py 提取模型信息。

用法:
    python _backfill_tx.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "Model_Navigate"
TX_DIR = ROOT / "TXresearch"
ARTICLES_DIR = ROOT / "Extract" / "articles"

AI_SPEED_PATTERN = re.compile(r"腾讯研究院AI速递\s*\d{8}", re.IGNORECASE)


def main():
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(TX_DIR.glob("articles_*.json"))
    print(f"Found {len(json_files)} JSON files in {TX_DIR}")

    total_saved = 0
    total_skipped = 0
    total_existed = 0

    for json_path in json_files:
        print(f"\n--- {json_path.name} ---")
        with open(json_path, "r", encoding="utf-8") as f:
            articles = json.load(f)

        for article in articles:
            # 兼容中文和英文字段名
            title = article.get("标题", article.get("title", ""))
            fulltext = article.get("全文", article.get("fulltext", article.get("full_text", "")))
            seq = article.get("序号", article.get("seq", 0))
            link = article.get("链接", article.get("link", ""))

            # 只保留 AI 速递文章
            if not AI_SPEED_PATTERN.search(title):
                total_skipped += 1
                continue

            if not fulltext or fulltext.startswith("[爬取失败]") or fulltext.startswith("[内容过短]"):
                print(f"  [SKIP] 无有效全文: {title[:50]}")
                total_skipped += 1
                continue

            # 文件名格式
            safe_title = title.split('\n')[0].strip()
            safe_title = re.sub(r'[\\/:*?"<>|\r\n\t]', '', safe_title)
            safe_title = safe_title[:80]
            txt_filename = f"{seq:02d}_{safe_title}.txt"
            txt_path = ARTICLES_DIR / txt_filename

            if txt_path.exists():
                total_existed += 1
                continue

            content = f"标题: {title}\n链接: {link}\n序号: {seq}\n{'=' * 80}\n\n{fulltext}"
            txt_path.write_text(content, encoding="utf-8")
            total_saved += 1
            print(f"  [SAVE] {txt_filename}")

    print(f"\n{'='*60}")
    print(f"  AI速递文章保存: {total_saved} 篇新保存")
    print(f"  已存在跳过: {total_existed} 篇")
    print(f"  非速递/无效跳过: {total_skipped} 篇")
    print(f"  TXT目录: {ARTICLES_DIR}")


if __name__ == "__main__":
    main()
