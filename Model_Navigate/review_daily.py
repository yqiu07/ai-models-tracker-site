# 2026/05/20/11:06
# name: review_daily
# description: 巡检修正当日日报 — 调用 LLM 审核 daily_report.json 中的模型，移除不属于时间窗口的模型，修正错误信息

"""
日报巡检修正脚本
===============
读取 docs/data/daily_report.json，对其中的模型调用 LLM 审核：
1. 移除不属于时间窗口的模型（旧模型、产品泛称）
2. 修正错误字段（公司名、分类、开闭源等）
3. 补全缺失字段（发布时间、官网、尺寸等）
4. 将审核后的结果写回 daily_report.json 和总表

用法:
    python review_daily.py                    # 审核最新日报
    python review_daily.py --since 20260519 --until 20260519  # 指定时间范围
    python review_daily.py --dry-run          # 预览模式，不写回

环境变量:
    LLM_API_KEY / LLM_API_BASE  — 主审核 LLM (GPT-5.5)
    LLM_MODEL — 审核用模型（默认 gpt-5.5）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"
DOCS_DATA_DIR = ROOT.parent / "docs" / "data"
DAILY_REPORT_PATH = DOCS_DATA_DIR / "daily_report.json"
EXCEL_PATH = DATA_DIR / "Object-Models.xlsx"

# ── 回收站历史删除案例（RAG 参考） ──
RECYCLE_JSON_PATH = DOCS_DATA_DIR / "recycle.json"


def _load_recycle_examples() -> str:
    """从 recycle.json 加载删除历史，提炼为 few-shot 参考文本。"""
    if not RECYCLE_JSON_PATH.exists():
        return ""
    try:
        with open(RECYCLE_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        models = data.get("models", [])
        if not models:
            return ""
        seen_categories = {}
        for m in reversed(models):
            reason = m.get("reason", "")
            if not reason:
                continue
            category = reason.split(":")[0].strip()
            if category not in seen_categories:
                seen_categories[category] = m
        if not seen_categories:
            return ""
        lines = []
        for category, m in seen_categories.items():
            lines.append(
                f'  - {m["name"]}（{m.get("company", "")}）→ 已删除，原因: {m.get("reason", "")}'
            )
        return "\n".join(lines)
    except Exception:
        return ""


REVIEW_PROMPT_PREFIX = """## ⚠️ 历史删除参考（重要）
以下模型曾被人工审核后从追踪列表中删除。请参考这些案例的删除原因，在审核时避免放行同类问题：

### 典型删除案例（few-shot）
1. **gap 过时**：GPT-5.5 Instant（OpenAI）— 发布 2026-05-05，录入 2026-05-30，gap=25 天。只追踪近期新发布的模型，发布日期距离录入超过 7 天的应标记删除。
2. **重复录入**：豆包 Seed 2.0 Pro / Doubao-Seed-2.0-Pro — 同一模型的中英文名，名称归一化后重复。注意识别中英文、连字符/空格等变体。
3. **非模型**：Claude Code（Anthropic）— 编程智能体/产品工具，非基座模型或模型版本更新。
4. **未经证实**：DeepSeek V4 — 版本号存疑，无官方发布渠道可验证。
5. **未公开发布**：Mythos Preview（Anthropic）— 无限期封印的内部模型。

### 动态历史记录
{recycle_examples}

### 审核原则
- 遇到与上述案例同类模式的模型，应标记 should_remove = true
- gap 过时规则：created_date - release_date > 7 天 → 建议删除（仅对 2026-05-28 及之后创建的模型生效）
- 重复检测：注意中英文名、连字符/空格/大小写变体
- 产品 vs 模型：编程工具、搜索引擎、聊天产品等不是模型本身

---

"""

REVIEW_PROMPT = """你是一名资深 AI 模型追踪分析师。请审核以下日报中的模型数据。

## 时间窗口
本次日报的时间窗口为 **{since} ~ {until}**。

## 审核任务

### 1. 时间窗口过滤（最重要）
判断每个模型是否真正属于这个时间窗口：
- 该时间窗口内首次发布/重大版本更新 → 保留
- 发布于 2025 年或更早 → should_remove = true
- 产品泛称无版本号（如"ChatGPT""豆包""Sora"）→ should_remove = true
- 宁可保留，不要误删（宽松原则）

### 2. 字段修正
- 公司名统一（如"阿里"→"阿里巴巴/通义"）
- 分类修正（如把产品分成基座是错误的）
- 开闭源修正
- 补全发布时间（YYYY-MM-DD）、官网、尺寸

### 3. 备注优化
- 精简冗长备注，保留核心技术特征
- 移除 [重要性:X|xxx] 等内部标注

## 输出格式
严格 JSON 数组，每个元素对应一个模型：
[
  {{
    "name": "原始模型名称（不要修改）",
    "should_remove": false,
    "reason": "保留/删除原因（一句话）",
    "corrections": {{
      "company": "修正后的公司名（不改则不写）",
      "type": "修正后的分类",
      "open_source": "修正后",
      "release_date": "2026-05-19",
      "size": "70B",
      "note": "优化后的备注"
    }}
  }}
]

