import json
import threading
from pathlib import Path

STORE_PATH = Path(__file__).parent / "data" / "reports_store.json"
_lock = threading.Lock()

# Seed counts so the community-stats panel isn't empty on a fresh demo checkout.
_SEED_CATEGORIES = {
    "OTP / PIN request": 41,
    "Fake bank/wallet alert": 37,
    "Fake instant loan app": 22,
    "Investment / crypto scam": 18,
    "Lottery / prize scam": 15,
}


def _load() -> dict:
    if not STORE_PATH.exists():
        return {"reports": [], "seed_categories": _SEED_CATEGORIES}
    with open(STORE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_report(message: str, category: str | None, location: str | None) -> int:
    with _lock:
        data = _load()
        new_id = len(data["reports"]) + 1
        data["reports"].append(
            {
                "id": new_id,
                "message": message,
                "category": category or "Uncategorized",
                "location": location,
            }
        )
        _save(data)
        return new_id


def get_stats() -> dict:
    data = _load()
    counts = dict(data.get("seed_categories", _SEED_CATEGORIES))
    for r in data["reports"]:
        counts[r["category"]] = counts.get(r["category"], 0) + 1

    top = sorted(
        ({"category": k, "count": v} for k, v in counts.items()),
        key=lambda x: x["count"],
        reverse=True,
    )[:5]

    return {
        "total_reports": sum(counts.values()),
        "top_categories": top,
    }
