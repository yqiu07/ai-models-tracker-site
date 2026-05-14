# 2026/05/14/11:14
# name: cross_check
# description: LLM 交叉巡检 — 调用 DashScope 联网搜索 API，搜索指定时间段内新发布的
#              AI 模型/智能体，与已采集数据交叉比对，找出遗漏模型并可选追加到 Excel。
#              作为流水线的补漏环节，在所有数据源采集完成后运行。
"""
LLM 交叉巡检（Cross-Check via LLM）
====================================
调用 DashScope Qwen 联网搜索，检索指定时间段内新发布的 AI 模型/智能体，
与已有采集数据交叉比对，输出遗漏模型列表，可选追加到 Excel 总表。

用法:
    python cross_check.py --since 20260509 --until 20260513
    python cross_check.py --since 20260509 --until 20260513 --dry-run
    python cross_check.py --since 20260509 --until 20260513 --excel data/Object-Models-Updated.xlsx

依赖:
    pip install requests pandas openpyxl
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows 终端编码修复：避免 emoji/中文输出 GBK 报错
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import requests
import urllib3

# 抑制内网自签证书的 InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 路径常量 ──
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DEFAULT_EXCEL = DATA_DIR / "Object-Models-Updated.xlsx"

# ── Excel 列结构（与 auto_collect.py 一致）──
EXCEL_COLUMNS = [
    "模型名称", "是否接入", "workflow接入进展", "公司", "国内外",
    "开闭源", "尺寸", "类型", "能否推理", "任务类型",
    "官网", "备注", "模型发布时间", "记录创建时间", "是否新增", "核实情况",
]

# ── API 配置 ──
DEFAULT_MODEL = "qwen-plus"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 300


# ================================================================
#  环境与配置（复用 verify_models.py 模式）
# ================================================================

def load_env():
    """加载 .env 文件（如果存在）。"""
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
#  Prompt 构造
# ================================================================

VENDORS_LIST = (
    "OpenAI, Google/DeepMind, Anthropic, Meta, Microsoft, xAI (Elon Musk), "
    "Mistral, NVIDIA, Cohere, AI21 Labs, Stability AI, Reka, "
    "百度, 阿里巴巴/通义, 字节跳动/豆包, 腾讯/混元, 深度求索/DeepSeek, "
    "智谱AI/GLM, MiniMax/海螺, 月之暗面/Kimi, 小米/MiMo, "
    "阶跃星辰/Step, 零一万物/Yi, 百川智能, 商汤科技, 科大讯飞, "
    "华为/盘古, 快手, vivo, OPPO, 美团, 京东, 哔哩哔哩, 网易"
)


def build_search_prompt(since_str: str, until_str: str) -> str:
    """构造让 LLM 联网搜索新发布模型的 Prompt。

    Args:
        since_str: 起始日期，格式 YYYYMMDD。
        until_str: 截止日期，格式 YYYYMMDD。

    Returns:
        完整的用户 Prompt 文本。
    """
    since_formatted = f"{since_str[:4]}-{since_str[4:6]}-{since_str[6:]}"
    until_formatted = f"{until_str[:4]}-{until_str[4:6]}-{until_str[6:]}"

    return f"""请联网搜索 {since_formatted} 至 {until_formatted} 期间新发布的 AI 模型和智能体。

搜索范围包括但不限于以下厂商：{VENDORS_LIST}

请尽可能多地列出该时间段内首次发布或发布新版本的模型，包括大语言模型、多模态模型、代码模型、图像/视频/音频模型、智能体等。

