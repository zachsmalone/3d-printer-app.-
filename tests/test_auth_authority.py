"""Sign-out authority: an explicit sign-out must REMOVE authority, not merely hide the
security panel while the old legacy cookie silently signs the same user back in.

Upgraded legacy records keep their users.json key (it owns their builds), so the fix is
to retire the legacy cookie on this browser at the moment authority ends: on upgrade
completion, on logout, on revoke-current-session and on sign-out-everywhere. A DIFFERENT
legacy cookie on the same browser is never part of the session and must survive.
Also covers the /api/me auth capability object the sign-in UI renders from."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig, Limits
from app.auth.service import AuthService
from app.auth.store import AuthStore
from app.api.auth import zeim_account_created, zeim_signed_in, zeim_signup_validator
from app.community import identity as idn
from app.community.store import USERS
from tests.auth_helpers import FakeBackend, FakeClock, FakeMailer, SoftKey
from tests.make_sample import make

BASE = "https://zeim.test"
H = {"X-Requested-With": "zeim", "Origin": BASE}


@pytest.fixture()
def zapp(tmp_path):
    """The real ZEIM app with its auth service swapped for one that uses a fake passkey
    backend (same ZEIM hooks) — the test_auth_session_e2e pattern."""
    from app.main import app
    st = app.state
    saved = (getattr(st, "auth_service", None), getattr(st, "legacy_resolver", None), getattr(st, "on_signed_in", None))
    cfg = AuthConfig(rp_id="zeim.test", origins=(BASE,), pepper=b"p" * 40, mail_async=False, limits=Limits())
    import time
    svc = AuthService(cfg, AuthStore(":memory:"), FakeBackend(), FakeMailer(), clock=FakeClock(time.time()),
                      signup_validator=zeim_signup_validator(cfg), on_account_created=zeim_account_created)
    from app.api.auth import legacy_cookie_resolver
    st.auth_service, st.legacy_resolver, st.on_signed_in = svc, legacy_cookie_resolver, zeim_signed_in
    sample = make(str(tmp_path / "s.png"))
    yield app, svc, sample
    st.auth_service, st.legacy_resolver, st.on_signed_in = saved


def browser(app):
    return TestClient(app, base_url=BASE)


def legacy_signup(c, name="Legacy Lee"):
    r = c.post("/api/me/signup", json={"display_name": name, "dob": "1990-02-02"})
    assert r.status_code == 200, r.text
    return r


def upgrade_with_passkey(c, key=None, cred_name="phone"):
    key = key or SoftKey()
    b = c.post("/api/auth/passkeys/begin", headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/passkeys/finish", json={"ceremony_id": b.json()["ceremony_id"],
               "credential": key.register(b.json()["options"]), "name": cred_name}, headers=H)
    assert r.status_code == 201, r.text
    return key, r


def passkey_signup(c, name="Passkey Pat"):
    key = SoftKey()
    b = c.post("/api/auth/signup/begin", json={"display_name": name, "birth_date": "1990-01-01"}, headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/signup/finish", json={"ceremony_id": b.json()["ceremony_id"],
               "credential": key.register(b.json()["options"]), "name": "laptop"}, headers=H)
    assert r.status_code == 201, r.text
    return key


def build(c, sample):
    r = c.post("/api/generate", files={"file": ("s.png", open(sample, "rb"), "image/png")},
               data={"mode": "lithophane", "width_mm": "40", "resolution": "40"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def my_builds(c):
    return {b["id"] for b in c.get("/api/builds").json()["builds"]}


def test_signout_after_upgrade_removes_authority(zapp):
    """The reviewer's revocation concern, end to end: a legacy cookie account upgrades
    with a passkey, signs out — and the browser must NOT silently fall back to the old
    cookie identity. Authority is gone; signing back in with the passkey returns it."""
    app, svc, sample = zapp
    a = browser(app)
    legacy_signup(a)                                   # a cookie-only account
    assert a.get("/api/me").json()["signed_up"] is True
    bid = build(a, sample)                             # a build owned by the legacy sid
    # upgrade: add a passkey while holding the legacy cookie
    key, r = upgrade_with_passkey(a)
    # the upgrade response RETIRES the legacy cookie on this browser
    setc = " ".join(r.headers.get("set-cookie", "").split("\n") if isinstance(r.headers.get("set-cookie"), list)
                    else [r.headers.get("set-cookie", "")])
    assert f"{idn.COOKIE}=" not in setc or f'Max-Age=0' in setc, setc
    assert idn.COOKIE not in a.cookies                 # gone from the browser
    me = a.get("/api/me").json()
    assert me["signed_up"] is True                     # still the same account, via the session
    assert bid in my_builds(a)                          # ...and its builds are intact
    # sign out: authority must END (the old cookie must not resurrect it)
    out = a.post("/api/auth/logout", headers=H)
    assert out.status_code == 200, out.text
    me = a.get("/api/me").json()
    assert me["signed_up"] is False                     # a guest — NOT the legacy identity
    assert bid not in my_builds(a)                      # private builds are private again
    # sign back in with the same passkey: the account and its build return
    b = a.post("/api/auth/signin/begin", headers=H).json()
    fin = a.post("/api/auth/signin/finish", json={"ceremony_id": b["ceremony_id"],
                 "credential": key.assertion(b["options"])}, headers=H)
    assert fin.status_code == 200, fin.text
    assert a.get("/api/me").json()["signed_up"] is True
    assert bid in my_builds(a)


def test_a_different_legacy_cookie_survives_signout(zapp):
    """A browser holding legacy account A's cookie signs in as passkey account B and
    signs out: A's cookie was never part of B's session and must keep working."""
    app, svc, sample = zapp
    a = browser(app)
    legacy_signup(a, "Legacy Lee")                      # A: cookie-only account
    # B: a passkey-born account (no legacy cookie involved)
    key = passkey_signup(a, "Passkey Pat")
    # hmm: signing up on THIS browser while A's cookie exists creates B under... check:
    # signup is a fresh auth account; A's cookie stays untouched.
    me = a.get("/api/me").json()
    assert me["signed_up"] is True
    assert a.cookies.get(idn.COOKIE) is not None        # A's legacy cookie still present
    out = a.post("/api/auth/logout", headers=H)
    assert out.status_code == 200, out.text
    # A's legacy cookie survives B's sign-out (different account — never part of the session)
    me = a.get("/api/me").json()
    assert me["signed_up"] is True                      # back to A, the legacy identity


def test_revoke_all_signs_out_the_legacy_identity_too(zapp):
    app, svc, sample = zapp
    a = browser(app)
    legacy_signup(a)
    key, _ = upgrade_with_passkey(a)
    r = a.post("/api/auth/sessions/revoke-all", json={"keep_current": False}, headers=H)
    assert r.status_code == 200, r.text
    me = a.get("/api/me").json()
    assert me["signed_up"] is False                     # authority fully removed


def test_revoke_current_session_retires_legacy_identity(zapp):
    app, svc, sample = zapp
    a = browser(app)
    legacy_signup(a)
    key, _ = upgrade_with_passkey(a)
    s = svc.resolve_session(a.cookies.get(svc.cfg.cookie_name))
    r = a.delete(f"/api/auth/sessions/{s.id}", headers=H)
    assert r.status_code == 200, r.text
    me = a.get("/api/me").json()
    assert me["signed_up"] is False                     # not silently back as the legacy cookie


def test_me_exposes_auth_capabilities(zapp):
    """The sign-in UI renders from /api/me's auth capability object — derived from what
    is actually mounted (never from a request merely succeeding), with no internals."""
    app, svc, sample = zapp
    a = browser(app)
    me = a.get("/api/me").json()
    assert me["auth"]["available"] is True
    assert me["auth"]["email_codes"] is True            # the fake mailer counts as enabled
    assert me["auth"]["session"] is False               # guest
    passkey_signup(a)
    me = a.get("/api/me").json()
    assert me["auth"]["session"] is True                # signed in via the auth session


def test_pages_reference_the_auth_client(zapp):
    """Wiring check: the main page must actually load the auth client + controller —
    an auth system the UI never includes is unreachable (that was the gap this round)."""
    app, svc, sample = zapp
    a = browser(app)
    html = a.get("/").text
    assert "/static/zeim-auth.js" in html
    assert "/static/zeim-auth.css" in html
    assert "/static/zeim-account.js" in html
    for f in ("zeim-auth.js", "zeim-auth.css", "zeim-account.js"):
        r = a.get(f"/static/{f}")
        assert r.status_code == 200, (f, r.status_code)
