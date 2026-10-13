"""Auth session end-to-end (docs/auth.md open item 4): with a live passkey/email session, builds and Showcase
ownership use the auth owner_id on every device; the old p3d_sid cookie login keeps working alongside it."""
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
    """The real ZEIM app with its auth service swapped for one that uses a fake passkey backend (same ZEIM hooks)."""
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


def build(c, sample):
    r = c.post("/api/generate", files={"file": ("s.png", open(sample, "rb"), "image/png")},
               data={"mode": "lithophane", "width_mm": "40", "resolution": "40"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def ids(c):
    return {b["id"] for b in c.get("/api/builds").json()["builds"]}


def passkey_signup(c, name="Passkey Pat", born="1990-01-01"):
    key = SoftKey()
    b = c.post("/api/auth/signup/begin", json={"display_name": name, "birth_date": born}, headers=H)
    assert b.status_code == 200, b.text
    r = c.post("/api/auth/signup/finish", json={"ceremony_id": b.json()["ceremony_id"],
               "credential": key.register(b.json()["options"]), "name": "laptop"}, headers=H)
    assert r.status_code == 201, r.text
    return key


def passkey_signin(c, key):
    b = c.post("/api/auth/signin/begin", headers=H).json()
    r = c.post("/api/auth/signin/finish", json={"ceremony_id": b["ceremony_id"], "credential": key.assertion(b["options"])}, headers=H)
    assert r.status_code == 200, r.text


def session_of(c, svc):
    return svc.resolve_session(c.cookies.get(svc.cfg.cookie_name))


def test_passkey_account_owns_builds_on_every_device(zapp):
    app, svc, sample = zapp
    a = browser(app)
    guest_bid = build(a, sample)                       # made while signed out on this browser
    key = passkey_signup(a)
    me = a.get("/api/me").json()
    s = session_of(a, svc)
    assert me["signed_up"] is True and me["id"] == s.owner_id == s.account_id
    assert me["display_name"] == "Passkey Pat" and me["username"]
    assert guest_bid in ids(a)                         # signed-out builds on this browser follow the new account
    rec = next(u for u in USERS.read().values() if u["id"] == s.owner_id)
    assert rec.get("dob") == "1990-01-01"              # 18+ was checked at sign-up; the record carries the date like cookie accounts

    b = browser(app)                                   # a second device
    assert guest_bid not in ids(b)
    passkey_signin(b, key)
    assert b.get("/api/me").json()["id"] == s.owner_id
    assert guest_bid in ids(b)
    bid2 = build(b, sample)
    assert bid2 in ids(a)                              # same account on both devices
    assert b.get(f"/api/builds/{guest_bid}").status_code == 200


def test_showcase_ownership_follows_auth_owner(zapp):
    app, svc, sample = zapp
    a = browser(app)
    key = passkey_signup(a, name="Show Sam")
    bid = build(a, sample)
    p = a.post("/api/showcase", json={"build_id": bid, "title": "Auth owned plate", "accept_guidelines": True,
                                      "visibility": "public"})
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    b = browser(app)
    assert b.get(f"/api/showcase/{pid}").json().get("owned") is False
    passkey_signin(b, key)
    item = b.get(f"/api/showcase/{pid}").json()
    assert item.get("owned") is True
    owner_key = next(i for i in __import__("app.community.store", fromlist=["LISTINGS"]).LISTINGS.read() if i["id"] == pid)["owner_sid"]
    assert USERS.read()[owner_key]["id"] == session_of(b, svc).owner_id


def test_logout_returns_browser_to_its_own_cookie_identity(zapp):
    app, svc, sample = zapp
    a = browser(app)
    passkey_signup(a, name="Leaving Lee")
    bid = build(a, sample)
    assert a.post("/api/auth/logout", headers=H).status_code == 200
    a.cookies.delete(svc.cfg.cookie_name)
    me = a.get("/api/me").json()
    assert me["signed_up"] is False
    assert bid not in ids(a)                           # account builds stay with the account, not the signed-out browser


def test_me_signout_also_ends_the_passkey_session(zapp):
    app, svc, sample = zapp
    a = browser(app)
    passkey_signup(a, name="Signout Sue")
    tok = a.cookies.get(svc.cfg.cookie_name)
    assert svc.resolve_session(tok) is not None
    r = a.post("/api/me/signout")
    assert r.status_code == 200
    assert svc.resolve_session(tok) is None
    a.cookies.delete(svc.cfg.cookie_name)
    assert a.get("/api/me").json()["signed_up"] is False


def test_legacy_cookie_account_keeps_its_id_and_builds_after_passkey_upgrade(zapp):
    app, svc, sample = zapp
    a = browser(app)
    assert a.post("/api/me/signup", json={"display_name": "Old Olive", "dob": "1985-03-04"}).status_code == 200
    legacy_id = a.get("/api/me").json()["id"]
    bid = build(a, sample)
    key = SoftKey()
    bg = a.post("/api/auth/passkeys/begin", headers=H)
    assert bg.status_code == 200, bg.text
    r = a.post("/api/auth/passkeys/finish", json={"ceremony_id": bg.json()["ceremony_id"],
               "credential": key.register(bg.json()["options"]), "name": "phone"}, headers=H)
    assert r.status_code == 201, r.text
    assert session_of(a, svc).owner_id == legacy_id
    assert a.get("/api/me").json()["id"] == legacy_id and bid in ids(a)

    b = browser(app)                                   # new phone, passkey only
    passkey_signin(b, key)
    assert b.get("/api/me").json()["id"] == legacy_id
    assert bid in ids(b)
    assert session_of(b, svc).owner_id == legacy_id


def test_cookie_login_unchanged_without_auth_session(zapp):
    app, svc, sample = zapp
    a = browser(app)
    assert a.post("/api/me/signup", json={"display_name": "Cookie Cal", "dob": "1980-01-01"}).status_code == 200
    bid = build(a, sample)
    assert a.cookies.get(svc.cfg.cookie_name) is None
    assert bid in ids(a) and a.get("/api/me").json()["signed_up"] is True


def test_browser_with_own_cookie_account_is_never_merged(zapp):
    app, svc, sample = zapp
    a = browser(app)
    key = passkey_signup(a, name="Pass Pia")
    pass_bid = build(a, sample)
    b = browser(app)
    assert b.post("/api/me/signup", json={"display_name": "Cookie Cory", "dob": "1980-01-01"}).status_code == 200
    cory_id = b.get("/api/me").json()["id"]
    cory_bid = build(b, sample)
    passkey_signin(b, key)                             # Pia signs in on Cory's browser
    assert pass_bid in ids(b) and cory_bid not in ids(b)
    assert cory_bid not in ids(a)                      # Cory's builds were not pulled into Pia's account
    b.post("/api/auth/logout", headers=H); b.cookies.delete(svc.cfg.cookie_name)
    assert b.get("/api/me").json()["id"] == cory_id and cory_bid in ids(b)


def test_account_keys_cannot_be_used_as_browser_cookie(zapp):
    app, svc, sample = zapp
    a = browser(app)
    passkey_signup(a, name="Key Kim")
    key = next(k for k, u in USERS.read().items() if u.get("display_name") == "Key Kim")
    assert key.startswith("acct_")
    evil = browser(app)
    evil.cookies.set(idn.COOKIE, key)
    assert evil.get("/api/me").json()["signed_up"] is False


def test_missing_legacy_record_is_not_invented(zapp):
    """An auth session linked to a cookie account whose record is gone falls back to the browser cookie."""
    app, svc, sample = zapp
    aid = svc.ensure_legacy_account("gone-legacy-id", "Ghost")
    tok, _s = svc.session_for_legacy(aid, "ua")
    a = browser(app)
    a.cookies.set(svc.cfg.cookie_name, tok)
    assert a.get("/api/me").json()["signed_up"] is False
    assert not any(u.get("id") == "gone-legacy-id" for u in USERS.read().values())


def test_passkey_signup_runs_zeim_display_name_filter(zapp):
    app, svc, sample = zapp
    a = browser(app)
    r = a.post("/api/auth/signup/begin", json={"display_name": "kid@example.com", "birth_date": "1990-01-01"}, headers=H)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bad_name"
    r = a.post("/api/auth/signup/begin", json={"display_name": "Young", "birth_date": "2012-01-01"}, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "too_young"


def test_link_auth_account_is_idempotent():
    k1, u1 = idn.link_auth_account("acc_idem_test", "Idem", "1990-01-01")
    k2, u2 = idn.link_auth_account("acc_idem_test", "Other name", None)
    assert k1 == k2 and u2["display_name"] == "Idem" and u1["id"] == "acc_idem_test"


def test_mount_wires_zeim_hooks():
    from app.main import app
    if not getattr(app.state, "auth_mounted", False):
        pytest.skip("auth not mounted in this environment")
    from app.api import auth as auth_api
    svc = app.state.auth_service
    assert svc.on_account_created is auth_api.zeim_account_created
    assert app.state.on_signed_in is auth_api.zeim_signed_in
