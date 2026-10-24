"""Security properties of the (still unmounted) auth router: CSRF, cookie flags, 15-minute reauth,
session revoke, legacy owner ids and the 18+ gate."""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import init_auth, router
from app.auth.config import AuthConfig, ConfigError
from tests.auth_helpers import FakeClock, SoftKey, T0, make_service

H = {"X-Requested-With": "zeim", "Origin": "https://zeim.test"}
COOKIE = "__Host-zeim_session"


def client(resolver=None, **kw):
    clock = FakeClock()
    app = FastAPI(); svc = make_service(clock=clock, **kw)
    init_auth(app, service=svc, legacy_resolver=resolver); app.include_router(router)
    return TestClient(app, base_url="https://zeim.test"), svc, clock


def signup(c, born="1990-01-01"):
    key = SoftKey()
    b = c.post("/api/auth/signup/begin", json={"display_name": "Sam", "birth_date": born}, headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/signup/finish", json={"ceremony_id": b.json()["ceremony_id"],
               "credential": key.register(b.json()["options"]), "name": "laptop"}, headers=H)
    assert r.status_code == 201, r.text
    return key


def signin(c, key):
    b = c.post("/api/auth/signin/begin", headers=H).json()
    r = c.post("/api/auth/signin/finish", json={"ceremony_id": b["ceremony_id"], "credential": key.assertion(b["options"])}, headers=H)
    assert r.status_code == 200, r.text
    return r


# ---- CSRF ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("method,path", [("post", "/api/auth/signup/begin"), ("post", "/api/auth/email/request"),
                                         ("post", "/api/auth/password/login"), ("post", "/api/auth/password/register"),
                                         ("post", "/api/auth/logout"), ("post", "/api/auth/sessions/revoke-all"),
                                         ("delete", "/api/auth/email"), ("delete", "/api/auth/sessions/abc")])
def test_state_changing_routes_need_the_csrf_header(method, path):
    c, _, _ = client()
    kw = {"json": {}} if method == "post" else {}
    r = getattr(c, method)(path, headers={"Origin": "https://zeim.test"}, **kw)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf"


@pytest.mark.parametrize("origin", ["https://evil.example", "http://zeim.test", "https://zeim.test.evil.example", "null"])
def test_foreign_origins_are_rejected_even_with_the_header(origin):
    c, _, _ = client()
    r = c.post("/api/auth/signin/begin", headers={"X-Requested-With": "zeim", "Origin": origin})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf"


def test_wrong_header_value_rejected_and_reads_are_not_blocked():
    c, _, _ = client()
    assert c.post("/api/auth/signin/begin", headers={"X-Requested-With": "XMLHttpRequest", "Origin": "https://zeim.test"}).status_code == 403
    assert c.get("/api/auth/session").status_code == 200


# ---- cookie --------------------------------------------------------------------------------------------------------
def test_host_cookie_flags_on_signin_and_cleared_on_logout():
    c, _, _ = client()
    key = signup(c); c.cookies.clear()
    sc = signin(c, key).headers["set-cookie"]
    low = sc.lower()
    assert sc.startswith(COOKIE + "=") and "httponly" in low and "secure" in low and "path=/" in low
    assert "samesite=lax" in low and "domain=" not in low and "max-age=" in low
    out = c.post("/api/auth/logout", headers=H)
    clear = out.headers["set-cookie"].lower()
    assert out.status_code == 200 and clear.startswith(COOKIE.lower() + "=") and "max-age=0" in clear and "secure" in clear
    c.cookies.clear()
    assert c.get("/api/auth/session").json() == {"signed_in": False}


def test_insecure_cookie_name_only_in_dev():
    env = {"ZEIM_RP_ID": "zeim.test", "ZEIM_ORIGINS": "https://zeim.test", "ZEIM_AUTH_PEPPER": "x" * 32}
    assert AuthConfig.from_env(env).cookie_name == COOKIE
    assert AuthConfig.from_env(env | {"ZEIM_INSECURE_COOKIES": "1"}).cookie_name == COOKIE   # ignored outside dev
    with pytest.raises(ConfigError):
        AuthConfig.from_env(env | {"ZEIM_AUTH_PEPPER": "short"})
    with pytest.raises(ConfigError):
        AuthConfig.from_env(env | {"ZEIM_ORIGINS": "http://zeim.test"})


# ---- 15-minute reauth ----------------------------------------------------------------------------------------------
def _second_key(c):
    k2 = SoftKey()
    b = c.post("/api/auth/passkeys/begin", headers=H).json()
    r = c.post("/api/auth/passkeys/finish", json={"ceremony_id": b["ceremony_id"], "credential": k2.register(b["options"]), "name": "phone"}, headers=H)
    assert r.status_code == 201, r.text
    return [p["id"] for p in c.get("/api/auth/account").json()["passkeys"]]


