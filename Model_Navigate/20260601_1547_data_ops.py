# 2026/06/01/15:47
# name: data_ops_actions_proxy
# description: GitHub Actions 数据操作代理；接收前端操作意图，在仓库内修改 JSON 并提交，避免 GitHub Pages 前端直写 Contents API
# prompt: 用户确认将删除/恢复/同步等写仓库动作迁移到 GitHub Actions 代理，解决浏览器直连 api.github.com 导致删除失败的问题。

"""
GitHub Actions 数据操作代理。

支持操作：
- delete_model: 从总表/日报删除模型并放入回收站
- restore_model: 从回收站恢复模型
- purge_recycle: 从回收站彻底清除模型
- sync_daily_to_all: 从日报/历史日报同步到总表，并按模型名称唯一化
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DOCS_DATA_DIR = ROOT.parent / "docs" / "data"
ALL_MODELS_PATH = DOCS_DATA_DIR / "all_models.json"
RECYCLE_PATH = DOCS_DATA_DIR / "recycle.json"
DAILY_REPORT_PATH = DOCS_DATA_DIR / "daily_report.json"
HISTORY_INDEX_PATH = DOCS_DATA_DIR / "history_index.json"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        print(f"[WARN] Skip invalid JSON file: {path} ({error})")
        return default


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def normalize_model_key(model: dict[str, Any] | str) -> str:
    name = model if isinstance(model, str) else model.get("name", "")
    return re.sub(r"[\s\-_:/（）()【】\[\]]+", "", str(name).strip().lower())


def is_same_model(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = normalize_model_key(left)
    right_key = normalize_model_key(right)
    if not left_key or left_key != right_key:
        return False
    left_company = str(left.get("company", "")).strip().lower()
    right_company = str(right.get("company", "")).strip().lower()
    return not left_company or not right_company or left_company == right_company


def strip_recycle_meta(model: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in model.items()
        if key not in {"source", "source_path", "deleted_at"}
    }


def update_meta(data: dict[str, Any], models_key: str = "models") -> None:
    data.setdefault("meta", {})
    data["meta"]["total"] = len(data.get(models_key, []))
    data["meta"]["count"] = len(data.get(models_key, []))
    data["meta"]["updated_at"] = now_text()


def resolve_data_path(path_text: str) -> Path:
    if not path_text:
        return DAILY_REPORT_PATH
    normalized = path_text.replace("\\", "/")
    if normalized.startswith("docs/data/"):
        return ROOT.parent / normalized
    if normalized.startswith("data/"):
        return DOCS_DATA_DIR / normalized.removeprefix("data/")
    return ROOT.parent / normalized


def deduplicate_models(models: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    unique_models: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}
    duplicate_count = 0
    for model in models:
        model_key = normalize_model_key(model)
        if not model_key:
            continue
        if model_key in key_to_index:
            unique_models[key_to_index[model_key]] = {
                **unique_models[key_to_index[model_key]],
                **model,
            }
            duplicate_count += 1
        else:
            key_to_index[model_key] = len(unique_models)
            unique_models.append(model)
    return unique_models, duplicate_count


def delete_model(model_name: str, source: str, source_path: str) -> None:
    target_model = {"name": model_name}
    all_data = load_json(ALL_MODELS_PATH, {"models": [], "meta": {}})
    recycle_data = load_json(RECYCLE_PATH, {"models": [], "meta": {}})

    removed_models: list[dict[str, Any]] = []
    kept_all_models = []
    for model in all_data.get("models", []):
        if is_same_model(model, target_model):
            removed_models.append(model)
        else:
            kept_all_models.append(model)
    all_data["models"] = kept_all_models

    if source == "daily":
        daily_path = resolve_data_path(source_path)
        daily_data = load_json(daily_path, {"models": [], "meta": {}})
        kept_daily_models = []
        for model in daily_data.get("models", []):
            if is_same_model(model, target_model):
                removed_models.append(model)
            else:
                kept_daily_models.append(model)
        daily_data["models"] = kept_daily_models
        update_meta(daily_data)
        save_json(daily_path, daily_data)

    if not removed_models:
        raise SystemExit(f"No model matched for deletion: {model_name}")

    recycle_models = recycle_data.setdefault("models", [])
    existing_recycle_keys = {normalize_model_key(model) for model in recycle_models}
    recycled_model = {**removed_models[0], "source": source, "deleted_at": now_text()}
    if source == "daily":
        recycled_model["source_path"] = source_path or "docs/data/daily_report.json"
    if normalize_model_key(recycled_model) not in existing_recycle_keys:
        recycle_models.append(recycled_model)

    update_meta(all_data)
    update_meta(recycle_data)
    save_json(ALL_MODELS_PATH, all_data)
    save_json(RECYCLE_PATH, recycle_data)
    print(f"[OK] Deleted {model_name} from {source}, moved to recycle")


def restore_model(model_name: str) -> None:
    all_data = load_json(ALL_MODELS_PATH, {"models": [], "meta": {}})
    recycle_data = load_json(RECYCLE_PATH, {"models": [], "meta": {}})
    recycle_models = recycle_data.get("models", [])

    target_index = next(
        (index for index, model in enumerate(recycle_models) if normalize_model_key(model) == normalize_model_key(model_name)),
        -1,
    )
    if target_index < 0:
        raise SystemExit(f"No model matched in recycle: {model_name}")

    recycled_model = recycle_models.pop(target_index)
    restored_model = strip_recycle_meta(recycled_model)

    all_models = all_data.setdefault("models", [])
    if not any(is_same_model(model, restored_model) for model in all_models):
        all_models.insert(0, restored_model)

    if recycled_model.get("source") == "daily":
        daily_path = resolve_data_path(str(recycled_model.get("source_path", "docs/data/daily_report.json")))
        daily_data = load_json(daily_path, {"models": [], "meta": {}})
        daily_models = daily_data.setdefault("models", [])
        if not any(is_same_model(model, restored_model) for model in daily_models):
            daily_models.insert(0, restored_model)
        update_meta(daily_data)
        save_json(daily_path, daily_data)

    update_meta(all_data)
    update_meta(recycle_data)
    save_json(ALL_MODELS_PATH, all_data)
    save_json(RECYCLE_PATH, recycle_data)
    print(f"[OK] Restored {model_name}")


def purge_recycle(model_name: str) -> None:
    recycle_data = load_json(RECYCLE_PATH, {"models": [], "meta": {}})
    before_count = len(recycle_data.get("models", []))
    recycle_data["models"] = [
        model for model in recycle_data.get("models", [])
        if normalize_model_key(model) != normalize_model_key(model_name)
    ]
    update_meta(recycle_data)
    save_json(RECYCLE_PATH, recycle_data)
    print(f"[OK] Purged {before_count - len(recycle_data['models'])} recycled model(s)")


def collect_daily_models(start_date: str, end_date: str) -> list[dict[str, Any]]:
    candidate_models: list[dict[str, Any]] = []
    daily_data = load_json(DAILY_REPORT_PATH, {"models": [], "meta": {}})
    candidate_models.extend(filter_models_by_date(daily_data.get("models", []), start_date, end_date))

    history_index = load_json(HISTORY_INDEX_PATH, []) if HISTORY_INDEX_PATH.exists() else []
    if isinstance(history_index, list):
        for entry in history_index:
            file_name = str(entry.get("file", ""))
            match = re.search(r"(\d{4})(\d{2})(\d{2})", file_name)
            if not match:
                continue
            file_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            if start_date <= file_date <= end_date:
                history_data = load_json(DOCS_DATA_DIR / file_name, {"models": [], "meta": {}})
                candidate_models.extend(history_data.get("models", []))
    return candidate_models


def filter_models_by_date(models: list[dict[str, Any]], start_date: str, end_date: str) -> list[dict[str, Any]]:
    filtered_models = []
    for model in models:
        model_date = str(model.get("created_date") or model.get("release_date") or "")[:10]
        if start_date <= model_date <= end_date:
            filtered_models.append(model)
    return filtered_models


def sync_daily_to_all(start_date: str, end_date: str) -> None:
    all_data = load_json(ALL_MODELS_PATH, {"models": [], "meta": {}})
    merged_models = list(all_data.get("models", []))
    key_to_index = {
        normalize_model_key(model): index
        for index, model in enumerate(merged_models)
        if normalize_model_key(model)
    }

    added_count = 0
    updated_count = 0
    for candidate_model in collect_daily_models(start_date, end_date):
        model_key = normalize_model_key(candidate_model)
        if not model_key:
            continue
        if model_key in key_to_index:
            merged_models[key_to_index[model_key]] = {
                **merged_models[key_to_index[model_key]],
                **candidate_model,
            }
            updated_count += 1
        else:
            key_to_index[model_key] = len(merged_models)
            merged_models.append(candidate_model)
            added_count += 1

    all_data["models"], duplicate_count = deduplicate_models(merged_models)
    update_meta(all_data)
    save_json(ALL_MODELS_PATH, all_data)
    print(f"[OK] Synced daily to all: added={added_count}, updated={updated_count}, duplicates={duplicate_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Actions data operation proxy")
    parser.add_argument("--operation", required=True, choices=["delete_model", "restore_model", "purge_recycle", "sync_daily_to_all"])
    parser.add_argument("--model-name", default="")
    parser.add_argument("--source", default="all", choices=["all", "daily"])
    parser.add_argument("--source-path", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    args = parser.parse_args()

    if args.operation == "delete_model":
        delete_model(args.model_name, args.source, args.source_path)
    elif args.operation == "restore_model":
        restore_model(args.model_name)
    elif args.operation == "purge_recycle":
        purge_recycle(args.model_name)
    elif args.operation == "sync_daily_to_all":
        if not args.start_date or not args.end_date:
            raise SystemExit("start-date and end-date are required for sync_daily_to_all")
        sync_daily_to_all(args.start_date, args.end_date)


if __name__ == "__main__":
    main()
