"""
GPT-5.5 审核 + 补全 + 置信度标注
================================
读取主表格中本次新增的模型，分批发送给 GPT-5.5 进行：
1. 补全缺失字段（尺寸/发布时间/官网）
2. 质量审核（分类、公司名统一性、重复检测）
3. 置信度标注（高/中/低）

高置信度修正自动应用到表格，低置信度写入核实情况列让人确认。

用法:
    python review_models.py                           # 审核本次新增模型
    python review_models.py --all                     # 审核全部模型
    python review_models.py --dry-run                 # 预览，不调用 LLM
    python review_models.py --batch-size 15           # 每批 15 个模型

环境变量（或 .env 文件）:
    LLM_API_KEY=sk-xxx
    LLM_API_BASE=https://api.kuai.host/v1
    REVIEW_MODEL=gpt-5.5                              # 审核用模型

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
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ── 路径 ──
ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "Report"
EXCEL_PATH = DATA_DIR / "Object-Models-Updated.xlsx"
REVIEW_REPORT_PATH = REPORT_DIR / "review_report.md"

# ── 回收站历史删除案例（RAG 参考） ──
# 审核时动态加载 recycle.json 作为参考，让 LLM 了解哪些模型曾被删除及原因
RECYCLE_JSON_PATH = ROOT.parent / "docs" / "data" / "recycle.json"


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
        # 按 reason 去重，每类取最新一条作为代表
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


# ── 审核 Prompt ──
REVIEW_PROMPT_PREFIX = """## ⚠️ 历史删除参考（重要）
以下模型曾被人工审核后从追踪列表中删除。请参考这些案例的删除原因，在审核时避免放行同类问题：

### 典型删除案例（few-shot）
1. **gap 过时**：GPT-5.5 Instant（OpenAI）— 发布 2026-05-05，录入 2026-05-30，gap=25 天。我们只追踪近期新发布的模型，发布日期距离录入超过 7 天的应标记删除。
2. **重复录入**：豆包 Seed 2.0 Pro / Doubao-Seed-2.0-Pro — 同一模型的中英文名，名称归一化后重复。注意识别中英文、带连字符/空格等变体。
3. **非模型**：Claude Code（Anthropic）— 编程智能体/产品工具，非基座模型或模型版本更新。我们只追踪模型本身，不追踪基于模型的产品。
4. **未经证实**：DeepSeek V4 — 版本号存疑，无官方发布渠道可验证。对于无法从官方渠道确认的模型信息，应标记存疑。
5. **未公开发布**：Mythos Preview（Anthropic）— 无限期封印的内部模型，无法公开使用或验证。

### 动态历史记录
以下是回收站中的更多删除案例（来自 recycle.json），供你参考判断模式：
{recycle_examples}

### 审核原则
- 遇到与上述案例**同类模式**的模型，应标记 should_remove = true
- gap 过时规则：created_date - release_date > 7 天 → 建议删除（仅对 2026-05-28 及之后创建的模型生效）
- 重复检测：注意中英文名、连字符/空格/大小写变体
- 产品 vs 模型：编程工具、搜索引擎、聊天产品等不是模型本身

---

"""

REVIEW_PROMPT = """你是一名资深 AI 模型追踪分析师。请审核以下模型数据，完成四项任务：

## 任务 1：模型名称规范性审核（最重要）
检查每个模型名称是否符合规范：
- **必须是具体的模型/产品名称 + 版本号/型号**，不能是产品泛称
- 正确示例：`DeepSeek-V4-Pro-Max`、`Claude Opus 4.7`、`Qwen3.6-27B`、`可灵AI视频3.0`
- 错误示例：`千问`、`豆包`、`元宝`、`ChatGPT`、`Cursor`、`Sora`、`Manus`、`即梦`（这些是产品泛称，不指向具体版本）
- 如果模型名称是产品泛称（无版本号），在 issues 中标注"建议删除：产品泛称无版本号"，并将 should_remove 设为 true

## 任务 2：判断是否为近期新兴模型（宽松保留，分级标注）
本次追踪的时间窗口为 **{time_window}**。请基于你的世界知识判断每个模型：

