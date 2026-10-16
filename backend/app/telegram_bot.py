import html
import logging
import os
import threading
from collections import OrderedDict
from contextlib import contextmanager

from fastapi import HTTPException

from app import checker, image_reader, limits, monitor, reports_store
from app import telegram_api as tg
from app import telegram_store as store
from app.bot_i18n import COMMANDS, LANGUAGE_NAMES, PRIVACY_NOTE, s
from app.schemas import VerifyResponse

logger = logging.getLogger("trustline.telegram_bot")

MAX_MESSAGE_LENGTH = 4000
# An account warning is only shown once this many *different* people reported it, so a single
# person (or a handful of throwaway accounts) can't easily brand an innocent account.
ACCOUNT_WARN_THRESHOLD = int(os.getenv("ACCOUNT_WARN_THRESHOLD", "3"))

_limiter = limits.RateLimiter(max_calls=10, window_seconds=60)
_image_limiter = limits.RateLimiter(max_calls=5, window_seconds=60)
_group_limiter = limits.RateLimiter(max_calls=8, window_seconds=60)
_seen: OrderedDict[int, None] = OrderedDict()
_seen_lock = threading.Lock()

TYPING_REFRESH_SECONDS = 4  # Telegram clears "typing…" after about 5 seconds


@contextmanager
def _typing(chat_id: int):
    """Keep the "typing…" indicator alive while a slow check runs, so the bot never looks frozen."""
    stop = threading.Event()

    def keep_alive():
        while not stop.is_set():
            tg.send_chat_action(chat_id)
            stop.wait(TYPING_REFRESH_SECONDS)

    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()


_ICON = {"likely_scam": "⚠️", "uncertain": "🤔", "likely_safe": "✅", "link_unsupported": "🔗"}
_LABEL_KEY = {
    "likely_scam": "label_scam",
    "uncertain": "label_uncertain",
    "likely_safe": "label_safe",
    "link_unsupported": "label_link",
}


def _already_seen(update_id: int | None) -> bool:
    """Telegram resends an update if we're slow to answer; handle each one once."""
    if update_id is None:
        return False
    with _seen_lock:
        if update_id in _seen:
            return True
        _seen[update_id] = None
        while len(_seen) > 2000:
            _seen.popitem(last=False)
    return False


def process_update(update: dict) -> None:
    try:
        if _already_seen(update.get("update_id")):
            return
        if "callback_query" in update:
            _handle_callback(update["callback_query"])
        elif "message" in update:
            _handle_message(update["message"])
        elif "my_chat_member" in update:
            monitor.handle_my_chat_member(update["my_chat_member"])
    except Exception:
        logger.exception("Telegram update failed")


# ---- helpers --------------------------------------------------------------

def _language(chat_hash: str, telegram_code: str | None) -> str:
    stored = store.get_language(chat_hash)
    if stored in LANGUAGE_NAMES:
        return stored
    prefix = (telegram_code or "").lower().split("-")[0]
    return prefix if prefix in LANGUAGE_NAMES else "en"


def _trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _forwarded_account(message: dict, sender: dict) -> dict | None:
    """Who originally sent a forwarded message. Telegram fills this in itself, so the person
    forwarding can't fake it; it is absent when the original sender hides their account."""
    origin = message.get("forward_origin")
    user = chat = None
    if origin:
        kind = origin.get("type")
        if kind == "user":
            user = origin.get("sender_user")
        elif kind in ("chat", "channel"):
            chat = origin.get("sender_chat") or origin.get("chat")
    else:  # older Telegram payloads
        user = message.get("forward_from")
        chat = message.get("forward_from_chat")

    if user and user.get("id") and user["id"] != sender.get("id"):
        name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
        return {"kind": "user", "tg_id": user["id"], "username": user.get("username"), "name": name or None}
    if chat and chat.get("id"):
        return {"kind": "chat", "tg_id": chat["id"], "username": chat.get("username"), "name": chat.get("title")}
    return None


