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
    "官网", "备注", "记录创建时间", "模型发布时间", "是否新增", "核实情况",
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
            "官网": f"https://llm-stats.com/models/{model_id}" if model_id else "",
            "备注": _build_llmstats_note(model),
            "记录创建时间": today_str(),
            "模型发布时间": date_str,
            "是否新增": "New",
            "核实情况": "llm-stats.com 排行榜",
        }
        rows.append(row)

    print(f"  📊 时间窗口 {since_int}~{until_int} 内: {len(rows)} 个模型")
    return rows

def _infer_type(model: dict) -> str:
    """从模型字段推断类型（对齐项目已有分类）。"""
    multimodal = model.get("multimodal")
    name_lower = (model.get("name") or "").lower()
    model_id = (model.get("model_id") or "").lower()

    # 代码类
    if any(kw in name_lower or kw in model_id for kw in ("code", "codex", "coder")):
        return "代码"
    # 语音类
    if any(kw in name_lower or kw in model_id for kw in ("whisper", "tts", "stt", "speech", "audio", "voice", "vox")):
        return "语音"
    # 多模态
    if isinstance(multimodal, list) and len(multimodal) > 0:
        return "多模态"
    if multimodal is True:
        return "多模态"
    # 基座 vs 领域（按参数量区分）
    is_moe = model.get("is_moe")
    params = model.get("params") or 0
    if params >= 50_000_000_000 or is_moe:
        return "基座"
    if params >= 1_000_000_000:
        return "基座"
    return "领域"


def _infer_reasoning(model: dict) -> str:
    """推断模型是否支持推理（thinking）。"""
    name_lower = (model.get("name") or "").lower()
    model_id = (model.get("model_id") or "").lower()
    combined = name_lower + " " + model_id

    if any(kw in combined for kw in ("thinking", "reason", "o1", "o3", "o4", "r1", "r2")):
        return "thinking"
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

def collect_txresearch(since_int: int, until_int: int) -> list[dict]:
    """自动爬取腾讯研究院文章全文并保存到本地。

    流程：
      1. 自动调用 crawl_sohu.py 爬取文章列表 + 全文（需要 Chrome + Selenium）
      2. 将全文保存到 Extract/articles/ 目录（TXT 文件）
      3. 保存 JSON 到 TXresearch/ 目录
      4. 模型信息的提取由用户在对话中让 AI 从全文中人工提取

    注意：本函数不返回 Excel 行数据（不内置 LLM 提取）。
    返回空列表，但会打印抓取状态供用户确认后手动触发 AI 提取。
    """
    print("\n📡 数据源: 腾讯研究院（搜狐号）")
    print("=" * 50)

    tag = f"{since_int}-{until_int}"
    json_path = TX_DIR / f"articles_{tag}.json"
    crawl_script = ROOT / "Crawl" / "TXresearch" / "crawl_sohu.py"
    articles_dir = ROOT / "Extract" / "articles"

    # ── 第一步：获取文章（自动爬取 or 已有缓存）──
    if json_path.exists():
        print(f"  📂 已有抓取缓存: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        print(f"  📄 共 {len(articles)} 篇文章")
    elif crawl_script.exists():
        # 自动调用 crawl_sohu.py（需要 Chrome + Selenium）
        print(f"  🚀 自动启动爬虫: crawl_sohu.py --since {since_int} --until {until_int}")
        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(crawl_script),
                 "--since", str(since_int), "--until", str(until_int)],
                cwd=str(crawl_script.parent),
                encoding="utf-8", errors="replace",
                timeout=600,
            )
            if result.returncode == 0:
                print(f"  ✅ 爬虫完成")
                # 爬虫输出到 TXresearch/ 目录，检查 JSON
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        articles = json.load(f)
                    print(f"  📄 共 {len(articles)} 篇文章")
                else:
                    # 爬虫可能输出到 crawl_script.parent 目录
                    alt_json = crawl_script.parent / f"articles_{tag}.json"
                    if alt_json.exists():
                        # 复制到标准位置
                        TX_DIR.mkdir(parents=True, exist_ok=True)
                        import shutil
                        shutil.copy2(alt_json, json_path)
                        with open(json_path, "r", encoding="utf-8") as f:
                            articles = json.load(f)
                        print(f"  📄 共 {len(articles)} 篇文章（从爬虫输出目录复制）")
                    else:
                        print(f"  ⚠️ 爬虫运行成功但未找到输出 JSON")
                        articles = []
            else:
                print(f"  ⚠️ 爬虫失败（退出码 {result.returncode}），尝试使用已有文章缓存")
                print(f"  💡 手动运行：cd Crawl\\TXresearch && python crawl_sohu.py --since {since_int} --until {until_int}")
                # Graceful fallback：检查 articles 目录是否已有文章
                articles = []
        except subprocess.TimeoutExpired:
            print(f"  ⏰ 爬虫超时（600秒），尝试使用已有文章缓存")
            articles = []
        except Exception as exc:
            print(f"  ⚠️ 爬虫启动失败: {exc}，尝试使用已有文章缓存")
            articles = []
    else:
        print(f"  ⚠️ 未找到爬虫脚本: {crawl_script}")
        print(f"  ⚠️ 也未找到缓存: {json_path}")
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
        choices=["all", "llmstats", "txresearch"],
        help="数据源 (默认 all)",
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

    # 1. llmstats
    if args.source in ("all", "llmstats"):
        llmstats_rows = collect_llmstats(since_int, until_int)
        llmstats_unique = deduplicate_rows(llmstats_rows, existing_names)
        print(f"  去重后: {len(llmstats_unique)}/{len(llmstats_rows)} 条")
        all_new_rows.extend(llmstats_unique)

    # 2. 腾讯研究院
    if args.source in ("all", "txresearch"):
        tx_rows = collect_txresearch(since_int, until_int)
        tx_unique = deduplicate_rows(tx_rows, existing_names)
        print(f"  去重后: {len(tx_unique)}/{len(tx_rows)} 条")
        all_new_rows.extend(tx_unique)

    # 3. HuggingFace 核实（对开源模型自动验证）
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
