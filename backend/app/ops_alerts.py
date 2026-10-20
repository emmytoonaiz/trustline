"""Tells the owner on Telegram when the AI part of TrustLine stops working.

A rejected or expired key, an empty credit balance, or a reached daily cap otherwise fail quietly:
visitors just get weaker answers. Alerts go to the same chat as the feedback notifications
(FEEDBACK_NOTIFY_CHAT_ID, or OWNER_NOTIFY_CHAT_ID if you prefer a separate name) and repeat at most
once per cooldown, so a busy site can't flood the owner. Alerts never contain the key itself.
"""
import logging
import os
import threading
import time

from app import telegram_api

logger = logging.getLogger("trustline.ops")

COOLDOWN_SECONDS = {"key": 6 * 3600, "credit": 6 * 3600, "cap": 12 * 3600, "nokey": 24 * 3600}
KEY_CHECK_EVERY_SECONDS = 6 * 3600

MESSAGES = {
    "key": (
        "⚠️ <b>TrustLine: the Anthropic API key is being rejected.</b>\n"
        "Visitors are getting weaker fallback answers instead of AI checks.\n\n"
        "Fix: Anthropic Console → API keys → create a key in the <b>Default</b> workspace, then update "
        "ANTHROPIC_API_KEY in Railway (and backend/.env). Keys can expire, so set a reminder for the new one.\n\n"
        "This alert repeats at most every 6 hours."
    ),
    "credit": (
        "⚠️ <b>TrustLine: the Anthropic credit balance is too low.</b>\n"
        "AI checks are failing, so visitors get weaker fallback answers.\n\n"
        "Fix: top up the balance (or switch on auto-reload) in the Anthropic Console → Billing."
    ),
    "cap": (
        "ℹ️ <b>TrustLine reached today's AI check limit (LLM_DAILY_CAP).</b>\n"
        "Until midnight UTC, messages outside the built-in patterns get fallback answers.\n\n"
        "If this is real demand, raise LLM_DAILY_CAP in Railway."
    ),
    "nokey": (
        "⚠️ <b>TrustLine has no ANTHROPIC_API_KEY set.</b>\n"
        "Only the built-in scam patterns are working; the AI check is off."
    ),
}

_last_sent: dict[str, float] = {}
_lock = threading.Lock()


def _chat_id() -> int | None:
    raw = (os.getenv("OWNER_NOTIFY_CHAT_ID") or os.getenv("FEEDBACK_NOTIFY_CHAT_ID") or "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


def _spawn(fn, *args) -> None:
    """Sending takes a network round trip, so it never delays a visitor's answer."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def notify(kind: str) -> None:
    chat_id = _chat_id()
    if chat_id is None or kind not in MESSAGES:
        return
    now = time.monotonic()
    with _lock:
        if now - _last_sent.get(kind, float("-inf")) < COOLDOWN_SECONDS[kind]:
            return
        _last_sent[kind] = now
    logger.warning("Ops alert: %s", kind)
    _spawn(telegram_api.send_message, chat_id, MESSAGES[kind])


def classify_ai_error(exc: Exception) -> str | None:
    """Which kind of owner-fixable problem an AI failure is, or None for ordinary hiccups (timeouts etc.)."""
    import anthropic

    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "key"
    if isinstance(exc, anthropic.BadRequestError):
        text = str(exc).lower()
        if "credit balance" in text:
            return "credit"
        if "workspace" in text:
            return "key"
    return None


def check_key() -> None:
    """A free request (it lists a model, no tokens) that proves the key still works."""
    import anthropic

    if not os.getenv("ANTHROPIC_API_KEY"):
        notify("nokey")
        return
    try:
        anthropic.Anthropic(timeout=15.0, max_retries=0).models.list(limit=1)
    except Exception as exc:
        kind = classify_ai_error(exc)
        if kind:
            notify(kind)
        else:
            logger.warning("AI key check inconclusive: %s", type(exc).__name__)


def start_key_watch() -> None:
    """Checks the key shortly after start-up and every few hours, so an expiry is noticed before visitors do."""
    if _chat_id() is None:
        return

    def loop():
        time.sleep(60)
        while True:
            try:
                check_key()
            except Exception:
                logger.exception("AI key watch failed")
            time.sleep(KEY_CHECK_EVERY_SECONDS)

    threading.Thread(target=loop, name="ai-key-watch", daemon=True).start()