def _format(result: VerifyResponse, lang: str, warning: str | None) -> str:
    esc = html.escape
    lines: list[str] = []
    if warning:
        lines += [esc(warning), ""]
    head = f"{_ICON.get(result.verdict, '🤔')} <b>{esc(s(lang, _LABEL_KEY.get(result.verdict, 'label_uncertain')))}</b>"
    if result.confidence > 0:
        head += f" · {result.confidence}%"
    lines.append(head)
    if result.headline:
        lines.append(esc(_trim(result.headline, 300)))

    if result.verdict == "link_unsupported":
        lines += ["", esc(_trim(result.link_notice or "", 600))]
    elif result.matched:
        reasons = result.matched.why[:3]
        if reasons:
            lines += ["", f"<b>{esc(s(lang, 'why'))}</b>"] + [f"• {esc(_trim(r, 350))}" for r in reasons]
        lines += ["", f"<b>{esc(s(lang, 'todo'))}</b>", esc(_trim(result.matched.advice, 600))]
    elif result.generic_advice:
        lines += ["", esc(_trim(result.generic_advice, 700))]
    return "\n".join(lines)


def _keyboard(lang: str, pid: str | None, show_report: bool, show_account: bool) -> dict:
    rows = []
    if pid and show_report:
        rows.append([{"text": s(lang, "btn_report"), "callback_data": f"r:{pid}"}])
    if pid and show_account:
        rows.append([{"text": s(lang, "btn_account"), "callback_data": f"a:{pid}"}])
    rows.append([{"text": s(lang, "btn_language"), "callback_data": "lang"}])
    return {"inline_keyboard": rows}


def _language_keyboard() -> dict:
    return {
        "inline_keyboard": [[{"text": name, "callback_data": f"l:{code}"}] for code, name in LANGUAGE_NAMES.items()]
    }


# ---- messages ---------------------------------------------------------------

def _content_of(message: dict, chat_id: int) -> tuple[str | None, str | None, str | None]:
    """What to check in a message: (text, text read from an image, problem).
    `problem` is a bot-text key when there is nothing usable to check."""
    typed = message.get("text") or message.get("caption")
    image_text = None
    photos = message.get("photo")
    if photos:
        for size in list(reversed(photos))[:2]:  # largest first; fall back to a smaller copy
            data = tg.get_file_bytes(size["file_id"])
            if data:
                image_text = image_reader.transcribe(data)
                break
        if not image_text and not typed:
            return None, None, "image_unreadable"
    parts = [p for p in (typed, image_text) if p]
    if not parts:
        return None, None, "unsupported"
    return "\n\n".join(parts), image_text, None


def _with_image_note(text: str, image_text: str | None, lang: str) -> str:
    if not image_text:
        return text
    return f"{html.escape(s(lang, 'image_read'))}\n<i>{html.escape(_trim(image_text, 300))}</i>\n\n{text}"


def _handle_message(message: dict) -> None:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return
    if chat.get("type") == "private":
        _handle_private(message, chat, sender)
    elif chat.get("type") in ("group", "supergroup"):
        _handle_group(message, chat, sender)