**保留原则（宽松）**：只要模型的发布时间在 2026 年且与时间窗口相关，就应该保留。具体：
- 时间窗口内首次发布/重大版本更新/新上线 → 保留
- 时间窗口前后 1-2 周内发布的新兴模型 → 也保留（可能是采集延迟）
- 2026 年内发布但超出窗口较远的 → 仍保留，但标注"窗口外"

**仅删除**：
- 发布于 2025 年或更早的旧模型 → should_remove = true，标注"旧模型（发布于YYYY年）"
- 产品泛称（已在任务1处理）

**不要过度过滤**：宁可多保留、靠重要性分级来区分价值，也不要误删近期新兴模型。
如果你确定知道该模型的实际发布时间，在 corrections 中补全。

## 任务 3：补全缺失字段（重点：发布时间、备注、官网）
对每个模型，基于你的知识库补全以下缺失字段：
- **模型发布时间**（YYYY-MM-DD 格式，最重要）：指**模型提供方的官方发布日期**，不是平台上架日期。例如 DeepSeek-V4 的发布时间是 2026-04-24（官方公告日），不是某平台的上架日期。仅填你确定知道的。
- **备注**（语义化标签式，分号分隔）：描述模型核心特征、亮点、定价等。示例：`MoE架构；1T参数；262k上下文；GPQA 90.5%；$0.95/4`、`视频生成；成本减半`。不要写"DashScope百炼平台"这种来源信息，要写模型自身的技术特征。
- **官网**（模型提供方的官方页面）：指模型提供方自己的网站（如 `https://api-docs.deepseek.com`），不是代理平台的文档链接（如阿里云 DashScope 文档）。
- **尺寸**（参数量，如 "70B"、"1.8T"）：仅填你确定知道的
- **任务类型**（通用对话/代码生成/图像生成/视频生成/语音合成 等）

## 任务 4：质量审核 + 重要性评级
检查以下质量问题：
- 分类错误：如把产品分成基座、把智能体分成领域模型
- 公司名不统一：如"阿里"vs"阿里巴巴"、"Google"vs"谷歌"
- 重复模型：同一模型出现多次（名称略有不同）
- 开闭源标注错误

重要性评级（基于重点关注清单 + 模型自身价值）：

### 评级标准
| 评级 | 条件（满足任一即可） |
|------|---------------------|
| **高** | 1. 来自**重点关注公司**的旗舰/重大版本更新 2. 技术突破性模型（SOTA / 新范式） 3. 引发行业广泛讨论的模型 |
| **中** | 1. 来自**优秀关注公司**的模型 2. 重点公司的非旗舰/小更新 3. 特定领域重要的模型 |
| **低** | 1. 来自**其他公司**的增量更新 2. 跟随性产品 3. 高校/科研机构的领域微调模型 |

### 重点关注公司清单
**国内重点**：阿里/通义/Qwen、字节跳动/豆包/Seed、月之暗面/Kimi、MiniMax/海螺、智谱/GLM、腾讯/混元
**国内优秀**：小米/Mimo、智源/Emu、百度/Ernie、蚂蚁/LingBot、美团/LongCat、快手/可灵
**国外重点**：OpenAI/GPT、Google DeepMind/Gemini、Anthropic/Claude
**国外优秀**：Meta/Llama、xAI/Grok、NVIDIA、Mistral AI、Runway
**其他**：StepFun/阶跃星辰、科大讯飞、小红书/FireRed、宇树、高校科研机构等

注意：同一家公司，旗舰模型=高，小更新/子变体=中。例如 GPT-5.5 Pro=高，GPT-4o-mini 增量更新=中。

## 输出格式
请严格以 JSON 数组格式输出，每个元素对应一个模型的审核结果：
[
  {{
    "model_name": "原始模型名称（不要修改）",
    "should_remove": false,
    "corrections": {{
      "尺寸": "70B",
      "模型发布时间": "2026-04-15",
      "官网": "https://example.com",
      "任务类型": "通用对话",
      "公司": "修正后的公司名（如需统一）",
      "类型": "修正后的分类（如需修正）",
      "开闭源": "修正后（如需修正）"
    }},
    "confidence": "高",
    "importance": "高",
    "importance_reason": "一句话说明为何给出该重要性评级（必填）",
    "issues": ["问题描述1", "问题描述2"],
    "notes": "审核备注（可选）"
  }}
]

