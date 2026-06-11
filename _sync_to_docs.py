"""临时脚本：将 LLM 提取的新模型同步到 docs/data/all_models.json 和 daily_report.json"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
EXTRACTED = ROOT / "Model_Navigate" / "Extract" / "extracted_models_llm.json"
ALL_MODELS = ROOT / "docs" / "data" / "all_models.json"
DAILY_REPORT = ROOT / "docs" / "data" / "daily_report.json"

today = datetime.now().strftime("%Y-%m-%d")

# 1. Load extracted models
with open(EXTRACTED, "r", encoding="utf-8") as f:
    extracted = json.load(f)

# 2. Load all_models.json
with open(ALL_MODELS, "r", encoding="utf-8") as f:
    all_data = json.load(f)

existing_names = set()
for m in all_data["models"]:
    existing_names.add(m.get("name", "").strip().lower())

# 3. Map and deduplicate
new_models = []
for e in extracted:
    name = e.get("model_name", "").strip()
    if not name or name.lower() in existing_names:
        continue
    existing_names.add(name.lower())
    new_models.append({
        "name": name,
        "connected": "",
        "workflow_progress": "",
        "company": e.get("company", ""),
        "domestic": e.get("domestic", ""),
        "open_source": e.get("open_source", ""),
        "size": e.get("size", ""),
        "type": e.get("model_type", ""),
        "reasoning": e.get("can_reason", ""),
        "task_type": e.get("task_type", ""),
        "website": e.get("website", ""),
        "note": e.get("brief", ""),
        "release_date": e.get("release_date", ""),
        "created_date": today,
        "data_source": "txresearch",
    })

all_data["models"].extend(new_models)
all_data["meta"]["total"] = len(all_data["models"])
all_data["meta"]["last_updated"] = today

with open(ALL_MODELS, "w", encoding="utf-8") as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)

print(f"Added {len(new_models)} new models to all_models.json")
print(f"Total now: {len(all_data['models'])}")

# 4. Update daily_report.json
with open(DAILY_REPORT, "r", encoding="utf-8") as f:
    dr = json.load(f)

dr_existing = set(m.get("name", "").lower() for m in dr.get("models", []))
dr_new = []
for m in new_models:
    if m["name"].lower() not in dr_existing:
        dr_new.append({
            "name": m["name"],
            "company": m["company"],
            "domestic": m["domestic"],
            "type": m["type"],
            "release_date": m["release_date"],
            "created_date": today,
            "note": m["note"],
            "data_source": "txresearch",
        })

dr["models"].extend(dr_new)
dr["meta"] = dr.get("meta", {})
dr["meta"]["last_updated"] = today

with open(DAILY_REPORT, "w", encoding="utf-8") as f:
    json.dump(dr, f, ensure_ascii=False, indent=2)

print(f"Added {len(dr_new)} models to daily_report.json")
