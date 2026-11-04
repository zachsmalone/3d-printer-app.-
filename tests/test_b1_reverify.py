"""Kenji's re-check 1 (reports/safety-reverify-1.md): S-01 in local mode, QR vs forged Host, per-address age gate,
admin-token throttling, cookie flags, security headers, no public /docs."""
import pytest
from fastapi.testclient import TestClient
from app import config
from app.main import app
from tests.b1 import client, ADULT, ADMIN

BODY = {"public_base_url": "https://evil.example", "printers": []}


# ------------------------------------------------------------------ S-01 in local mode (what ./run.sh does)
def test_local_mode_still_works_for_the_owner_on_this_computer(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")
    c = client()
    assert c.put("/api/settings", json={"printers": []}).status_code == 200


@pytest.mark.parametrize("hdrs", [
    {"X-Forwarded-For": "203.0.113.9"},                     # a tunnel / reverse proxy
    {"CF-Connecting-IP": "203.0.113.9"},
    {"Host": "abc-def.trycloudflare.com"},                  # public name
    {"Host": "192.168.1.20:8765"},                          # a LAN visitor
])
def test_local_mode_refuses_settings_from_tunnel_or_lan(monkeypatch, hdrs):
    monkeypatch.setattr(config, "MODE", "local")
    c = client()
    assert c.put("/api/settings", json=BODY, headers=hdrs).status_code == 403
    assert c.get("/api/settings", headers=hdrs).json()["can_edit"] is False
    assert c.delete("/api/accounts/tiktok", headers=hdrs).status_code == 403
    assert c.get("/api/me", headers=hdrs).json()["send"]["role"] == "basic"            # and anonymous visitors are not 'the owner' either
    assert c.put("/api/settings", json=BODY, headers={**hdrs, **ADMIN}).status_code == 200   # the admin token still works
    assert c.put("/api/settings", json={"public_base_url": "", "printers": []}, headers=ADMIN).status_code == 200   # tidy up


def test_local_mode_other_peer_address_is_not_the_owner(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")
    monkeypatch.setattr(config, "LOCAL_CLIENTS", ("127.0.0.1",))                         # the TestClient peer is 'testclient'
    assert client().put("/api/settings", json=BODY).status_code == 403


# ------------------------------------------------------------------ QR / forged Host


# ------------------------------------------------------------------ S-04 per address


def test_age_ip_lock_expires(monkeypatch):
    import time
    monkeypatch.setattr(config, "AGE_IP_LOCK_MINUTES", 30)
    for _ in range(config.AGE_IP_LOCK_AFTER + 1): TestClient(app).post("/api/me/signup", json={"display_name": "kid", "dob": "2018-01-01"})
    real = time.time; monkeypatch.setattr(time, "time", lambda: real() + 31 * 60)
    assert TestClient(app).post("/api/me/signup", json={"display_name": "Ada", "dob": "1985-05-05"}).status_code == 200




# ------------------------------------------------------------------ admin token guessing
def test_admin_token_guesses_are_throttled(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    c = client()
    codes = [c.put("/api/settings", json={"printers": []}, headers={"X-Admin-Token": f"guess{n}"}).status_code for n in range(config.ADMIN_FAIL_LIMIT + 3)]
    assert codes[:config.ADMIN_FAIL_LIMIT] == [403] * config.ADMIN_FAIL_LIMIT and codes[config.ADMIN_FAIL_LIMIT:] == [429] * 3
    assert c.put("/api/settings", json={"printers": []}, headers=ADMIN).status_code == 429          # even the right one waits
    from app.core import ratelimit; ratelimit.reset()
    assert c.put("/api/settings", json={"printers": []}, headers=ADMIN).status_code == 200


# ------------------------------------------------------------------ cookies, headers, docs
def test_session_cookie_is_secure_over_https_and_httponly_always():
    c = TestClient(app, base_url="https://testserver")
    r = c.get("/api/config")
    sc = r.headers.get("set-cookie", "")
    assert "HttpOnly" in sc and "Secure" in sc and "SameSite=lax" in sc, sc
    r = TestClient(app).get("/api/config"); sc = r.headers.get("set-cookie", "")
    assert "HttpOnly" in sc and "Secure" not in sc                                                   # plain http (localhost) must keep working


def test_cookie_secure_flag_can_be_forced(monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", "true")
    assert "Secure" in TestClient(app).get("/api/config").headers["set-cookie"]




def test_security_headers_on_pages_api_and_files():
    c = TestClient(app)
    for url in ("/", "/api/config", "/healthz", "/static/app.js", "/l/nope", "/sharetest"):
        h = c.get(url).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer", url
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "object-src 'none'" in h["content-security-policy"], url
        assert "camera=(self)" in h["permissions-policy"], url
    csp = c.get("/").headers["content-security-policy"]
    assert "script-src 'self' 'sha256-" in csp and "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp
    assert "strict-transport-security" not in c.get("/healthz").headers
    assert "strict-transport-security" in TestClient(app, base_url="https://testserver").get("/healthz").headers


def test_inline_scripts_are_covered_by_csp_hashes():
    import base64, hashlib, re
    csp = TestClient(app).get("/").headers["content-security-policy"]
    for f in ("index.html", "sharetest.html"):
        html = (config.STATIC / f).read_text()
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
            assert "sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode() in csp, f
        assert not re.search(r"\son(click|load|error|change|submit)=", html), "inline event handlers would need unsafe-inline"


def test_api_docs_are_not_public():
    c = TestClient(app)
    for u in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(u).status_code == 404, u
