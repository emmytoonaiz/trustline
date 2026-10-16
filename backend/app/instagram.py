"""Instagram comment monitoring (prototype, one account).

Comments reach us two ways: Meta's webhook (what a production app would use) and a light polling
loop (works in Meta's development mode for your own account, where webhooks may not fire). Either
way a comment goes through the same filter and check as Telegram groups, and a likely scam produces
a private Telegram alert with Hide / Delete / Keep buttons. Nothing is hidden or deleted without
the owner's tap.
"""
import hashlib
import hmac
import html
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from app import instagram_api as api
from app import instagram_store as store
from app import monitor
from app import telegram_api as tg
from app.bot_i18n import s

logger = logging.getLogger("trustline.instagram")

MIN_TEXT_LENGTH = 8
MAX_CHECKED_LENGTH = 1500
POLL_OVERLAP = timedelta(minutes=5)  # comments can show up in the API a little late
_seen: dict[str, float] = {}  # comment id -> when we looked, so one comment is checked once
_SEEN_LIMIT = 5000


# ---- webhook plumbing ---------------------------------------------------------------------------

def verify_token() -> str:
    return os.getenv("INSTAGRAM_VERIFY_TOKEN", "")


def verify_signature(body: bytes, header: str | None) -> bool:
    """Meta signs every webhook with the app secret: X-Hub-Signature-256 = sha256=<hex hmac of the body>."""
    secret = os.getenv("INSTAGRAM_APP_SECRET", "")
    if not secret or not header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def handle_webhook(payload: dict) -> None:
    if payload.get("object") != "instagram":
        return
    for entry in payload.get("entry") or []:
        ig_user_id = str(entry.get("id") or "")
        for change in entry.get("changes") or []:
            if change.get("field") != "comments":
                continue
            value = change.get("value") or {}
            sender = value.get("from") or {}
            process_comment(
                ig_user_id,
                str(value.get("id") or value.get("comment_id") or ""),
                value.get("text") or "",
                str(sender.get("id") or ""),
                sender.get("username") or value.get("username"),
            )


# ---- one comment ---------------------------------------------------------------------------------

def _remember(comment_id: str) -> bool:
    """True the first time we see a comment."""
    if comment_id in _seen:
        return False
    if len(_seen) >= _SEEN_LIMIT:
        for old in sorted(_seen, key=_seen.get)[: _SEEN_LIMIT // 2]:
            del _seen[old]
    _seen[comment_id] = time.monotonic()
    return True


def process_comment(ig_user_id: str, comment_id: str, text: str, sender_id: str | None, username: str | None) -> None:
    link = store.get_link(ig_user_id)
    if link is None or not comment_id or not _remember(comment_id):
        return
    if (sender_id and sender_id == link.ig_user_id) or (username and username.lower() == link.username.lower()):
        return  # the owner's own comments and replies

    text = (text or "").strip()
    if len(text) < MIN_TEXT_LENGTH:
        return
    text = text[:MAX_CHECKED_LENGTH]

    lang = link.owner_language
    result = monitor.assess(text, f"ig:{ig_user_id}", lang)
    if result is None:
        return

    sender_label = f"@{username}" if username else "Unknown"
    alert_id = store.create_alert(link, comment_id, sender_label, text, monitor.category_of(result), result.confidence)
    if alert_id is None:
        return
    title = f"Instagram @{link.username}"
    body = monitor.alert_body(lang, title, sender_label, text, result)
    delivered = tg.send_message(link.owner_user_id, body, _keyboard(lang, alert_id))
    logger.warning("Instagram: alert %s to owner", "delivered" if delivered else "FAILED (owner has not started the bot?)")


def _keyboard(lang: str, alert_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": s(lang, "btn_hide"), "callback_data": f"i:h:{alert_id}"},
                {"text": s(lang, "btn_delete_comment"), "callback_data": f"i:d:{alert_id}"},
            ],
            [{"text": s(lang, "btn_keep"), "callback_data": f"i:k:{alert_id}"}],
        ]
    }


# ---- polling (development-mode fallback) -----------------------------------------------------------