def _handle_private(message: dict, chat: dict, sender: dict) -> None:
    chat_id = chat["id"]
    chat_hash = store.hash_id("chat", chat_id)
    lang = _language(chat_hash, sender.get("language_code"))

    try:
        _limiter.check(chat_hash)
        if message.get("photo"):
            _image_limiter.check(chat_hash)
    except HTTPException:
        tg.send_message(chat_id, html.escape(s(lang, "rate_limited")))
        return

    typed = message.get("text")
    if typed and typed.startswith("/"):
        _handle_command(chat_id, lang, typed)
        return
    if typed and len(typed) > MAX_MESSAGE_LENGTH:
        tg.send_message(chat_id, html.escape(s(lang, "too_long")))
        return

    with _typing(chat_id):
        text, image_text, problem = _content_of(message, chat_id)
        if problem:
            tg.send_message(chat_id, html.escape(s(lang, problem)))
            return
        text = text[:MAX_MESSAGE_LENGTH]
        try:
            result = checker.check_message(text, lang)
        except Exception:
            logger.exception("Check failed")
            tg.send_message(chat_id, html.escape(s(lang, "error")))
            return

    account = _forwarded_account(message, sender)
    warning = None
    if account:
        n = store.account_reporter_count(account["kind"], account["tg_id"])
        if n >= ACCOUNT_WARN_THRESHOLD:
            warning = s(lang, "account_warning", n=n)

    reply = _with_image_note(_format(result, lang, warning), image_text, lang)

    if result.verdict == "link_unsupported":
        tg.send_message(chat_id, reply, _keyboard(lang, None, False, False))
        return

    category = (result.matched.category_en or result.matched.category) if result.matched else "Uncategorized"
    offer_account = bool(account) and result.verdict in ("likely_scam", "uncertain")
    pid = store.create_pending(chat_hash, category, text, account if offer_account else None)
    tg.send_message(chat_id, reply, _keyboard(lang, pid, True, offer_account))


def _handle_group(message: dict, chat: dict, sender: dict) -> None:
    """Groups: unless the owner has switched monitoring on, the bot never reads the conversation.
    It acts when someone replies to a message with /check, and answers under that message."""
    typed = message.get("text") or ""
    if not typed.startswith("/") or typed.split()[0].split("@")[0].lower() != "/check":
        logger.warning("Group message update in chat type=%s (monitored check follows)", chat.get("type"))
        monitor.handle_group_message(message, chat, sender)  # only acts in groups the owner asked us to watch
        return

    chat_id = chat["id"]
    user_hash = store.hash_id("chat", sender.get("id", 0))  # same hash as that user's private chat
    lang = _language(user_hash, sender.get("language_code"))
    ask_id = message.get("message_id")
    target = message.get("reply_to_message")

    try:
        _limiter.check(user_hash)
        _group_limiter.check(store.hash_id("group", chat_id))
        if target and target.get("photo"):
            _image_limiter.check(user_hash)
    except HTTPException:
        tg.send_message(chat_id, html.escape(s(lang, "rate_limited")), reply_to=ask_id)
        return

    if not target:
        # Field names only (never content), so we can see what Telegram actually sent.
        logger.warning(
            "Group /check arrived without reply_to_message; message fields=%s chat_type=%s",
            sorted(message.keys()),
            chat.get("type"),
        )
        tg.send_message(chat_id, html.escape(s(lang, "group_hint")), reply_to=ask_id)
        return
    if (target.get("from") or {}).get("is_bot"):
        return

    with _typing(chat_id):
        text, image_text, problem = _content_of(target, chat_id)
        if problem:
            tg.send_message(chat_id, html.escape(s(lang, problem)), reply_to=target.get("message_id"))
            return
        try:
            result = checker.check_message(text[:MAX_MESSAGE_LENGTH], lang)
        except Exception:
            logger.exception("Group check failed")
            tg.send_message(chat_id, html.escape(s(lang, "error")), reply_to=ask_id)
            return
    tg.send_message(
        chat_id,
        _with_image_note(_format(result, lang, None), image_text, lang),
        reply_to=target.get("message_id"),
    )


def _handle_command(chat_id: int, lang: str, text: str) -> None:
    command = text.split()[0].split("@")[0].lower()
    if command == "/language":
        tg.send_message(chat_id, html.escape(s(lang, "language_prompt")), _language_keyboard())
    elif command == "/start":
        tg.send_message(chat_id, s(lang, "welcome"), _keyboard(lang, None, False, False))
    else:
        tg.send_message(chat_id, s(lang, "help") + "\n\n" + html.escape(PRIVACY_NOTE.get(lang, PRIVACY_NOTE["en"])))


