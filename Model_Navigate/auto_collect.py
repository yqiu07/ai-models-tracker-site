"""
自动化数据采集 + 结构化映射 + 写入 Excel
========================================
替代原有手动步骤 2-6（录入腾讯研究院/llmstats/综合更新/核实/发布时间）。

用法:
    python auto_collect.py --since 20260417 --until 20260423
    python auto_collect.py --since 20260417                    # until 默认今天
    python auto_collect.py --source llmstats                   # 只跑 llmstats
    python auto_collect.py --source txresearch                 # 只跑腾讯研究院
    python auto_collect.py --dry-run                           # 预览，不写 Excel

输出:
    Object-Models-Updated.xlsx（追加新模型）
    TXresearch/articles_YYYYMMDD-YYYYMMDD.json（腾讯研究院文章全文）
    Crawl/Arena_x/llmstats_models.json（llmstats 结构化数据）

依赖:
    pip install requests aiohttp beautifulsoup4 pandas openpyxl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# ── 路径常量 ──
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
EXCEL_PATH = DATA_DIR / "Object-Models-Updated.xlsx"
EXCEL_OLD_PATH = DATA_DIR / "Object-Models-Old.xlsx"
LLMSTATS_DIR = ROOT / "Crawl" / "Arena_x"
TX_DIR = ROOT / "TXresearch"

# ── llmstats 页面配置 ──
LLMSTATS_PAGES = {
    "ai": {
        "url": "https://llm-stats.com",
        "file": LLMSTATS_DIR / "llm-stats-ai.com",
        "label": "AI Leaderboard (首页)",
    },
    "llm": {
        "url": "https://llm-stats.com/leaderboards/llm-leaderboard",
        "file": LLMSTATS_DIR / "llm-stats-LLM.com",
        "label": "LLM Leaderboard (详情)",
    },
    "open": {
        "url": "https://llm-stats.com/leaderboards/open-llm-leaderboard",
        "file": LLMSTATS_DIR / "llm-stats-open-llm.com",
        "label": "Open LLM Leaderboard",
    },
    "updates": {
        "url": "https://llm-stats.com/llm-updates",
        "file": LLMSTATS_DIR / "llm-stats-updates.com",
        "label": "LLM Updates (时间线)",
    },
}

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

# ── 中国公司列表（用于判断国内/国外）──
CN_ORGS = {
    "alibaba", "qwen", "baidu", "bytedance", "tencent", "deepseek",
    "zhipu", "minimax", "moonshot", "stepfun", "sensetime", "01.ai",
    "iflytek", "kuaishou", "huawei", "xiaomi", "vivo", "meituan",
    "jd", "honor", "oppo", "bilibili", "netease",
}

# ── Excel 列结构 ──
EXCEL_COLUMNS = [
    "模型名称", "是否接入", "workflow接入进展", "公司", "国内外",
    "开闭源", "尺寸", "类型", "能否推理", "任务类型",
    "官网", "备注", "模型发布时间", "记录创建时间", "是否新增", "核实情况",
]


# ================================================================
#  工具函数
# ================================================================

def detect_proxy() -> str | None:
    """检测系统 HTTP 代理。"""
    for env_key in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        proxy = os.environ.get(env_key)
        if proxy:
            return proxy
    return None


def format_params(params) -> str:
    """格式化参数量（如 236B）。"""
    if not params:
        return ""
    if isinstance(params, str):
        return params
    if params >= 1_000_000_000_000:
        return f"{params / 1_000_000_000_000:.0f}T"
    if params >= 1_000_000_000:
        return f"{params / 1_000_000_000:.0f}B"
    if params >= 1_000_000:
        return f"{params / 1_000_000:.0f}M"
    return str(params)


def _infer_size_from_name(name: str) -> str:
    """从模型名称中正则提取参数量（如 Qwen3-8B → 8B, 35B-A3B → 35B(A3B)）。"""
    if not name:
        return ""
    # 匹配 MoE 格式: 122B-A10B, 35B-A3B
    moe_match = re.search(r'(\d+\.?\d*)[Bb]-[Aa](\d+\.?\d*)[Bb]', name)
    if moe_match:
        return f"{moe_match.group(1)}B(A{moe_match.group(2)}B)"
    # 匹配常规参数量: 8B, 0.5B, 72B, 1.5B, 14b
    size_match = re.search(r'(\d+\.?\d*)\s*[Bb]\b', name)
    if size_match:
        return f"{size_match.group(1)}B"
    # 匹配 M 级别: 500M, 125M
    m_match = re.search(r'(\d+\.?\d*)\s*[Mm]\b', name)
    if m_match:
        return f"{m_match.group(1)}M"
    return ""


def is_domestic(org_id: str, org_country: str = "") -> bool:
    """判断是否为国内公司。"""
    org_lower = (org_id or "").lower().replace(" ", "").replace("-", "")
    if org_country and org_country.upper() == "CN":
        return True
    return any(cn in org_lower for cn in CN_ORGS)


def load_existing_models(excel_path: Path) -> set[str]:
    """从 Excel 加载已有模型名称集合（用于去重）。"""
    if not excel_path.exists():
        return set()
    df = pd.read_excel(excel_path, engine="openpyxl")
    names = set()
    for val in df.iloc[:, 0].dropna():
        names.add(str(val).strip().lower())
    return names


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ================================================================
#  数据源 1：llm-stats.com
# ================================================================

def fetch_llmstats_html(page_key: str, config: dict, proxy: str | None) -> str | None:
    """自动 HTTP 抓取 llmstats 页面 HTML，并保存到本地。"""
    url = config["url"]
    local_file = config["file"]
    label = config["label"]

    proxies = {"http": proxy, "https": proxy} if proxy else None

    # 构造尝试列表：先直连，有代理时再试代理
    attempts = [("直连", None)]
    if proxies:
        attempts.append(("代理", proxies))

    for attempt_label, attempt_proxies in attempts:
        try:
            resp = requests.get(
                url, headers=HTTP_HEADERS,
                proxies=attempt_proxies, timeout=30, verify=False,
            )
            if resp.status_code == 200:
                html = resp.text
                # 保存到本地（供 extract_llmstats_json.py 后续使用）
                local_file.write_text(html, encoding="utf-8")
                print(f"  ✅ {label}: {attempt_label}成功 ({len(html):,} bytes) → {local_file.name}")
                return html
            print(f"  ⚠️ {label}: {attempt_label} HTTP {resp.status_code}")
        except Exception as exc:
            print(f"  ⚠️ {label}: {attempt_label}失败: {exc}")

    # 回退到本地文件
    if local_file.exists():
        html = local_file.read_text(encoding="utf-8")
        print(f"  📂 {label}: 使用本地缓存 ({len(html):,} bytes)")
        return html

    print(f"  ❌ {label}: 抓取失败且无本地缓存")
    return None


def parse_next_f_models(html: str) -> list[dict] | None:
    """从 Next.js self.__next_f.push 数据中提取模型列表。"""
    pattern = r'self\.__next_f\.push\(\[1,"(.*?)"\]\)'
    chunks = re.findall(pattern, html, re.DOTALL)
    combined = "".join(chunks)
    combined = combined.replace('\\"', '"').replace('\\\\', '\\')

    candidate_keys = ['"initialHomepageLLMModels":', '"initialData":', '"recentUpdates":']
    idx = -1
    for key in candidate_keys:
        idx = combined.find(key)
        if idx >= 0:
            break
    if idx < 0:
        return None

    array_start = combined.find("[", idx)
    if array_start < 0:
        return None

    depth = 0
    array_end = array_start
    for i in range(array_start, len(combined)):
        if combined[i] == "[":
            depth += 1
        elif combined[i] == "]":
            depth -= 1
            if depth == 0:
                array_end = i + 1
                break

    json_str = combined[array_start:array_end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        model_pattern = r'\{"model_id":"[^"]+?".*?\}'
        matches = re.findall(model_pattern, json_str)
        models = []
        for match_str in matches:
            try:
                models.append(json.loads(match_str))
            except json.JSONDecodeError:
                continue
        return models if models else None


def collect_llmstats(since_int: int, until_int: int) -> list[dict]:
    """从 llm-stats.com 自动抓取+解析，返回 Excel 行格式的模型列表。"""
    print("\n📡 数据源: llm-stats.com")
    print("=" * 50)

    proxy = detect_proxy()
    if proxy:
        print(f"  代理: {proxy}")

    # 抓取 + 解析每个页面
    all_page_models: dict[str, list[dict]] = {}
    for page_key, config in LLMSTATS_PAGES.items():
        html = fetch_llmstats_html(page_key, config, proxy)
        if not html:
            continue
        models = parse_next_f_models(html)
        if models:
            print(f"    → 解析到 {len(models)} 个模型")
            all_page_models[page_key] = models
        else:
            print(f"    → 未解析到模型数据")

    if not all_page_models:
        print("  ❌ 所有页面均失败，跳过 llmstats")
        return []

    # 按优先级合并（同 extract_llmstats_json.py 逻辑）
    merged: dict[str, dict] = {}
    for page_key in ["llm", "ai", "open", "updates"]:
        for model in all_page_models.get(page_key, []):
            model_id = model.get("model_id", "")
            if not model_id:
                continue
            cleaned = {k: v for k, v in model.items() if v != "$undefined"}
            if model_id not in merged:
                merged[model_id] = dict(cleaned)
                merged[model_id]["_source_pages"] = [page_key]
            else:
                merged[model_id]["_source_pages"].append(page_key)
                for fk, fv in cleaned.items():
                    if fk not in merged[model_id] or merged[model_id][fk] is None:
                        merged[model_id][fk] = fv

    # 保存合并后的 JSON
    model_list = sorted(
        merged.values(),
        key=lambda m: m.get("announcement_date") or m.get("release_date") or "",
        reverse=True,
    )
    json_path = LLMSTATS_DIR / "llmstats_models.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(model_list, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 JSON 已保存: {json_path} ({len(model_list)} 个模型)")

    # 按时间窗口筛选 + 映射到 Excel 行格式
    rows = []
    for model in model_list:
        date_str = model.get("announcement_date") or model.get("release_date") or ""
        if date_str:
            try:
                model_date_int = int(date_str.replace("-", ""))
                if model_date_int < since_int or model_date_int > until_int:
                    continue
            except ValueError:
                pass

        name = model.get("name", "")
        org = model.get("organization", "")
        org_id = model.get("organization_id", "")
        org_country = model.get("organization_country", "")
        params = model.get("params")
        is_open = model.get("is_open_source")
        multimodal = model.get("multimodal")
        model_id = model.get("model_id", "")

        # 映射到 Excel 列
        row = {
            "模型名称": name,
            "是否接入": "",
            "workflow接入进展": "",
            "公司": org,
            "国内外": "国内" if is_domestic(org_id, org_country) else "国外",
            "开闭源": "开源" if is_open is True else ("闭源" if is_open is False else "未知"),
            "尺寸": format_params(params) if params else "",
            "类型": _infer_type(model),
            "能否推理": _infer_reasoning(model),
            "任务类型": "通用对话",
            "官网": _pick_website(model, model_id),
            "备注": _build_llmstats_note(model),
            "记录创建时间": today_str(),
            "模型发布时间": date_str,
            "是否新增": "New",
            "核实情况": "llm-stats.com 排行榜",
        }
        rows.append(row)

    print(f"  📊 时间窗口 {since_int}~{until_int} 内: {len(rows)} 个模型")
    return rows

def _pick_website(model: dict, model_id: str) -> str:
    """优先使用模型自身的官方链接，无官方链接时回退到 llmstats 页面。"""
    for key in ("website", "url", "homepage", "link"):
        value = model.get(key)
        if value and isinstance(value, str) and value.startswith("http"):
            return value
    if model_id:
        return f"https://llm-stats.com/models/{model_id}"
    return ""


def _infer_type(model: dict) -> str:
    """从模型字段推断类型（对齐项目已有分类）。

    推断顺序：关键词匹配 → 多模态字段 → 知名基座模型名称 → 参数量 → 未知。
    """
    multimodal = model.get("multimodal")
    name_lower = (model.get("name") or "").lower()
    model_id = (model.get("model_id") or "").lower()
    combined = name_lower + " " + model_id

    # 代码类
    if any(kw in combined for kw in ("code", "codex", "coder")):
        return "代码"
    # 语音类
    if any(kw in combined for kw in ("whisper", "tts", "stt", "speech", "audio", "voice", "vox")):
        return "语音"
    # 图像生成类
    if any(kw in combined for kw in ("dall-e", "midjourney", "stable-diffusion", "flux", "imagen", "seedream", "ideogram", "firefly")):
        return "图像"
    # 视频生成类
    if any(kw in combined for kw in ("sora", "runway", "pika", "luma", "kling", "veo", "wan")):
        return "视频"
    # 多模态
    if isinstance(multimodal, list) and len(multimodal) > 0:
        return "多模态"
    if multimodal is True:
        return "多模态"
    # 知名基座模型系列（无论参数量是否可知，都应归为基座）
    foundation_patterns = (
        "gpt", "grok", "claude", "gemini", "llama", "mistral", "qwen",
        "deepseek", "phi", "command", "jamba", "dbrx", "yi-", "glm",
        "baichuan", "internlm", "minimax", "step", "hunyuan", "ernie",
        "palm", "gemma", "olmo", "falcon", "vicuna", "solar", "arctic",
        "mercury", "nemotron", "longcat", "mimo", "sarvam", "minicpm",
    )
    if any(kw in combined for kw in foundation_patterns):
        return "基座"
    # 按参数量区分
    is_moe = model.get("is_moe")
    params = model.get("params") or 0
    if params >= 1_000_000_000 or is_moe:
        return "基座"
    # 无法确定时标为"未知"而非默认"领域"
    return "未知"


def _infer_reasoning(model: dict) -> str:
    """推断模型是否支持推理（thinking）。

    判定顺序：
    1. 名称中含 lite/mini/nano/flash-lite 等轻量后缀 → 排除 thinking
    2. 名称中含 thinking/reason/o1/o3/o4/r1/r2 → thinking
    3. 已知默认支持 thinking 的系列 → thinking
    4. index_reasoning > 40 → thinking
    5. 其他 → non-thinking
    """
    name_lower = (model.get("name") or "").lower()
    model_id = (model.get("model_id") or "").lower()
    combined = name_lower + " " + model_id

    # 显式否定关键词优先（non-reasoning 等明确标记为不支持推理）
    if "non-reasoning" in combined or "non-thinking" in combined:
        return "non-thinking"

    # 轻量模型排除（flash-lite、nano 等通常不支持推理）
    lite_patterns = ("flash-lite", "flashlite", "nano", "-lite")
    if any(kw in combined for kw in lite_patterns):
        return "non-thinking"

    # 显式推理关键词
    if any(kw in combined for kw in ("thinking", "reason", "o1", "o3", "o4", "r1", "r2")):
        return "thinking"

    # 已知默认支持 thinking 的模型系列
    # GLM-4.7+ 系列支持 thinking
    # Mercury 系列是推理优化模型
    # Nemotron 3+ Super 支持推理
    # Kimi-k2+ 系列支持 thinking
    thinking_series_unconditional = (
        "qwq", "glm-4.7", "glm-5", "glm4.7", "glm5",
        "mercury", "nemotron", "kimi-k2", "kimi-k3",
        "deepseek-r", "deepseek-v3", "deepseek-v4",
        "gemini-3.1-pro", "gemini-3.1-flash",
        "grok-4", "grok4",
    )
    if any(kw in combined for kw in thinking_series_unconditional):
        return "thinking"

    # Qwen3/3.5 系列：参数量 ≥ 27B 才视为 thinking（小模型推理能力有限）
    if "qwen3" in combined:
        params = model.get("params") or 0
        if params >= 27_000_000_000:
            return "thinking"
        # 尝试从名称中提取参数量（如 qwen3.5-27b → 27B）
        param_match = re.search(r"(\d+(?:\.\d+)?)\s*b", combined)
        if param_match:
            param_val = float(param_match.group(1))
            if param_val >= 27:
                return "thinking"
        return "non-thinking"

    idx_reasoning = model.get("index_reasoning")
    if idx_reasoning is not None and idx_reasoning > 40:
        return "thinking"
    return "non-thinking"


def _build_llmstats_note(model: dict) -> str:
    """从 llmstats 模型数据生成语义化备注。

    风格：语义化标签式，分号分隔，中文为主技术术语保留英文。
    重在模型定位/架构特性/核心能力描述，而不是堆积 benchmark 数字。

    好的备注示例：
      "MoE架构；1T参数；262k上下文；MIT (modified)"
      "视觉+文本统一多模态；支持代码生成"
      "开源Agent框架；内置学习循环"
    """
    parts = []

    # 1. 架构特征（MoE / Dense）
    is_moe = model.get("is_moe")
    params = model.get("params")
    if is_moe:
        if params:
            parts.append(f"MoE架构；{format_params(params)}参数")
        else:
            parts.append("MoE架构")

    # 2. 上下文长度（只在显著时提及）
    ctx = model.get("context")
    if ctx and ctx >= 100000:
        ctx_k = ctx // 1000
        parts.append(f"{ctx_k}k上下文")

    # 3. 多模态能力（语义化表达）
    multimodal = model.get("multimodal")
    if isinstance(multimodal, list) and multimodal:
        modalities = [str(m) for m in multimodal if m]
        if modalities:
            parts.append("统一" + "+".join(modalities[:3]))

    # 4. 核心能力定位（取最突出的一个指标做语义化描述，而非罗列数字）
    gpqa = model.get("gpqa_score")
    swe = model.get("swe_bench_verified_score")

    if gpqa is not None:
        gpqa_pct = gpqa * 100 if gpqa <= 1 else gpqa
        if gpqa_pct >= 90:
            parts.append("顶级推理能力")
        elif gpqa_pct >= 80:
            parts.append("强推理能力")
    if swe is not None:
        swe_pct = swe * 100 if swe <= 1 else swe
        if swe_pct >= 70:
            parts.append("顶级编码能力")
        elif swe_pct >= 50:
            parts.append("强编码能力")

    # 5. 价格定位（语义化）
    price_in = model.get("input_price")
    price_out = model.get("output_price")
    if price_in is not None and price_out is not None:
        try:
            total = float(price_in) + float(price_out)
            if total <= 1:
                parts.append("低成本")
            elif total >= 20:
                parts.append("高端定价")
        except (ValueError, TypeError):
            pass

    # 6. 许可证（标准化表达）
    lic = model.get("license") or ""
    if lic and lic != "proprietary":
        license_map = {
            "apache_2_0": "Apache 2.0",
            "apache_2.0": "Apache 2.0",
            "apache-2.0": "Apache 2.0",
            "mit": "MIT",
            "modified_mit_license": "MIT (modified)",
            "gpl_3_0": "GPL 3.0",
            "cc_by_4_0": "CC BY 4.0",
            "cc_by_nc_4_0": "CC BY-NC 4.0",
            "llama3": "Llama 3 License",
            "llama3.1": "Llama 3.1 License",
            "gemma": "Gemma License",
            "qwen": "Qwen License",
            "deepseek": "DeepSeek License",
        }
        lic_clean = license_map.get(lic.lower(), lic.replace("_", " ").title())
        parts.append(lic_clean)

    return "；".join(parts)

# ================================================================
#  数据源 2：腾讯研究院（搜狐号）
# ================================================================

def start_txresearch_crawl(since_int: int, until_int: int) -> subprocess.Popen | None:
    """非阻塞启动腾讯研究院爬虫（后台 Selenium 进程）。

    爬虫本身是纯工具（Selenium + requests + BeautifulSoup），不依赖任何 AI 能力，
    因此可以在后台异步运行，主流水线同时处理其他数据源（如 llmstats）。

    Returns:
        subprocess.Popen 进程对象（供后续 wait_txresearch_result 等待），
        如果已有缓存或爬虫脚本不存在则返回 None。
    """
    tag = f"{since_int}-{until_int}"
    json_path = TX_DIR / f"articles_{tag}.json"
    crawl_script = ROOT / "Crawl" / "TXresearch" / "crawl_sohu.py"

    if json_path.exists():
        print(f"  📂 腾讯研究院: 已有抓取缓存 {json_path.name}，跳过爬虫")
        return None

    if not crawl_script.exists():
        print(f"  ⚠️ 腾讯研究院: 爬虫脚本不存在 {crawl_script}")
        return None

    print(f"  🚀 腾讯研究院: 后台启动爬虫 crawl_sohu.py --since {since_int} --until {until_int}")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(crawl_script),
         "--since", str(since_int), "--until", str(until_int)],
        cwd=str(crawl_script.parent),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )
    print(f"  🔄 爬虫已在后台运行 (PID={proc.pid})，主流水线继续处理其他数据源...")
    return proc


def wait_txresearch_result(
    proc: subprocess.Popen | None,
    since_int: int,
    until_int: int,
    timeout_minutes: int = 30,
    heartbeat_seconds: int = 60,
    silent_limit: int = 300,
) -> list[dict]:
    """等待后台爬虫完成并收集文章数据。

    如果 proc 为 None（已有缓存或未启动），直接从缓存加载。
    否则用心跳探测模式等待爬虫进程结束。

    Returns:
        文章列表（JSON 中的 dict 数组），失败返回空列表。
    """
    import time as _time

    tag = f"{since_int}-{until_int}"
    json_path = TX_DIR / f"articles_{tag}.json"
    crawl_script = ROOT / "Crawl" / "TXresearch" / "crawl_sohu.py"

    # 已有缓存，直接加载
    if proc is None:
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                articles = json.load(f)
            print(f"  📄 腾讯研究院: 从缓存加载 {len(articles)} 篇文章")
            return articles
        return []

    # 等待后台爬虫完成（心跳探测模式）
    print(f"\n  ⏳ 等待腾讯研究院爬虫完成 (PID={proc.pid})...")
    max_wait = timeout_minutes * 60
    elapsed = 0
    last_output_time = _time.time()

    while elapsed < max_wait:
        try:
            proc.wait(timeout=heartbeat_seconds)
            # 进程已结束，读取剩余输出
            remaining = proc.stdout.read() if proc.stdout else ""
            if remaining:
                for line in remaining.strip().split('\n'):
                    if line.strip():
                        print(f"    {line.strip()}")
            break
        except subprocess.TimeoutExpired:
            elapsed += heartbeat_seconds
            # 读取所有可用输出
            try:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    print(f"    {line.rstrip()}")
                    last_output_time = _time.time()
            except Exception:
                pass
            # 检查进程是否还在运行
            if proc.poll() is not None:
                break
            # 健康探测：超过 silent_limit 无输出则判定不健康
            silent_seconds = _time.time() - last_output_time
            if silent_seconds > silent_limit:
                print(f"  ⚠️ 爬虫已 {int(silent_seconds)}s 无输出，判定为不健康，终止")
                proc.kill()
                proc.wait()
                return []
            minutes_elapsed = elapsed // 60
            print(f"  💓 心跳 [{minutes_elapsed}min/{timeout_minutes}min] 爬虫运行中...")

    # 超时处理
    if elapsed >= max_wait and proc.poll() is None:
        print(f"  ⏰ 爬虫超时（{timeout_minutes}分钟），终止")
        proc.kill()
        proc.wait()
        return []

    returncode = proc.returncode if proc.returncode is not None else -1
    if returncode != 0:
        print(f"  ⚠️ 爬虫失败（退出码 {returncode}）")
        print(f"  💡 手动运行：cd Crawl\\TXresearch && python crawl_sohu.py --since {since_int} --until {until_int}")
        return []

    print(f"  ✅ 爬虫完成")

    # 查找输出 JSON
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        print(f"  📄 共 {len(articles)} 篇文章")
        return articles

    # 爬虫可能输出到 crawl_script.parent 目录
    alt_json = crawl_script.parent / f"articles_{tag}.json"
    if alt_json.exists():
        import shutil
        TX_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(alt_json, json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        print(f"  📄 共 {len(articles)} 篇文章（从爬虫输出目录复制）")
        return articles

    print(f"  ⚠️ 爬虫运行成功但未找到输出 JSON")
    return []


def collect_txresearch(since_int: int, until_int: int,
                       crawl_proc: subprocess.Popen | None = None) -> list[dict]:
    """采集腾讯研究院数据：等待爬虫 → 保存全文 → 同步 Excel。

    支持两种调用模式：
      - 异步模式：先调 start_txresearch_crawl() 拿到 proc，传入 crawl_proc
      - 同步模式（兼容旧逻辑）：crawl_proc=None 时自动启动并等待

    注意：爬虫本身不依赖 AI，是纯 Selenium 工具。
    本函数不返回 Excel 行数据（模型提取由 LLM 在后续步骤处理）。
    """
    print("\n📡 数据源: 腾讯研究院（搜狐号）")
    print("=" * 50)

    articles_dir = ROOT / "Extract" / "articles"

    # 如果没有预先启动爬虫，走同步模式（兼容旧调用方式）
    if crawl_proc is None:
        crawl_proc = start_txresearch_crawl(since_int, until_int)

    articles = wait_txresearch_result(crawl_proc, since_int, until_int)

    tag = f"{since_int}-{until_int}"
    json_path = TX_DIR / f"articles_{tag}.json"

    if not articles:
        if not json_path.exists():
            print(f"  ⚠️ 无文章数据可处理")
            return []

    # ── 第二步：保存全文到 Extract/articles/ 目录（TXT 文件）──
    articles_dir.mkdir(parents=True, exist_ok=True)
    saved_count = 0
    for article in articles:
        title = article.get("标题", "")
        seq = article.get("序号", 0)
        fulltext = article.get("全文", "")
        link = article.get("链接", "")

        if not fulltext or fulltext.startswith("[爬取失败]") or fulltext.startswith("[内容过短]"):
            continue

        # 文件名格式：01_腾讯研究院AI速递 20260416.txt
        # 标题可能包含换行符（爬虫返回的原始标题），需截断并清理
        safe_title = title.split('\n')[0].strip()
        safe_title = re.sub(r'[\\/:*?"<>|\r\n\t]', '', safe_title)
        safe_title = safe_title[:80]  # 限制长度，避免路径过长
        txt_filename = f"{seq:02d}_{safe_title}.txt"
        txt_path = articles_dir / txt_filename

        if not txt_path.exists():
            content = f"标题: {title}\n链接: {link}\n序号: {seq}\n{'=' * 80}\n\n{fulltext}"
            txt_path.write_text(content, encoding="utf-8")
            saved_count += 1

    if saved_count > 0:
        print(f"  💾 新保存 {saved_count} 篇全文到 {articles_dir}")
    else:
        print(f"  📂 全文文件已是最新（{articles_dir}）")

    # ── 第三步：同步到 TXCrawl Excel（文章元数据汇总） ──
    txcrawl_path = ROOT / "Extract" / "TXCrawl.xlsx"
    txcrawl_result_path = ROOT / "Extract" / "TXCrawl_result.xlsx"

    if articles:
        _sync_txcrawl_excel(articles, txcrawl_path, txcrawl_result_path)

    # ── 第四步：汇总状态 ──
    valid_articles = [a for a in articles
                      if a.get("全文", "")
                      and not a["全文"].startswith("[爬取失败]")
                      and not a["全文"].startswith("[内容过短]")]

    print(f"\n  📊 腾讯研究院抓取汇总:")
    print(f"     时间窗口: {since_int} ~ {until_int}")
    print(f"     文章总数: {len(articles)}")
    print(f"     全文可用: {len(valid_articles)}")
    print(f"     全文目录: {articles_dir}")
    print(f"     JSON 缓存: {json_path}")
    print(f"     TXCrawl Excel: {txcrawl_path}")
    print(f"\n  💡 模型信息提取：请在对话中让 AI 读取全文并提取模型信息")
    print(f"     或使用 LLM API：python Extract/extract_models_llm.py --since {since_int} --until {until_int}")

    # 不返回 Excel 行——模型信息由用户在对话中让 AI 提取（或通过 LLM API）
    return []


def _sync_txcrawl_excel(articles: list[dict], txcrawl_path: Path, txcrawl_result_path: Path):
    """将抓取到的文章追加到 TXCrawl.xlsx 和 TXCrawl_result.xlsx，跳过已存在的文章。"""
    # 读取已有数据
    existing_titles = set()
    if txcrawl_path.exists():
        existing_df = pd.read_excel(txcrawl_path, engine="openpyxl")
        existing_titles = set(existing_df["标题"].dropna().astype(str))
        max_seq = int(existing_df["序号"].max()) if not existing_df.empty else 0
    else:
        existing_df = pd.DataFrame(columns=["序号", "标题", "简介", "链接", "发布时间", "阅读数", "评论数"])
        max_seq = 0

    # 筛选新文章（去重）
    new_rows = []
    for article in articles:
        title = article.get("标题", "")
        if title in existing_titles:
            continue
        max_seq += 1
        fulltext = article.get("全文", "")
        summary = _extract_summary(fulltext) if fulltext else ""
        date_str = article.get("发布时间", "")
        if len(date_str) == 8:
            date_str = f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:]}"
        new_rows.append({
            "序号": max_seq,
            "标题": title,
            "简介": summary,
            "链接": article.get("链接", ""),
            "发布时间": date_str,
            "阅读数": "",
            "评论数": "",
        })

    if not new_rows:
        print(f"  📂 TXCrawl Excel 已是最新（无新文章需追加）")
        return

    new_df = pd.DataFrame(new_rows)

    # 追加到 TXCrawl.xlsx
    crawl_df = pd.concat([existing_df, new_df], ignore_index=True)
    crawl_df.to_excel(txcrawl_path, index=False, engine="openpyxl")
    print(f"  💾 TXCrawl.xlsx: 追加 {len(new_rows)} 篇 → 共 {len(crawl_df)} 行")

    # 追加到 TXCrawl_result.xlsx（模型列留空，等 LLM 提取）
    if txcrawl_result_path.exists():
        result_df = pd.read_excel(txcrawl_result_path, engine="openpyxl")
    else:
        result_df = pd.DataFrame(columns=[
            "序号", "标题", "简介", "链接", "发布时间", "阅读数", "评论数",
            "文章提及的新兴模型", "未追踪的新模型",
        ])
    new_result_df = new_df.copy()
    new_result_df["文章提及的新兴模型"] = ""
    new_result_df["未追踪的新模型"] = ""
    result_df = pd.concat([result_df, new_result_df], ignore_index=True)
    result_df.to_excel(txcrawl_result_path, index=False, engine="openpyxl")
    print(f"  💾 TXCrawl_result.xlsx: 追加 {len(new_rows)} 篇 → 共 {len(result_df)} 行")


def _extract_summary(fulltext: str, max_length: int = 150) -> str:
    """从全文中提取简介（取前几个段落，截断到指定长度）。"""
    if not fulltext:
        return ""
    lines = [line.strip() for line in fulltext.split("\n") if len(line.strip()) > 10]
    summary = "；".join(lines[:3])
    if len(summary) > max_length:
        summary = summary[:max_length] + "…"
    return summary


# ================================================================
#  数据源 3：平台模型目录采集（通用适配器框架）
# ================================================================
# 通过各 AI 平台的模型目录 API 获取全量可用模型变体。
# 支持 OpenAI 兼容 /models API 和自定义 REST API，通过注册表配置驱动。
# 不做时间窗口过滤——平台时间戳是上架时间，不等于模型发布时间，由去重决定是否新增。

# ── 国内公司集合（用于推断"国内外"字段）──
DOMESTIC_COMPANIES = frozenset({
    "阿里", "深度求索", "智谱", "月之暗面", "MiniMax", "百度", "腾讯",
    "字节跳动", "百川", "零一万物", "昆仑万维", "商汤", "讯飞", "阶跃星辰",
    "面壁智能", "稀宇科技", "幻方量化", "硅基流动",
    "蚂蚁", "美团", "小米", "快手", "小红书", "宇树", "智源",
})

# ── 平台注册表 ──
# 每个平台是一个 dict，包含以下字段：
#   name:            显示名称
#   type:            "openai" (OpenAI 兼容 /models) 或 "custom" (自定义适配器)
#   api_base_env:    API Base URL 环境变量名
#   api_key_env:     API Key 环境变量名
#   default_company: 平台方默认公司（模型 ID 无法匹配 owner_map 时使用）
#   owner_map:       模型 ID 前缀 → 公司名映射（按最长前缀优先匹配）
#   skip_patterns:   跳过的模型 ID 子串列表（旧版/非独立模型）
#   doc_url:         官方文档链接（写入"官网"字段）
#   note:            备注文本（写入"备注"字段）
#   fetch_fn:        (仅 type="custom") 自定义获取函数名，签名: (config) -> list[{id, created}]

PLATFORM_REGISTRY = [
    {
        "name": "DashScope 百炼",
        "type": "openai",
        "api_base_env": "LLM_API_BASE",
        "api_key_env": "LLM_API_KEY",
        "default_company": "阿里",
        "owner_map": {
            "codeqwen": "阿里", "qwen": "阿里", "qwq": "阿里", "qvq": "阿里",
            "deepseek": "深度求索", "glm": "智谱", "minimax": "MiniMax",
            "kimi": "月之暗面", "gui": "阿里",
        },
        "skip_patterns": ["qwen-1.8b", "qwen-7b", "qwen-14b", "qwen-72b", "qwen1.5-", "qwen2-"],
        "doc_url": "https://help.aliyun.com/zh/model-studio/models",
        "note": "DashScope 百炼平台",
    },
    {
        "name": "硅基流动 SiliconFlow",
        "type": "openai",
        "api_base_env": "SILICONFLOW_API_BASE",
        "api_key_env": "SILICONFLOW_API_KEY",
        "default_company": "硅基流动",
        "owner_map": {
            "qwen": "阿里", "deepseek": "深度求索", "glm": "智谱",
            "internlm": "上海AI实验室", "yi-": "零一万物", "baichuan": "百川",
            "meta-llama": "Meta", "mistral": "Mistral", "gemma": "Google",
        },
        "skip_patterns": [],
        "doc_url": "https://docs.siliconflow.cn/quickstart/models",
        "note": "硅基流动 SiliconFlow",
    },
    {
        "name": "DeepSeek",
        "type": "openai",
        "api_base_env": "DEEPSEEK_API_BASE",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_company": "深度求索",
        "owner_map": {},
        "skip_patterns": [],
        "doc_url": "https://api-docs.deepseek.com",
        "note": "DeepSeek 官方 API",
    },
    {
        "name": "火山引擎 Volcengine",
        "type": "openai",
        "api_base_env": "VOLCENGINE_API_BASE",
        "api_key_env": "VOLCENGINE_API_KEY",
        "default_company": "字节跳动",
        "owner_map": {
            "doubao": "字节跳动", "deepseek": "深度求索", "qwen": "阿里",
            "glm": "智谱", "minimax": "MiniMax",
        },
        "skip_patterns": [],
        "doc_url": "https://www.volcengine.com/docs/82379/1330310",
        "note": "火山引擎方舟平台",
    },
    {
        "name": "Moonshot 月之暗面",
        "type": "openai",
        "api_base_env": "MOONSHOT_API_BASE",
        "api_key_env": "MOONSHOT_API_KEY",
        "default_company": "月之暗面",
        "owner_map": {},
        "skip_patterns": [],
        "doc_url": "https://platform.moonshot.cn/docs",
        "note": "Moonshot 月之暗面",
    },
    {
        "name": "智谱 Zhipu",
        "type": "openai",
        "api_base_env": "ZHIPU_API_BASE",
        "api_key_env": "ZHIPU_API_KEY",
        "default_company": "智谱",
        "owner_map": {},
        "skip_patterns": [],
        "doc_url": "https://open.bigmodel.cn/dev/api",
        "note": "智谱 BigModel",
    },
    {
        "name": "百度千帆 Qianfan",
        "type": "custom",
        "api_base_env": "QIANFAN_API_BASE",
        "api_key_env": "QIANFAN_API_KEY",
        "default_company": "百度",
        "owner_map": {
            "ernie": "百度", "qwen": "阿里", "deepseek": "深度求索",
            "llama": "Meta", "mistral": "Mistral",
        },
        "skip_patterns": [],
        "doc_url": "https://cloud.baidu.com/doc/qianfan/s/rmh4stp0j",
        "note": "百度千帆平台",
        "fetch_fn": "_fetch_qianfan_models",
    },
    # ── 官方平台（补全 Focus.xlsx 重点厂商）──
    {
        "name": "MiniMax",
        "type": "openai",
        "api_base_env": "MINIMAX_API_BASE",
        "api_key_env": "MINIMAX_API_KEY",
        "default_company": "MiniMax",
        "owner_map": {},
        "skip_patterns": [],
        "doc_url": "https://platform.minimaxi.com/docs",
        "note": "MiniMax 开放平台",
    },
    {
        "name": "腾讯混元 Hunyuan",
        "type": "openai",
        "api_base_env": "HUNYUAN_API_BASE",
        "api_key_env": "HUNYUAN_API_KEY",
        "default_company": "腾讯",
        "owner_map": {"deepseek": "深度求索", "qwen": "阿里"},
        "skip_patterns": [],
        "doc_url": "https://cloud.tencent.com/document/product/1729/111007",
        "note": "腾讯混元平台",
    },
    {
        "name": "阶跃星辰 StepFun",
        "type": "openai",
        "api_base_env": "STEPFUN_API_BASE",
        "api_key_env": "STEPFUN_API_KEY",
        "default_company": "阶跃星辰",
        "owner_map": {"deepseek": "深度求索"},
        "skip_patterns": [],
        "doc_url": "https://platform.stepfun.com/docs",
        "note": "阶跃星辰 StepFun",
    },
    # ── 聚合平台（兜底补充源）──
    {
        "name": "OpenRouter",
        "type": "custom",
        "api_base_env": "OPENROUTER_API_BASE",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_company": "未知",
        "owner_map": {},
        "skip_patterns": [],
        "doc_url": "https://openrouter.ai/docs",
        "note": "OpenRouter 聚合平台",
        "fetch_fn": "_fetch_openrouter_models",
    },
    {
        "name": "酷爱 Kuai",
        "type": "openai",
        "api_base_env": "KUAI_API_BASE",
        "api_key_env": "KUAI_API_KEY",
        "default_company": "未知",
        "owner_map": {
            "qwen": "阿里", "deepseek": "深度求索", "glm": "智谱",
            "gpt": "OpenAI", "claude": "Anthropic", "gemini": "Google",
            "llama": "Meta", "mistral": "Mistral", "doubao": "字节跳动",
            "ernie": "百度", "hunyuan": "腾讯", "kimi": "月之暗面",
            "minimax": "MiniMax", "step": "阶跃星辰",
        },
        "skip_patterns": [],
        "doc_url": "https://doc.kuai.host",
        "note": "酷爱 Kuai 聚合平台",
    },
]


def _fetch_openai_compatible_models(config: dict) -> list[dict]:
    """通过 OpenAI 兼容 /models 端点获取模型列表。

    返回: [{id: str, created: int}, ...]
    """
    api_base = os.environ.get(config["api_base_env"], "")
    api_key = os.environ.get(config["api_key_env"], "")
    url = f"{api_base.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    return data.get("data", [])


def _fetch_qianfan_models(config: dict) -> list[dict]:
    """通过百度千帆 /v2/models 端点获取模型列表。

    千帆 API 返回格式: {result: [{modelId, modelName, ...}]}
    需要转换为统一的 {id, created} 格式。
    """
    api_base = os.environ.get(config["api_base_env"], "")
    api_key = os.environ.get(config["api_key_env"], "")

    url = f"{api_base.rstrip('/')}/v2/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"pageSize": 200}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    raw_models = data.get("result", data.get("data", []))

    unified = []
    for model in raw_models:
        model_id = model.get("modelName") or model.get("model") or model.get("id", "")
        created = model.get("createTime", 0)
        # 千帆的 createTime 可能是毫秒时间戳
        if created > 1e12:
            created = int(created / 1000)
        unified.append({"id": model_id, "created": created})
    return unified


# ── OpenRouter org slug → 公司名映射 ──
_OPENROUTER_ORG_MAP = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
    "meta-llama": "Meta", "mistralai": "Mistral", "nvidia": "NVIDIA",
    "x-ai": "xAI", "cohere": "Cohere", "amazon": "Amazon",
    "qwen": "阿里", "deepseek": "深度求索", "thudm": "智谱",
    "01-ai": "零一万物", "baichuan-inc": "百川",
    "minimax": "MiniMax", "moonshot": "月之暗面",
    "stepfun": "阶跃星辰", "bytedance": "字节跳动",
    "microsoft": "Microsoft", "databricks": "Databricks",
    "ai21": "AI21 Labs", "perplexity": "Perplexity",
    "inflection": "Inflection", "nousresearch": "Nous Research",
}


def _fetch_openrouter_models(config: dict) -> list[dict]:
    """通过 OpenRouter /api/v1/models 获取全球模型聚合列表。

    OpenRouter 返回额外字段（pricing, architecture, top_provider 等），
    模型 ID 格式为 org/model-name，可直接从 org 推断公司归属。
    返回统一的 [{id, created, _owner}] 格式，_owner 用于覆盖默认公司推断。
    """
    api_base = os.environ.get(config["api_base_env"], "")
    api_key = os.environ.get(config["api_key_env"], "")
    url = f"{api_base.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = requests.get(url, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    raw_models = data.get("data", [])

    unified = []
    for model in raw_models:
        model_id = model.get("id", "")
        created = model.get("created", 0)

        # 从 org/model-name 格式提取 org 并映射到公司名
        org_slug = model_id.split("/")[0] if "/" in model_id else ""
        owner = _OPENROUTER_ORG_MAP.get(org_slug, "")

        # 用模型名部分（去掉 org 前缀）作为 display name
        display_name = model_id.split("/", 1)[1] if "/" in model_id else model_id

        unified.append({
            "id": display_name,
            "created": created,
            "_owner": owner,  # 额外字段，供 _model_to_row 使用
        })
    return unified


# ── 自定义 fetch 函数注册表（通过函数名字符串映射到实际函数）──
_CUSTOM_FETCH_FNS = {
    "_fetch_qianfan_models": _fetch_qianfan_models,
    "_fetch_openrouter_models": _fetch_openrouter_models,
}


def _resolve_company(model_id_lower: str, config: dict) -> str:
    """根据模型 ID 前缀匹配 owner_map，返回公司名。"""
    owner_map = config.get("owner_map", {})
    # 按前缀长度降序匹配，确保最长前缀优先
    for prefix in sorted(owner_map, key=len, reverse=True):
        if model_id_lower.startswith(prefix):
            return owner_map[prefix]
    return config.get("default_company", "未知")


def _model_to_row(model_id: str, created_ts: int, config: dict,
                   owner_override: str = "") -> dict:
    """将平台返回的单个模型信息转换为标准行格式。

    owner_override: 由自定义适配器预解析的公司名（如 OpenRouter 从 org slug 解析）。
    """
    display_name = model_id.split("/")[-1] if "/" in model_id else model_id
    company = owner_override or _resolve_company(model_id.lower(), config)
    domestic = "国内" if company in DOMESTIC_COMPANIES else "国外"

    # 推断开闭源：带参数量后缀的通常是开源模型的部署版
    open_source = "开源" if re.search(r'\d+[bB]', display_name) else "闭源"

    model_info = {"name": display_name, "model_id": model_id}
    pub_date = datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d") if created_ts else ""

    return {
        "模型名称": display_name,
        "公司": company,
        "国内外": domestic,
        "开闭源": open_source,
        "尺寸": _infer_size_from_name(display_name),
        "类型": _infer_type(model_info),
        "能否推理": _infer_reasoning(model_info),
        "任务类型": "",
        "官网": config.get("doc_url", ""),
        "备注": config.get("note", ""),
        "模型发布时间": pub_date,
        "记录创建时间": today_str(),
    }


def _collect_single_platform(config: dict) -> list[dict]:
    """采集单个平台的全量模型目录，返回标准行列表。"""
    platform_name = config["name"]
    api_base = os.environ.get(config["api_base_env"], "")
    api_key = os.environ.get(config["api_key_env"], "")

    if not api_base or not api_key:
        return []

    print(f"\n  📡 {platform_name}")
    print(f"  {'─' * 46}")

    try:
        if config["type"] == "openai":
            raw_models = _fetch_openai_compatible_models(config)
        else:
            fetch_fn_name = config.get("fetch_fn", "")
            fetch_fn = _CUSTOM_FETCH_FNS.get(fetch_fn_name)
            if not fetch_fn:
                print(f"    ❌ 未知的自定义适配器: {fetch_fn_name}")
                return []
            raw_models = fetch_fn(config)
    except Exception as exc:
        print(f"    ❌ 请求失败: {exc}")
        return []

    print(f"    ✅ 获取到 {len(raw_models)} 个模型")

    skip_patterns = config.get("skip_patterns", [])
    rows = []
    skipped_pattern = 0
    skipped_old = 0

    # 2026-01-01 00:00:00 UTC 的 Unix 时间戳
    # 平台目录只追踪 2026 年及之后的模型，旧版模型不纳入增量追踪
    cutoff_ts = 1735689600  # 2026-01-01T00:00:00Z

    for model in raw_models:
        model_id = model.get("id", "")
        created_ts = model.get("created", 0)
        model_id_lower = model_id.lower()

        if any(pat in model_id_lower for pat in skip_patterns):
            skipped_pattern += 1
            continue

        # 时效性过滤：只保留 2026 年及之后上架的模型
        if created_ts and created_ts < cutoff_ts:
            skipped_old += 1
            continue

        # 自定义适配器可能预解析了 _owner 字段（如 OpenRouter）
        owner_override = model.get("_owner", "")
        rows.append(_model_to_row(model_id, created_ts, config, owner_override))

    if skipped_pattern:
        print(f"    ⏭️ 跳过: {skipped_pattern} 个（模式匹配）")
    if skipped_old:
        print(f"    ⏭️ 跳过: {skipped_old} 个（2026 年以前的旧模型）")
    print(f"    📊 可用: {len(rows)} 个（2026+）")
    return rows


def collect_platform_catalogs(since_int: int, until_int: int) -> list[dict]:
    """遍历所有已配置的平台，采集模型目录并合并去重。

    只有环境变量中配置了 API Key 的平台才会被采集。
    时效性过滤：平台 created 时间戳早于 2026 年的旧模型会被跳过，
    只追踪 2026 年及之后的新模型（增量追踪原则）。
    """
    configured = [
        cfg for cfg in PLATFORM_REGISTRY
        if os.environ.get(cfg["api_base_env"]) and os.environ.get(cfg["api_key_env"])
    ]

    if not configured:
        print("\n⚠️ 平台模型目录: 无已配置的平台（需在 .env 中配置 API Key）")
        return []

    platform_names = ", ".join(cfg["name"] for cfg in configured)
    print(f"\n📡 数据源: 平台模型目录（{len(configured)} 个平台: {platform_names}）")
    print("=" * 50)

    all_rows = []
    seen_names: set[str] = set()

    for config in configured:
        rows = _collect_single_platform(config)
        # 跨平台去重（同一模型可能在多个平台上架）
        unique_rows = []
        for row in rows:
            name_lower = row["模型名称"].strip().lower()
            if name_lower not in seen_names:
                seen_names.add(name_lower)
                unique_rows.append(row)
        all_rows.extend(unique_rows)
        if len(rows) != len(unique_rows):
            print(f"    🔄 跨平台去重: {len(rows)} → {len(unique_rows)}")

    print(f"\n  📊 平台目录合计: {len(all_rows)} 个模型（跨 {len(configured)} 个平台）")
    return all_rows


# ================================================================
#  数据源 4：HuggingFace API（批量发现开源模型）
# ================================================================

# 要扫描的 HuggingFace 组织列表（覆盖主流 AI 模型发布方）
HF_ORGS_TO_SCAN = [
    "Qwen", "deepseek-ai", "THUDM", "meta-llama", "google",
    "mistralai", "microsoft", "nvidia", "01-ai", "LGAI-EXAONE",
    "FunAudioLLM", "stepfun", "MiniMaxAI",
]


def collect_huggingface(since_int: int, until_int: int,
                        orgs: list[str] | None = None) -> list[dict]:
    """通过 HuggingFace API 批量发现开源模型。

    用 GET /api/models?author={org} 获取各组织的模型列表，
    筛选出在时间窗口内创建/更新的模型，映射为流水线标准行格式。

    Args:
        since_int: 起始日期 YYYYMMDD
        until_int: 截止日期 YYYYMMDD
        orgs: 要扫描的组织列表，默认用 HF_ORGS_TO_SCAN
    """
    scan_orgs = orgs or HF_ORGS_TO_SCAN
    print(f"\n🔍 数据源: HuggingFace API（{len(scan_orgs)} 个组织）")
    print("=" * 50)

    proxy = detect_proxy()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    hf_headers = dict(HTTP_HEADERS)
    hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token:
        hf_headers["Authorization"] = f"Bearer {hf_token}"

    all_rows = []
    since_iso = f"{str(since_int)[:4]}-{str(since_int)[4:6]}-{str(since_int)[6:]}"
    until_iso = f"{str(until_int)[:4]}-{str(until_int)[4:6]}-{str(until_int)[6:]}"

    for org in scan_orgs:
        try:
            # 使用 hf-mirror.com 镜像站（huggingface.co 在国内被墙）
            api_url = f"https://hf-mirror.com/api/models?author={org}&sort=createdAt&direction=-1&limit=200"
            resp = None
            for attempt in range(3):
                try:
                    resp = requests.get(api_url, headers=hf_headers, proxies=proxies,
                                        timeout=60, verify=False)
                    if resp.status_code == 200:
                        break
                    if resp.status_code in (429, 500, 502, 503, 521):
                        import time as _time
                        _time.sleep(3 * (attempt + 1))
                        continue
                except requests.exceptions.Timeout:
                    if attempt < 2:
                        continue
                    raise
            if resp is None or resp.status_code != 200:
                status = resp.status_code if resp else "no response"
                print(f"  ⚠️ {org}: HTTP {status}（重试3次仍失败）")
                continue

            models_data = resp.json()
            org_count = 0

            for model in models_data:
                model_id = model.get("modelId", "")  # e.g. "Qwen/Qwen3-8B"
                created = model.get("createdAt", "")[:10]  # "2026-01-15"
                last_modified = model.get("lastModified", "")[:10]

                # 时间窗口过滤：createdAt 在 since~until 内
                if created and created >= since_iso and created <= until_iso:
                    pass  # 在窗口内
                elif last_modified and last_modified >= since_iso and last_modified <= until_iso:
                    pass  # 最近更新的也纳入
                else:
                    continue

                # 提取模型名称（去掉组织前缀）
                short_name = model_id.split("/", 1)[-1] if "/" in model_id else model_id

                # 跳过非模型 repo（datasets、spaces、GGUF 量化等）
                tags = model.get("tags", [])
                if any(skip in short_name.lower() for skip in
                       ("gguf", "gptq", "awq", "bnb", "demo", "chat-template")):
                    continue

                # 提取参数量（列表 API 通常不含 safetensors，fallback 到名称推断）
                safetensors = model.get("safetensors") or {}
                params = safetensors.get("total", 0)
                size_str = format_params(params) if params else _infer_size_from_name(short_name)

                # 推断公司
                company = _hf_org_to_company(org)
                domestic = "国内" if is_domestic(org.lower()) else "国外"

                # 推断开闭源
                pipeline_tag = model.get("pipeline_tag", "")

                # 构造行
                row = {
                    "模型名称": short_name,
                    "公司": company,
                    "国内外": domestic,
                    "开闭源": "开源",
                    "尺寸": size_str,
                    "类型": _infer_type({"name": short_name, "model_id": model_id}),
                    "能否推理": _infer_reasoning({"name": short_name, "model_id": model_id}),
                    "任务类型": "",
                    "官网": f"https://huggingface.co/{model_id}",
                    "备注": f"HuggingFace {pipeline_tag}" if pipeline_tag else "HuggingFace",
                    "模型发布时间": created,
                    "记录创建时间": today_str(),
                }
                all_rows.append(row)
                org_count += 1

            if org_count > 0:
                print(f"  ✅ {org}: {org_count} 个模型")
            else:
                print(f"  📂 {org}: 时间窗口内无新模型")

        except requests.exceptions.Timeout:
            print(f"  ⏰ {org}: 超时")
        except Exception as exc:
            print(f"  ⚠️ {org}: {exc}")

    print(f"\n  📊 HuggingFace 共发现 {len(all_rows)} 个模型")
    return all_rows


def _hf_org_to_company(org: str) -> str:
    """HuggingFace 组织名 → 公司名。"""
    mapping = {
        "Qwen": "阿里", "deepseek-ai": "深度求索", "THUDM": "智谱",
        "meta-llama": "Meta", "google": "Google", "mistralai": "Mistral",
        "microsoft": "微软", "nvidia": "英伟达", "01-ai": "零一万物",
        "LGAI-EXAONE": "LG", "FunAudioLLM": "阿里", "stepfun": "阶跃星辰",
        "MiniMaxAI": "MiniMax",
    }
    return mapping.get(org, org)


# ================================================================
#  核实：HuggingFace API
# ================================================================

# ── HuggingFace 组织名映射（llmstats org_id → HuggingFace org slug）──
HF_ORG_MAP = {
    "moonshotai": ["moonshotai", "moonshot-ai"],
    "alibaba": ["Qwen", "alibaba-nlp", "modelscope"],
    "qwen": ["Qwen"],
    "google": ["google"],
    "meta": ["meta-llama", "facebook"],
    "openai": ["openai"],
    "anthropic": ["anthropic"],
    "mistral": ["mistralai"],
    "zhipu": ["THUDM"],
    "deepseek": ["deepseek-ai"],
    "bytedance": ["bytedance-research"],
    "01-ai": ["01-ai"],
    "nvidia": ["nvidia"],
    "microsoft": ["microsoft"],
    "tencent": ["tencent"],
    "xiaomi": ["xiaomi"],
    "stepfun": ["stepfun"],
    "minimax": ["MiniMaxAI"],
    "nous-research": ["NousResearch"],
    "sarvam-ai": ["sarvamai"],
}


def _build_hf_search_names(name: str, company: str, org_id: str) -> list[str]:
    """构造 HuggingFace 搜索路径列表（按可能性从高到低排列）。"""
    candidates = []
    name_slug = name.lower().replace(" ", "-")
    model_id_slug = re.sub(r"[^a-z0-9\-.]", "-", name_slug)

    # 1. 用已知的 HuggingFace 组织名映射
    org_key = (org_id or "").lower().replace(" ", "").replace("-", "")
    hf_orgs = HF_ORG_MAP.get(org_key, [])
    for hf_org in hf_orgs:
        candidates.append(f"{hf_org}/{name}")
        candidates.append(f"{hf_org}/{model_id_slug}")

    # 2. 用公司名直接猜
    if company:
        company_slug = company.lower().replace(" ", "-").split("/")[0].strip()
        candidates.append(f"{company_slug}/{name}")
        candidates.append(f"{company_slug}/{model_id_slug}")

    # 3. 直接用模型名搜索
    candidates.append(name)

    # 去重、保留顺序
    seen = set()
    unique = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def verify_via_huggingface(rows: list[dict]) -> list[dict]:
    """对标记为开源的模型，通过 HuggingFace API 交叉校验信息。

    校验内容：
      1. 模型是否存在于 HuggingFace（确认开源状态）
      2. 参数量（补充/修正"尺寸"列）
      3. License（交叉校验"开闭源"和备注中的 license）
      4. 模型标签（补充类型信息）
    """
    open_source_rows = [r for r in rows if r.get("开闭源") == "开源"]
    if not open_source_rows:
        return rows

    print(f"\n🔍 HuggingFace 交叉校验（{len(open_source_rows)} 个开源模型）")

    proxy = detect_proxy()
    proxies = {"http": proxy, "https": proxy} if proxy else None

    # 构造 HuggingFace 请求 headers（带 Token 认证可访问 gated model）
    hf_headers = dict(HTTP_HEADERS)
    hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token:
        hf_headers["Authorization"] = f"Bearer {hf_token}"
        print(f"  🔑 已配置 HF_TOKEN（可访问 gated model）")
    else:
        print(f"  ⚠️ 未配置 HF_TOKEN，gated model 将无法获取详情")

    for row in open_source_rows:
        name = row.get("模型名称", "")
        company = row.get("公司", "")
        org_id = ""
        # 从备注中尝试提取 org_id（llmstats 数据源）
        existing_note = row.get("核实情况", "")

        search_names = _build_hf_search_names(name, company, org_id)

        verified = False
        for search_name in search_names:
            try:
                api_url = f"https://huggingface.co/api/models/{search_name}"
                resp = requests.get(
                    api_url, headers=hf_headers,
                    proxies=proxies, timeout=15, verify=False,
                )
                if resp.status_code == 200:
                    data = resp.json()

                    # 提取参数量
                    safetensors = data.get("safetensors") or {}
                    hf_params = safetensors.get("total", 0)

                    # 提取 license
                    hf_tags = data.get("tags", [])
                    hf_license = next(
                        (t.replace("license:", "") for t in hf_tags if t.startswith("license:")),
                        None,
                    )

                    # 提取 pipeline tag（模型类型）
                    pipeline_tag = data.get("pipeline_tag", "")

                    # 构造核实信息
                    verify_parts = [f"HuggingFace 已核实({search_name})"]
                    if hf_params:
                        hf_size_str = format_params(hf_params)
                        verify_parts.append(f"参数量={hf_size_str}")
                        # 交叉校验：如果 llmstats 没给尺寸，用 HF 的
                        if not row.get("尺寸"):
                            row["尺寸"] = hf_size_str
                    if hf_license:
                        verify_parts.append(hf_license)
                    if pipeline_tag:
                        verify_parts.append(pipeline_tag)

                    row["核实情况"] = " · ".join(verify_parts)
                    print(f"  ✅ {name}: {row['核实情况']}")
                    verified = True
                    break

                elif resp.status_code == 401:
                    row["核实情况"] = f"{existing_note} · HuggingFace 需登录({search_name})"
                    print(f"  🔒 {name}: 需登录同意 License ({search_name})")
                    verified = True
                    break

            except requests.exceptions.Timeout:
                continue
            except Exception:
                continue

        if not verified:
            print(f"  ⚠️ {name}: HuggingFace 未找到（尝试了 {len(search_names)} 个路径）")

    return rows


# ================================================================
#  LLM 提取结果加载（腾讯研究院文章 → 结构化模型数据）
# ================================================================

def load_llm_extracted_models(since_int: int, until_int: int) -> list[dict]:
    """加载 LLM 从腾讯研究院文章中提取的模型数据，转换为标准行格式。

    读取 Extract/extracted_models_llm.json，按 source_date 过滤时间窗口，
    将 JSON 字段映射为 Excel 列名。
    """
    json_path = ROOT / "Extract" / "extracted_models_llm.json"
    if not json_path.exists():
        print("\n  📭 LLM 提取结果不存在，跳过")
        return []

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"\n📡 数据源: LLM 提取（腾讯研究院文章）")
    print("=" * 50)
    print(f"  📄 JSON 记录总数: {len(records)}")

    # 字段映射: JSON key → Excel 列名
    field_map = {
        "model_name": "模型名称",
        "company": "公司",
        "domestic": "国内外",
        "open_source": "开闭源",
        "size": "尺寸",
        "model_type": "类型",
        "can_reason": "能否推理",
        "task_type": "任务类型",
        "website": "官网",
        "release_date": "模型发布时间",
    }

    rows = []
    for record in records:
        source_date = record.get("source_date", 0)
        if source_date and (source_date < since_int or source_date > until_int):
            continue

        model_name = (record.get("model_name") or "").strip()
        if not model_name:
            continue

        row = {}
        for json_key, excel_col in field_map.items():
            row[excel_col] = record.get(json_key, "")

        # 补充元数据
        brief = record.get("brief", "")
        source_article = record.get("source_article", "")
        note_parts = []
        if brief:
            note_parts.append(brief)
        if source_article:
            note_parts.append(f"来源: {source_article}")
        row["备注"] = " | ".join(note_parts) if note_parts else ""
        row["记录创建时间"] = today_str()
        row["是否新增"] = "New"

        rows.append(row)

    print(f"  📊 时间窗口内: {len(rows)} 条模型")
    return rows


# ================================================================
#  写入 Excel
# ================================================================

def deduplicate_rows(new_rows: list[dict], existing_names: set[str]) -> list[dict]:
    """去重：过滤掉 Excel 中已有的模型。"""
    unique_rows = []
    for row in new_rows:
        name = (row.get("模型名称") or "").strip().lower()
        if name and name not in existing_names:
            unique_rows.append(row)
            existing_names.add(name)  # 避免同批次内重复
    return unique_rows


def write_to_excel(new_rows: list[dict], excel_path: Path, dry_run: bool = False):
    """将新模型追加到 Excel 表格。"""
    if not new_rows:
        print("\n  📭 无新模型需要写入")
        return

    if dry_run:
        print(f"\n  🔍 [DRY-RUN] 将写入 {len(new_rows)} 条新记录:")
        for row in new_rows[:10]:
            print(f"    [{row['公司']}] {row['模型名称']}")
        if len(new_rows) > 10:
            print(f"    ... 还有 {len(new_rows) - 10} 条")
        return

    # 读取现有 Excel
    if excel_path.exists():
        df_existing = pd.read_excel(excel_path, engine="openpyxl")
    else:
        df_existing = pd.DataFrame(columns=EXCEL_COLUMNS)

    # 追加新行
    df_new = pd.DataFrame(new_rows, columns=EXCEL_COLUMNS)
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)

    # 写入 Excel
    df_combined.to_excel(excel_path, index=False, engine="openpyxl")
    print(f"\n  📊 Excel 已更新: {excel_path}")
    print(f"    原有: {len(df_existing)} 行")
    print(f"    新增: {len(df_new)} 行")
    print(f"    合计: {len(df_combined)} 行")


# ================================================================
#  CLI 入口
# ================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="自动化数据采集 + 写入 Excel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python auto_collect.py --since 20260417 --until 20260423\n"
            "  python auto_collect.py --source llmstats\n"
            "  python auto_collect.py --dry-run\n"
        ),
    )
    parser.add_argument("--since", type=str, help="起始日期 (YYYYMMDD)")
    parser.add_argument("--until", type=str, help="截止日期 (YYYYMMDD)")
    parser.add_argument(
        "--source", type=str, default="all",
        choices=["all", "llmstats", "txresearch", "huggingface", "platform", "llm_extract"],
        help="数据源 (默认 all；platform 获取各平台模型目录；llm_extract 加载 LLM 提取结果)",
    )
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写 Excel")
    return parser.parse_args()


def main():
    args = parse_args()

    today = datetime.now()
    if args.until:
        until_int = int(args.until)
    else:
        until_int = int(today.strftime("%Y%m%d"))
    if args.since:
        since_int = int(args.since)
    else:
        since_int = int((today - timedelta(days=7)).strftime("%Y%m%d"))

    print("🚀 自动化数据采集")
    print(f"  时间窗口: {since_int} ~ {until_int}")
    print(f"  数据源: {args.source}")
    if args.dry_run:
        print("  模式: 🔍 DRY-RUN（不写入 Excel）")
    print()

    # 加载已有模型（用于去重）
    existing_names = load_existing_models(EXCEL_PATH)
    print(f"  📋 已有模型: {len(existing_names)} 个\n")

    all_new_rows = []

    # ── 异步并行：先启动腾讯研究院爬虫（后台），再跑 llmstats ──
    # 爬虫是纯 Selenium 工具，不依赖 AI，可以后台异步运行
    crawl_proc = None
    if args.source in ("all", "txresearch"):
        crawl_proc = start_txresearch_crawl(since_int, until_int)

    # 1. llmstats（HTTP 抓取，秒级完成，爬虫在后台同时运行）
    if args.source in ("all", "llmstats"):
        llmstats_rows = collect_llmstats(since_int, until_int)
        llmstats_unique = deduplicate_rows(llmstats_rows, existing_names)
        print(f"  去重后: {len(llmstats_unique)}/{len(llmstats_rows)} 条")
        all_new_rows.extend(llmstats_unique)

    # 2. 腾讯研究院（等待后台爬虫完成，处理结果）
    if args.source in ("all", "txresearch"):
        tx_rows = collect_txresearch(since_int, until_int, crawl_proc=crawl_proc)
        tx_unique = deduplicate_rows(tx_rows, existing_names)
        print(f"  去重后: {len(tx_unique)}/{len(tx_rows)} 条")
        all_new_rows.extend(tx_unique)

    # 2.5 LLM 提取结果（腾讯研究院文章 → 模型数据）
    if args.source in ("all", "txresearch", "llm_extract"):
        llm_rows = load_llm_extracted_models(since_int, until_int)
        combined_existing = existing_names | {
            r.get("模型名称", "").strip().lower() for r in all_new_rows
        }
        llm_unique = deduplicate_rows(llm_rows, combined_existing)
        print(f"  去重后: {len(llm_unique)}/{len(llm_rows)} 条")
        all_new_rows.extend(llm_unique)

    # 3. 平台模型目录（通用适配器：DashScope / 硅基流动 / DeepSeek / 火山引擎等）
    if args.source in ("all", "platform"):
        platform_rows = collect_platform_catalogs(since_int, until_int)
        combined_existing = existing_names | {
            r.get("模型名称", "").strip().lower() for r in all_new_rows
        }
        platform_unique = deduplicate_rows(platform_rows, combined_existing)
        print(f"  去重后: {len(platform_unique)}/{len(platform_rows)} 条")
        all_new_rows.extend(platform_unique)

    # 4. HuggingFace API（批量发现开源模型）
    if args.source in ("all", "huggingface"):
        hf_rows = collect_huggingface(since_int, until_int)
        # 去重时要考虑前面已经采集到的模型
        combined_existing = existing_names | {
            r.get("模型名称", "").strip().lower() for r in all_new_rows
        }
        hf_unique = deduplicate_rows(hf_rows, combined_existing)
        print(f"  去重后: {len(hf_unique)}/{len(hf_rows)} 条")
        all_new_rows.extend(hf_unique)

    # 4. HuggingFace 核实（对开源模型自动验证）
    if all_new_rows:
        all_new_rows = verify_via_huggingface(all_new_rows)

    # 写入 Excel
    print(f"\n{'='*50}")
    print(f"  📊 汇总: {len(all_new_rows)} 条新模型")
    print(f"{'='*50}")

    write_to_excel(all_new_rows, EXCEL_PATH, dry_run=args.dry_run)

    # 打印新增模型列表
    if all_new_rows:
        print(f"\n  新增模型列表:")
        for row in all_new_rows:
            company = row.get("公司", "?")
            name = row.get("模型名称", "?")
            pub_time = row.get("模型发布时间", "")
            print(f"    {pub_time or '?'} | [{company}] {name}")


def _load_env():
    """加载 .env 文件中的环境变量（如 HF_TOKEN、DINGTALK_WEBHOOK 等）。"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    # Windows GBK 终端兼容：强制 UTF-8 输出
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    _load_env()
    main()
