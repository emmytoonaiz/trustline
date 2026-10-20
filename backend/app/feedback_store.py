from sqlalchemy import select

from app import db, visits_store


def add(message: str, rating: int | None, contact: str | None, wants_pilot: bool, ref: str | None, language: str) -> int:
    with db.session() as s:
        row = db.Feedback(
            message=message.strip()[:2000],
            rating=rating,
            contact=(contact or "").strip()[:200] or None,
            wants_pilot=wants_pilot,
            ref=visits_store.clean_ref(ref),
            language=language[:8],
        )
        s.add(row)
        s.flush()
        return row.id


def latest(limit: int = 50) -> list[dict]:
    with db.session() as s:
        rows = s.execute(select(db.Feedback).order_by(db.Feedback.created_at.desc()).limit(limit)).scalars().all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "rating": r.rating,
                "message": r.message,
                "contact": r.contact,
                "wants_pilot": r.wants_pilot,
                "ref": r.ref,
                "language": r.language,
            }
            for r in rows
        ]