# ---- button presses -----------------------------------------------------------

def _handle_callback(cb: dict) -> None:
    cb_id = cb.get("id")
    user = cb.get("from") or {}
    message = cb.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        tg.answer_callback_query(cb_id)
        return

    chat_id = chat["id"]
    chat_hash = store.hash_id("chat", chat_id)
    lang = _language(chat_hash, user.get("language_code"))
    data = cb.get("data") or ""

    if data.startswith("m:"):
        monitor.handle_callback(cb, data, lang)
        return

    if data == "lang":
        tg.answer_callback_query(cb_id)
        tg.send_message(chat_id, html.escape(s(lang, "language_prompt")), _language_keyboard())
        return

    if data.startswith("l:"):
        code = data[2:]
        if code in LANGUAGE_NAMES:
            store.set_language(chat_hash, code)
            tg.answer_callback_query(cb_id)
            tg.send_message(chat_id, html.escape(s(code, "language_set")), _keyboard(code, None, False, False))
        else:
            tg.answer_callback_query(cb_id)
        return

    if data[:2] in ("r:", "a:"):
        pid = data[2:]
        pending = store.get_pending(pid, chat_hash)
        if pending is None:
            tg.answer_callback_query(cb_id, s(lang, "expired"))
            return

        if data[0] == "r":
            if pending.scam_reported:
                tg.answer_callback_query(cb_id, s(lang, "already"))
                return
            reports_store.add_report(pending.excerpt, pending.category, None, source="telegram")
            store.mark_pending(pid, scam_reported=True)
            tg.answer_callback_query(cb_id, s(lang, "reported"))
        else:
            if not pending.account_kind or pending.account_reported:
                tg.answer_callback_query(cb_id, s(lang, "already"))
                return
            reporter = store.hash_id("user", user.get("id", chat_id))
            if store.reporter_reports_today(reporter) >= store.ACCOUNT_REPORTS_PER_DAY:
                tg.answer_callback_query(cb_id, s(lang, "account_limit"))
                return
            n, _ = store.report_account(
                pending.account_kind,
                pending.account_tg_id,
                pending.account_username,
                pending.account_name,
                reporter,
                pending.category,
            )
            store.mark_pending(pid, account_reported=True)
            tg.answer_callback_query(cb_id, s(lang, "reported_account", n=n))

        # Drop the button that was just used, keep the rest.
        fresh = store.get_pending(pid, chat_hash)
        if fresh and message.get("message_id"):
            tg.edit_reply_markup(
                chat_id,
                message["message_id"],
                _keyboard(lang, pid, not fresh.scam_reported, bool(fresh.account_kind) and not fresh.account_reported),
            )
        return

    tg.answer_callback_query(cb_id)


# ---- start-up ------------------------------------------------------------------

_bot_username: str | None = None


def bot_url() -> str | None:
    """Public link to the bot (for the website's "Check on Telegram" button), if one is configured."""
    name = os.getenv("TELEGRAM_BOT_USERNAME") or _bot_username
    return f"https://t.me/{name.lstrip('@')}" if name else None


def register_webhook() -> None:
    """Point Telegram at this server. Uses the bot token from the environment; nothing is
    logged or returned that contains it."""
    global _bot_username
    bot_token = tg.token()
    if not bot_token:
        return
    _bot_username = tg.get_bot_username()
    base = os.getenv("PUBLIC_BASE_URL") or (
        f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}" if os.getenv("RAILWAY_PUBLIC_DOMAIN") else None
    )
    if not base:
        logger.info("Telegram token set but no public URL known; webhook not registered")
        return
    tg.set_webhook(base.rstrip("/") + "/telegram/webhook", tg.webhook_secret(bot_token))
    tg.set_commands(COMMANDS)
    logger.info("Telegram webhook registered")
