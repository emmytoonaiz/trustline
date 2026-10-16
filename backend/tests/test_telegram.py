from conftest import (
    SAFE_TEXT,
    SCAM_TEXT,
    button,
    callbacks,
    forwarded_from_user,
    last_message,
    new_user_id,
    private_message,
    webhook,
)


def test_webhook_rejects_wrong_secret(client, sent):
    assert webhook(client, private_message(new_user_id(), "hi"), secret="wrong").status_code == 403
    assert sent == []


def test_webhook_rejects_missing_secret(client, sent):
    r = client.post("/telegram/webhook", json={"update_id": 1, "message": {}})
    assert r.status_code == 403


def test_start_greets_in_the_users_telegram_language(client, sent):
    webhook(client, private_message(new_user_id(), "/start", lang_code="fr-FR"))
    assert "Bienvenue" in last_message(sent)["text"]


def test_unknown_telegram_language_falls_back_to_english(client, sent):
    webhook(client, private_message(new_user_id(), "/start", lang_code="de"))
    assert "Welcome" in last_message(sent)["text"]


def test_scam_message_gets_verdict_and_report_buttons(client, sent):
    uid = new_user_id()
    webhook(client, private_message(uid, SCAM_TEXT))
    msg = last_message(sent)
    assert "Likely a scam" in msg["text"] and "%" in msg["text"]
    assert any(c.startswith("r:") for c in callbacks(msg))
    assert not any(c.startswith("a:") for c in callbacks(msg)), "no account button without a forward"
    assert ("sendChatAction", {"chat_id": uid, "action": "typing"}) in sent


def test_verdict_is_in_the_selected_language(client, sent):
    webhook(client, private_message(new_user_id(), SCAM_TEXT, lang_code="sw"))
    assert "Huenda ni ulaghai" in last_message(sent)["text"]


def test_report_button_records_once(client, sent):
    from app import reports_store

    uid = new_user_id()
    before = reports_store.get_stats()["total_reports"]
    webhook(client, private_message(uid, SCAM_TEXT))
    pid = next(c for c in callbacks(last_message(sent)) if c.startswith("r:"))

    webhook(client, button(uid, pid))
    assert reports_store.get_stats()["total_reports"] == before + 1
    webhook(client, button(uid, pid))  # second tap must not double count
    assert reports_store.get_stats()["total_reports"] == before + 1


def test_report_button_only_works_for_the_chat_that_made_the_check(client, sent):
    from app import reports_store

    owner, intruder = new_user_id(), new_user_id()
    webhook(client, private_message(owner, SCAM_TEXT))
    pid = next(c for c in callbacks(last_message(sent)) if c.startswith("r:"))
    before = reports_store.get_stats()["total_reports"]
    webhook(client, button(intruder, pid))
    assert reports_store.get_stats()["total_reports"] == before


def test_language_choice_is_remembered(client, sent):
    uid = new_user_id()
    webhook(client, private_message(uid, "/language"))
    assert "l:yo" in callbacks(last_message(sent))
    webhook(client, button(uid, "l:yo"))
    webhook(client, private_message(uid, SCAM_TEXT))
    assert "Ó ṣeé ṣe kó jẹ́ ìjìbìtì" in last_message(sent)["text"]


def test_images_and_groups(client, sent):
    uid = new_user_id()
    webhook(client, private_message(uid, None, photo=[{"file_id": "x"}]))
    assert "text and links" in last_message(sent)["text"]

    sent.clear()
    group = private_message(uid, SCAM_TEXT)
    group["message"]["chat"] = {"id": -100, "type": "group"}
    webhook(client, group)
    assert sent == [], "the bot ignores group chats"


def test_same_update_is_handled_only_once(client, sent):
    update = {"update_id": 999999, **private_message(new_user_id(), SCAM_TEXT)}
    headers = {"x-telegram-bot-api-secret-token": __import__("app.telegram_api", fromlist=["x"]).webhook_secret("123456:TEST-TOKEN")}
    client.post("/telegram/webhook", json=update, headers=headers)
    client.post("/telegram/webhook", json=update, headers=headers)
    assert len([1 for m, _ in sent if m == "sendMessage"]) == 1


def test_too_long_message_is_refused(client, sent):
    webhook(client, private_message(new_user_id(), "x" * 4001))
    assert "too long" in last_message(sent)["text"]


