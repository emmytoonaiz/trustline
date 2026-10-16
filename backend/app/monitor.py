import html
import logging
import os

from fastapi import HTTPException

from app import checker, limits, monitor_store, triage
from app import telegram_api as tg
from app.bot_i18n import LANGUAGE_NAMES, s

logger = logging.getLogger("trustline.monitor")

MAX_CHECKED_LENGTH = 1500
MIN_TEXT_LENGTH = 8
# Precision matters more than recall here: hiding a real customer's comment costs the business money,
# so only confident verdicts reach the owner, and the owner still decides.
MIN_CONFIDENCE = int(os.getenv("MONITOR_MIN_CONFIDENCE", "70"))
# For testing alone: also check the owner's own messages (normally skipped).
INCLUDE_OWNER = os.getenv("MONITOR_INCLUDE_OWNER", "").lower() in ("1", "true", "yes")
# A busy group must not be able to run up the AI bill.
_hourly = limits.RateLimiter(max_calls=int(os.getenv("MONITOR_CHECKS_PER_HOUR", "60")), window_seconds=3600)


def _lang(code: str | None) -> str:
    prefix = (code or "").lower().split("-")[0]
    return prefix if prefix in LANGUAGE_NAMES else "en"


def _sender_label(sender: dict) -> str:
    name = " ".join(p for p in (sender.get("first_name"), sender.get("last_name")) if p) or "Unknown"
    return f"{name} (@{sender['username']})" if sender.get("username") else name


def _alert_keyboard(lang: str, alert_id: str, can_delete: bool) -> dict:
    row = []
    if can_delete:
        row.append({"text": s(lang, "btn_delete"), "callback_data": f"m:d:{alert_id}"})
    row.append({"text": s(lang, "btn_keep"), "callback_data": f"m:k:{alert_id}"})
    return {"inline_keyboard": [row]}


# ---- the bot being added to / removed from a group -------------------------------------------

def handle_my_chat_member(update: dict) -> None:
    chat = update.get("chat") or {}
    if chat.get("type") not in ("group", "supergroup"):
        logger.warning("Monitor: ignored membership change in a %s chat", chat.get("type"))
        return
    new = update.get("new_chat_member") or {}
    actor = update.get("from") or {}
    status = new.get("status")
    chat_id = chat["id"]
    logger.warning("Monitor: bot status in a %s is now %r (can_delete=%s)", chat.get("type"), status, new.get("can_delete_messages"))

    if status in ("left", "kicked"):
        monitor_store.stop_monitoring(chat_id)
        return
    if not actor.get("id") or actor.get("is_bot"):
        return

    lang = _lang(actor.get("language_code"))
    title = html.escape(chat.get("title") or "")

    if status == "administrator":
        can_delete = bool(new.get("can_delete_messages"))
        record = monitor_store.start_monitoring(chat_id, chat.get("title") or "", actor["id"], lang, can_delete)
        lang = record.owner_language
        note = s(lang, "mon_can_delete") if can_delete else s(lang, "mon_cannot_delete")
        sent = tg.send_message(record.owner_user_id, f"{s(lang, 'mon_on', title=title)}\n\n{html.escape(note)}")
        if not sent:
            _tell_group_to_start_bot(chat_id, lang)
    elif status == "member":
        sent = tg.send_message(actor["id"], s(lang, "mon_need_admin", title=title))
        if not sent:
            _tell_group_to_start_bot(chat_id, lang)


def _tell_group_to_start_bot(chat_id: int, lang: str) -> None:
    """The owner never started the bot, so it can't message them first: ask in the group instead."""
    from app import telegram_bot

    url = telegram_bot.bot_url()
    markup = {"inline_keyboard": [[{"text": s(lang, "mon_start_btn"), "url": f"{url}?start=alerts"}]]} if url else None
    tg.send_message(chat_id, html.escape(s(lang, "mon_hint_group")), markup)


# ---- messages in a watched group ---------------------------------------------------------------

