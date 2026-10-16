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


def test_voice_notes_are_politely_declined(client, sent):
    webhook(client, private_message(new_user_id(), None, voice={"file_id": "v"}))
    assert "voice notes" in last_message(sent)["text"]


# ---- screenshots ---------------------------------------------------------------

def read_image_as(monkeypatch, text):
    """Pretend the downloaded screenshot contains `text` (no real download or AI call)."""
    from app import image_reader, telegram_api

    monkeypatch.setattr(telegram_api, "get_file_bytes", lambda file_id, max_bytes=0: b"fake-image")
    monkeypatch.setattr(image_reader, "transcribe", lambda data, media_type="image/jpeg": text)


def test_screenshot_is_read_then_checked_like_any_message(client, sent, monkeypatch):
    read_image_as(monkeypatch, SCAM_TEXT)
    webhook(client, private_message(new_user_id(), None, photo=[{"file_id": "small"}, {"file_id": "big"}]))
    msg = last_message(sent)["text"]
    assert "Text I read from your image" in msg and "till number changed" in msg
    assert "Likely a scam" in msg


def test_screenshot_note_is_translated(client, sent, monkeypatch):
    read_image_as(monkeypatch, SCAM_TEXT)
    webhook(client, private_message(new_user_id(), None, lang_code="fr", photo=[{"file_id": "x"}]))
    assert "Texte lu dans votre image" in last_message(sent)["text"]


def test_unreadable_screenshot_asks_for_a_clearer_one(client, sent, monkeypatch):
    read_image_as(monkeypatch, None)
    webhook(client, private_message(new_user_id(), None, photo=[{"file_id": "x"}]))
    assert "read any text in that image" in last_message(sent)["text"]


def test_caption_is_still_checked_when_the_image_cannot_be_read(client, sent, monkeypatch):
    read_image_as(monkeypatch, None)
    webhook(client, private_message(new_user_id(), None, photo=[{"file_id": "x"}], caption=SCAM_TEXT))
    assert "Likely a scam" in last_message(sent)["text"]


def test_screenshot_text_cannot_inject_html(client, sent, monkeypatch):
    read_image_as(monkeypatch, "<b>hello</b> " + SCAM_TEXT)
    webhook(client, private_message(new_user_id(), None, photo=[{"file_id": "x"}]))
    assert "&lt;b&gt;hello&lt;/b&gt;" in last_message(sent)["text"]


def test_screenshots_are_rate_limited_harder_than_text(client, sent, monkeypatch):
    read_image_as(monkeypatch, SCAM_TEXT)
    uid = new_user_id()
    for _ in range(7):
        webhook(client, private_message(uid, None, photo=[{"file_id": "x"}]))
    assert "very fast" in last_message(sent)["text"]


# ---- group chats: only when asked --------------------------------------------

_group_ids = __import__("itertools").count(-1000)


def group_message(text, reply_to=None, user_id=None, lang_code="en"):
    msg = {
        "message_id": 50,
        "from": {"id": user_id or new_user_id(), "is_bot": False, "language_code": lang_code},
        "chat": {"id": next(_group_ids), "type": "supergroup"},
        "text": text,
    }
    if reply_to is not None:
        msg["reply_to_message"] = reply_to
    return {"message": msg}


def scam_post(**extra):
    return {"message_id": 49, "from": {"id": 4242, "is_bot": False}, "text": SCAM_TEXT, **extra}


def test_bot_never_reads_ordinary_group_conversation(client, sent):
    webhook(client, group_message(SCAM_TEXT))
    webhook(client, group_message("/start"))
    assert sent == []


def test_check_without_a_reply_explains_how(client, sent):
    webhook(client, group_message("/check"))
    msg = last_message(sent)
    assert "reply to it with /check" in msg["text"]
    assert msg["reply_parameters"]["message_id"] == 50


def test_check_in_a_reply_answers_under_the_scam_without_buttons(client, sent):
    webhook(client, group_message("/check", reply_to=scam_post()))
    msg = last_message(sent)
    assert "Likely a scam" in msg["text"]
    assert msg["reply_parameters"]["message_id"] == 49
    assert "reply_markup" not in msg