def test_fast_senders_are_slowed_down(client, sent):
    uid = new_user_id()
    for _ in range(12):
        webhook(client, private_message(uid, "/help"))
    assert "very fast" in last_message(sent)["text"]


# ---- account-level reports ----------------------------------------------------

def test_forwarded_scam_offers_account_report(client, sent):
    webhook(client, forwarded_from_user(new_user_id(), 777001, SCAM_TEXT))
    cbs = callbacks(last_message(sent))
    assert any(c.startswith("r:") for c in cbs) and any(c.startswith("a:") for c in cbs)


def test_hidden_sender_has_no_account_button(client, sent):
    webhook(
        client,
        private_message(new_user_id(), SCAM_TEXT, forward_origin={"type": "hidden_user", "sender_user_name": "Someone"}),
    )
    assert not any(c.startswith("a:") for c in callbacks(last_message(sent)))


def test_forwarding_your_own_message_has_no_account_button(client, sent):
    uid = new_user_id()
    webhook(client, forwarded_from_user(uid, uid, SCAM_TEXT))
    assert not any(c.startswith("a:") for c in callbacks(last_message(sent)))


def test_safe_message_cannot_be_used_to_report_an_account(client, sent):
    webhook(client, forwarded_from_user(new_user_id(), 777002, SAFE_TEXT))
    cbs = callbacks(last_message(sent))
    assert not any(c.startswith("a:") for c in cbs)


def test_channel_forward_can_be_reported(client, sent):
    webhook(
        client,
        private_message(
            new_user_id(),
            SCAM_TEXT,
            forward_origin={"type": "channel", "chat": {"id": -1009, "title": "Free Money", "username": "freemoney", "type": "channel"}},
        ),
    )
    assert any(c.startswith("a:") for c in callbacks(last_message(sent)))


def test_account_warning_appears_only_after_several_different_reporters(client, sent):
    from app import telegram_store

    scammer = 777003
    reporters = [new_user_id() for _ in range(3)]

    for i, uid in enumerate(reporters, start=1):
        webhook(client, forwarded_from_user(uid, scammer, SCAM_TEXT))
        assert "reported by" not in last_message(sent)["text"], f"no warning yet before reporter {i}"
        pid = next(c for c in callbacks(last_message(sent)) if c.startswith("a:"))
        webhook(client, button(uid, pid))
        assert telegram_store.account_reporter_count("user", scammer) == i

    webhook(client, forwarded_from_user(new_user_id(), scammer, SCAM_TEXT))
    assert "reported by 3 TrustLine users" in last_message(sent)["text"]


def test_one_person_cannot_inflate_an_accounts_count(client, sent):
    from app import telegram_store

    scammer, uid = 777004, new_user_id()
    for _ in range(3):
        webhook(client, forwarded_from_user(uid, scammer, SCAM_TEXT))
        pid = next(c for c in callbacks(last_message(sent)) if c.startswith("a:"))
        webhook(client, button(uid, pid))
    assert telegram_store.account_reporter_count("user", scammer) == 1


def test_reporter_identity_is_not_stored_in_clear(client, sent):
    from sqlalchemy import select

    from app import db

    scammer, uid = 777005, new_user_id()
    webhook(client, forwarded_from_user(uid, scammer, SCAM_TEXT))
    webhook(client, button(uid, next(c for c in callbacks(last_message(sent)) if c.startswith("a:"))))
    with db.session() as s:
        hashes = [r.reporter_hash for r in s.execute(select(db.AccountReport)).scalars()]
    assert hashes and all(len(h) == 64 and str(uid) not in h for h in hashes)


# ---- website endpoints still work on the database ------------------------------

def test_website_report_and_stats_use_the_database(client):
    before = client.get("/api/stats").json()["total_reports"]
    r = client.post("/api/report", json={"message": "scam text", "category": "Fake bank/wallet alert"})
    assert r.status_code == 200
    after = client.get("/api/stats").json()
    assert after["total_reports"] == before + 1
    assert any(c["category"] == "Fake bank/wallet alert" for c in after["top_categories"])


def test_website_verify_still_works(client):
    r = client.post("/api/verify", json={"message": SCAM_TEXT, "language": "fr"})
    assert r.status_code == 200 and r.json()["verdict"] == "likely_scam"
