import pytest
from fastapi.testclient import TestClient
from app.services import email


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(email.config, "DATA", tmp_path)
    monkeypatch.delenv("ZEIM_EMAIL_ENABLED", raising=False); monkeypatch.delenv("CLOUDFLARE_EMAIL_TOKEN", raising=False)
    return tmp_path


def boom(*a, **k): raise AssertionError("must not call the network")


def test_off_by_default_is_noop(monkeypatch):
    monkeypatch.setattr("httpx.post", boom)
    assert email.send("u1", "setup", day=1)["reason"] == "not opted in"
    email.opt_in("u1", "a@example.com", ["setup", "expiry"])
    r = email.send("u1", "expiry", count=2, days=3)
    assert r["sent"] is False and r["reason"] == "email switched off"
    p = r["payload"]
    assert p["from"] == {"address": "noreply@zeimapp.com", "name": "ZEIM"} and p["html"] and p["text"]
    assert "/api/email/unsubscribe?u=u1&t=" in p["text"] and "Stop these emails" in p["html"]
    monkeypatch.setenv("ZEIM_EMAIL_ENABLED", "1")          # flag without token: still off
    assert email.send("u1", "expiry")["reason"] == "email switched off"


def test_digest_blocked_on_cloudflare(monkeypatch):
    monkeypatch.setattr("httpx.post", boom)
    email.opt_in("u2", "b@example.com", ["digest"])
    monkeypatch.setenv("ZEIM_EMAIL_ENABLED", "1"); monkeypatch.setenv("CLOUDFLARE_EMAIL_TOKEN", "x")
    assert email.send("u2", "digest", titles=["Box"])["reason"].startswith("digest not allowed")


def test_sends_when_on(monkeypatch):
    seen = {}
    class R: status_code = 200
    def fake(url, json, timeout, headers): seen.update(url=url, json=json, headers=headers); return R()
    monkeypatch.setattr("httpx.post", fake)
    email.opt_in("u3", "c@example.com", ["setup"])
    monkeypatch.setenv("ZEIM_EMAIL_ENABLED", "1"); monkeypatch.setenv("CLOUDFLARE_EMAIL_TOKEN", "tok")
    assert email.send("u3", "setup", day=7)["sent"]
    assert seen["url"].endswith("/accounts/589efa2a3041d62f3b04dd398bcce6b7/email/sending/send")
    assert seen["headers"]["Authorization"] == "Bearer tok" and seen["json"]["to"] == ["c@example.com"]


def test_unsubscribe_route_deletes_address(data):
    from app.main import app
    email.opt_in("u4", "d@example.com", ["setup"])
    c = TestClient(app)
    assert "didn't work" in c.get("/api/email/unsubscribe?u=u4&t=bad").text
    assert "Done" in c.get(f"/api/email/unsubscribe?u=u4&t={email.unsub_token('u4')}").text
    assert email.subscribed("u4", "setup") is None and "d@example.com" not in (data / "email_optin.json").read_text()
    assert oct((data / "email_optin.json").stat().st_mode & 0o777) == "0o600"
