import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app import db

ALERT_RETENTION_DAYS = 14


def link_account(ig_user_id: str, username: str, owner_user_id: int, language: str) -> db.InstagramLink:
    """Pairing is protected by a code, so whoever holds it may (re)assign who receives alerts."""
    with db.session() as s:
        row = s.execute(select(db.InstagramLink).where(db.InstagramLink.ig_user_id == ig_user_id)).scalar_one_or_none()
        if row is None:
            row = db.InstagramLink(ig_user_id=ig_user_id, username=username[:64], owner_user_id=owner_user_id, owner_language=language)
            s.add(row)
        else:
            row.username = username[:64]
            row.owner_user_id = owner_user_id
            row.owner_language = language
            row.active = True
        s.flush()
    return row


def get_link(ig_user_id: str) -> db.InstagramLink | None:
    with db.session() as s:
        return s.execute(
            select(db.InstagramLink).where(db.InstagramLink.ig_user_id == ig_user_id, db.InstagramLink.active.is_(True))
        ).scalar_one_or_none()


def active_links() -> list[db.InstagramLink]:
    with db.session() as s:
        return list(s.execute(select(db.InstagramLink).where(db.InstagramLink.active.is_(True))).scalars())


def set_last_polled(link_id: int, when: datetime) -> None:
    with db.session() as s:
        row = s.get(db.InstagramLink, link_id)
        if row:
            row.last_polled_at = when


def create_alert(link: db.InstagramLink, comment_id: str, sender_label: str, excerpt: str, category: str, confidence: int) -> str | None:
    """None when this comment already produced an alert (webhook and polling can both see it)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ALERT_RETENTION_DAYS)
    alert_id = secrets.token_urlsafe(6)
    try:
        with db.session() as s:
            s.execute(delete(db.InstagramAlert).where(db.InstagramAlert.created_at < cutoff))
            if s.execute(select(db.InstagramAlert.id).where(db.InstagramAlert.comment_id == comment_id)).first():
                return None
            s.add(
                db.InstagramAlert(
                    id=alert_id,
                    link_id=link.id,
                    comment_id=comment_id,
                    sender_label=sender_label[:200],
                    excerpt=excerpt[:500],
                    category=category[:120],
                    confidence=confidence,
                )
            )
    except IntegrityError:
        return None
    return alert_id


def get_alert(alert_id: str) -> tuple[db.InstagramAlert, db.InstagramLink] | None:
    with db.session() as s:
        alert = s.get(db.InstagramAlert, alert_id)
        if alert is None:
            return None
        return alert, s.get(db.InstagramLink, alert.link_id)


def set_alert_status(alert_id: str, status: str) -> None:
    with db.session() as s:
        alert = s.get(db.InstagramAlert, alert_id)
        if alert:
            alert.status = status
