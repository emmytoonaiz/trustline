import anthropic
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import ops_alerts, verdict_engine
from app.spa import SinglePageStaticFiles

OWNER = 424242


def api_error(cls, status, message):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message, response=httpx.Response(status, request=request), body=None)


@pytest.fixture(autouse=True)
def alerts_on(monkeypatch, sent):
    """Alerts go to a known chat, are sent immediately (not on a thread), and the cooldowns start fresh."""
    monkeypatch.setenv("FEEDBACK_NOTIFY_CHAT_ID", str(OWNER))
    monkeypatch.setattr(ops_alerts, "_spawn", lambda fn, *a: fn(*a))
    ops_alerts._last_sent.clear()
    yield
    ops_alerts._last_sent.clear()


def alerts(sent):
    return [p["text"] for m, p in sent if m == "sendMessage" and p["chat_id"] == OWNER]


def test_an_alert_is_sent_once_per_cooldown(sent):
    ops_alerts.notify("key")
    ops_alerts.notify("key")
    ops_alerts.notify("cap")
    texts = alerts(sent)
    assert len(texts) == 2 and "API key is being rejected" in texts[0] and "daily" in texts[1].lower()


def test_no_chat_configured_means_no_alert(sent, monkeypatch):
    monkeypatch.delenv("FEEDBACK_NOTIFY_CHAT_ID")
    ops_alerts.notify("key")
    assert alerts(sent) == []


def test_errors_are_classified_correctly():
    assert ops_alerts.classify_ai_error(api_error(anthropic.AuthenticationError, 401, "invalid x-api-key")) == "key"
    assert ops_alerts.classify_ai_error(api_error(anthropic.PermissionDeniedError, 403, "forbidden")) == "key"
    assert ops_alerts.classify_ai_error(api_error(anthropic.BadRequestError, 400, "This API key is not scoped to a workspace")) == "key"
    assert ops_alerts.classify_ai_error(api_error(anthropic.BadRequestError, 400, "Your credit balance is too low")) == "credit"
    assert ops_alerts.classify_ai_error(api_error(anthropic.BadRequestError, 400, "messages: bad shape")) is None
    assert ops_alerts.classify_ai_error(TimeoutError("slow")) is None


class FailingClient:
    def __init__(self, error):
        self.messages = self
        self._error = error

    def parse(self, **kwargs):
        raise self._error


def test_a_rejected_key_during_a_check_alerts_the_owner_once_and_visitors_still_get_an_answer(sent, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    err = api_error(anthropic.AuthenticationError, 401, "invalid x-api-key")
    monkeypatch.setattr(verdict_engine, "_get_client", lambda: FailingClient(err))
    unknown = "Good afternoon, this is the estate office updating records, please send your ID photo."
    for _ in range(3):
        assert verdict_engine.analyze(unknown, "en").verdict
    texts = alerts(sent)
    assert len(texts) == 1 and "sk-test" not in texts[0]


def test_an_ordinary_ai_hiccup_does_not_alert(sent, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(verdict_engine, "_get_client", lambda: FailingClient(TimeoutError("slow")))
    verdict_engine.analyze("Good afternoon, this is the estate office updating records, please send your ID photo.", "en")
    assert alerts(sent) == []


def test_reaching_the_daily_cap_alerts_the_owner(sent, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_DAILY_CAP", "0")
    verdict_engine.analyze("Good afternoon, this is the estate office updating records, please send your ID photo.", "en")
    assert any("LLM_DAILY_CAP" in t for t in alerts(sent))


def test_the_key_check_alerts_on_a_dead_key_and_stays_quiet_otherwise(sent, monkeypatch):
    class FakeAnthropic:
        outcome = None

        def __init__(self, **kwargs):
            self.models = self

        def list(self, **kwargs):
            if FakeAnthropic.outcome:
                raise FakeAnthropic.outcome

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    ops_alerts.check_key()  # key works: nothing to say
    assert alerts(sent) == []

    FakeAnthropic.outcome = TimeoutError("network")
    ops_alerts.check_key()  # a network blip is not the owner's problem
    assert alerts(sent) == []

    FakeAnthropic.outcome = api_error(anthropic.AuthenticationError, 401, "invalid x-api-key")
    ops_alerts.check_key()
    assert len(alerts(sent)) == 1


def test_a_missing_key_is_reported(sent, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    ops_alerts.check_key()
    assert any("no ANTHROPIC_API_KEY" in t for t in alerts(sent))


# ---- mistyped links show the site -----------------------------------------------------------------------------

@pytest.fixture()
def site(tmp_path):
    (tmp_path / "index.html").write_text("<html>TrustLine app</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    app.mount("/", SinglePageStaticFiles(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_the_home_page_and_real_files_are_served(site):
    assert "TrustLine app" in site.get("/").text
    assert site.get("/assets/app.js").text == "console.log(1)"


def test_a_mistyped_link_opens_the_app_instead_of_an_error(site):
    for path in ("/ref=LinkedIn", "/linkedin", "/some/deep/page"):
        r = site.get(path)
        assert r.status_code == 200 and "TrustLine app" in r.text, path


def test_missing_files_and_server_addresses_are_still_404(site):
    assert site.get("/assets/missing.js").status_code == 404
    assert site.get("/wp-login.php").status_code == 404
    assert site.get("/api/nope").status_code == 404
    assert site.get("/telegram/nope").status_code == 404
    assert site.get("/api/ping").json() == {"pong": True}
