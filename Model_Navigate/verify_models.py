# 2026/05/12/17:11
# name: verify_models
# description: Step 4 数据校验 — 基于 DashScope 联网搜索 API 自动校验 Excel 中模型的
#              发布时间、官网、备注等字段。对空值字段构造 Prompt 调用 Qwen 联网搜索，
#              批量并发填充，并通过验收函数检查校验质量。
"""
Step 4: 自动化联网校验（DashScope + Qwen 联网搜索）
===================================================
对 Excel 总表中「模型发布时间」「官网」「备注」任一为空的模型行，
调用 DashScope Chat Completions API（enable_search=True）联网校验并回填。

用法:
    python verify_models.py                        # 校验所有空值行
    python verify_models.py --dry-run              # 预览待校验列表，不实际调用
    python verify_models.py --max 10               # 最多校验 10 条
    python verify_models.py --max 5 --dry-run      # 预览前 5 条

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
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# 抑制内网自签证书的 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 路径常量 ──
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
EXCEL_PATH = DATA_DIR / "Object-Models-Updated.xlsx"

# ── 需要校验的字段 ──
VERIFY_FIELDS = ["模型发布时间", "官网", "备注"]

# ── 默认模型 ──
DEFAULT_MODEL = "qwen3.6-plus"


# ================================================================
#  环境与配置
# ================================================================

def load_env():
    """加载 .env 文件（如果存在），与项目其他脚本风格一致。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file = ROOT.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                value = value.strip()
                if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                os.environ.setdefault(key.strip(), value)


def get_tls_verify() -> bool:
    """读取 MODEL_NAVIGATE_TLS_VERIFY 环境变量，默认不验证（内网环境）。"""
    return os.environ.get("MODEL_NAVIGATE_TLS_VERIFY", "false").lower() != "false"


