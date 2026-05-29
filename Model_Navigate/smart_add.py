"""
智能添加模型 — 从用户输入的文本/链接中提取模型信息并写入总表。
============================================================
Re 2026/05/25/15:00

name: smart_add.py
description: 接收用户输入（链接/文本/模型名称），调用 LLM 自动解析为结构化模型信息，
             查重后追加到 all_models.json 和对应日报文件中。
             由 GitHub Actions workflow_dispatch 触发。

用法:
    python smart_add.py --content "https://xxx 或 一段文本"

环境变量:
    LLM_API_KEY       — DashScope API Key
    LLM_API_BASE      — (可选) 默认 https://dashscope.aliyuncs.com/compatible-mode/v1
    LLM_MODEL         — (可选) 默认 qwen-plus
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── 路径 ──
ROOT = Path(__file__).parent
DOCS_DATA = ROOT.parent / "docs" / "data"
ALL_MODELS_PATH = DOCS_DATA / "all_models.json"
DAILY_REPORT_PATH = DOCS_DATA / "daily_report.json"
RECYCLE_PATH = DOCS_DATA / "recycle.json"

# ── LLM 配置 ──
API_BASE = os.environ.get("LLM_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "qwen-plus")

# ── 提取 Prompt ──
SMART_ADD_PROMPT = """你是一名 AI 模型信息提取专家。用户将提供一段内容（可能是URL、新闻文本、或模型名称），
请从中提取所有**具体的 AI 模型**信息。

## 规则

1. 只提取有具体名称和版本号的模型，不提取泛称（如"ChatGPT""豆包"）
2. 如果输入是 URL，请分析 URL 指向的可能内容（从域名和路径推断）
3. 如果输入只是模型名称（如"Gemini 3.5 Flash"），也要尝试补全公司、类型等信息
4. 发布日期：如果文本中有明确提及则填写，否则用今天的日期 {today}
5. 所有不确定的字段留空字符串 ""

## 输出字段

- name: 模型名称（官方名称+版本号）
- company: 发布公司
- domestic: 国内/国外
- open_source: 开源/闭源/（不确定则留空）
- size: 参数量（如 "70B"，不确定则留空）
- type: 类型（多模态/大语言模型/代码/语音/视频/图像/智能体 等）
- reasoning: thinking/non-thinking/（不确定则留空）
- task_type: 任务类型（通用对话/代码生成/图像生成 等，不确定则留空）
- website: 官网或来源URL（不确定则留空）
- note: 一句话描述或备注
- release_date: 发布日期 YYYY-MM-DD（不确定则留空）

## 输出格式

严格输出 JSON 数组，不要输出其他内容。如果无法提取任何模型，输出空数组 []。

示例：
[
  {{"name": "Gemini 3.5 Flash", "company": "Google", "domestic": "国外", "open_source": "闭源", "size": "", "type": "多模态", "reasoning": "thinking", "task_type": "通用对话", "website": "", "note": "Google DeepMind旗舰模型", "release_date": "2026-05-19"}}
]