规则：
- should_remove: 如果该模型不应被录入（产品泛称/旧模型），设为 true
- corrections 中只包含需要修正/补全的字段，不需要改的不要写
- 不确定的补全不要填，宁缺勿错
- confidence 含义：高=非常确定、中=较确定但建议人工复核、低=不太确定需人工确认
- importance 含义：高=最值得关注、中=值得关注、低=一般
- importance_reason: 必填，一句话说明理由（如"OpenAI旗舰模型重大更新"、"重点关注公司的非旗舰子变体"）

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


def get_review_model_config() -> tuple[str, str, str]:
    """获取审核用 LLM API 配置（GPT-5.5）。"""
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "https://api.kuai.host/v1")
    model = os.environ.get("REVIEW_MODEL", "gpt-5.5")
    return api_key, api_base, model


def call_review_llm(models_json: str, api_key: str, api_base: str, model: str,
                    time_window: str = "近期") -> list[dict]:
    """调用 LLM 进行审核。前缀包含历史删除案例 few-shot。"""
    recycle_examples = _load_recycle_examples()
    prefix = REVIEW_PROMPT_PREFIX.format(recycle_examples=recycle_examples) if recycle_examples else ""
    prompt = prefix + REVIEW_PROMPT.format(models_json=models_json, time_window=time_window)

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 8000,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()

    resp_json = resp.json()
    content = ""
    if "choices" in resp_json and resp_json["choices"]:
        choice = resp_json["choices"][0]
        if isinstance(choice, dict) and "message" in choice:
            content = choice["message"].get("content", "")

    if not content:
        raise ValueError(f"无法从 API 响应中提取内容，响应结构: {list(resp_json.keys())}")

    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return []


def apply_review_results(df: pd.DataFrame, review_results: list[dict]) -> tuple[int, int, int, list[str]]:
    """将审核结果应用到 DataFrame。

    返回: (自动应用数, 待人工确认数, 删除数, 审核日志列表)
    """
    auto_applied = 0
    pending_human = 0
    removed = 0
    rows_to_drop = []
    review_log = []

    # 建立模型名 → 审核结果的索引
    review_index: dict[str, dict] = {}
    for result in review_results:
        name = result.get("model_name", "").strip()
        if name:
            review_index[name.lower()] = result

    name_col = "模型名称"
    if name_col not in df.columns:
        return 0, 0, 0, ["❌ 表格中无'模型名称'列"]

    for idx, row in df.iterrows():
        model_name = str(row.get(name_col, "")).strip()
        if not model_name:
            continue

        result = review_index.get(model_name.lower())
        if not result:
            continue

        corrections = result.get("corrections", {})
        confidence = result.get("confidence", "低")
        importance = result.get("importance", "中")
        importance_reason = result.get("importance_reason", "")
        issues = result.get("issues", [])
        notes = result.get("notes", "")
        should_remove = result.get("should_remove", False)

        # 处理建议删除的模型（产品泛称/旧模型）
        if should_remove:
            issue_desc = "; ".join(issues) if issues else "GPT-5.5建议删除"
            if confidence == "高":
                # 高置信度的删除建议：直接删除
                rows_to_drop.append(idx)
                removed += 1
                review_log.append(f"  🗑️ [{model_name}] 已删除: {issue_desc}")
            else:
                # 中/低置信度的删除建议：标注待人工确认
                pending_human += 1
                human_note = f"⚠️ GPT-5.5建议删除({confidence}置信)待人工确认 — {issue_desc}"
                existing_verify = str(row.get("核实情况", "")).strip()
                new_verify = f"{existing_verify}; {human_note}" if existing_verify and existing_verify != "nan" else human_note
                df.at[idx, "核实情况"] = new_verify
                review_log.append(f"  ⚠️ [{model_name}] 建议删除待人工确认({confidence}): {issue_desc}")
            continue

        if not corrections and not issues:
            # 只更新重要性（写入备注末尾）
            if importance:
                _append_importance(df, idx, importance, importance_reason)
            continue

        if confidence == "高":
            # 高置信度：自动应用
            changes_made = []
            for field, value in corrections.items():
                if not value:
                    continue
                if field in df.columns:
                    current = str(row.get(field, "")).strip()
                    if not current or current == "nan" or current == "未知":
                        df.at[idx, field] = value
                        changes_made.append(f"{field}={value}")

            if changes_made:
                auto_applied += 1
                # 更新核实情况
                existing_verify = str(row.get("核实情况", "")).strip()
                new_verify = f"{existing_verify}; GPT-5.5审核补全(高置信)" if existing_verify and existing_verify != "nan" else "GPT-5.5审核补全(高置信)"
                df.at[idx, "核实情况"] = new_verify
                review_log.append(f"  ✅ [{model_name}] 自动补全: {', '.join(changes_made)}")
        else:
            # 中/低置信度：写入核实情况，待人工确认
            pending_human += 1
            correction_desc = "; ".join(f"{k}→{v}" for k, v in corrections.items() if v)
            issue_desc = "; ".join(issues) if issues else ""

            human_note_parts = []
            if correction_desc:
                human_note_parts.append(f"建议修正: {correction_desc}")
            if issue_desc:
                human_note_parts.append(f"问题: {issue_desc}")
            if notes:
                human_note_parts.append(notes)
            human_note = f"⚠️ GPT-5.5审核({confidence}置信)待人工确认 — {'; '.join(human_note_parts)}"

            existing_verify = str(row.get("核实情况", "")).strip()
            new_verify = f"{existing_verify}; {human_note}" if existing_verify else human_note
            df.at[idx, "核实情况"] = new_verify
            review_log.append(f"  ⚠️ [{model_name}] 待人工确认({confidence}): {correction_desc or issue_desc}")

        # 写入重要性（不对建议删除的模型标注）
        if importance and not should_remove:
            _append_importance(df, idx, importance, importance_reason)

    # 执行删除操作（高置信度的 should_remove）
    if rows_to_drop:
        df.drop(rows_to_drop, inplace=True)
        df.reset_index(drop=True, inplace=True)

    return auto_applied, pending_human, removed, review_log


