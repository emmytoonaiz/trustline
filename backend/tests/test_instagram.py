import hashlib
import hmac
import itertools
import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import SAFE_TEXT, SCAM_TEXT, new_user_id, private_message, webhook

from app import instagram, instagram_api, instagram_store, monitor

SECRET = "app-secret"
_ig_ids = itertools.count(9000)
_comment_ids = itertools.count(70000)


@pytest.fixture(autouse=True)
def instagram_env(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", SECRET)
    monkeypatch.setenv("INSTAGRAM_VERIFY_TOKEN", "verify-me")
    monkeypatch.setenv("INSTAGRAM_PAIRING_CODE", "open-sesame")
    monitor._hourly = type(monitor._hourly)(max_calls=60, window_seconds=3600)


@pytest.fixture()
def api(monkeypatch):
    """A fake Instagram that records what the bot asks it to do."""
    calls = {"hidden": [], "deleted": [], "ok": True, "media": [], "comments": {}}
    monkeypatch.setattr(instagram_api, "hide_comment", lambda cid: calls["hidden"].append(cid) or calls["ok"])
    monkeypatch.setattr(instagram_api, "delete_comment", lambda cid: calls["deleted"].append(cid) or calls["ok"])
    monkeypatch.setattr(instagram_api, "recent_media", lambda limit=3: calls["media"])
    monkeypatch.setattr(instagram_api, "media_comments", lambda mid, limit=50: calls["comments"].get(mid, []))
    return calls


def linked(owner=None, username="shopowner"):
    ig_id = str(next(_ig_ids))
    owner = owner or new_user_id()
    instagram_store.link_account(ig_id, username, owner, "en")
    return ig_id, owner


def comment_payload(ig_id, text, username="stranger", sender_id="555", comment_id=None, key="id"):
    cid = comment_id or str(next(_comment_ids))
    value = {key: cid, "text": text, "from": {"id": sender_id, "username": username}, "media": {"id": "m1"}}
    return {"object": "instagram", "entry": [{"id": ig_id, "time": 1, "changes": [{"field": "comments", "value": value}]}]}, cid


def post_signed(client, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/instagram/webhook", content=body, headers={"x-hub-signature-256": sig, "content-type": "application/json"})


def dm_to(sent, user_id):
    return [p for m, p in sent if m == "sendMessage" and p["chat_id"] == user_id]


def buttons(payload):
    return {b["callback_data"][2]: b["callback_data"] for row in payload["reply_markup"]["inline_keyboard"] for b in row}


def press(client, user_id, data):
    return webhook(client, {
        "callback_query": {
            "id": f"cb-{next(_comment_ids)}",
            "from": {"id": user_id, "is_bot": False, "language_code": "en"},
            "message": {"message_id": 9, "chat": {"id": user_id, "type": "private"}},
            "data": data,
        }
    })


# ---- webhook plumbing ---------------------------------------------------------------------------

def test_meta_handshake_returns_the_challenge(client):
    ok = client.get("/instagram/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"


def test_handshake_rejects_a_wrong_token(client):
    r = client.get("/instagram/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"})
    assert r.status_code == 403


def test_unsigned_or_wrongly_signed_webhooks_are_refused(client, sent, api):
    ig_id, owner = linked()
    payload, _ = comment_payload(ig_id, SCAM_TEXT)
    assert client.post("/instagram/webhook", json=payload).status_code == 403
    assert post_signed(client, payload, secret="wrong").status_code == 403
    assert dm_to(sent, owner) == []


# ---- comments -----------------------------------------------------------------------------------------

def test_scam_comment_alerts_the_owner_with_three_buttons(client, sent, api):
    ig_id, owner = linked()
    payload, _ = comment_payload(ig_id, SCAM_TEXT, username="sneaky")
    assert post_signed(client, payload).status_code == 200
    alerts = dm_to(sent, owner)
    assert len(alerts) == 1 and "@sneaky" in alerts[0]["text"] and "Instagram @shopowner" in alerts[0]["text"]
    assert set(buttons(alerts[0])) == {"h", "d", "k"}


def test_the_other_payload_shape_is_understood_too(client, sent, api):
    ig_id, owner = linked()
    payload, _ = comment_payload(ig_id, SCAM_TEXT, key="comment_id")
    post_signed(client, payload)
    assert len(dm_to(sent, owner)) == 1


def test_harmless_comments_cost_nothing_and_alert_nobody(client, sent, api, monkeypatch):
    ig_id, owner = linked()
    called = []
    monkeypatch.setattr("app.checker.check_message", lambda *a: called.append(a))
    post_signed(client, comment_payload(ig_id, "love this dress, see you saturday!")[0])
    post_signed(client, comment_payload(ig_id, SAFE_TEXT)[0])
    assert called == [] and dm_to(sent, owner) == []


def test_owners_own_comments_are_ignored(client, sent, api):
    ig_id, owner = linked(username="shopowner")
    post_signed(client, comment_payload(ig_id, SCAM_TEXT, username="ShopOwner")[0])
    post_signed(client, comment_payload(ig_id, SCAM_TEXT, sender_id=ig_id)[0])
    assert dm_to(sent, owner) == []


def test_the_same_comment_never_alerts_twice(client, sent, api):
    ig_id, owner = linked()
    payload, cid = comment_payload(ig_id, SCAM_TEXT)
    post_signed(client, payload)
    post_signed(client, payload)
    instagram._seen.pop(cid, None)  # even after a restart forgets it, the database still remembers
    post_signed(client, payload)
    assert len(dm_to(sent, owner)) == 1


def test_comments_on_unlinked_accounts_are_ignored(client, sent, api):
    payload, _ = comment_payload("424242", SCAM_TEXT)
    post_signed(client, payload)
    assert [m for m, _ in sent if m == "sendMessage"] == []


def test_alert_text_cannot_inject_html(client, sent, api):
    ig_id, owner = linked()
    post_signed(client, comment_payload(ig_id, SCAM_TEXT + " <b>pwn</b>", username="a<i>b")[0])
    text = dm_to(sent, owner)[0]["text"]
    assert "<b>pwn</b>" not in text and "<i>b" not in text


# ---- the owner's buttons --------------------------------------------------------------------------------------

def alert_for(client, sent):
    ig_id, owner = linked()
    payload, cid = comment_payload(ig_id, SCAM_TEXT)
    post_signed(client, payload)
    return owner, cid, buttons(dm_to(sent, owner)[-1])


def test_hide_hides_the_comment_on_instagram(client, sent, api):
    owner, cid, b = alert_for(client, sent)
    press(client, owner, b["h"])
    assert api["hidden"] == [cid] and api["deleted"] == []
    assert any(m == "editMessageReplyMarkup" for m, _ in sent)


def test_delete_deletes_the_comment_on_instagram(client, sent, api):
    owner, cid, b = alert_for(client, sent)
    press(client, owner, b["d"])
    assert api["deleted"] == [cid] and api["hidden"] == []


def test_keep_touches_nothing(client, sent, api):
    owner, cid, b = alert_for(client, sent)
    press(client, owner, b["k"])
    assert api["hidden"] == [] and api["deleted"] == []


def test_nobody_else_can_press_the_owners_buttons(client, sent, api):
    owner, cid, b = alert_for(client, sent)
    press(client, new_user_id(), b["d"])
    assert api["deleted"] == []


def test_a_failed_instagram_call_keeps_the_buttons(client, sent, api):
    owner, cid, b = alert_for(client, sent)
    api["ok"] = False
    press(client, owner, b["h"])
    assert not any(m == "editMessageReplyMarkup" for m, _ in sent)
    api["ok"] = True
    press(client, owner, b["h"])  # the owner can simply try again
    assert api["hidden"] == [cid, cid]


# ---- pairing ---------------------------------------------------------------------------------------------------------

def test_pairing_with_the_right_code_links_this_chat(client, sent, api, monkeypatch):
    uid = new_user_id()
    ig_id = str(next(_ig_ids))
    monkeypatch.setattr(instagram_api, "me", lambda: {"user_id": ig_id, "username": "brand<x>"})
    webhook(client, private_message(uid, "/instagram open-sesame"))
    assert instagram_store.get_link(ig_id).owner_user_id == uid
    assert ("deleteMessage", {"chat_id": uid, "message_id": 1}) in sent, "the code message is removed"
    assert "brand&lt;x&gt;" in dm_to(sent, uid)[-1]["text"]


def test_pairing_with_a_wrong_code_does_nothing(client, sent, api, monkeypatch):
    uid = new_user_id()
    ig_id = str(next(_ig_ids))
    monkeypatch.setattr(instagram_api, "me", lambda: {"user_id": ig_id, "username": "brand"})
    webhook(client, private_message(uid, "/instagram guess"))
    webhook(client, private_message(uid, "/instagram"))
    assert instagram_store.get_link(ig_id) is None


def test_pairing_is_off_until_a_code_is_configured(client, sent, api, monkeypatch):
    monkeypatch.delenv("INSTAGRAM_PAIRING_CODE")
    uid = new_user_id()
    ig_id = str(next(_ig_ids))
    monkeypatch.setattr(instagram_api, "me", lambda: {"user_id": ig_id, "username": "brand"})
    webhook(client, private_message(uid, "/instagram "))
    assert instagram_store.get_link(ig_id) is None


# ---- polling (development-mode fallback) ----------------------------------------------------------------------------------

def poll_only(monkeypatch, ig_id):
    """The fake Instagram answers for every link, so poll just the one under test."""
    all_links = instagram_store.active_links
    monkeypatch.setattr(instagram_store, "active_links", lambda: [l for l in all_links() if l.ig_user_id == ig_id])


def stamp(delta):
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S%z")


def test_first_poll_only_sets_a_baseline(client, sent, api, monkeypatch):
    ig_id, owner = linked()
    poll_only(monkeypatch, ig_id)
    api["media"] = [{"id": "m1"}]
    api["comments"]["m1"] = [{"id": "old1", "text": SCAM_TEXT, "username": "x", "timestamp": stamp(timedelta(days=-2))}]
    instagram.poll_once()
    assert dm_to(sent, owner) == []
    assert instagram_store.get_link(ig_id).last_polled_at is not None


def test_later_polls_alert_on_new_scam_comments_only(client, sent, api, monkeypatch):
    ig_id, owner = linked()
    poll_only(monkeypatch, ig_id)
    api["media"] = [{"id": "m1"}]
    instagram.poll_once()  # baseline
    cid_new, cid_old = f"new{next(_comment_ids)}", f"old{next(_comment_ids)}"
    api["comments"]["m1"] = [
        {"id": cid_new, "text": SCAM_TEXT, "username": "x", "timestamp": stamp(timedelta(seconds=-30))},
        {"id": cid_old, "text": SCAM_TEXT, "username": "y", "timestamp": stamp(timedelta(days=-3))},
    ]
    instagram.poll_once()
    alerts = dm_to(sent, owner)
    assert len(alerts) == 1
    instagram.poll_once()  # the same comment on the next round does not alert again
    assert len(dm_to(sent, owner)) == 1
