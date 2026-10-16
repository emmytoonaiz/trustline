import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app import db

RETENTION_DAYS = 90
_REF = re.compile(r"^[a-z0-9_-]{1,24}$")


def clean_ref(raw: str | None) -> str:
    """Only short, plain labels (tiktok, x, friend1) are kept; anything else counts as direct."""
    ref = (raw or "").strip().lower()
    return ref if _REF.match(ref) else "direct"


def record(ref: str | None) -> None:
    """Counts a visit. No IP, no cookie, no identifier: just which link brought it."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    with db.session() as s:
        s.execute(delete(db.SiteVisit).where(db.SiteVisit.created_at < cutoff))
        s.add(db.SiteVisit(ref=clean_ref(ref)))


def counts(days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with db.session() as s:
        rows = s.execute(
            select(db.SiteVisit.ref, func.count()).where(db.SiteVisit.created_at >= since).group_by(db.SiteVisit.ref)
        ).all()
    by_ref = {ref: n for ref, n in sorted(rows, key=lambda r: -r[1])}
    return {"days": days, "total": sum(by_ref.values()), "by_ref": by_ref}
