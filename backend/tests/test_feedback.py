import pytest
from conftest import last_message, new_user_id, private_message, webhook

from app import limits


@pytest.fixture(autouse=True)
def fresh_limit(monkeypatch):
    monkeypatch.setattr(limits, "_feedback_limiter", limits.RateLimiter(max_calls=3, window_seconds=600))
    monkeypatch.setenv("ADMIN_KEY", "s3cret")
    monkeypatch.delenv("FEEDBACK_NOTIFY_CHAT_ID", raising=False)


def stored(client):
    return client.get("/api/feedback?limit=200", headers={"x-admin-key": "s3cret"}).json()


def test_feedback_is_saved_and_the_owner_can_read_it(client):
    r = client.post("/api/feedback", json={
        "message": "Caught my fake prize SMS, but the advice was long.",
        "rating": 4,
        "contact": "ada@example.com",
        "wants_pilot": True,
        "ref": "LinkedIn",
        "language": "fr",
    })
    assert r.status_code == 200
    mine = [f for f in stored(client) if f["message"].startswith("Caught my fake prize")]
    assert len(mine) == 1
    assert mine[0]["rating"] == 4 and mine[0]["wants_pilot"] is True and mine[0]["ref"] == "linkedin"
    assert mine[0]["contact"] == "ada@example.com" and mine[0]["language"] == "fr"


def test_reading_feedback_needs_the_admin_key(client, monkeypatch):
    assert client.get("/api/feedback").status_code == 403
    assert client.get("/api/feedback", headers={"x-admin-key": "wrong"}).status_code == 403
    monkeypatch.delenv("ADMIN_KEY")
    assert client.get("/api/feedback").status_code == 404


def test_contact_and_rating_are_optional(client):
    assert client.post("/api/feedback", json={"message": "Please add Igbo."}).status_code == 200
    row = next(f for f in stored(client) if f["message"] == "Please add Igbo.")
    assert row["rating"] is None and row["contact"] is None and row["wants_pilot"] is False


def test_the_hidden_field_traps_bots(client):
    r = client.post("/api/feedback", json={"message": "Buy cheap watches now", "website": "http://spam.example"})
    assert r.status_code == 200
    assert not any(f["message"] == "Buy cheap watches now" for f in stored(client))


def test_bad_input_is_refused(client):
    assert client.post("/api/feedback", json={"message": "x"}).status_code == 422
    assert client.post("/api/feedback", json={"message": "fine message", "rating": 9}).status_code == 422
    assert client.post("/api/feedback", json={"message": "y" * 2001}).status_code == 422


def test_a_visitor_cannot_flood_the_form(client):
    codes = [client.post("/api/feedback", json={"message": f"note number {i}"}).status_code for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_the_owner_is_told_on_telegram_with_the_text_escaped(client, sent, monkeypatch):
    monkeypatch.setenv("FEEDBACK_NOTIFY_CHAT_ID", "4242")
    client.post("/api/feedback", json={"message": "Nice <b>tool</b>", "rating": 5, "contact": "@ada", "wants_pilot": True})
    msg = [p for m, p in sent if m == "sendMessage" and p["chat_id"] == 4242][-1]
    assert "Nice &lt;b&gt;tool&lt;/b&gt;" in msg["text"] and "@ada" in msg["text"] and "★★★★★" in msg["text"]
    assert "business pilot" in msg["text"]


def test_no_notification_when_the_chat_id_is_not_set(client, sent):
    client.post("/api/feedback", json={"message": "Silent note"})
    assert [m for m, _ in sent if m == "sendMessage"] == []


def test_myid_tells_you_your_chat_id(client, sent):
    uid = new_user_id()
    webhook(client, private_message(uid, "/myid"))
    assert str(uid) in last_message(sent)["text"]
