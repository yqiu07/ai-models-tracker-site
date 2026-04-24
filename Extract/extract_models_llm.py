"""
基于 LLM API 自动从腾讯研究院文章全文中提取模型信息。
===========================================================
次级方案：当用户无法在对话中让 AI 手动提取时，可通过本脚本自动提取。

用法:
    python extract_models_llm.py                          # 提取所有文章
    python extract_models_llm.py --since 20260417         # 只提取指定时间段
    python extract_models_llm.py --dry-run                # 预览，不调用 LLM

环境变量（或上级目录 .env 文件）:
    LLM_API_KEY=sk-xxx          # LLM API Key（默认用 DashScope 百炼）
    LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
    LLM_MODEL=qwen-plus         # 推荐 qwen-plus（便宜且够用）

依赖:
    pip install requests pandas openpyxl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ── 路径 ──
ROOT = Path(__file__).parent.parent  # action/
EXTRACT_DIR = Path(__file__).parent  # action/Extract/
ARTICLES_DIR = EXTRACT_DIR / "articles"
RESULT_XLSX = EXTRACT_DIR / "TXCrawl_result.xlsx"
EXISTING_XLSX = ROOT / "data" / "Object-Models-Updated.xlsx"

# ── LLM 提取 Prompt ──
EXTRACT_PROMPT = """你是一名 AI 模型追踪分析师。请从以下腾讯研究院 AI 速递文章中，提取所有**具体的 AI 模型/智能体/AI 产品**。

提取标准（参考 Taxonomy）：
- 具体的模型名称（基座/领域/微调/多模态/智能体/集成产品）
- 新发布的版本号模型
- 新发布的产品/智能体平台
排除：纯硬件发布、纯算法论文、纯商业事件（投融资/人事变动）、benchmark/评测工具

对每个提取到的模型，请填写以下字段（不确定的留空）：
- model_name: 模型/产品名称（用官方名称，含版本号）
- company: 发布公司/组织
- domestic: 国内/国外
- open_source: 开源/闭源/未知
- model_type: 基座/领域/微调/多模态/智能体/集成产品/代码/语音/视频/图像/具身
- can_reason: thinking/non-thinking/未知
- brief: 一句话描述（20字以内，突出核心能力或定位）

请严格以 JSON 数组格式输出，不要输出其他内容。示例：
[
  {"model_name": "Claude Opus 4.7", "company": "Anthropic", "domestic": "国外", "open_source": "闭源", "model_type": "基座", "can_reason": "thinking", "brief": "Anthropic旗舰模型"},
  {"model_name": "Spark 2.0", "company": "World Labs", "domestic": "国外", "open_source": "开源", "model_type": "多模态", "can_reason": "non-thinking", "brief": "3D高斯点云渲染引擎"}
]