规则：
- corrections 中只包含需要修改的字段，不需要改的不要写
- 不确定的不要填
- reason 必填

---
待审核的模型数据：
{models_json}
"""


def load_env():
    """加载 .env 文件。"""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), value)


def call_llm(prompt: str) -> str:
    """调用 LLM API。"""
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "https://api.kuai.host/v1")
    model = os.environ.get("REVIEW_MODEL", "gpt-5.5")

    if not api_key:
        print("[ERROR] No API key configured (LLM_API_KEY)")
        sys.exit(1)

    url = f"{api_base}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 8000,
    }

    print(f"[INFO] Calling {model} for review...")
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return content
        except Exception as exc:
            print(f"[WARN] Attempt {attempt + 1} failed: {exc}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    print("[ERROR] All LLM attempts failed")
    sys.exit(1)


def parse_review_response(response_text: str) -> list[dict]:
    """从 LLM 响应中提取 JSON 数组。"""
    json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if not json_match:
        print("[ERROR] Cannot parse LLM response as JSON array")
        print(f"[DEBUG] Response: {response_text[:500]}")
        return []
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError as exc:
        print(f"[ERROR] JSON decode error: {exc}")
        return []


def apply_review(models: list[dict], reviews: list[dict]) -> list[dict]:
    """应用审核结果到模型列表。返回修正后的模型列表（已移除 should_remove 的）。"""
    review_map = {}
    for r in reviews:
        name = r.get("name", "")
        if name:
            review_map[name] = r

    result = []
    removed_count = 0
    corrected_count = 0

    for model in models:
        model_name = model.get("name", "")
        review = review_map.get(model_name)

        if review and review.get("should_remove"):
            removed_count += 1
            print(f"  [REMOVE] {model_name} - {review.get('reason', '')}")
            continue

        if review and review.get("corrections"):
            corrections = review["corrections"]
            for field, value in corrections.items():
                if value and field in model:
                    model[field] = value
                    corrected_count += 1

        result.append(model)

    print(f"\n[OK] Review applied: {removed_count} removed, {corrected_count} corrections")
    return result


def main():
    parser = argparse.ArgumentParser(description="巡检修正当日日报")
    parser.add_argument("--since", help="起始日期 YYYYMMDD")
    parser.add_argument("--until", help="截止日期 YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写回")
    args = parser.parse_args()

    load_env()

    # 读取日报
    if not DAILY_REPORT_PATH.exists():
        print(f"[ERROR] daily_report.json not found: {DAILY_REPORT_PATH}")
        sys.exit(1)

    with open(DAILY_REPORT_PATH, "r", encoding="utf-8") as f:
        report = json.load(f)

    models = report.get("models", [])
    meta = report.get("meta", {})

    if not models:
        print("[INFO] No models in daily report, nothing to review")
        return

    since = args.since or meta.get("since", "").replace("-", "")
    until = args.until or meta.get("until", "").replace("-", "")
    since_dash = f"{since[:4]}-{since[4:6]}-{since[6:8]}" if len(since) == 8 else meta.get("since", "")
    until_dash = f"{until[:4]}-{until[4:6]}-{until[6:8]}" if len(until) == 8 else meta.get("until", "")

    print(f"[INFO] Reviewing daily report: {since_dash} ~ {until_dash}, {len(models)} models")

    # 构造审核 prompt（前缀含历史删除案例 few-shot）
    recycle_examples = _load_recycle_examples()
    prefix = REVIEW_PROMPT_PREFIX.format(recycle_examples=recycle_examples) if recycle_examples else ""
    models_json = json.dumps(models, ensure_ascii=False, indent=2)
    prompt = prefix + REVIEW_PROMPT.format(
        since=since_dash,
        until=until_dash,
        models_json=models_json,
    )

    # 调用 LLM
    response = call_llm(prompt)
    reviews = parse_review_response(response)

    if not reviews:
        print("[WARN] No review results, keeping original report")
        return

    print(f"[INFO] Got {len(reviews)} review results")

    # 应用审核结果
    reviewed_models = apply_review(models, reviews)

    if args.dry_run:
        print(f"\n[DRY-RUN] Would keep {len(reviewed_models)} / {len(models)} models")
        print("[DRY-RUN] Not writing back")
        return

    # 写回 daily_report.json
    report["models"] = reviewed_models
    report["meta"]["count"] = len(reviewed_models)
    report["meta"]["reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(DAILY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] Written back to {DAILY_REPORT_PATH.name} ({len(reviewed_models)} models)")

    # 同步更新总表（移除被删除的模型）
    if EXCEL_PATH.exists():
        try:
            df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
            removed_names = set(m.get("name", "") for m in models) - set(m.get("name", "") for m in reviewed_models)
            if removed_names:
                before_count = len(df)
                df = df[~df["模型名称"].isin(removed_names)]
                after_count = len(df)
                df.to_excel(EXCEL_PATH, index=False, engine="openpyxl")
                print(f"[OK] Updated master table: removed {before_count - after_count} models")
        except Exception as exc:
            print(f"[WARN] Failed to update master table: {exc}")


if __name__ == "__main__":
    main()
