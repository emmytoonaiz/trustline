import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def database_url() -> str:
    """Postgres on Railway (DATABASE_URL), a local SQLite file otherwise."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        path = Path(__file__).parent / "data" / "trustline.db"
        return f"sqlite:///{path.as_posix()}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ScamReport(Base):
    __tablename__ = "scam_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    category: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(16), default="web")
    message_excerpt: Mapped[str] = mapped_column(String(1000), default="")
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ReportedAccount(Base):
    """A Telegram account (or channel) that users reported via the bot."""

    __tablename__ = "reported_accounts"
    __table_args__ = (UniqueConstraint("kind", "tg_id", name="uq_reported_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # "user" or "chat"
    tg_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AccountReport(Base):
    """One person's report of one account. The reporter is stored only as a salted hash."""

    __tablename__ = "account_reports"
    __table_args__ = (UniqueConstraint("account_id", "reporter_hash", name="uq_one_report_per_reporter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("reported_accounts.id"), index=True)
    reporter_hash: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class TelegramUser(Base):
    """Remembered language choice, keyed by a salted hash (no raw Telegram id is stored)."""

    __tablename__ = "telegram_users"

    chat_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    language: Mapped[str] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PendingCheck(Base):
    """A checked message held briefly so the Report buttons work; deleted after 24 hours."""

    __tablename__ = "pending_checks"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    chat_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    category: Mapped[str] = mapped_column(String(120))
    excerpt: Mapped[str] = mapped_column(String(1000), default="")
    scam_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    account_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    account_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)
    account_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    account_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MonitoredChat(Base):
    """A group whose owner asked TrustLine to watch it. We keep the chat and owner ids because
    the bot has to send the owner private alerts."""

    __tablename__ = "monitored_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    owner_user_id: Mapped[int] = mapped_column(BigInteger)
    owner_language: Mapped[str] = mapped_column(String(8), default="en")
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MonitorAlert(Base):
    """A flagged message waiting for the owner's decision. Purged after 14 days."""

    __tablename__ = "monitor_alerts"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("monitored_chats.id"), index=True)
    tg_message_id: Mapped[int] = mapped_column(BigInteger)
    sender_label: Mapped[str] = mapped_column(String(200), default="")
    excerpt: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(120), default="")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open / deleted / kept
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class InstagramLink(Base):
    """An Instagram account whose comments we watch, and the Telegram user who gets the alerts."""

    __tablename__ = "instagram_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ig_user_id: Mapped[str] = mapped_column(String(40), unique=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    owner_user_id: Mapped[int] = mapped_column(BigInteger)
    owner_language: Mapped[str] = mapped_column(String(8), default="en")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InstagramAlert(Base):
    """A flagged Instagram comment waiting for the owner's decision. Purged after 14 days."""

    __tablename__ = "instagram_alerts"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("instagram_links.id"), index=True)
    comment_id: Mapped[str] = mapped_column(String(40), unique=True)
    sender_label: Mapped[str] = mapped_column(String(200), default="")
    excerpt: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(120), default="")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open / hidden / deleted / kept
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Feedback(Base):
    """A note left through the website's feedback form. Contact details are optional and only for replying."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(String(2000))
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    wants_pilot: Mapped[bool] = mapped_column(Boolean, default=False)
    ref: Mapped[str] = mapped_column(String(24), default="direct")
    language: Mapped[str] = mapped_column(String(8), default="en")


class SiteVisit(Base):
    """One website visit and the link label it came with (?ref=tiktok). Nothing identifies the visitor."""

    __tablename__ = "site_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = database_url()
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session():
    get_engine()
    s = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