def test_check_command_addressed_to_this_bot_works(client, sent):
    webhook(client, group_message("/check@TrustLineBot", reply_to=scam_post()))
    assert "Likely a scam" in last_message(sent)["text"]


def test_check_uses_the_askers_language(client, sent):
    webhook(client, group_message("/check", reply_to=scam_post(), lang_code="sw"))
    assert "Huenda ni ulaghai" in last_message(sent)["text"]


def test_bot_messages_are_not_checked_in_groups(client, sent):
    webhook(client, group_message("/check", reply_to=scam_post(**{"from": {"id": 1, "is_bot": True}})))
    assert sent == []


def test_check_can_read_a_screenshot_posted_in_a_group(client, sent, monkeypatch):
    read_image_as(monkeypatch, SCAM_TEXT)
    target = {"message_id": 49, "from": {"id": 4242, "is_bot": False}, "photo": [{"file_id": "x"}]}
    webhook(client, group_message("/check", reply_to=target))
    assert "Text I read from your image" in last_message(sent)["text"]


# ---- website link to the bot -------------------------------------------------------

def test_config_hides_telegram_link_until_the_bot_is_known(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
    from app import telegram_bot

    monkeypatch.setattr(telegram_bot, "_bot_username", None)
    assert client.get("/api/config").json()["telegram_url"] is None


def test_config_exposes_the_bots_public_link(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "@TrustLineScamBot")
    assert client.get("/api/config").json()["telegram_url"] == "https://t.me/TrustLineScamBot"


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


# ---- responsiveness -------------------------------------------------------------

def test_typing_indicator_stays_alive_during_a_slow_check_and_then_stops(sent, monkeypatch):
    import time

    from app import telegram_bot

    monkeypatch.setattr(telegram_bot, "TYPING_REFRESH_SECONDS", 0.05)
    with telegram_bot._typing(123):
        time.sleep(0.3)
    during = len([1 for m, _ in sent if m == "sendChatAction"])
    assert during >= 3, "indicator should refresh repeatedly while the check runs"

    time.sleep(0.2)
    assert len([1 for m, _ in sent if m == "sendChatAction"]) == during, "and stop once the check is done"


# ---- site visits + business contact ---------------------------------------------------------

def test_visits_are_counted_per_link_label(client, monkeypatch):
    from app import visits_store

    before = visits_store.counts()["by_ref"].get("tiktok", 0)
    assert client.post("/api/visit", json={"ref": "TikTok"}).status_code == 200
    assert visits_store.counts()["by_ref"]["tiktok"] == before + 1


def test_odd_visit_labels_count_as_direct(client):
    from app import visits_store

    before = visits_store.counts()["by_ref"].get("direct", 0)
    client.post("/api/visit", json={"ref": "<script>alert(1)</script>"})
    client.post("/api/visit", json={})
    assert visits_store.counts()["by_ref"]["direct"] == before + 2


def test_visit_counts_need_the_admin_key(client, monkeypatch):
    monkeypatch.delenv("ADMIN_KEY", raising=False)
    assert client.get("/api/visits").status_code == 404
    monkeypatch.setenv("ADMIN_KEY", "s3cret")
    assert client.get("/api/visits").status_code == 403
    assert client.get("/api/visits", headers={"x-admin-key": "wrong"}).status_code == 403
    ok = client.get("/api/visits", headers={"x-admin-key": "s3cret"})
    assert ok.status_code == 200 and "by_ref" in ok.json()


def test_business_contact_is_exposed_as_a_link_or_mailto(client, monkeypatch):
    monkeypatch.delenv("BUSINESS_CONTACT", raising=False)
    assert client.get("/api/config").json()["business_contact"] is None
    monkeypatch.setenv("BUSINESS_CONTACT", "hello@example.com")
    assert client.get("/api/config").json()["business_contact"] == "mailto:hello@example.com"
    monkeypatch.setenv("BUSINESS_CONTACT", "https://tiktok.com/@trustline")
    assert client.get("/api/config").json()["business_contact"] == "https://tiktok.com/@trustline"
    monkeypatch.setenv("BUSINESS_CONTACT", "javascript:alert(1)")
    assert client.get("/api/config").json()["business_contact"] is None