请返回 JSON 数组格式：
[
  {{
    "model_name": "模型全称（含版本号）",
    "company": "发布公司",
    "release_date": "发布日期（YYYY-MM-DD）",
    "model_type": "模型类型",
    "description": "一句话描述"
  }}
]"""


# ================================================================
#  LLM API 调用（带重试）
# ================================================================

def call_llm_with_search(prompt: str) -> str:
    """调用 DashScope Chat Completions API（enable_search=True），带重试机制。

    Args:
        prompt: 用户 Prompt 文本。

    Returns:
        模型返回的 content 文本；所有重试均失败时返回空字符串。
    """
    config = get_api_config()
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个专业的 AI 行业信息检索助手。"
                    "请根据用户要求联网搜索最新的 AI 模型发布信息，"
                    "严格按照指定的 JSON 格式返回结果。"
                    "只返回你通过联网搜索能确认的信息，不要编造。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "enable_search": True,
        "temperature": 0.1,
    }

    verify_ssl = get_tls_verify()

    # 不可重试的 HTTP 状态码（客户端错误，重试无意义）
    non_retryable_status_codes = {400, 401, 403, 404, 405, 422}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  🔄 API 调用中（第 {attempt}/{MAX_RETRIES} 次）...")
            response = requests.post(
                url, headers=headers, json=payload,
                timeout=REQUEST_TIMEOUT, verify=verify_ssl,
            )
            if response.status_code != 200:
                print(f"  ⚠️ API 返回 HTTP {response.status_code}: {response.text[:300]}")
                # 4xx 客户端错误（除 429 限流）不可重试，立即终止
                if response.status_code in non_retryable_status_codes:
                    print(f"  ❌ 不可重试的客户端错误（HTTP {response.status_code}），请检查 API Key / 参数配置")
                    return ""
                # 429 限流或 5xx 服务端错误可重试
                if attempt < MAX_RETRIES:
                    wait_seconds = 5 * attempt
                    print(f"  ⏳ 等待 {wait_seconds}s 后重试...")
                    time.sleep(wait_seconds)
                continue

            # 防御性 JSON 解析：API 可能返回 200 但 body 非法（如 HTML 错误页面）
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as json_err:
                print(f"  ⚠️ API 返回 200 但 JSON 解析失败: {json_err}")
                print(f"  📄 响应前 300 字符: {response.text[:300]}")
                if attempt < MAX_RETRIES:
                    time.sleep(3)
                continue

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                print(f"  ✅ API 调用成功，返回 {len(content)} 字符")
                return content

            print("  ⚠️ API 返回内容为空")
            if attempt < MAX_RETRIES:
                time.sleep(3)

        except requests.exceptions.Timeout:
            print(f"  ⚠️ API 调用超时（{REQUEST_TIMEOUT}s）")
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)
        except requests.exceptions.RequestException as request_error:
            print(f"  ⚠️ API 调用异常: {request_error}")
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)

    print("  ❌ 所有重试均失败")
    return ""


# ================================================================
#  JSON 解析
# ================================================================

def parse_llm_response(raw_content: str) -> list[dict]:
    """从 LLM 返回的文本中提取 JSON 数组。

    支持处理 markdown 代码块包裹、前后有额外说明文字等情况。

    Args:
        raw_content: LLM 返回的原始文本。

    Returns:
        解析后的模型列表；解析失败返回空列表。
    """
    if not raw_content.strip():
        return []

    # 尝试提取 markdown 代码块中的 JSON
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw_content, re.DOTALL)
    json_text = code_block_match.group(1).strip() if code_block_match else raw_content.strip()

    # 尝试提取最外层的 JSON 数组
    bracket_match = re.search(r"\[.*\]", json_text, re.DOTALL)
    if bracket_match:
        json_text = bracket_match.group(0)

    try:
        parsed = json.loads(json_text)
        if isinstance(parsed, list):
            return parsed
        print(f"  ⚠️ JSON 解析结果不是数组: {type(parsed)}")
        return []
    except json.JSONDecodeError as json_error:
        print(f"  ⚠️ JSON 解析失败: {json_error}")
        print(f"  📄 原始内容前 500 字符: {raw_content[:500]}")
        return []


# ================================================================
#  交叉比对与格式转换
# ================================================================

def normalize_model_name(name: str) -> str:
    """标准化模型名称用于比对（小写、去空格、去连字符）。"""
    return re.sub(r"[\s\-_\.]+", "", name.lower())


def cross_check_via_llm(
    since_str: str,
    until_str: str,
    existing_names: set[str],
) -> list[dict]:
    """LLM 交叉巡检核心函数：联网搜索新模型，与已有数据比对，返回遗漏列表。

    Args:
        since_str: 起始日期，格式 YYYYMMDD（如 '20260509'）。
        until_str: 截止日期，格式 YYYYMMDD（如 '20260513'）。
        existing_names: 已采集的模型名称集合（用于去重比对）。

    Returns:
        遗漏模型列表，每个元素为符合 EXCEL_COLUMNS 的字典。
    """
    print(f"\n🔍 LLM 交叉巡检: {since_str} → {until_str}")
    print(f"📊 已有模型数量: {len(existing_names)}")

    # 构造标准化名称索引，用于模糊匹配
    normalized_existing = {normalize_model_name(name) for name in existing_names}

    # 构造 Prompt 并调用 LLM
    prompt = build_search_prompt(since_str, until_str)
    raw_response = call_llm_with_search(prompt)
    if not raw_response:
        print("❌ LLM 未返回有效内容，巡检中止")
        return []

    # 解析 JSON
    discovered_models = parse_llm_response(raw_response)
    print(f"🔎 LLM 发现 {len(discovered_models)} 个模型")

    # 交叉比对
    missing_models = []
    for model_info in discovered_models:
        model_name = model_info.get("model_name", "").strip()
        if not model_name:
            continue

        normalized = normalize_model_name(model_name)
        is_existing = any(
            normalized in existing_norm or existing_norm in normalized
            for existing_norm in normalized_existing
        )

        if is_existing:
            print(f"  ✅ 已存在: {model_name}")
        else:
            print(f"  🆕 遗漏: {model_name}")
            row = convert_to_excel_row(model_info)
            missing_models.append(row)

    print(f"\n📋 巡检完成: 发现 {len(missing_models)} 个遗漏模型")
    return missing_models


def convert_to_excel_row(model_info: dict) -> dict:
    """将 LLM 返回的模型信息转换为 Excel 标准行格式。

    Args:
        model_info: LLM 返回的单个模型字典。

    Returns:
        符合 EXCEL_COLUMNS 的字典。
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    company = model_info.get("company", "")
    domestic_companies = {
        "百度", "阿里", "通义", "字节", "豆包", "腾讯", "混元",
        "深度求索", "DeepSeek", "智谱", "GLM", "MiniMax", "海螺",
        "月之暗面", "Kimi", "小米", "MiMo", "阶跃", "Step",
        "零一万物", "Yi", "百川", "商汤", "科大讯飞", "华为", "盘古",
        "快手", "vivo", "OPPO", "美团", "京东", "哔哩哔哩", "网易",
    }
    is_domestic = "国内" if any(kw in company for kw in domestic_companies) else "国外"

    return {
        "模型名称": model_info.get("model_name", ""),
        "是否接入": "",
        "workflow接入进展": "",
        "公司": company,
        "国内外": is_domestic,
        "开闭源": "",
        "尺寸": "",
        "类型": model_info.get("model_type", ""),
        "能否推理": "",
        "任务类型": "",
        "官网": "",
        "备注": model_info.get("description", ""),
        "模型发布时间": model_info.get("release_date", ""),
        "记录创建时间": now_str,
        "是否新增": "是",
        "核实情况": "待核实（LLM交叉巡检发现）",
    }