---
今日日期：{today}
用户输入内容：
{content}
"""


def call_llm(content: str) -> list[dict]:
    """调用 LLM 解析用户输入，返回模型信息列表。"""
    if not API_KEY:
        print("[ERROR] LLM_API_KEY not set")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    prompt = SMART_ADD_PROMPT.format(today=today, content=content)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }

    print(f"[INFO] Calling LLM ({MODEL})...")
    resp = requests.post(f"{API_BASE}/chat/completions", headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    text = result["choices"][0]["message"]["content"].strip()
    # 提取 JSON（可能被 markdown 包裹）
    if "```" in text:
        match = text.split("```")[1]
        if match.startswith("json"):
            match = match[4:]
        text = match.strip()

    models = json.loads(text)
    if not isinstance(models, list):
        models = [models]

    print(f"[INFO] LLM extracted {len(models)} model(s)")
    return models


def load_all_models() -> dict:
    """加载 all_models.json。"""
    if ALL_MODELS_PATH.exists():
        with open(ALL_MODELS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"models": [], "meta": {"total": 0}}


def deduplicate(new_models: list[dict], existing: list[dict]) -> list[dict]:
    """按名称查重，返回不重复的新模型。"""
    existing_names = {m.get("name", "").lower() for m in existing}
    # 也排除回收站中的
    if RECYCLE_PATH.exists():
        with open(RECYCLE_PATH, "r", encoding="utf-8") as f:
            recycle = json.load(f)
            for m in recycle.get("models", []):
                existing_names.add(m.get("name", "").lower())

    unique = []
    for m in new_models:
        name = m.get("name", "").strip()
        if name and name.lower() not in existing_names:
            existing_names.add(name.lower())
            unique.append(m)
    return unique


def normalize_model(raw: dict) -> dict:
    """将 LLM 输出标准化为总表字段格式。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "name": raw.get("name", "").strip(),
        "company": raw.get("company", "").strip(),
        "domestic": raw.get("domestic", "").strip(),
        "open_source": raw.get("open_source", "").strip(),
        "size": raw.get("size", "").strip(),
        "type": raw.get("type", "").strip(),
        "reasoning": raw.get("reasoning", "").strip(),
        "task_type": raw.get("task_type", "").strip(),
        "website": raw.get("website", "").strip(),
        "note": raw.get("note", "").strip(),
        "release_date": raw.get("release_date", "").strip() or today,
        "created_date": today,
        "connected": "",
        "workflow_progress": "",
    }


def save_all_models(data: dict):
    """保存 all_models.json。"""
    data["meta"]["total"] = len(data["models"])
    data["meta"]["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ALL_MODELS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Saved {len(data['models'])} models to all_models.json")


def load_daily_report() -> dict:
    """加载 daily_report.json。"""
    if DAILY_REPORT_PATH.exists():
        with open(DAILY_REPORT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"models": [], "meta": {"total": 0}}


def save_daily_report(data: dict):
    """保存 daily_report.json。"""
    data.setdefault("meta", {})
    data["meta"]["total"] = len(data.get("models", []))
    data["meta"]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(DAILY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Saved {len(data.get('models', []))} models to daily_report.json")


def add_to_daily_report(new_models: list[dict]):
    """将新增模型追加到最新日报，按名称避免重复。"""
    daily_data = load_daily_report()
    daily_models = daily_data.setdefault("models", [])
    existing_names = {m.get("name", "").strip().lower() for m in daily_models}
    models_to_add = [m for m in new_models if m.get("name", "").strip().lower() not in existing_names]
    if not models_to_add:
        print("[INFO] No new model needs to be added to daily_report.json")
        return
    daily_data["models"] = models_to_add + daily_models
    save_daily_report(daily_data)


def main():
    parser = argparse.ArgumentParser(description="智能添加模型")
    parser.add_argument("--content", required=True, help="用户输入的文本/链接")
    parser.add_argument("--target", choices=["all", "daily"], default="all", help="写入目标：all=仅总表，daily=总表+最新日报")
    args = parser.parse_args()

    content = args.content.strip()
    if not content:
        print("[ERROR] Empty content")
        sys.exit(1)

    print(f"[INFO] Input ({len(content)} chars): {content[:100]}...")

    # 1. 调用 LLM 提取
    raw_models = call_llm(content)
    if not raw_models:
        print("[INFO] No models extracted. Done.")
        return

    # 2. 标准化
    normalized = [normalize_model(m) for m in raw_models]

    # 3. 加载现有数据并查重
    all_data = load_all_models()
    unique_models = deduplicate(normalized, all_data["models"])

    if not unique_models:
        print("[INFO] All extracted models already exist in the table. Done.")
        return

    print(f"[INFO] {len(unique_models)} new model(s) to add:")
    for m in unique_models:
        print(f"  - {m['name']} ({m['company']}, {m['type']})")

    # 4. 追加到总表
    all_data["models"] = unique_models + all_data["models"]
    save_all_models(all_data)

    if args.target == "daily":
        add_to_daily_report(unique_models)

    # 5. 输出摘要
    print(f"\n[DONE] Successfully added {len(unique_models)} model(s).")


if __name__ == "__main__":
    main()
