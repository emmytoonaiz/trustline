import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app import db

ALERT_RETENTION_DAYS = 14
_CACHE_SECONDS = 30
_cache: dict[int, tuple[float, db.MonitoredChat | None]] = {}


def _forget(tg_chat_id: int) -> None:
    _cache.pop(tg_chat_id, None)


def get_active_chat(tg_chat_id: int) -> db.MonitoredChat | None:
    """Looked up for every group message, so remembered briefly instead of hitting the database."""
    hit = _cache.get(tg_chat_id)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    with db.session() as s:
        row = s.execute(
            select(db.MonitoredChat).where(db.MonitoredChat.tg_chat_id == tg_chat_id, db.MonitoredChat.active.is_(True))
        ).scalar_one_or_none()
    _cache[tg_chat_id] = (time.monotonic() + _CACHE_SECONDS, row)
    return row


def start_monitoring(tg_chat_id: int, title: str, owner_user_id: int, language: str, can_delete: bool) -> db.MonitoredChat:
    """Switch monitoring on. The person who added the bot stays the owner while monitoring continues;
    after it was switched off, whoever adds the bot again becomes the owner."""
    with db.session() as s:
        row = s.execute(select(db.MonitoredChat).where(db.MonitoredChat.tg_chat_id == tg_chat_id)).scalar_one_or_none()
        if row is None:
            row = db.MonitoredChat(
                tg_chat_id=tg_chat_id, title=title[:200], owner_user_id=owner_user_id, owner_language=language, can_delete=can_delete
            )
            s.add(row)
        else:
            if not row.active:
                row.owner_user_id = owner_user_id
                row.owner_language = language
            row.title = title[:200]
            row.can_delete = can_delete
            row.active = True
        s.flush()
    _forget(tg_chat_id)
    return row


def stop_monitoring(tg_chat_id: int) -> None:
    with db.session() as s:
        row = s.execute(select(db.MonitoredChat).where(db.MonitoredChat.tg_chat_id == tg_chat_id)).scalar_one_or_none()
        if row:
            row.active = False
    _forget(tg_chat_id)


def create_alert(chat: db.MonitoredChat, tg_message_id: int, sender_label: str, excerpt: str, category: str, confidence: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ALERT_RETENTION_DAYS)
    alert_id = secrets.token_urlsafe(6)
    with db.session() as s:
        s.execute(delete(db.MonitorAlert).where(db.MonitorAlert.created_at < cutoff))
        s.add(
            db.MonitorAlert(
                id=alert_id,
                chat_id=chat.id,
                tg_message_id=tg_message_id,
                sender_label=sender_label[:200],
                excerpt=excerpt[:500],
                category=category[:120],
                confidence=confidence,
            )
        )
        row = s.get(db.MonitoredChat, chat.id)
        if row:
            row.alerts_sent += 1
    return alert_id


def get_alert(alert_id: str) -> tuple[db.MonitorAlert, db.MonitoredChat] | None:
    with db.session() as s:
        alert = s.get(db.MonitorAlert, alert_id)
        if alert is None:
            return None
        return alert, s.get(db.MonitoredChat, alert.chat_id)


def set_alert_status(alert_id: str, status: str) -> None:
    with db.session() as s:
        alert = s.get(db.MonitorAlert, alert_id)
        if alert:
            alert.status = status
