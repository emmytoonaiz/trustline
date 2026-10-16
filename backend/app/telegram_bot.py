import html
import logging
import os
import threading
from collections import OrderedDict

from fastapi import HTTPException

from app import checker, limits, reports_store
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
_seen: OrderedDict[int, None] = OrderedDict()
_seen_lock = threading.Lock()

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

def _handle_message(message: dict) -> None:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if chat.get("type") != "private" or sender.get("is_bot"):
        return  # private chats only, for now

    chat_id = chat["id"]
    chat_hash = store.hash_id("chat", chat_id)
    lang = _language(chat_hash, sender.get("language_code"))

    try:
        _limiter.check(chat_hash)
    except HTTPException:
        tg.send_message(chat_id, html.escape(s(lang, "rate_limited")))
        return

    text = message.get("text") or message.get("caption")
    if not text:
        tg.send_message(chat_id, html.escape(s(lang, "unsupported")))
        return

    if text.startswith("/"):
        _handle_command(chat_id, lang, text)
        return

    if len(text) > MAX_MESSAGE_LENGTH:
        tg.send_message(chat_id, html.escape(s(lang, "too_long")))
        return

    tg.send_chat_action(chat_id)
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

    if result.verdict == "link_unsupported":
        tg.send_message(chat_id, _format(result, lang, warning), _keyboard(lang, None, False, False))
        return

    category = (result.matched.category_en or result.matched.category) if result.matched else "Uncategorized"
    offer_account = bool(account) and result.verdict in ("likely_scam", "uncertain")
    pid = store.create_pending(chat_hash, category, text, account if offer_account else None)
    tg.send_message(chat_id, _format(result, lang, warning), _keyboard(lang, pid, True, offer_account))


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

def register_webhook() -> None:
    """Point Telegram at this server. Uses the bot token from the environment; nothing is
    logged or returned that contains it."""
    bot_token = tg.token()
    if not bot_token:
        return
    base = os.getenv("PUBLIC_BASE_URL") or (
        f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}" if os.getenv("RAILWAY_PUBLIC_DOMAIN") else None
    )
    if not base:
        logger.info("Telegram token set but no public URL known; webhook not registered")
        return
    tg.set_webhook(base.rstrip("/") + "/telegram/webhook", tg.webhook_secret(bot_token))
    tg.set_commands(COMMANDS)
    logger.info("Telegram webhook registered")