---
文章内容：
{article_text}
"""


def load_env():
    """加载 .env 文件。"""
    for env_path in [EXTRACT_DIR / ".env", ROOT / ".env", ROOT.parent / "models-tracker" / ".env"]:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), value)


def get_llm_config() -> tuple[str, str, str]:
    """获取 LLM API 配置，按优先级查找。"""
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("TRACKER_FIELD_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or ""
    )
    api_base = (
        os.environ.get("LLM_API_BASE")
        or os.environ.get("TRACKER_FIELD_API_BASE")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model = os.environ.get("LLM_MODEL") or "qwen-plus"
    return api_key, api_base, model


def call_llm(article_text: str, api_key: str, api_base: str, model: str) -> list[dict]:
    """调用 LLM API 提取模型信息，返回结构化列表。"""
    prompt = EXTRACT_PROMPT.format(article_text=article_text[:8000])

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4000,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # 提取 JSON 数组（LLM 可能在前后添加 markdown 标记）
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return []
    except requests.exceptions.HTTPError as exc:
        print(f"    ❌ LLM API 错误: {exc}")
        if exc.response is not None:
            print(f"    响应: {exc.response.text[:200]}")
        return []
    except json.JSONDecodeError:
        print(f"    ⚠️ LLM 输出不是合法 JSON")
        print(f"    原始输出: {content[:300]}")
        return []
    except Exception as exc:
        print(f"    ❌ LLM 调用失败: {exc}")
        return []


def load_articles(since_int: int | None = None, until_int: int | None = None) -> list[dict]:
    """从 Extract/articles/ 目录加载文章。"""
    articles = []
    if not ARTICLES_DIR.exists():
        return articles

    for txt_file in sorted(ARTICLES_DIR.glob("*.txt")):
        content = txt_file.read_text(encoding="utf-8")

        # 解析文件头
        title = ""
        link = ""
        seq = 0
        body_lines = []
        header_done = False
        for line in content.split("\n"):
            if not header_done:
                if line.startswith("标题:"):
                    title = line[3:].strip()
                elif line.startswith("链接:"):
                    link = line[3:].strip()
                elif line.startswith("序号:"):
                    try:
                        seq = int(line[3:].strip())
                    except ValueError:
                        pass
                elif line.startswith("=" * 10):
                    header_done = True
            else:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()
        if not body or len(body) < 50:
            continue

        # 从标题中提取日期
        date_match = re.search(r'(\d{8})', title)
        article_date_int = int(date_match.group(1)) if date_match else 0

        # 时间筛选
        if since_int and article_date_int and article_date_int < since_int:
            continue
        if until_int and article_date_int and article_date_int > until_int:
            continue

        articles.append({
            "序号": seq,
            "标题": title,
            "链接": link,
            "日期": article_date_int,
            "全文": body,
            "文件": txt_file.name,
        })

    return articles


def normalize_name(name: str) -> str:
    """标准化模型名称用于去重匹配。"""
    name_lower = name.lower().strip()
    name_lower = re.sub(r'\s*[\(（].*?[\)）]', '', name_lower)
    name_lower = re.sub(r'\s+', ' ', name_lower).strip()
    return name_lower


def load_existing_models() -> set[str]:
    """加载已追踪的模型名称。"""
    existing = set()
    if EXISTING_XLSX.exists():
        df = pd.read_excel(EXISTING_XLSX, engine="openpyxl")
        name_col = "模型名称"
        if name_col in df.columns:
            for name in df[name_col].dropna():
                existing.add(normalize_name(str(name)))
    return existing


def main():
    parser = argparse.ArgumentParser(description="LLM 自动提取腾讯研究院文章中的模型信息")
    parser.add_argument("--since", type=str, help="起始日期 (YYYYMMDD)")
    parser.add_argument("--until", type=str, help="截止日期 (YYYYMMDD)")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不调用 LLM")
    args = parser.parse_args()

    since_int = int(args.since) if args.since else None
    until_int = int(args.until) if args.until else None

    load_env()
    api_key, api_base, model = get_llm_config()

    print("📚 LLM 自动提取腾讯研究院模型信息")
    print(f"  API: {api_base}")
    print(f"  模型: {model}")
    print(f"  时间: {since_int or '全部'} ~ {until_int or '全部'}")
    if args.dry_run:
        print("  模式: 🔍 DRY-RUN")
    print()

    if not api_key and not args.dry_run:
        print("  ❌ 未配置 LLM API Key")
        print("  💡 请设置环境变量 LLM_API_KEY 或在 .env 中配置")
        print("  💡 也可使用 TRACKER_FIELD_API_KEY 或 DASHSCOPE_API_KEY")
        return

    # 加载文章
    articles = load_articles(since_int, until_int)
    if not articles:
        print("  📭 未找到符合条件的文章")
        print(f"  💡 请确认 {ARTICLES_DIR} 目录下有 .txt 文件")
        return

    print(f"  📄 找到 {len(articles)} 篇文章")

    # 加载已追踪模型
    existing_models = load_existing_models()
    print(f"  📊 已追踪 {len(existing_models)} 个模型")
    print()

    # 逐篇提取
    all_extracted = []
    article_results = []

    for idx, article in enumerate(articles, 1):
        title = article["标题"]
        body = article["全文"]
        date_int = article["日期"]

        print(f"  [{idx}/{len(articles)}] {title}")

        if args.dry_run:
            print(f"    🔍 DRY-RUN: 跳过 LLM 调用（全文 {len(body)} 字）")
            article_results.append({
                "序号": article["序号"],
                "标题": title,
                "提及的模型": "(dry-run)",
                "未追踪到的模型": "(dry-run)",
            })
            continue

        # 调用 LLM
        models = call_llm(body, api_key, api_base, model)

        if not models:
            print(f"    ⚠️ 未提取到模型")
            article_results.append({
                "序号": article["序号"],
                "标题": title,
                "提及的模型": "无明确新模型",
                "未追踪到的模型": "",
            })
            continue

        # 分类：已追踪 vs 未追踪
        mentioned_names = []
        untracked_names = []

        for model_info in models:
            model_name = model_info.get("model_name", "")
            if not model_name:
                continue

            mentioned_names.append(model_name)
            normalized = normalize_name(model_name)

            is_tracked = normalized in existing_models
            if not is_tracked:
                # 模糊匹配
                for existing in existing_models:
                    if len(normalized) > 4 and len(existing) > 4:
                        if normalized in existing or existing in normalized:
                            is_tracked = True
                            break

            if not is_tracked:
                untracked_names.append(model_name)
                model_info["_untracked"] = True

            all_extracted.append({
                **model_info,
                "source_article": title,
                "source_date": date_int,
            })

        tracked_count = len(mentioned_names) - len(untracked_names)
        print(f"    ✅ 提取 {len(mentioned_names)} 个模型（已追踪 {tracked_count}，未追踪 {len(untracked_names)}）")

        article_results.append({
            "序号": article["序号"],
            "标题": title,
            "提及的模型": "\n".join(mentioned_names),
            "未追踪到的模型": "\n".join(untracked_names) if untracked_names else "均已追踪",
        })

        # 礼貌调用间隔
        if idx < len(articles):
            time.sleep(1)

    # ── 保存结果 ──
    if not args.dry_run and article_results:
        # 保存文章级结果到 TXCrawl_result.xlsx
        df_result = pd.DataFrame(article_results)
        df_result.to_excel(RESULT_XLSX, index=False, engine="openpyxl")
        print(f"\n  💾 文章级结果: {RESULT_XLSX}")

        # 保存完整提取结果到 JSON
        extracted_json_path = EXTRACT_DIR / "extracted_models_llm.json"
        with open(extracted_json_path, "w", encoding="utf-8") as f:
            json.dump(all_extracted, f, ensure_ascii=False, indent=2)
        print(f"  💾 完整提取结果: {extracted_json_path}")

    # ── 汇总 ──
    print(f"\n{'='*60}")
    print("  汇总")
    print(f"{'='*60}")

    if args.dry_run:
        print(f"  📄 文章数: {len(articles)}")
        print(f"  🔍 DRY-RUN 模式，未调用 LLM")
        return

    untracked_all = {}
    for model_info in all_extracted:
        if model_info.get("_untracked"):
            key = normalize_name(model_info["model_name"])
            if key not in untracked_all:
                untracked_all[key] = model_info

    print(f"  📄 文章数: {len(articles)}")
    print(f"  🤖 提取到的模型总数: {len(all_extracted)}")
    print(f"  🆕 未追踪的新模型: {len(untracked_all)}")

    if untracked_all:
        print(f"\n  未追踪模型列表:")
        for idx, (_, info) in enumerate(sorted(untracked_all.items()), 1):
            name = info["model_name"]
            company = info.get("company", "")
            brief = info.get("brief", "")
            mtype = info.get("model_type", "")
            print(f"    {idx}. {name} ({company}) [{mtype}] — {brief}")

    print(f"\n  💡 主方案：在对话中让 AI Copilot 读取文章并提取（更准确）")
    print(f"  💡 次级方案：本脚本通过 LLM API 自动提取（更快速）")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