def test_removing_a_passkey_needs_a_signin_within_15_minutes():
    c, _, clock = client()
    key = signup(c); ids = _second_key(c)
    clock.advance(15 * 60 + 1)
    assert c.get("/api/auth/account").json()["recent_signin"] is False
    r = c.delete(f"/api/auth/passkeys/{ids[1]}", headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reauth_required"
    signin(c, key)                                         # fresh proof of identity
    assert c.delete(f"/api/auth/passkeys/{ids[1]}", headers=H).status_code == 200


def test_within_15_minutes_is_fine():
    c, _, clock = client()
    signup(c); ids = _second_key(c)
    clock.advance(14 * 60)
    assert c.delete(f"/api/auth/passkeys/{ids[1]}", headers=H).status_code == 200


# ---- revoke --------------------------------------------------------------------------------------------------------
def test_revoke_one_device_signs_only_that_device_out():
    c, svc, _ = client()
    key = signup(c)
    other = TestClient(c.app, base_url="https://zeim.test"); signin(other, key)
    devices = c.get("/api/auth/account").json()["devices"]
    assert len(devices) == 2
    theirs = next(d["id"] for d in devices if not d["current"])
    assert c.delete(f"/api/auth/sessions/{theirs}", headers=H).status_code == 200
    assert other.get("/api/auth/account").status_code == 401
    assert c.get("/api/auth/account").status_code == 200


def test_cannot_revoke_someone_elses_session():
    c, _, _ = client()
    signup(c)
    other = TestClient(c.app, base_url="https://zeim.test"); signup(other)
    theirs = other.get("/api/auth/account").json()["devices"][0]["id"]
    assert c.delete(f"/api/auth/sessions/{theirs}", headers=H).status_code == 404
    assert other.get("/api/auth/account").status_code == 200


def test_revoke_all_keep_current():
    c, _, _ = client()
    key = signup(c)
    other = TestClient(c.app, base_url="https://zeim.test"); signin(other, key)
    r = c.post("/api/auth/sessions/revoke-all", json={"keep_current": True}, headers=H)
    assert r.json()["signed_out"] == 1 and "set-cookie" not in r.headers
    assert c.get("/api/auth/account").status_code == 200 and other.get("/api/auth/account").status_code == 401


def test_stolen_token_is_dead_after_logout():
    c, svc, _ = client()
    signup(c); tok = c.cookies.get(COOKIE)
    c.post("/api/auth/logout", headers=H)
    assert svc.resolve_session(tok) is None


# ---- legacy --------------------------------------------------------------------------------------------------------
def test_legacy_upgrade_keeps_owner_id_and_is_stable():
    c, svc, _ = client(resolver=lambda req: ("legacy-42", "Old Sam"))
    k = SoftKey()
    b = c.post("/api/auth/passkeys/begin", headers=H).json()
    r = c.post("/api/auth/passkeys/finish", json={"ceremony_id": b["ceremony_id"], "credential": k.register(b["options"]), "name": "p"}, headers=H)
    assert r.status_code == 201
    s = svc.resolve_session(c.cookies.get(COOKIE))
    assert s.owner_id == "legacy-42" and svc.is_upgraded("legacy-42")
    assert svc.ensure_legacy_account("legacy-42") == s.account_id        # same account on repeat


def test_no_resolver_means_no_legacy_access():
    c, _, _ = client()
    assert c.post("/api/auth/passkeys/begin", headers=H).status_code == 401


def test_legacy_pseudo_session_cannot_revoke_or_remove():
    c, _, _ = client(resolver=lambda req: ("legacy-7", "X"))
    assert c.post("/api/auth/sessions/revoke-all", json={}, headers=H).status_code == 401
    assert c.delete("/api/auth/email", headers=H).status_code == 401


# ---- 18+ -----------------------------------------------------------------------------------------------------------
def _born_years_ago(years, days_offset=0):
    from datetime import timedelta
    today = date.fromtimestamp(T0)
    return (today.replace(year=today.year - years) + timedelta(days=days_offset)).isoformat()


@pytest.mark.parametrize("born", [_born_years_ago(18, 1), _born_years_ago(13), _born_years_ago(17)])
def test_under_18_signup_rejected(born):
    c, svc, _ = client()
    r = c.post("/api/auth/signup/begin", json={"display_name": "Kid", "birth_date": born}, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "too_young" and "18" in r.json()["detail"]["message"]
    assert svc.store.one("SELECT COUNT(*) AS n FROM accounts")["n"] == 0


def test_18th_birthday_today_is_allowed():
    c, _, _ = client()
    signup(c, born=_born_years_ago(18))
