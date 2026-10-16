import itertools

import pytest
from conftest import SAFE_TEXT, SCAM_TEXT, new_user_id, webhook

from app import monitor, monitor_store

_chat_ids = itertools.count(-100500)
_msg_ids = itertools.count(100)


@pytest.fixture(autouse=True)
def fresh_allowance():
    monitor._hourly = type(monitor._hourly)(max_calls=60, window_seconds=3600)


def new_chat_id() -> int:
    return next(_chat_ids)


def made_admin(client, chat_id, owner, can_delete=True, status="administrator", lang_code="en"):
    return webhook(client, {
        "my_chat_member": {
            "chat": {"id": chat_id, "type": "supergroup", "title": "Ada <Shop>"},
            "from": {"id": owner, "is_bot": False, "first_name": "Ada", "language_code": lang_code},
            "new_chat_member": {"status": status, "can_delete_messages": can_delete, "user": {"id": 1, "is_bot": True}},
        }
    })


def post(client, chat_id, text, user_id=None, **extra):
    uid = user_id or new_user_id()
    message = {
        "message_id": next(_msg_ids),
        "from": {"id": uid, "is_bot": False, "first_name": "Chidi", "username": "chidi99"},
        "chat": {"id": chat_id, "type": "supergroup", "title": "Ada <Shop>"},
        "text": text,
        **extra,
    }
    return webhook(client, {"message": message}), message


def dm_to(sent, user_id):
    return [p for m, p in sent if m == "sendMessage" and p["chat_id"] == user_id]


def test_adding_bot_as_admin_starts_monitoring_and_tells_the_owner(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    assert monitor_store.get_active_chat(chat).owner_user_id == owner
    texts = dm_to(sent, owner)
    assert texts and "Ada &lt;Shop&gt;" in texts[0]["text"], "group title must be HTML-escaped"


def test_owner_is_told_when_bot_cannot_delete(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner, can_delete=False)
    assert monitor_store.get_active_chat(chat).can_delete is False
    assert dm_to(sent, owner)


def test_plain_member_gets_asked_for_admin_rights_and_nothing_is_watched(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner, status="member")
    assert monitor_store.get_active_chat(chat) is None
    assert dm_to(sent, owner)


def test_group_is_told_to_start_the_bot_when_owner_cannot_be_messaged(client, monkeypatch):
    chat, owner = new_chat_id(), new_user_id()
    calls = []

    def fake_post(method, payload, timeout=15):
        calls.append((method, payload))
        if method == "sendMessage" and payload["chat_id"] == owner:
            return {"ok": False}
        return {"ok": True}

    monkeypatch.setattr("app.telegram_api._post", fake_post)
    monkeypatch.setattr("app.telegram_bot.bot_url", lambda: "https://t.me/TestBot")
    made_admin(client, chat, owner)
    in_group = [p for m, p in calls if m == "sendMessage" and p["chat_id"] == chat]
    assert in_group and "https://t.me/TestBot?start=alerts" in str(in_group[0]["reply_markup"])


def test_removing_the_bot_stops_monitoring(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    made_admin(client, chat, owner, status="kicked")
    assert monitor_store.get_active_chat(chat) is None


def test_unwatched_groups_are_never_read(client, sent):
    chat = new_chat_id()
    post(client, chat, SCAM_TEXT)
    assert sent == []


def test_scam_comment_alerts_the_owner_privately_not_the_group(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    post(client, chat, SCAM_TEXT)
    alerts = dm_to(sent, owner)
    assert len(alerts) == 1
    assert "chidi99" in alerts[0]["text"]
    data = [b["callback_data"] for row in alerts[0]["reply_markup"]["inline_keyboard"] for b in row]
    assert any(d.startswith("m:d:") for d in data) and any(d.startswith("m:k:") for d in data)
    assert [p for m, p in sent if p.get("chat_id") == chat] == [], "nothing is posted in the group"


def test_alert_has_no_delete_button_when_bot_cannot_delete(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner, can_delete=False)
    sent.clear()
    post(client, chat, SCAM_TEXT)
    data = [b["callback_data"] for row in dm_to(sent, owner)[0]["reply_markup"]["inline_keyboard"] for b in row]
    assert not any(d.startswith("m:d:") for d in data)


def test_ordinary_chatter_costs_nothing_and_alerts_nobody(client, sent, monkeypatch):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    called = []
    monkeypatch.setattr("app.checker.check_message", lambda *a: called.append(a))
    post(client, chat, "lovely dress, see you at the market tomorrow")
    post(client, chat, SAFE_TEXT)
    assert called == [] and sent == []


def test_owner_own_messages_and_channel_posts_are_ignored(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    post(client, chat, SCAM_TEXT, user_id=owner)
    post(client, chat, SCAM_TEXT, is_automatic_forward=True)
    post(client, chat, SCAM_TEXT, sender_chat={"id": -1, "type": "channel"})
    assert sent == []


def test_low_confidence_verdicts_do_not_alert(client, sent, monkeypatch):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    monkeypatch.setattr(monitor, "MIN_CONFIDENCE", 101)
    post(client, chat, SCAM_TEXT)
    assert sent == []


def test_hourly_allowance_caps_ai_checks(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    monitor._hourly = type(monitor._hourly)(max_calls=2, window_seconds=3600)
    for _ in range(5):
        post(client, chat, SCAM_TEXT)
    assert len(dm_to(sent, owner)) == 2


def alert_buttons(sent, owner):
    payload = dm_to(sent, owner)[-1]
    return {b["callback_data"][2]: b["callback_data"] for row in payload["reply_markup"]["inline_keyboard"] for b in row}


def press(client, user_id, data):
    return webhook(client, {
        "callback_query": {
            "id": f"cb-{next(_msg_ids)}",
            "from": {"id": user_id, "is_bot": False, "language_code": "en"},
            "message": {"message_id": 9, "chat": {"id": user_id, "type": "private"}},
            "data": data,
        }
    })


def test_owner_can_delete_the_flagged_message(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    _, message = post(client, chat, SCAM_TEXT)
    press(client, owner, alert_buttons(sent, owner)["d"])
    assert ("deleteMessage", {"chat_id": chat, "message_id": message["message_id"]}) in sent
    assert any(m == "editMessageReplyMarkup" for m, _ in sent), "buttons are removed after a decision"


def test_keep_leaves_the_message_alone(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    post(client, chat, SCAM_TEXT)
    press(client, owner, alert_buttons(sent, owner)["k"])
    assert not any(m == "deleteMessage" for m, _ in sent)


def test_nobody_else_can_press_the_owners_buttons(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    post(client, chat, SCAM_TEXT)
    press(client, new_user_id(), alert_buttons(sent, owner)["d"])
    assert not any(m == "deleteMessage" for m, _ in sent)


def test_expired_or_unknown_alert_is_handled_gracefully(client, sent):
    owner = new_user_id()
    r = press(client, owner, "m:d:doesnotexist")
    assert r.status_code == 200
    assert not any(m == "deleteMessage" for m, _ in sent)


def test_alert_text_cannot_inject_html(client, sent):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    post(client, chat, SCAM_TEXT + " <b>pwn</b>")
    assert "<b>pwn</b>" not in dm_to(sent, owner)[0]["text"]


def test_owner_messages_are_checked_when_the_test_switch_is_on(client, sent, monkeypatch):
    chat, owner = new_chat_id(), new_user_id()
    made_admin(client, chat, owner)
    sent.clear()
    monkeypatch.setattr(monitor, "INCLUDE_OWNER", True)
    post(client, chat, SCAM_TEXT, user_id=owner)
    assert len(dm_to(sent, owner)) == 1
