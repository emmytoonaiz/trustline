import hashlib
import logging
import os

import requests

logger = logging.getLogger("trustline.telegram_api")

API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")


def token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN") or None


def webhook_secret(bot_token: str) -> str:
    """Derived from the token so there is no second secret to configure."""
    return hashlib.sha256(("trustline-webhook:" + bot_token).encode()).hexdigest()[:48]


def _post(method: str, payload: dict, timeout: int = 15) -> dict | None:
    bot_token = token()
    if not bot_token:
        return None
    try:
        resp = requests.post(f"{API_BASE}/bot{bot_token}/{method}", json=payload, timeout=timeout)
        data = resp.json()
        if not data.get("ok"):
            # Never log the URL: it contains the bot token.
            logger.warning("Telegram %s failed: %s", method, data.get("description"))
        return data
    except Exception:
        logger.exception("Telegram %s request failed", method)
        return None


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _post("sendMessage", payload)


def send_chat_action(chat_id: int, action: str = "typing") -> None:
    _post("sendChatAction", {"chat_id": chat_id, "action": action}, timeout=5)


def answer_callback_query(callback_id: str, text: str | None = None) -> None:
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    _post("answerCallbackQuery", payload, timeout=5)


def edit_reply_markup(chat_id: int, message_id: int, reply_markup: dict) -> None:
    _post("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup})


def set_webhook(url: str, secret: str) -> None:
    _post(
        "setWebhook",
        {"url": url, "secret_token": secret, "allowed_updates": ["message", "callback_query"]},
    )


def set_commands(commands: list[dict]) -> None:
    _post("setMyCommands", {"commands": commands})
