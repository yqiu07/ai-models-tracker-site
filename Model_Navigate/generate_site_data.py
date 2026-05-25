# Re 2026/05/19/18:01
# name: generate_site_data
# description: 从总表生成静态站所需的 JSON 数据文件，供 GitHub Pages 前端展示日报和仪表盘

"""
从 Object-Models.xlsx 总表生成前端展示所需的 JSON 数据。

输出到 docs/data/ 目录：
  - daily_report.json     — 最新日报数据（按发布时间筛选）
  - dashboard.json        — 仪表盘统计数据（趋势、分布等）
  - all_models.json       — 全量模型数据（含所有Excel列，供前端交互表格）
  - history_index.json    — 历史日报文件列表（供前端切换）
  - site_meta.json        — 站点元信息（数据源列表、README内容等）
  - history/YYYYMMDD.json — 历史日报归档

用法:
    python generate_site_data.py --since 20260518 --until 20260519
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
EXCEL_PATH = ROOT / "data" / "Object-Models.xlsx"
README_PATH = ROOT.parent / "README.md"
DOCS_DIR = ROOT.parent / "docs"
DATA_DIR = DOCS_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"

# 当前启用的数据源（与 auto_collect.py 同步维护）
ACTIVE_DATA_SOURCES = [
    {
        "name": "llm-stats.com",
        "url": "https://llm-stats.com",
        "status": "active",
        "description": "HTTP 直连 + Next.js RSC JSON 解析，有可靠时间戳",
        "sub_sources": [
            {"name": "llm-stats-LLM.com", "url": "https://llm-stats.com", "description": "主站 LLM 模型列表"},
            {"name": "llm-stats-ai.com", "url": "https://ai.llm-stats.com", "description": "AI 综合模型数据"},
            {"name": "llm-stats-open-llm.com", "url": "https://open-llm.llm-stats.com", "description": "开源 LLM 排行"},
            {"name": "llm-stats-updates.com", "url": "https://updates.llm-stats.com", "description": "模型更新动态"},
        ],
    },
    {
        "name": "腾讯研究院AI速递",
        "url": "https://mp.sohu.com/profile?xpt=bGl1amluc29uZzIwMDBAMTI2LmNvbQ==",
        "status": "active",
        "description": "双模式爬虫 + LLM 提取，文章自带日期天然时间锚定",
    },
    {
        "name": "HuggingFace",
        "url": "https://huggingface.co",
        "status": "active",
        "description": "API createdAt 字段精确到秒，时间过滤可靠",
    },
    {
        "name": "平台模型目录（12平台）",
        "url": "",
        "status": "suspended",
        "description": "灌入旧模型根因未解决（created=0 + LLM降级查错）",
        "sub_sources": [
            {"name": "火山引擎（字节/豆包）", "url": "https://ark.cn-beijing.volces.com/api/v3"},
            {"name": "OpenRouter（聚合平台）", "url": "https://openrouter.ai/api/v1"},
            {"name": "Moonshot / Kimi", "url": "https://api.moonshot.cn/v1"},
            {"name": "智谱 BigModel（GLM）", "url": "https://open.bigmodel.cn/api/paas/v4"},
            {"name": "MiniMax（海螺AI）", "url": "https://api.minimaxi.com/v1"},
            {"name": "MIMO（小米）", "url": "https://api.xiaomimimo.com/v1"},
            {"name": "百度千帆（ERNIE）", "url": "https://qianfan.baidubce.com"},
            {"name": "硅基流动 SiliconFlow", "url": "https://api.siliconflow.cn/v1"},
            {"name": "DeepSeek 官方", "url": "https://api.deepseek.com"},
            {"name": "阶跃星辰 StepFun", "url": "https://api.stepfun.com/v1"},
            {"name": "DashScope（通义千问）", "url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
            {"name": "腾讯混元", "url": "https://api.hunyuan.cloud.tencent.com/v1"},
        ],
    },
    {
        "name": "LM Arena 排行榜",
        "url": "https://lmarena.ai",
        "status": "suspended",
        "description": "排行榜无发布时间，全量灌入无法过滤",
    },
]


def _clean_value(value) -> str:
    """将 pandas 单元格值转为干净的字符串（处理 NaN、NaT、None）。"""
    if value is None:
        return ""
    s = str(value)
    if s in ("nan", "NaN", "NaT", "None", "nat"):
        return ""
    return s.strip()


def _normalize_date(value) -> str:
    """将日期值统一为 YYYY-MM-DD 格式（去掉时间部分）。"""
    if value is None:
        return ""
    # pandas NaT
    if pd.isna(value):
        return ""
    # pandas Timestamp / datetime
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if s in ("nan", "NaN", "NaT", "None", "nat", ""):
        return ""
    # 已经是 YYYY-MM-DD 格式
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # YYYY-MM-DD HH:MM:SS 格式，截取日期部分
    if re.match(r"^\d{4}-\d{2}-\d{2}\s", s):
        return s[:10]
    # 尝试解析其他格式
    try:
        dt = pd.to_datetime(s)
        if pd.notna(dt):
            return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    return s


def load_master_table() -> pd.DataFrame:
    """加载总表。"""
    if not EXCEL_PATH.exists():
        print(f"[ERROR] master table not found: {EXCEL_PATH}")
        return pd.DataFrame()
    return pd.read_excel(EXCEL_PATH, engine="openpyxl")


def _row_to_model(row) -> dict:
    """将 DataFrame 行转为标准模型字典（14列，去掉是否新增和核实情况）。"""
    return {
        "name": _clean_value(row.get("模型名称")),
        "connected": _clean_value(row.get("是否接入")),
        "workflow_progress": _clean_value(row.get("workflow接入进展")),
        "company": _clean_value(row.get("公司")),
        "domestic": _clean_value(row.get("国内外")),
        "open_source": _clean_value(row.get("开闭源")),
        "size": _clean_value(row.get("尺寸")),
        "type": _clean_value(row.get("类型")),
        "reasoning": _clean_value(row.get("能否推理")),
        "task_type": _clean_value(row.get("任务类型")),
        "website": _clean_value(row.get("官网")),
        "note": _clean_value(row.get("备注")),
        "release_date": _normalize_date(row.get("模型发布时间")),
        "created_date": _normalize_date(row.get("记录创建时间")),
    }


def generate_daily_report(dataframe: pd.DataFrame, since: str, until: str) -> dict:
    """生成日报 JSON 数据。"""
    since_dash = f"{since[:4]}-{since[4:6]}-{since[6:8]}"
    until_dash = f"{until[:4]}-{until[4:6]}-{until[6:8]}"

    if "模型发布时间" not in dataframe.columns:
        return {"models": [], "meta": {"since": since_dash, "until": until_dash, "count": 0}}

    # 统一日期格式后再筛选
    normalized_dates = dataframe["模型发布时间"].apply(_normalize_date)
    mask = (normalized_dates >= since_dash) & (normalized_dates <= until_dash)
    filtered = dataframe[mask].copy()

    models = [_row_to_model(row) for _, row in filtered.iterrows()]

    return {
        "models": models,
        "meta": {
            "since": since_dash,
            "until": until_dash,
            "count": len(models),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def generate_dashboard(dataframe: pd.DataFrame) -> dict:
    """生成仪表盘统计 JSON 数据。"""
    total = len(dataframe)
    if total == 0:
        return {"total": 0, "by_type": {}, "by_domestic": {}, "by_open_source": {}, "trend": []}

    by_type = Counter(dataframe.get("类型", pd.Series(dtype=str)).fillna("未知"))
    by_domestic = Counter(dataframe.get("国内外", pd.Series(dtype=str)).fillna("未知"))
    by_open_source = Counter(dataframe.get("开闭源", pd.Series(dtype=str)).fillna("未知"))

    # 按月趋势（模型发布时间）
    trend = []
    if "模型发布时间" in dataframe.columns:
        dates = pd.to_datetime(dataframe["模型发布时间"], errors="coerce")
        monthly = dates.dt.to_period("M").value_counts().sort_index()
        for period, count in monthly.items():
            if pd.notna(period):
                trend.append({"month": str(period), "count": int(count)})

    # 最近7天新增
    recent_count = 0
    if "记录创建时间" in dataframe.columns:
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        created_col = dataframe["记录创建时间"].astype(str)
        recent_count = int(((created_col >= week_ago) & (created_col <= today + "z")).sum())

    return {
        "total": total,
        "recent_7d": recent_count,
        "by_type": dict(by_type.most_common()),
        "by_domestic": dict(by_domestic),
        "by_open_source": dict(by_open_source),
        "trend": trend,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    parser = argparse.ArgumentParser(description="生成静态站 JSON 数据")
    parser.add_argument("--since", required=True, help="起始日期 YYYYMMDD")
    parser.add_argument("--until", required=True, help="截止日期 YYYYMMDD")
    args = parser.parse_args()

    # 确保目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # 加载总表
    dataframe = load_master_table()
    if dataframe.empty:
        print("[WARN] master table is empty, generating empty data")

    # 1. 日报
    report = generate_daily_report(dataframe, args.since, args.until)
    report_path = DATA_DIR / "daily_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] daily_report: {report_path.name} ({report['meta']['count']} models)")

    # 归档历史
    history_path = HISTORY_DIR / f"{args.since}_{args.until}.json"
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] history: {history_path.name}")

    # 2. 仪表盘
    dashboard = generate_dashboard(dataframe)
    dashboard_path = DATA_DIR / "dashboard.json"
    with open(dashboard_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    print(f"[OK] dashboard: {dashboard_path.name} (total {dashboard['total']} models)")

    # 3. 全量模型数据（含所有 Excel 列，供前端交互式表格）
    # 读取回收站文件，排除其中的模型
    recycle_path = DATA_DIR / "recycle.json"
    recycled_names = set()
    if recycle_path.exists():
        with open(recycle_path, "r", encoding="utf-8") as f:
            recycle_data = json.load(f)
            for item in recycle_data.get("models", []):
                recycled_names.add(item.get("name", ""))

    all_models_list = [_row_to_model(row) for _, row in dataframe.iterrows()]
    # 过滤掉回收站中的模型
    active_models = [m for m in all_models_list if m.get("name", "") not in recycled_names]
    all_models_data = {
        "models": active_models,
        "meta": {
            "total": len(active_models),
            "recycled": len(recycled_names),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
    all_models_path = DATA_DIR / "all_models.json"
    with open(all_models_path, "w", encoding="utf-8") as f:
        json.dump(all_models_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] all_models: {all_models_path.name} ({len(active_models)} models, {len(recycled_names)} recycled)")

    # 3.5 接入站数据（workflow接入进展=1 的模型）
    connected_path = DATA_DIR / "connected.json"
    # 如果 connected.json 已存在且有手动维护的数据，保留它；否则从 Excel 生成
    if not connected_path.exists():
        connected_models = [m for m in all_models_list if m.get("workflow_progress") == "1.0" or m.get("workflow_progress") == "1"]
        connected_data = {
            "models": connected_models,
            "meta": {
                "total": len(connected_models),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
        with open(connected_path, "w", encoding="utf-8") as f:
            json.dump(connected_data, f, ensure_ascii=False, indent=2)
        print(f"[OK] connected: {connected_path.name} ({len(connected_models)} models, initial generation)")
    else:
        print(f"[SKIP] connected: {connected_path.name} already exists (manually maintained)")

    # 4. 历史日报索引
    # 同步 Report/ 下的 JSON 日报到 history/
    report_dir = ROOT / "Report"
    if report_dir.exists():
        import shutil
        for rpt_file in report_dir.glob("*.json"):
            if rpt_file.name == "review_results.json":
                continue
            dest = HISTORY_DIR / rpt_file.name
            if not dest.exists():
                shutil.copy2(rpt_file, dest)
                print(f"[OK] synced Report/{rpt_file.name} -> history/")

    # 列出 history/ 下所有 JSON 文件供前端切换
    history_files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    history_index = []
    for hf in history_files:
        if hf.name == ".gitkeep":
            continue
        stem = hf.stem
        parts = stem.split("_")
        if len(parts) == 2:
            since_str = f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]}"
            until_str = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}"
            history_index.append({
                "file": f"history/{hf.name}",
                "since": since_str,
                "until": until_str,
                "label": f"{since_str} ~ {until_str}",
            })

    # 同时扫描 Report/ 下的 daily_report_*.md，复制到 history/ 并加入索引
    if report_dir.exists():
        import shutil as _shutil
        for md_file in sorted(report_dir.glob("daily_report_*.md"), reverse=True):
            match = re.search(r"daily_report_(\d{8})-(\d{8})", md_file.name)
            if match:
                s, u = match.group(1), match.group(2)
                since_str = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
                until_str = f"{u[:4]}-{u[4:6]}-{u[6:8]}"
                label = f"{since_str} ~ {until_str}"
                # 复制到 history/ 目录
                dest = HISTORY_DIR / md_file.name
                if not dest.exists():
                    _shutil.copy2(md_file, dest)
                # 避免重复
                if not any(h["label"] == label for h in history_index):
                    history_index.append({
                        "file": f"history/{md_file.name}",
                        "since": since_str,
                        "until": until_str,
                        "label": label,
                        "format": "md",
                    })

    # 按 since 降序排列
    history_index.sort(key=lambda x: x.get("since", ""), reverse=True)

    history_index_path = DATA_DIR / "history_index.json"
    with open(history_index_path, "w", encoding="utf-8") as f:
        json.dump(history_index, f, ensure_ascii=False, indent=2)
    print(f"[OK] history_index: {history_index_path.name} ({len(history_index)} entries)")

    # 5. 站点元信息（数据源列表 + README 内容）
    readme_content = ""
    if README_PATH.exists():
        readme_content = README_PATH.read_text(encoding="utf-8")

    site_meta = {
        "data_sources": ACTIVE_DATA_SOURCES,
        "readme": readme_content,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    site_meta_path = DATA_DIR / "site_meta.json"
    with open(site_meta_path, "w", encoding="utf-8") as f:
        json.dump(site_meta, f, ensure_ascii=False, indent=2)
    print(f"[OK] site_meta: {site_meta_path.name} (readme {len(readme_content)} chars)")


if __name__ == "__main__":
    main()