def _append_importance(df: pd.DataFrame, idx: int, importance: str, reason: str = ""):
    """将重要性评级和理由写入备注字段末尾。

    格式：[重要性:高|OpenAI旗舰模型重大更新]
    兼容旧格式：[重要性:高]（无理由时）
    """
    if "备注" not in df.columns:
        return
    existing = str(df.at[idx, "备注"]).strip()
    if existing == "nan":
        existing = ""
    # 避免重复标注
    if "重要性:" in existing or "重要性：" in existing:
        return
    reason_clean = reason.strip() if reason else ""
    if reason_clean:
        importance_tag = f"[重要性:{importance}|{reason_clean}]"
    else:
        importance_tag = f"[重要性:{importance}]"
    df.at[idx, "备注"] = f"{existing} {importance_tag}".strip() if existing else importance_tag


def generate_review_report(review_results: list[dict], auto_applied: int,
                           pending_human: int, removed: int, review_log: list[str]) -> str:
    """生成审核报告 Markdown。"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(review_results)

    high_importance = sum(1 for r in review_results if r.get("importance") == "高")
    mid_importance = sum(1 for r in review_results if r.get("importance") == "中")
    low_importance = sum(1 for r in review_results if r.get("importance") == "低")
    remove_suggested = sum(1 for r in review_results if r.get("should_remove"))

    lines = [
        f"# GPT-5.5 模型审核报告",
        f"",
        f"**生成时间**: {now_str}",
        f"**审核模型数**: {total}",
        f"",
        f"## 审核统计",
        f"",
        f"| 指标 | 数量 |",
        f"|------|------|",
        f"| 自动补全（高置信） | {auto_applied} |",
        f"| 待人工确认（中/低置信） | {pending_human} |",
        f"| 🗑️ 已删除（泛称/旧模型） | {removed} |",
        f"| 无需修改 | {total - auto_applied - pending_human - remove_suggested} |",
        f"",
        f"## 重要性分布",
        f"",
        f"| 重要性 | 数量 |",
        f"|--------|------|",
        f"| 🔴 高（最值得关注） | {high_importance} |",
        f"| 🟡 中（值得关注） | {mid_importance} |",
        f"| 🟢 低（一般） | {low_importance} |",
        f"",
    ]

    # 高重要性模型列表
    high_models = [r for r in review_results if r.get("importance") == "高"]
    if high_models:
        lines.append("## 🔴 最值得关注的模型")
        lines.append("")
        for r in high_models:
            name = r.get("model_name", "")
            notes = r.get("notes", "")
            lines.append(f"- **{name}**: {notes}" if notes else f"- **{name}**")
        lines.append("")

    # 审核详情
    if review_log:
        lines.append("## 审核详情")
        lines.append("")
        for log_line in review_log:
            lines.append(log_line)
        lines.append("")

    # 待人工确认列表
    pending_models = [r for r in review_results if r.get("confidence") in ("中", "低")]
    if pending_models:
        lines.append("## ⚠️ 待人工确认")
        lines.append("")
        for r in pending_models:
            name = r.get("model_name", "")
            confidence = r.get("confidence", "")
            corrections = r.get("corrections", {})
            issues = r.get("issues", [])
            desc_parts = []
            if corrections:
                desc_parts.append("建议: " + ", ".join(f"{k}→{v}" for k, v in corrections.items() if v))
            if issues:
                desc_parts.append("问题: " + ", ".join(issues))
            desc = " | ".join(desc_parts)
            lines.append(f"- [{confidence}置信] **{name}**: {desc}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="GPT-5.5 模型审核 + 补全 + 置信度")
    parser.add_argument("--all", action="store_true", help="审核全部模型（默认只审核新增模型）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不调用 LLM")
    parser.add_argument("--batch-size", type=int, default=20, help="每批审核的模型数（默认 20）")
    parser.add_argument("--since", type=str, default=None, help="追踪窗口起始日期 (YYYYMMDD)")
    parser.add_argument("--until", type=str, default=None, help="追踪窗口截止日期 (YYYYMMDD)")
    args = parser.parse_args()

    load_env()
    api_key, api_base, model = get_review_model_config()

    print("🔍 GPT-5.5 模型审核")
    print(f"  API: {api_base}")
    print(f"  模型: {model}")
    print(f"  模式: {'全部模型' if args.all else '仅新增模型'}")
    if args.dry_run:
        print(f"  🔍 DRY-RUN 模式")
    print()

    if not api_key and not args.dry_run:
        print("  ❌ 未配置 LLM_API_KEY")
        return

    if not EXCEL_PATH.exists():
        print(f"  ❌ 表格不存在: {EXCEL_PATH}")
        return

    df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    # 将可能为空（被推断为 float64）的文本列强制转为 object，避免写入字符串时报错
    text_columns = ["核实情况", "是否接入", "workflow接入进展", "备注", "官网", "模型发布时间", "触发时间"]
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].astype(object)
    print(f"  📊 表格总行数: {len(df)}")

    # 筛选待审核模型
    if args.all:
        review_df = df
    else:
        is_new_col = "是否新增"
        if is_new_col in df.columns:
            review_df = df[df[is_new_col].astype(str).str.lower().isin(["new", "是"])]
        else:
            review_df = df

    if review_df.empty:
        print("  📭 无待审核模型")
        return

    print(f"  🎯 待审核: {len(review_df)} 个模型")

    # 构造审核输入（精简字段，减少 token 消耗）
    review_fields = ["模型名称", "公司", "国内外", "开闭源", "尺寸", "类型",
                     "能否推理", "任务类型", "官网", "备注", "模型发布时间", "核实情况"]
    review_data = []
    for _, row in review_df.iterrows():
        item = {}
        for field in review_fields:
            val = str(row.get(field, "")).strip()
            if val and val != "nan":
                item[field] = val
        review_data.append(item)

    if args.dry_run:
        print(f"\n  🔍 DRY-RUN: 将审核 {len(review_data)} 个模型，分 {(len(review_data) + args.batch_size - 1) // args.batch_size} 批")
        print(f"  示例（前 3 个）:")
        for item in review_data[:3]:
            print(f"    {json.dumps(item, ensure_ascii=False)[:120]}")
        return

    # 分批审核
    all_review_results = []
    total_batches = (len(review_data) + args.batch_size - 1) // args.batch_size
    total_start = time.time()

    for batch_idx in range(total_batches):
        batch_start = batch_idx * args.batch_size
        batch_end = min(batch_start + args.batch_size, len(review_data))
        batch = review_data[batch_start:batch_end]

        bar_filled = int((batch_idx / total_batches) * 20)
        bar_str = f"[{'#' * bar_filled}{'.' * (20 - bar_filled)}]"
        print(f"\n  {bar_str} 批次 [{batch_idx + 1}/{total_batches}]（模型 {batch_start + 1}-{batch_end}）")

        batch_json = json.dumps(batch, ensure_ascii=False, indent=2)
        batch_api_start = time.time()

        # 构造时间窗口描述（传给 GPT-5.5 做新发布判断）
        time_window = "近期"
        if args.since or args.until:
            since_fmt = f"{args.since[:4]}-{args.since[4:6]}-{args.since[6:]}" if args.since else "?"
            until_fmt = f"{args.until[:4]}-{args.until[4:6]}-{args.until[6:]}" if args.until else "?"
            time_window = f"{since_fmt} ~ {until_fmt}"

        try:
            results = call_review_llm(batch_json, api_key, api_base, model, time_window=time_window)
            batch_elapsed = time.time() - batch_api_start
            print(f"    ✅ 审核完成（{batch_elapsed:.1f}s），返回 {len(results)} 条结果")
            all_review_results.extend(results)
        except Exception as exc:
            batch_elapsed = time.time() - batch_api_start
            print(f"    ❌ 审核失败（{batch_elapsed:.1f}s）: {exc}")

        # 礼貌间隔
        if batch_idx < total_batches - 1:
            time.sleep(2)

    total_elapsed = time.time() - total_start

    if not all_review_results:
        print(f"\n  ❌ 未获得任何审核结果（总耗时 {total_elapsed:.1f}s）")
        return

    # 应用审核结果
    print(f"\n  📝 应用审核结果...")
    auto_applied, pending_human, removed, review_log = apply_review_results(df, all_review_results)

    # 保存表格
    try:
        df.to_excel(EXCEL_PATH, index=False, engine="openpyxl")
        print(f"  💾 表格已更新: {EXCEL_PATH}")
    except PermissionError:
        print(f"  ❌ 表格被占用（请关闭 Excel）: {EXCEL_PATH}")
    except Exception as exc:
        print(f"  ❌ 保存失败: {exc}")

    # 保存审核结果 JSON
    review_json_path = REPORT_DIR / "review_results.json"
    REPORT_DIR.mkdir(exist_ok=True)
    with open(review_json_path, "w", encoding="utf-8") as f:
        json.dump(all_review_results, f, ensure_ascii=False, indent=2)
    print(f"  💾 审核结果: {review_json_path}")

    # 生成审核报告
    report_content = generate_review_report(all_review_results, auto_applied, pending_human, removed, review_log)
    REVIEW_REPORT_PATH.write_text(report_content, encoding="utf-8")
    print(f"  📋 审核报告: {REVIEW_REPORT_PATH}")

    # 汇总
    print(f"\n{'='*60}")
    print(f"  审核汇总（总耗时 {total_elapsed:.1f}s）")
    print(f"{'='*60}")
    print(f"  审核模型数: {len(all_review_results)}")
    print(f"  ✅ 自动补全（高置信）: {auto_applied}")
    print(f"  🗑️ 已删除（泛称/旧模型）: {removed}")
    print(f"  ⚠️ 待人工确认（中/低置信）: {pending_human}")

    # 重要性分布
    high_count = sum(1 for r in all_review_results if r.get("importance") == "高")
    mid_count = sum(1 for r in all_review_results if r.get("importance") == "中")
    low_count = sum(1 for r in all_review_results if r.get("importance") == "低")
    print(f"  🔴 高重要性: {high_count}  🟡 中: {mid_count}  🟢 低: {low_count}")

    if high_count > 0:
        print(f"\n  🔴 最值得关注:")
        for r in all_review_results:
            if r.get("importance") == "高":
                print(f"     • {r['model_name']}")


if __name__ == "__main__":
    main()