# ================================================================
#  Excel 读写
# ================================================================

def load_existing_model_names(excel_path: Path) -> set[str]:
    """从 Excel 文件中读取已有的模型名称集合。

    Args:
        excel_path: Excel 文件路径。

    Returns:
        模型名称集合；文件不存在时返回空集合。
    """
    if not excel_path.exists():
        print(f"⚠️ Excel 文件不存在: {excel_path}")
        return set()

    try:
        dataframe = pd.read_excel(excel_path, engine="openpyxl")
        if "模型名称" not in dataframe.columns:
            print("⚠️ Excel 中未找到「模型名称」列")
            return set()

        names = set(dataframe["模型名称"].dropna().astype(str).tolist())
        print(f"📂 从 Excel 加载 {len(names)} 个已有模型名称")
        return names

    except Exception as read_error:
        print(f"⚠️ 读取 Excel 失败: {read_error}")
        return set()


def append_to_excel(excel_path: Path, new_rows: list[dict]) -> bool:
    """将遗漏模型追加到 Excel 总表。

    Args:
        excel_path: Excel 文件路径。
        new_rows: 待追加的模型行列表。

    Returns:
        是否追加成功。
    """
    if not new_rows:
        print("📭 无新数据需要写入")
        return True

    try:
        if excel_path.exists():
            existing_dataframe = pd.read_excel(excel_path, engine="openpyxl")
        else:
            existing_dataframe = pd.DataFrame(columns=EXCEL_COLUMNS)

        new_dataframe = pd.DataFrame(new_rows, columns=EXCEL_COLUMNS)
        merged_dataframe = pd.concat([existing_dataframe, new_dataframe], ignore_index=True)
        merged_dataframe.to_excel(excel_path, index=False, engine="openpyxl")

        print(f"💾 已追加 {len(new_rows)} 条记录到 {excel_path}")
        return True

    except Exception as write_error:
        print(f"❌ 写入 Excel 失败: {write_error}")
        return False


