import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app import db

PENDING_TTL_HOURS = 24
ACCOUNT_REPORTS_PER_DAY = 20


def _salt() -> bytes:
    explicit = os.getenv("PRIVACY_SALT")
    if explicit:
        return explicit.encode()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    return hashlib.sha256(("trustline-salt:" + token).encode()).digest()


def hash_id(kind: str, value: int | str) -> str:
    """One-way, salted hash so we can recognise a returning user without storing their id."""
    return hmac.new(_salt(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


# ---- language preference -------------------------------------------------

def get_language(chat_hash: str) -> str | None:
    with db.session() as s:
        row = s.get(db.TelegramUser, chat_hash)
        return row.language if row else None


def set_language(chat_hash: str, language: str) -> None:
    with db.session() as s:
        row = s.get(db.TelegramUser, chat_hash)
        if row:
            row.language = language
            row.updated_at = datetime.now(timezone.utc)
        else:
            s.add(db.TelegramUser(chat_hash=chat_hash, language=language))


# ---- pending checks (so the Report buttons work) -------------------------

def create_pending(chat_hash: str, category: str, excerpt: str, account: dict | None) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_TTL_HOURS)
    pid = secrets.token_urlsafe(6)
    with db.session() as s:
        s.execute(delete(db.PendingCheck).where(db.PendingCheck.created_at < cutoff))
        s.add(
            db.PendingCheck(
                id=pid,
                chat_hash=chat_hash,
                category=category[:120],
                excerpt=excerpt[:1000],
                account_kind=account["kind"] if account else None,
                account_tg_id=account["tg_id"] if account else None,
                account_username=account.get("username") if account else None,
                account_name=account.get("name") if account else None,
            )
        )
    return pid


def get_pending(pid: str, chat_hash: str) -> db.PendingCheck | None:
    with db.session() as s:
        row = s.get(db.PendingCheck, pid)
        if row is None or row.chat_hash != chat_hash:
            return None
        return row


def mark_pending(pid: str, **flags) -> None:
    with db.session() as s:
        row = s.get(db.PendingCheck, pid)
        if row:
            for k, v in flags.items():
                setattr(row, k, v)


# ---- account-level reports ------------------------------------------------

def account_reporter_count(kind: str, tg_id: int) -> int:
    with db.session() as s:
        account = s.execute(
            select(db.ReportedAccount).where(
                db.ReportedAccount.kind == kind, db.ReportedAccount.tg_id == tg_id
            )
        ).scalar_one_or_none()
        if account is None:
            return 0
        return s.execute(
            select(func.count()).select_from(db.AccountReport).where(db.AccountReport.account_id == account.id)
        ).scalar_one()


def reporter_reports_today(reporter_hash: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    with db.session() as s:
        return s.execute(
            select(func.count())
            .select_from(db.AccountReport)
            .where(db.AccountReport.reporter_hash == reporter_hash, db.AccountReport.created_at >= since)
        ).scalar_one()


def report_account(
    kind: str,
    tg_id: int,
    username: str | None,
    name: str | None,
    reporter_hash: str,
    category: str,
) -> tuple[int, bool]:
    """Record one reporter's report. Returns (distinct reporters so far, was this report new)."""
    now = datetime.now(timezone.utc)
    with db.session() as s:
        account = s.execute(
            select(db.ReportedAccount).where(
                db.ReportedAccount.kind == kind, db.ReportedAccount.tg_id == tg_id
            )
        ).scalar_one_or_none()
        if account is None:
            account = db.ReportedAccount(kind=kind, tg_id=tg_id, username=username, display_name=name)
            s.add(account)
            s.flush()
        else:
            account.username = username or account.username
            account.display_name = name or account.display_name
            account.last_reported_at = now

        already = s.execute(
            select(db.AccountReport.id).where(
                db.AccountReport.account_id == account.id,
                db.AccountReport.reporter_hash == reporter_hash,
            )
        ).first()
        is_new = already is None
        if is_new:
            s.add(db.AccountReport(account_id=account.id, reporter_hash=reporter_hash, category=category[:120]))
            s.flush()

        total = s.execute(
            select(func.count()).select_from(db.AccountReport).where(db.AccountReport.account_id == account.id)
        ).scalar_one()
        return total, is_new