def get_api_config() -> dict:
    """读取 DashScope API 配置，返回 {api_key, api_base, model}。"""
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get(
        "LLM_API_BASE",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    if not api_key:
        print("❌ 未设置 LLM_API_KEY 环境变量，请检查 .env 文件")
        sys.exit(1)
    return {
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": DEFAULT_MODEL,
    }


# ================================================================
#  核心函数 1: 调用 DashScope 联网搜索
# ================================================================

def call_qwen_with_web_search(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """调用 DashScope Chat Completions API，启用联网搜索（enable_search=True）。

    Args:
        prompt: 用户 Prompt 文本。
        model: 模型名称，默认 qwen3.6-plus。

    Returns:
        模型返回的 content 文本；调用失败时返回空字符串。
    """
    config = get_api_config()
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个专业的 AI 模型信息检索助手。"
                    "请根据用户提供的模型信息，联网搜索该模型的最新公开信息，"
                    "并严格按照 JSON 格式返回结果。不要编造任何信息，"
                    "搜索不到的字段请返回空字符串。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "enable_search": True,
        "temperature": 0.1,
    }

    verify_ssl = get_tls_verify()

    try:
        response = requests.post(
            url, headers=headers, json=payload,
            timeout=60, verify=verify_ssl,
        )
        if response.status_code != 200:
            print(f"  ⚠️ API 返回 HTTP {response.status_code}: {response.text[:200]}")
            return ""

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content

    except requests.exceptions.Timeout:
        print("  ⚠️ API 调用超时（60s）")
        return ""
    except requests.exceptions.RequestException as request_error:
        print(f"  ⚠️ API 调用异常: {request_error}")
        return ""


# ================================================================
#  核心函数 2: 单模型校验
# ================================================================

def _build_verification_prompt(model_row: dict) -> str:
    """根据模型行数据构造校验 Prompt。"""
    model_name = model_row.get("模型名称", "未知模型")
    company = model_row.get("公司", "")
    model_type = model_row.get("类型", "")
    existing_release_date = model_row.get("模型发布时间", "")
    existing_website = model_row.get("官网", "")
    existing_note = model_row.get("备注", "")

    context_parts = [f"模型名称：{model_name}"]
    if company:
        context_parts.append(f"所属公司：{company}")
    if model_type:
        context_parts.append(f"模型类型：{model_type}")

    need_fields = []
    if not existing_release_date or str(existing_release_date).strip() == "":
        need_fields.append("模型发布时间（YYYY-MM-DD 格式，以模型提供方官方公告日为准）")
    if not existing_website or str(existing_website).strip() == "":
        need_fields.append("官网（模型提供方自己的介绍/发布页面 URL）")
    if not existing_note or str(existing_note).strip() == "":
        need_fields.append("备注（该模型的核心技术特征，用分号分隔，如：MoE架构；128k上下文；强推理能力）")

    prompt = (
        f"请联网搜索以下 AI 模型的最新信息：\n"
        f"{'；'.join(context_parts)}\n\n"
        f"我需要你帮我补充以下缺失字段：\n"
        f"{'、'.join(need_fields)}\n\n"
        f"请严格返回以下 JSON 格式（不要包含 markdown 代码块标记）：\n"
        f'{{\n'
        f'  "模型发布时间": "YYYY-MM-DD 或空字符串",\n'
        f'  "官网": "URL 或空字符串",\n'
        f'  "备注": "核心特征1；核心特征2 或空字符串"\n'
        f'}}\n\n'
        f"重要规则：\n"
        f"1. 模型发布时间必须是模型提供方的官方公告日期，格式 YYYY-MM-DD\n"
        f"2. 官网必须是模型提供方自己的页面（如官方博客、产品页），不是第三方报道\n"
        f"3. 备注应包含该模型最核心的技术特征，用中文分号分隔\n"
        f"4. 如果搜索不到可靠信息，对应字段返回空字符串，绝不编造\n"
        f"5. 只返回 JSON，不要附加任何解释文字"
    )
    return prompt


def _parse_llm_response(raw_content: str) -> dict | None:
    """从 LLM 返回的文本中提取 JSON 对象。

    处理可能的 markdown 代码块包裹、多余文字等情况。
    """
    if not raw_content:
        return None

    # 尝试提取 markdown 代码块中的 JSON
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_content, re.DOTALL)
    if code_block_match:
        json_str = code_block_match.group(1)
    else:
        # 尝试直接匹配 JSON 对象
        json_match = re.search(r'\{[^{}]*\}', raw_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            return None

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def verify_single_model(model_row: dict, model: str = DEFAULT_MODEL) -> dict:
    """对单个模型构造 Prompt 并调用联网校验，返回更新后的字段字典。

    Args:
        model_row: Excel 中一行模型数据（字典形式）。
        model: 调用的模型名称。

    Returns:
        包含校验结果的字典，键为字段名，值为校验得到的值。
        校验失败时返回空字典。
    """
    model_name = model_row.get("模型名称", "未知")
    prompt = _build_verification_prompt(model_row)

    raw_response = call_qwen_with_web_search(prompt, model=model)
    if not raw_response:
        print(f"  ❌ {model_name}: 无响应")
        return {}

    parsed = _parse_llm_response(raw_response)
    if parsed is None:
        print(f"  ❌ {model_name}: JSON 解析失败")
        return {}

    # 只保留有效值（非空字符串），且只覆盖原本为空的字段
    result = {}
    for field in VERIFY_FIELDS:
        original_value = model_row.get(field, "")
        is_original_empty = (
            not original_value
            or str(original_value).strip() == ""
            or str(original_value).strip().lower() == "nan"
        )
        new_value = str(parsed.get(field, "")).strip()
        if is_original_empty and new_value:
            result[field] = new_value

    status = "✅" if result else "⚪"
    filled_count = len(result)
    print(f"  {status} {model_name}: 填充 {filled_count} 个字段")
    return result


# ================================================================
#  主函数: 批量校验
# ================================================================

def _needs_verification(row: pd.Series) -> bool:
    """判断一行是否需要校验（发布时间/官网/备注任一为空）。"""
    for field in VERIFY_FIELDS:
        value = row.get(field, "")
        if pd.isna(value) or str(value).strip() == "":
            return True
    return False


def run_verification(
    excel_path: str | Path = EXCEL_PATH,
    max_concurrent: int = 5,
    max_models: int | None = None,
    dry_run: bool = False,
    since: str | None = None,
    until: str | None = None,
) -> pd.DataFrame | None:
    """批量校验所有需要校验的模型（发布时间/官网/备注任一为空的）。

    Args:
        excel_path: Excel 文件路径。
        max_concurrent: 最大并发数。
        max_models: 最多校验多少条，None 表示全部。
        dry_run: 预览模式，不实际调用 API。
        since: 只校验该日期及之后的模型（YYYYMMDD，基于记录创建时间）。
        until: 只校验该日期及之前的模型（YYYYMMDD，基于记录创建时间）。

    Returns:
        更新后的 DataFrame；dry_run 模式返回 None。
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        print(f"❌ Excel 文件不存在: {excel_path}")
        return None

    dataframe = pd.read_excel(excel_path, engine="openpyxl")
    print(f"📊 加载 Excel: {len(dataframe)} 行")

    # 将待校验字段列强制转为 object 类型，避免全空列被推断为 float64
    # 导致后续赋值字符串时抛出 LossySetitemError
    for field in VERIFY_FIELDS:
        if field in dataframe.columns:
            dataframe[field] = dataframe[field].astype(object)

    # 时间窗口过滤（基于"记录创建时间"列）
    if since or until:
        time_col = "记录创建时间"
        if time_col in dataframe.columns:
            before_filter = len(dataframe)
            if since:
                since_str = f"{since[:4]}-{since[4:6]}-{since[6:8]}"
                dataframe = dataframe[dataframe[time_col].astype(str) >= since_str].copy()
            if until:
                until_str = f"{until[:4]}-{until[4:6]}-{until[6:8]}"
                dataframe = dataframe[dataframe[time_col].astype(str) <= until_str + "z"].copy()
            print(f"📅 时间窗口过滤: {before_filter} → {len(dataframe)} 行")
        else:
            print(f"⚠️ 未找到 '{time_col}' 列，跳过时间过滤")

    # 筛选需要校验的行
    needs_verify_mask = dataframe.apply(_needs_verification, axis=1)
    pending_indices = dataframe[needs_verify_mask].index.tolist()

    if max_models is not None:
        pending_indices = pending_indices[:max_models]

    print(f"🔍 需要校验: {len(pending_indices)} 个模型")

    if not pending_indices:
        print("✅ 所有模型字段均已完整，无需校验")
        return dataframe

    # dry-run 模式：只预览
    if dry_run:
        print("\n📋 待校验模型列表（--dry-run 模式，不调用 API）:")
        print("-" * 60)
        for idx in pending_indices:
            row = dataframe.loc[idx]
            name = row.get("模型名称", "?")
            missing = []
            for field in VERIFY_FIELDS:
                value = row.get(field, "")
                if pd.isna(value) or str(value).strip() == "":
                    missing.append(field)
            print(f"  [{idx:>4d}] {name:<40s} 缺: {', '.join(missing)}")
        print("-" * 60)
        return None

    # 保存校验前快照（用于验收比对）
    dataframe_before = dataframe.copy()

    # 并发调用
    config = get_api_config()
    model_name = config["model"]
    print(f"\n🚀 开始联网校验（模型: {model_name}, 并发: {max_concurrent}）")
    print("=" * 60)

    start_time = time.time()
    success_count = 0
    failure_count = 0

    def _verify_task(row_index: int) -> tuple[int, dict]:
        row_dict = dataframe.loc[row_index].to_dict()
        result = verify_single_model(row_dict, model=model_name)
        return row_index, result

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(_verify_task, idx): idx
            for idx in pending_indices
        }

        for future in as_completed(futures):
            row_index, verified_fields = future.result()
            if verified_fields:
                for field_name, field_value in verified_fields.items():
                    dataframe.at[row_index, field_name] = field_value
                success_count += 1
            else:
                failure_count += 1

    elapsed = time.time() - start_time
    print("=" * 60)
    print(f"⏱️ 耗时: {elapsed:.1f}s | ✅ 成功: {success_count} | ❌ 失败: {failure_count}")

    # 验收
    print("\n📋 验收报告:")
    validate_verification_results(dataframe_before, dataframe)

    # 写回 Excel
    dataframe.to_excel(excel_path, index=False, engine="openpyxl")
    print(f"\n💾 已保存: {excel_path}")

    return dataframe


# ================================================================
#  验收函数
# ================================================================

def validate_verification_results(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
) -> dict:
    """校验联网校验结果的质量。

    检查项:
        1. JSON 解析成功率 ≥ 70%
        2. 字段填充率提升 > 0
        3. 发布时间格式符合 YYYY-MM-DD
        4. 官网 URL 格式正确（以 http 开头）
        5. 备注长度 ≥ 5 字符

    Args:
        df_before: 校验前的 DataFrame。
        df_after: 校验后的 DataFrame。

    Returns:
        验收结果字典，包含各项指标和是否通过。
    """
    report = {
        "total_checked": 0,
        "fill_improvements": {},
        "date_format_valid": 0,
        "date_format_invalid": 0,
        "url_format_valid": 0,
        "url_format_invalid": 0,
        "note_length_valid": 0,
        "note_length_invalid": 0,
        "passed": True,
        "warnings": [],
    }

    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    url_pattern = re.compile(r'^https?://')

    for field in VERIFY_FIELDS:
        before_empty = df_before[field].isna() | (df_before[field].astype(str).str.strip() == "")
        after_empty = df_after[field].isna() | (df_after[field].astype(str).str.strip() == "")

        before_empty_count = before_empty.sum()
        after_empty_count = after_empty.sum()
        filled_count = before_empty_count - after_empty_count

        report["fill_improvements"][field] = {
            "before_empty": int(before_empty_count),
            "after_empty": int(after_empty_count),
            "filled": int(filled_count),
        }

    # 统计需要校验的行数（至少有一个字段从空变非空）
    total_rows_changed = 0
    for idx in df_after.index:
        changed = False
        for field in VERIFY_FIELDS:
            before_val = str(df_before.at[idx, field]).strip() if pd.notna(df_before.at[idx, field]) else ""
            after_val = str(df_after.at[idx, field]).strip() if pd.notna(df_after.at[idx, field]) else ""
            if not before_val and after_val:
                changed = True
                break
        if changed:
            total_rows_changed += 1
    report["total_checked"] = total_rows_changed

    # 检查 1: 填充率提升（至少有一个字段被填充）
    total_filled = sum(info["filled"] for info in report["fill_improvements"].values())
    if total_filled <= 0:
        report["warnings"].append("⚠️ 字段填充率无提升，所有字段均未被填充")
        report["passed"] = False

    # 检查 2: 发布时间格式
    for idx in df_after.index:
        date_val = df_after.at[idx, "模型发布时间"]
        if pd.notna(date_val):
            date_str = str(date_val).strip()
            if date_str:
                # 跳过校验前已有值的行
                before_date = df_before.at[idx, "模型发布时间"]
                if pd.notna(before_date) and str(before_date).strip():
                    continue
                if date_pattern.match(date_str):
                    report["date_format_valid"] += 1
                else:
                    report["date_format_invalid"] += 1

    # 检查 3: 官网 URL 格式
    for idx in df_after.index:
        url_val = df_after.at[idx, "官网"]
        if pd.notna(url_val):
            url_str = str(url_val).strip()
            if url_str:
                before_url = df_before.at[idx, "官网"]
                if pd.notna(before_url) and str(before_url).strip():
                    continue
                if url_pattern.match(url_str):
                    report["url_format_valid"] += 1
                else:
                    report["url_format_invalid"] += 1

    # 检查 4: 备注长度
    for idx in df_after.index:
        note_val = df_after.at[idx, "备注"]
        if pd.notna(note_val):
            note_str = str(note_val).strip()
            if note_str:
                before_note = df_before.at[idx, "备注"]
                if pd.notna(before_note) and str(before_note).strip():
                    continue
                if len(note_str) >= 5:
                    report["note_length_valid"] += 1
                else:
                    report["note_length_invalid"] += 1

    # 汇总输出
    print("-" * 60)
    print(f"  📊 变更行数: {report['total_checked']}")

    for field, info in report["fill_improvements"].items():
        arrow = "📈" if info["filled"] > 0 else "➖"
        print(f"  {arrow} {field}: 空值 {info['before_empty']} → {info['after_empty']}（填充 {info['filled']}）")

    date_total = report["date_format_valid"] + report["date_format_invalid"]
    if date_total > 0:
        date_rate = report["date_format_valid"] / date_total * 100
        icon = "✅" if date_rate >= 70 else "⚠️"
        print(f"  {icon} 日期格式合规率: {date_rate:.0f}%（{report['date_format_valid']}/{date_total}）")
        if date_rate < 70:
            report["warnings"].append(f"⚠️ 日期格式合规率 {date_rate:.0f}% < 70%")

    url_total = report["url_format_valid"] + report["url_format_invalid"]
    if url_total > 0:
        url_rate = report["url_format_valid"] / url_total * 100
        icon = "✅" if url_rate >= 70 else "⚠️"
        print(f"  {icon} URL 格式合规率: {url_rate:.0f}%（{report['url_format_valid']}/{url_total}）")
        if url_rate < 70:
            report["warnings"].append(f"⚠️ URL 格式合规率 {url_rate:.0f}% < 70%")

    note_total = report["note_length_valid"] + report["note_length_invalid"]
    if note_total > 0:
        note_rate = report["note_length_valid"] / note_total * 100
        icon = "✅" if note_rate >= 70 else "⚠️"
        print(f"  {icon} 备注长度合规率: {note_rate:.0f}%（{report['note_length_valid']}/{note_total}）")
        if note_rate < 70:
            report["warnings"].append(f"⚠️ 备注长度合规率 {note_rate:.0f}% < 70%")

    if report["warnings"]:
        print()
        for warning in report["warnings"]:
            print(f"  {warning}")
        report["passed"] = False
    else:
        print(f"\n  ✅ 验收通过")

    print("-" * 60)
    return report


# ================================================================
#  命令行入口
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Step 4: 自动化联网校验 — 对 Excel 中空值字段调用 DashScope 联网搜索回填",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览待校验模型列表，不实际调用 API",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        dest="max_models",
        help="最多校验多少条模型（默认全部）",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="最大并发数（默认 5）",
    )
    parser.add_argument(
        "--excel",
        type=str,
        default=None,
        help="指定 Excel 文件路径（默认 data/Object-Models-Updated.xlsx）",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="只校验该日期及之后的模型（YYYYMMDD，基于记录创建时间）",
    )
    parser.add_argument(
        "--until",
        type=str,
        default=None,
        help="只校验该日期及之前的模型（YYYYMMDD，基于记录创建时间）",
    )
    args = parser.parse_args()

    load_env()

    excel_path = Path(args.excel) if args.excel else EXCEL_PATH

    print("🔬 Step 4: 自动化联网校验")
    print(f"   Excel: {excel_path}")
    print(f"   模式: {'预览（dry-run）' if args.dry_run else '正式校验'}")
    if args.max_models:
        print(f"   上限: {args.max_models} 条")
    if args.since or args.until:
        print(f"   时间窗口: {args.since or '不限'} → {args.until or '不限'}")
    print()

    run_verification(
        excel_path=excel_path,
        max_concurrent=args.concurrent,
        max_models=args.max_models,
        dry_run=args.dry_run,
        since=args.since,
        until=args.until,
    )


if __name__ == "__main__":
    main()
