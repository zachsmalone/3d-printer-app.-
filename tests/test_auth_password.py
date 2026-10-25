"""Username/email + password, beside passkeys.

Covers register, login, a wrong password, adding a password to a passkey account
(including one whose username is ZeimApp), and that the passkey still signs in.
Passwords are Argon2id hashes. The plaintext never lands in the database or a log line.
"""
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import init_auth, router, zeim_account_created, zeim_signup_validator
from app.auth.config import AuthConfig, Limits
from app.auth.errors import AuthError, RateLimited
from app.auth.mailer import NullMailer
from app.auth.service import AuthService
from app.auth.store import AuthStore
from app.community.store import USERS
from app.community.usernames import UsernameError
from tests.auth_helpers import FakeBackend, FakeClock, FakeMailer, SoftKey, add_email, make_service, signup

H = {"X-Requested-With": "zeim", "Origin": "https://zeim.test"}
PW = "correct horse battery"


@pytest.fixture
def community_users():
    """Password tests that create ZEIM account records must not leave them behind.

    tests/test_b2_usernames.py asserts every username in the shared file is unique.
    """
    before = set(USERS.read().keys())
    yield
    def f(d):
        for k in [k for k in d if k not in before]:
            d.pop(k, None)
    USERS.update(f)


def _register(svc, username="MakerSam", password=PW, email=None, name="Sam", born="1990-05-01", ip="1.1.1.1"):
    return svc.password_register(name, born, username, password, email, "ua", ip)


def test_register_then_login_with_username_any_case():
    svc = make_service()
    token, session, flags = _register(svc)
    assert flags == {"email_pending": False, "email_skipped": False}
    assert svc.resolve_session(token).account_id == session.account_id
    token2, s2 = svc.password_login("makersam", PW, "ua", "2.2.2.2")
    assert s2.account_id == session.account_id and token2 != token
    assert svc.overview(s2)["has_password"] is True
    assert svc.overview(s2)["login_name"] == "makersam"


def test_wrong_password_and_unknown_account_look_the_same(caplog):
    svc = make_service()
    _register(svc)
    caplog.set_level("DEBUG")
    with pytest.raises(AuthError) as bad:
        svc.password_login("MakerSam", "not the password", "ua", "3.3.3.3")
    with pytest.raises(AuthError) as missing:
        svc.password_login("NobodyHere", "not the password", "ua", "3.3.3.3")
    assert bad.value.code == missing.value.code == "signin_failed"
    assert bad.value.message == missing.value.message
    assert "not the password" not in bad.value.message
    dump = svc.store.dump_text()
    assert PW not in dump and "not the password" not in dump
    assert "$argon2id$" in dump
    blob = dump + caplog.text
    assert PW not in blob and "not the password" not in blob


def test_short_password_and_password_equal_to_username_are_refused():
    svc = make_service()
    with pytest.raises(AuthError) as e:
        _register(svc, password="short")
    assert e.value.code == "bad_password" and e.value.status == 422
    with pytest.raises(AuthError) as e:
        _register(svc, username="MakerSamOK", password="MakerSamOK")
    assert e.value.code == "bad_password"
    assert svc.store.one("SELECT COUNT(*) AS n FROM accounts")["n"] == 0


def test_duplicate_username_is_refused_and_rename_follows_the_password():
    svc = make_service()
    _, session, _ = _register(svc, username="OldMaker")
    with pytest.raises(AuthError) as e:
        _register(svc, username="oldmaker", name="Other")
    assert e.value.code == "username_taken"
    svc.prepare_login_rename(session.account_id, "NewMaker")
    svc.sync_login_name(session.account_id, "NewMaker")
    assert svc.password_login("NewMaker", PW, "ua", "1.2.3.4")[1].account_id == session.account_id
    with pytest.raises(AuthError):
        svc.password_login("OldMaker", PW, "ua", "1.2.3.4")


