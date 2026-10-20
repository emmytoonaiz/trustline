import itertools
import os
import sys
import tempfile
from pathlib import Path

# Configure the environment before the app is imported: a throwaway database, a fake bot token,
# and no AI/YouTube keys so tests never call paid services (a real .env must not leak in).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["YOUTUBE_API_KEY"] = ""
os.environ["PUBLIC_BASE_URL"] = ""
os.environ["RAILWAY_PUBLIC_DOMAIN"] = ""

import pytest
from fastapi.testclient import TestClient

from app import telegram_api
from app.main import app

SCAM_TEXT = "Our till number changed, please scan this new QR code to complete your payment"
SAFE_TEXT = "Hi, are we still meeting for lunch tomorrow at one?"

_update_ids = itertools.count(1000)
_user_ids = itertools.count(5000)


@pytest.fixture(autouse=True)
def forget_wrong_admin_keys(monkeypatch):
    """Every test is a fresh visitor as far as the admin lock-out is concerned."""
    from app import limits

    monkeypatch.setattr(limits, "_admin_fail_limiter", limits.RateLimiter(max_calls=5, window_seconds=600))


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sent(monkeypatch):
    """Records every call the bot makes to Telegram instead of making it."""
    calls = []

    def fake_post(method, payload, timeout=15):
        calls.append((method, payload))
        return {"ok": True}

    monkeypatch.setattr(telegram_api, "_post", fake_post)
    return calls


def new_user_id() -> int:
    return next(_user_ids)


def webhook(client, update: dict, secret: str | None = None):
    update = {"update_id": next(_update_ids), **update}
    headers = {"x-telegram-bot-api-secret-token": secret or telegram_api.webhook_secret(os.environ["TELEGRAM_BOT_TOKEN"])}
    return client.post("/telegram/webhook", json=update, headers=headers)


def private_message(uid: int, text: str | None = None, lang_code: str = "en", **extra) -> dict:
    message = {
        "message_id": 1,
        "from": {"id": uid, "is_bot": False, "first_name": "Tester", "language_code": lang_code},
        "chat": {"id": uid, "type": "private"},
        **extra,
    }
    if text is not None:
        message["text"] = text
    return {"message": message}


def button(uid: int, data: str, lang_code: str = "en") -> dict:
    return {
        "callback_query": {
            "id": f"cb-{next(_update_ids)}",
            "from": {"id": uid, "is_bot": False, "language_code": lang_code},
            "message": {"message_id": 7, "chat": {"id": uid, "type": "private"}},
            "data": data,
        }
    }


def last_message(sent) -> dict:
    return [p for m, p in sent if m == "sendMessage"][-1]


def callbacks(payload: dict) -> list[str]:
    return [b["callback_data"] for row in payload["reply_markup"]["inline_keyboard"] for b in row]


def forwarded_from_user(uid: int, scammer_id: int, text: str, **user_extra) -> dict:
    return private_message(
        uid,
        text,
        forward_origin={
            "type": "user",
            "sender_user": {"id": scammer_id, "is_bot": False, "first_name": "Bad", "username": f"bad{scammer_id}", **user_extra},
        },
    )
