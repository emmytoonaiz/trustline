import pytest

KEY = "a-long-random-admin-key"


@pytest.fixture(autouse=True)
def admin_key(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", KEY)


def get(client, path, key):
    return client.get(path, headers={"x-admin-key": key})


@pytest.mark.parametrize("path", ["/api/visits", "/api/feedback"])
def test_the_right_key_works_and_nothing_is_cached(client, path):
    r = get(client, path, KEY)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/api/visits", "/api/feedback"])
def test_a_wrong_or_missing_key_is_refused(client, path):
    assert client.get(path).status_code == 403
    assert get(client, path, "nope").status_code == 403


def test_endpoints_do_not_exist_until_a_key_is_configured(client, monkeypatch):
    monkeypatch.delenv("ADMIN_KEY")
    assert get(client, "/api/visits", KEY).status_code == 404
    assert get(client, "/api/feedback", KEY).status_code == 404


def test_five_wrong_guesses_lock_the_visitor_out_even_for_the_right_key(client):
    for _ in range(5):
        assert get(client, "/api/visits", "guess").status_code == 403
    assert get(client, "/api/visits", "guess").status_code == 429
    assert get(client, "/api/visits", KEY).status_code == 429, "guessing must gain nothing once locked"
    assert get(client, "/api/feedback", KEY).status_code == 429, "the lock covers both endpoints"


def test_correct_logins_never_count_towards_the_lock(client):
    for _ in range(10):
        assert get(client, "/api/visits", KEY).status_code == 200