def test_legacy_cookie_account_can_add_a_password_without_a_new_signup(community_users):
    from app.community.store import USERS
    sid = "cookie-sid-legacy-password-test-001"
    uid = "legacy-user-pw-1"
    USERS.update(lambda d: d.__setitem__(sid, {
        "id": uid, "display_name": "Lee", "username": "LeeMaker", "dob": "1990-01-01"}))
    app = FastAPI()
    svc = make_service()
    init_auth(app, service=svc, legacy_resolver=lambda req: (uid, "Lee") if req.cookies.get("p3d_sid") == sid else None)
    app.include_router(router)
    c = TestClient(app, base_url="https://zeim.test")
    c.cookies.set("p3d_sid", sid)
    r = c.post("/api/auth/password/add", json={"password": PW}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["login_name"] == "leemaker"
    assert svc.is_upgraded(uid)
    fresh = TestClient(app, base_url="https://zeim.test")
    ok = fresh.post("/api/auth/password/login", json={"identifier": "LeeMaker", "password": PW}, headers=H)
    assert ok.status_code == 200
    assert fresh.get("/api/auth/account").json()["login_name"] == "leemaker"


def test_under_18_password_signup_stores_nothing():
    svc = make_service()
    with pytest.raises(AuthError) as e:
        _register(svc, born="2015-01-01")
    assert e.value.code == "too_young"
    assert svc.store.one("SELECT COUNT(*) AS n FROM accounts")["n"] == 0


def test_login_failure_is_rate_limited():
    svc = make_service(limits=Limits(password_login_fail_ip=(2, 900)))
    _register(svc)
    for _ in range(2):
        with pytest.raises(AuthError):
            svc.password_login("MakerSam", "wrong password", "ua", "9.9.9.9")
    with pytest.raises(RateLimited) as e:
        svc.password_login("MakerSam", "wrong password", "ua", "9.9.9.9")
    assert e.value.status == 429 and e.value.retry_after > 0


def test_passkey_still_works_after_a_password_is_added_and_can_be_removed():
    svc = make_service()
    key, token, session = signup(svc)
    added = svc.password_add(session, PW, "PhoneSam")
    assert added["login_name"] == "phonesam"
    b = svc.signin_begin("1.1.1.1")
    token2, s2 = svc.signin_finish(b["ceremony_id"], key.assertion(b["options"]), "ua", "1.1.1.1")
    assert s2.account_id == session.account_id
    token3, s3 = svc.password_login("PhoneSam", PW, "ua", "4.4.4.4")
    assert s3.account_id == session.account_id
    with pytest.raises(AuthError) as e:
        svc.password_login("PhoneSam", "wrong password", "ua", "4.4.4.4")
    assert e.value.code == "signin_failed"
    # the password counts as another way in, so the passkey may be removed
    cred_id = key.id
    svc.remove_passkey(s2, cred_id)
    b = svc.signin_begin("1.1.1.1")
    with pytest.raises(AuthError):
        svc.signin_finish(b["ceremony_id"], key.assertion(b["options"]), "ua", "1.1.1.1")
    assert svc.password_login("phonesam", PW, "ua", "4.4.4.4")[1].account_id == session.account_id
    assert PW not in svc.store.dump_text()


def test_adding_a_password_needs_a_recent_sign_in():
    clock = FakeClock()
    svc = make_service(clock=clock)
    _, token, _ = signup(svc)
    clock.advance(16 * 60)
    session = svc.resolve_session(token)
    with pytest.raises(AuthError) as e:
        svc.password_add(session, PW, "RecentSam")
    assert e.value.code == "reauth_required"


def test_email_code_sets_a_password_on_a_passkey_account_and_signs_in(caplog):
    caplog.set_level("DEBUG")
    m = FakeMailer()
    svc = make_service(mailer=m)
    key, token, session = signup(svc)
    add_email(svc, m, session, "Zach@Example.com")
    before = m.count()
    svc.password_reset_request("nobody@example.com", "1.1.1.1")
    assert m.count() == before
    svc.password_reset_request("zach@example.com", "1.1.1.1")
    code = m.last_code("zach@example.com")
    assert "set a password" in m.sent[-1][2].lower()
    assert PW not in m.sent[-1][2]
    new_token, signed = svc.password_reset_confirm("zach@example.com", code, PW, "ua", "1.1.1.1")
    assert signed.account_id == session.account_id
    assert svc.resolve_session(token) is None          # other sessions ended
    assert svc.resolve_session(new_token).account_id == session.account_id
    assert svc.password_login("zach@example.com", PW, "ua", "5.5.5.5")[1].account_id == session.account_id
    b = svc.signin_begin("1.1.1.1")
    assert svc.signin_finish(b["ceremony_id"], key.assertion(b["options"]), "ua", "1.1.1.1")[1].account_id == session.account_id
    assert "zach@example.com" not in svc.store.dump_text().lower()
    assert PW not in svc.store.dump_text() and PW not in caplog.text


def test_change_password_signs_out_other_devices():
    svc = make_service()
    token, session, _ = _register(svc, username="ChangeSam")
    token2, other = svc.password_login("ChangeSam", PW, "ua", "6.6.6.6")
    svc.password_change(session, PW, "a different phrase")
    assert svc.resolve_session(token2) is None
    assert svc.resolve_session(token) is not None
    with pytest.raises(AuthError):
        svc.password_login("ChangeSam", PW, "ua", "6.6.6.6")
    assert svc.password_login("ChangeSam", "a different phrase", "ua", "6.6.6.6")[1].account_id == other.account_id


def test_signup_hook_failure_removes_the_new_account():
    svc = make_service()

    def boom(*_a, **_k):
        raise UsernameError("That name is taken. Please pick another.")

    svc.on_account_created = boom
    with pytest.raises(AuthError) as e:
        _register(svc, username="TakenName")
    assert e.value.code == "bad_username"
    assert svc.store.one("SELECT COUNT(*) AS n FROM accounts")["n"] == 0


def test_mailer_off_does_not_pretend_an_email_was_saved():
    svc = make_service(mailer=NullMailer())
    _, session, flags = _register(svc, email="sam@example.com")
    assert flags["email_pending"] is False and flags["email_skipped"] is True
    assert svc.overview(session)["email"] is None
    assert "sam@example.com" not in svc.store.dump_text().lower()


def test_old_auth_database_gains_password_columns_without_dropping_accounts(tmp_path):
    path = tmp_path / "auth.sqlite3"
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE accounts(
        id TEXT PRIMARY KEY, legacy_id TEXT UNIQUE, display_name TEXT NOT NULL DEFAULT '',
        email_hash TEXT UNIQUE, email_hint TEXT, email_verified_at REAL,
        created_at REAL NOT NULL, disabled_at REAL)""")
    db.execute("INSERT INTO accounts(id, display_name, created_at) VALUES('acc_zeimapp','Zach',1)")
    db.commit()
    db.close()
    store = AuthStore(str(path))
    row = store.one("SELECT display_name, login_name, password_hash FROM accounts WHERE id='acc_zeimapp'")
    assert row["display_name"] == "Zach" and row["login_name"] is None and row["password_hash"] is None
    store.close()


def _set_username(account_id, username):
    def f(d):
        for u in d.values():
            if u.get("id") == account_id:
                u["username"] = username
    USERS.update(f)


def test_zeimapp_passkey_account_adds_a_password_and_passkey_still_works(caplog, community_users):
    """The live account already has username ZeimApp. That name is allowed
    (only the bare word zeim is reserved), and the saved name must still
    become the password sign-in name. Nothing about the account is deleted."""
    caplog.set_level("DEBUG")
    cfg = AuthConfig(rp_id="zeim.test", origins=("https://zeim.test",), pepper=b"p" * 40, mail_async=False)
    svc = AuthService(cfg, AuthStore(":memory:"), FakeBackend(), FakeMailer(), clock=FakeClock(),
                      signup_validator=zeim_signup_validator(cfg), on_account_created=zeim_account_created)
    key, token, session = signup(svc, name="Zach")
    _set_username(session.account_id, "ZeimApp")
    out = svc.password_add(session, PW, "ZeimApp")
    assert out["login_name"] == "zeimapp"
    for typed in ("ZeimApp", "zeimapp", "ZEIMAPP"):
        assert svc.password_login(typed, PW, "ua", "7.7.7.7")[1].account_id == session.account_id
    b = svc.signin_begin("1.1.1.1")
    assert svc.signin_finish(b["ceremony_id"], key.assertion(b["options"]), "ua", "1.1.1.1")[1].account_id == session.account_id
    assert svc.resolve_session(token).account_id == session.account_id
    assert PW not in svc.store.dump_text() and PW not in caplog.text
    # the community record is still there, under the same id
    assert any(u.get("id") == session.account_id and u.get("username") == "ZeimApp" for u in USERS.read().values())


def test_http_register_login_wrong_password_and_zeimapp_add(caplog, community_users):
    caplog.set_level("DEBUG")
    cfg = AuthConfig(rp_id="zeim.test", origins=("https://zeim.test",), pepper=b"p" * 40, mail_async=False)
    svc = AuthService(cfg, AuthStore(":memory:"), FakeBackend(), FakeMailer(), clock=FakeClock(),
                      signup_validator=zeim_signup_validator(cfg), on_account_created=zeim_account_created)
    app = FastAPI()
    init_auth(app, service=svc)
    app.include_router(router)
    c = TestClient(app, base_url="https://zeim.test")

    no_csrf = c.post("/api/auth/password/login", json={"identifier": "x", "password": PW},
                     headers={"Origin": "https://zeim.test"})
    assert no_csrf.status_code == 403 and no_csrf.json()["detail"]["code"] == "csrf"

    kid = c.post("/api/auth/password/register", json={"display_name": "Kid", "birth_date": "2015-01-01",
                 "username": "KidMaker", "password": PW}, headers=H)
    assert kid.status_code == 403 and kid.json()["detail"]["code"] == "too_young"

    reserved = c.post("/api/auth/password/register", json={"display_name": "Zach", "birth_date": "1990-01-01",
                      "username": "adminx", "password": PW}, headers=H)
    assert reserved.status_code == 422 and reserved.json()["detail"]["code"] == "bad_username"

    made = c.post("/api/auth/password/register", json={"display_name": "Pat", "birth_date": "1990-05-01",
                  "username": "PatMaker", "password": PW}, headers=H)
    assert made.status_code == 201, made.text
    cookie = made.headers["set-cookie"].lower()
    assert cookie.startswith("__host-zeim_session=") and "httponly" in cookie and "secure" in cookie
    assert any(u.get("username") == "PatMaker" for u in USERS.read().values())
    assert PW not in svc.store.dump_text() and PW not in caplog.text

    c.cookies.clear()
    bad = c.post("/api/auth/password/login", json={"identifier": "PatMaker", "password": "wrong password"}, headers=H)
    assert bad.status_code == 401 and bad.json()["detail"]["code"] == "signin_failed"
    assert "set-cookie" not in {k.lower() for k in bad.headers.keys()} or "zeim_session=" not in bad.headers.get("set-cookie", "")
    ok = c.post("/api/auth/password/login", json={"identifier": "patmaker", "password": PW}, headers=H)
    assert ok.status_code == 200 and c.get("/api/auth/session").json()["signed_in"] is True

    # passkey account whose saved username is ZeimApp: add a password without sending the name again
    c.cookies.clear()
    key = SoftKey()
    b = c.post("/api/auth/signup/begin", json={"display_name": "Zach", "birth_date": "1990-01-01"}, headers=H)
    assert b.status_code == 200, b.text
    fin = c.post("/api/auth/signup/finish", json={"ceremony_id": b.json()["ceremony_id"],
                 "credential": key.register(b.json()["options"]), "name": "phone"}, headers=H)
    assert fin.status_code == 201, fin.text
    session = svc.resolve_session(c.cookies.get("__Host-zeim_session"))
    _set_username(session.account_id, "ZeimApp")
    add = c.post("/api/auth/password/add", json={"password": PW}, headers=H)
    assert add.status_code == 200, add.text
    assert add.json()["login_name"] == "zeimapp"
    assert svc.overview(session)["has_password"] is True

    c.cookies.clear()
    again = c.post("/api/auth/password/login", json={"identifier": "ZeimApp", "password": PW}, headers=H)
    assert again.status_code == 200
    c.cookies.clear()
    begin = c.post("/api/auth/signin/begin", headers=H).json()
    pk = c.post("/api/auth/signin/finish", json={"ceremony_id": begin["ceremony_id"],
                "credential": key.assertion(begin["options"])}, headers=H)
    assert pk.status_code == 200
    acct = c.get("/api/auth/account").json()
    assert acct["has_password"] is True and acct["login_name"] == "zeimapp"
    assert "password_hash" not in acct and PW not in str(acct)