# ================================================================
#  CLI 入口
# ================================================================

def parse_date_arg(date_string: str) -> str:
    """校验并标准化日期参数（YYYYMMDD 格式）。"""
    date_string = date_string.strip()
    if len(date_string) != 8 or not date_string.isdigit():
        print(f"❌ 日期格式错误: {date_string}，期望 YYYYMMDD（如 20260509）")
        sys.exit(1)
    try:
        datetime.strptime(date_string, "%Y%m%d")
    except ValueError:
        print(f"❌ 日期无效: {date_string}")
        sys.exit(1)
    return date_string


def print_results_table(missing_models: list[dict]):
    """以表格形式打印遗漏模型列表。"""
    if not missing_models:
        print("\n🎉 未发现遗漏模型，数据覆盖良好！")
        return

    print(f"\n{'='*80}")
    print(f"🆕 发现 {len(missing_models)} 个遗漏模型")
    print(f"{'='*80}")
    print(f"{'序号':<4} {'模型名称':<35} {'公司':<15} {'类型':<10} {'发布日期':<12}")
    print(f"{'-'*80}")

    for index, model_row in enumerate(missing_models, 1):
        name = model_row.get("模型名称", "")[:33]
        company = model_row.get("公司", "")[:13]
        model_type = model_row.get("类型", "")[:8]
        release_date = model_row.get("模型发布时间", "")[:10]
        print(f"{index:<4} {name:<35} {company:<15} {model_type:<10} {release_date:<12}")

    print(f"{'='*80}")


def main():
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(
        description="LLM 交叉巡检 — 联网搜索新发布模型，与已有数据比对找出遗漏",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cross_check.py --since 20260509 --until 20260513
  python cross_check.py --since 20260509 --until 20260513 --dry-run
  python cross_check.py --since 20260509 --until 20260513 --excel data/Object-Models-Updated.xlsx
        """,
    )
    parser.add_argument("--since", required=True, help="起始日期（YYYYMMDD）")
    parser.add_argument("--until", required=True, help="截止日期（YYYYMMDD）")
    parser.add_argument("--dry-run", action="store_true", help="只打印遗漏列表，不写入 Excel")
    parser.add_argument("--excel", type=str, default=None, help="指定已有数据 Excel 文件路径")

    args = parser.parse_args()

    # 加载环境变量
    load_env()

    # 校验日期
    since_date = parse_date_arg(args.since)
    until_date = parse_date_arg(args.until)

    # 校验日期先后顺序
    if since_date > until_date:
        print(f"❌ 起始日期 {since_date} 晚于截止日期 {until_date}，请检查参数")
        sys.exit(1)

    # 确定 Excel 路径
    excel_path = Path(args.excel) if args.excel else DEFAULT_EXCEL

    print("🚀 LLM 交叉巡检启动")
    print(f"📅 时间范围: {since_date} → {until_date}")
    print(f"📁 数据文件: {excel_path}")
    print(f"🏷️ 模式: {'预览（dry-run）' if args.dry_run else '正式运行'}")

    # 加载已有模型名称
    existing_names = load_existing_model_names(excel_path)

    # 执行交叉巡检
    missing_models = cross_check_via_llm(since_date, until_date, existing_names)

    # 输出结果
    print_results_table(missing_models)

    # 写入 Excel（非 dry-run 模式）
    if missing_models and not args.dry_run:
        write_success = append_to_excel(excel_path, missing_models)
        if not write_success:
            print("\n❌ Excel 写入失败，请检查文件是否被占用或路径是否正确")
            sys.exit(1)
    elif missing_models and args.dry_run:
        print("\n📝 dry-run 模式，未写入 Excel。去掉 --dry-run 参数可自动追加。")

    print("\n✨ 巡检结束")


if __name__ == "__main__":
    main()