def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z") if value else None
    except ValueError:
        return None


def poll_once() -> None:
    media_count = int(os.getenv("INSTAGRAM_POLL_MEDIA", "3"))
    for link in store.active_links():
        started = datetime.now(timezone.utc)
        if link.last_polled_at is None:
            store.set_last_polled(link.id, started)  # first run: start from now, never alert on old comments
            continue
        since = link.last_polled_at.replace(tzinfo=link.last_polled_at.tzinfo or timezone.utc) - POLL_OVERLAP
        for media in api.recent_media(media_count):
            for comment in api.media_comments(str(media["id"])):
                posted = _parse_time(comment.get("timestamp"))
                if posted is not None and posted < since:
                    continue
                process_comment(link.ig_user_id, str(comment["id"]), comment.get("text") or "", None, comment.get("username"))
        store.set_last_polled(link.id, started)


def start_poller() -> None:
    """Runs for the life of the server when an Instagram token is set (INSTAGRAM_POLL_SECONDS=0 turns it off)."""
    interval = int(os.getenv("INSTAGRAM_POLL_SECONDS", "180"))
    if not api.token() or interval <= 0:
        return

    def loop():
        while True:
            try:
                poll_once()
            except Exception:
                logger.exception("Instagram poll failed")
            time.sleep(interval)

    threading.Thread(target=loop, name="instagram-poller", daemon=True).start()


# ---- pairing the account with a Telegram chat ----------------------------------------------------------

def handle_link_command(chat_id: int, lang: str, text: str, message_id: int | None) -> None:
    """/instagram <pairing code>: alerts for the connected account will arrive in this chat."""
    parts = text.split(maxsplit=1)
    given = parts[1].strip() if len(parts) > 1 else ""
    code = os.getenv("INSTAGRAM_PAIRING_CODE", "")
    if message_id and given:
        tg.delete_message(chat_id, message_id)  # don't leave the code sitting in the chat
    if not code or not api.token() or not hmac.compare_digest(given.encode(), code.encode()):
        tg.send_message(chat_id, html.escape(s(lang, "ig_bad_code")))
        return
    account = api.me()
    if account is None:
        tg.send_message(chat_id, html.escape(s(lang, "ig_action_failed")))
        return
    store.link_account(account["user_id"], account["username"], chat_id, lang)
    tg.send_message(chat_id, s(lang, "ig_linked", username=html.escape(account["username"])))


# ---- the owner pressing a button on an alert ----------------------------------------------------------------

def handle_callback(cb: dict, data: str, lang: str) -> None:
    cb_id = cb.get("id")
    message = cb.get("message") or {}
    parts = data.split(":")
    if len(parts) != 3 or parts[1] not in ("h", "d", "k"):
        tg.answer_callback_query(cb_id)
        return
    action, alert_id = parts[1], parts[2]

    found = store.get_alert(alert_id)
    if found is None:
        tg.answer_callback_query(cb_id, s(lang, "mon_gone"))
        return
    alert, link = found
    if (cb.get("from") or {}).get("id") != link.owner_user_id:
        tg.answer_callback_query(cb_id)  # only the owner decides
        return
    lang = link.owner_language

    logger.warning("Instagram: owner chose %s", {"h": "hide", "d": "delete", "k": "keep"}[action])
    if action == "k":
        store.set_alert_status(alert_id, "kept")
        tg.answer_callback_query(cb_id, s(lang, "mon_kept"))
    else:
        done = api.hide_comment(alert.comment_id) if action == "h" else api.delete_comment(alert.comment_id)
        if not done:
            tg.answer_callback_query(cb_id, s(lang, "ig_action_failed"))
            return
        store.set_alert_status(alert_id, "hidden" if action == "h" else "deleted")
        tg.answer_callback_query(cb_id, s(lang, "ig_hidden" if action == "h" else "mon_deleted"))

    chat = message.get("chat") or {}
    if chat.get("id") and message.get("message_id"):
        tg.edit_reply_markup(chat["id"], message["message_id"], {"inline_keyboard": []})