def handle_group_message(message: dict, chat: dict, sender: dict) -> None:
    watched = monitor_store.get_active_chat(chat["id"])
    if watched is None:
        return
    if message.get("is_automatic_forward") or message.get("sender_chat") or (sender.get("id") == watched.owner_user_id and not INCLUDE_OWNER):
        logger.warning("Monitor: skipped (owner, channel or automatic post)")
        return

    text = (message.get("text") or message.get("caption") or "").strip()
    if len(text) < MIN_TEXT_LENGTH or text.startswith("/"):
        logger.warning("Monitor: skipped (no usable text)")
        return
    text = text[:MAX_CHECKED_LENGTH]

    lang = watched.owner_language
    result = assess(text, f"chat:{chat['id']}", lang)
    if result is None:
        return

    sender_label = _sender_label(sender)
    alert_id = monitor_store.create_alert(watched, message["message_id"], sender_label, text, category_of(result), result.confidence)
    body = alert_body(lang, watched.title, sender_label, text, result)
    delivered = tg.send_message(watched.owner_user_id, body, _alert_keyboard(lang, alert_id, watched.can_delete))
    logger.warning("Monitor: alert %s to owner", "delivered" if delivered else "FAILED (owner has not started the bot?)")


# ---- shared by every place we watch (Telegram groups, Instagram comments) -----------------------------

def assess(text: str, limiter_key: str, lang: str):
    """Decides whether a message deserves an alert: cheap risk filter, per-place hourly allowance,
    full check, then a confidence floor. Returns the verdict, or None when nothing should be sent."""
    if not triage.has_risk_signals(text):
        logger.warning("Monitor: no risk signals, not checked")
        return None
    try:
        _hourly.check(limiter_key)
    except HTTPException:
        logger.warning("Hourly AI-check allowance reached for a watched place")
        return None
    try:
        result = checker.check_message(text, lang)
    except Exception:
        logger.exception("Monitor check failed")
        return None
    logger.warning("Monitor: verdict=%s confidence=%s (alert needs likely_scam >= %s)", result.verdict, result.confidence, MIN_CONFIDENCE)
    if result.verdict != "likely_scam" or result.confidence < MIN_CONFIDENCE:
        return None
    return result


def category_of(result) -> str:
    return (result.matched.category_en or result.matched.category) if result.matched else "Uncategorized"


def alert_body(lang: str, title: str, sender_label: str, text: str, result) -> str:
    """The private alert shown to the owner (HTML-safe: every piece of user text is escaped)."""
    esc = html.escape
    lines = [
        f"<b>{s(lang, 'mon_alert_title', title=esc(title))}</b> · {result.confidence}%",
        f"{esc(s(lang, 'mon_from'))}: {esc(sender_label)}",
        "",
        f"<i>{esc(text[:300])}</i>",
    ]
    reasons = result.matched.why[:2] if result.matched else []
    if reasons:
        lines += ["", f"<b>{esc(s(lang, 'why'))}</b>"] + [f"• {esc(r[:300])}" for r in reasons]
    elif result.headline:
        lines += ["", esc(result.headline[:300])]
    return "\n".join(lines)


# ---- the owner pressing a button on an alert --------------------------------------------------------

def handle_callback(cb: dict, data: str, lang: str) -> None:
    cb_id = cb.get("id")
    message = cb.get("message") or {}
    parts = data.split(":")
    if len(parts) != 3 or parts[1] not in ("d", "k"):
        tg.answer_callback_query(cb_id)
        return
    action, alert_id = parts[1], parts[2]

    found = monitor_store.get_alert(alert_id)
    if found is None:
        tg.answer_callback_query(cb_id, s(lang, "mon_gone"))
        return
    alert, watched = found
    if (cb.get("from") or {}).get("id") != watched.owner_user_id:
        tg.answer_callback_query(cb_id)  # only the owner decides
        return
    lang = watched.owner_language

    logger.warning("Monitor: owner chose %s", "delete" if action == "d" else "keep")
    if action == "d":
        if not tg.delete_message(watched.tg_chat_id, alert.tg_message_id):
            tg.answer_callback_query(cb_id, s(lang, "mon_delete_failed"))
            return
        monitor_store.set_alert_status(alert_id, "deleted")
        tg.answer_callback_query(cb_id, s(lang, "mon_deleted"))
    else:
        monitor_store.set_alert_status(alert_id, "kept")
        tg.answer_callback_query(cb_id, s(lang, "mon_kept"))

    chat = message.get("chat") or {}
    if chat.get("id") and message.get("message_id"):
        tg.edit_reply_markup(chat["id"], message["message_id"], {"inline_keyboard": []})
