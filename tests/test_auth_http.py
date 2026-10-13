"""HTTP-level auth tests: CSRF, cookie flags, and end-to-end flows through the (unmounted) router."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import init_auth, router
from tests.auth_helpers import SoftKey, make_service

H = {"X-Requested-With": "zeim", "Origin": "https://zeim.test"}


def client(**kw):
    app = FastAPI(); svc = make_service(**kw); init_auth(app, service=svc); app.include_router(router)
    return TestClient(app, base_url="https://zeim.test"), svc


def do_signup(c, born="1990-01-01"):
    key = SoftKey()
    b = c.post("/api/auth/signup/begin", json={"display_name": "Sam", "birth_date": born}, headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/signup/finish", json={"ceremony_id": b.json()["ceremony_id"],
               "credential": key.register(b.json()["options"]), "name": "laptop"}, headers=H)
    return key, r


def test_signup_sets_host_cookie_with_safe_flags():
    c, _ = client()
    _, r = do_signup(c)
    assert r.status_code == 201
    sc = r.headers["set-cookie"]
    assert sc.startswith("__Host-zeim_session=")
    low = sc.lower()
    assert "httponly" in low and "secure" in low and "path=/" in low and "samesite=lax" in low and "domain" not in low
    assert r.headers["cache-control"] == "no-store"
    assert c.get("/api/auth/session").json() == {"signed_in": True}


def test_csrf_header_required():
    c, _ = client()
    r = c.post("/api/auth/signin/begin", headers={"Origin": "https://zeim.test"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf"


def test_foreign_origin_rejected():
    c, _ = client()
    r = c.post("/api/auth/signin/begin", headers={"X-Requested-With": "zeim", "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_under_18_rejected_over_http():
    c, _ = client()
    r = c.post("/api/auth/signup/begin", json={"display_name": "Kid", "birth_date": "2015-01-01"}, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "too_young"


def test_signin_then_sign_out_everywhere():
    c, _ = client()
    key, _ = do_signup(c)
    c.cookies.clear()
    b = c.post("/api/auth/signin/begin", headers=H).json()
    r = c.post("/api/auth/signin/finish", json={"ceremony_id": b["ceremony_id"], "credential": key.assertion(b["options"])}, headers=H)
    assert r.status_code == 200
    assert c.get("/api/auth/account").status_code == 200
    r = c.post("/api/auth/sessions/revoke-all", json={}, headers=H)
    assert r.status_code == 200 and r.json()["signed_out"] >= 2
    c.cookies.clear()
    assert c.get("/api/auth/account").status_code == 401


def test_rate_limit_returns_retry_after():
    from app.auth.config import Limits
    c, _ = client(limits=Limits(signin_begin_ip=(1, 300)))
    c.post("/api/auth/signin/begin", headers=H)
    r = c.post("/api/auth/signin/begin", headers=H)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_legacy_resolver_upgrade_keeps_owner_id():
    app = FastAPI(); svc = make_service()
    init_auth(app, service=svc, legacy_resolver=lambda req: ("legacy-42", "Old Sam")); app.include_router(router)
    c = TestClient(app, base_url="https://zeim.test")
    key = SoftKey()
    b = c.post("/api/auth/passkeys/begin", headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/passkeys/finish", json={"ceremony_id": b.json()["ceremony_id"],
               "credential": key.register(b.json()["options"]), "name": "phone"}, headers=H)
    assert r.status_code == 201, r.text
    tok = r.cookies.get("__Host-zeim_session") or c.cookies.get("__Host-zeim_session")
    assert svc.resolve_session(tok).owner_id == "legacy-42"
