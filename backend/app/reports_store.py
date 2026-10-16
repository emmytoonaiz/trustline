import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app import db

# Optional demo numbers so a brand-new deployment's stats panel isn't empty.
# Off by default: the panel should only ever show reports people really made.
_DEMO_SEED = {
    "OTP / PIN request": 41,
    "Fake bank/wallet alert": 37,
    "Fake instant loan app": 22,
    "Investment / crypto scam": 18,
    "Lottery / prize scam": 15,
}


def add_report(message: str, category: str | None, location: str | None, source: str = "web") -> int:
    with db.session() as s:
        row = db.ScamReport(
            category=category or "Uncategorized",
            source=source,
            message_excerpt=message[:1000],
            location=location,
        )
        s.add(row)
        s.flush()
        return row.id


def get_stats(days: int = 7) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with db.session() as s:
        rows = s.execute(
            select(db.ScamReport.category, func.count())
            .where(db.ScamReport.created_at >= since)
            .group_by(db.ScamReport.category)
        ).all()
    counts = {category: n for category, n in rows}

    if os.getenv("DEMO_SEED_STATS", "").lower() in ("1", "true", "yes"):
        for category, n in _DEMO_SEED.items():
            counts[category] = counts.get(category, 0) + n

    top = sorted(
        ({"category": k, "count": v} for k, v in counts.items()),
        key=lambda x: x["count"],
        reverse=True,
    )[:5]
    return {"total_reports": sum(counts.values()), "top_categories": top}
