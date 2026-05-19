# 2026/05/19/14:49
# name: generate_site_data
# description: 从总表生成静态站所需的 JSON 数据文件，供 GitHub Pages 前端展示日报和仪表盘

"""
从 Object-Models.xlsx 总表生成前端展示所需的 JSON 数据。

输出到 docs/data/ 目录：
  - daily_report.json   — 最新日报数据（按发布时间筛选）
  - dashboard.json      — 仪表盘统计数据（趋势、分布等）
  - all_models.json     — 全量模型数据（供前端搜索/筛选/排序交互表格）
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
DOCS_DIR = ROOT.parent / "docs"
DATA_DIR = DOCS_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"


def load_master_table() -> pd.DataFrame:
    """加载总表。"""
    if not EXCEL_PATH.exists():
        print(f"[ERROR] master table not found: {EXCEL_PATH}")
        return pd.DataFrame()
    return pd.read_excel(EXCEL_PATH, engine="openpyxl")


def generate_daily_report(dataframe: pd.DataFrame, since: str, until: str) -> dict:
    """生成日报 JSON 数据。"""
    since_dash = f"{since[:4]}-{since[4:6]}-{since[6:8]}"
    until_dash = f"{until[:4]}-{until[4:6]}-{until[6:8]}"

    if "模型发布时间" not in dataframe.columns:
        return {"models": [], "meta": {"since": since_dash, "until": until_dash, "count": 0}}

    date_col = dataframe["模型发布时间"].astype(str)
    mask = (date_col >= since_dash) & (date_col <= until_dash + "z")
    filtered = dataframe[mask].copy()

    models = []
    for _, row in filtered.iterrows():
        models.append({
            "name": str(row.get("模型名称", "")),
            "company": str(row.get("公司", "")),
            "domestic": str(row.get("国内外", "")),
            "open_source": str(row.get("开闭源", "")),
            "size": str(row.get("尺寸", "")),
            "type": str(row.get("类型", "")),
            "reasoning": str(row.get("能否推理", "")),
            "release_date": str(row.get("模型发布时间", "")),
            "note": str(row.get("备注", "")),
            "website": str(row.get("官网", "")),
        })

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

    # 3. 全量模型数据（供前端交互式表格）
    all_models_list = []
    for _, row in dataframe.iterrows():
        all_models_list.append({
            "name": str(row.get("模型名称", "")),
            "company": str(row.get("公司", "")),
            "domestic": str(row.get("国内外", "")),
            "open_source": str(row.get("开闭源", "")),
            "size": str(row.get("尺寸", "")),
            "type": str(row.get("类型", "")),
            "reasoning": str(row.get("能否推理", "")),
            "release_date": str(row.get("模型发布时间", "")),
            "created_date": str(row.get("记录创建时间", "")),
            "note": str(row.get("备注", "")),
            "website": str(row.get("官网", "")),
            "status": str(row.get("核实情况", "")),
        })

    all_models_data = {
        "models": all_models_list,
        "meta": {
            "total": len(all_models_list),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
    all_models_path = DATA_DIR / "all_models.json"
    with open(all_models_path, "w", encoding="utf-8") as f:
        json.dump(all_models_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] all_models: {all_models_path.name} ({len(all_models_list)} models)")


if __name__ == "__main__":
    main()
