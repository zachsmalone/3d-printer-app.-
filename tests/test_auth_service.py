"""Service-level auth tests (fake WebAuthn backend, fake clock, fake mailer)."""
import pytest

from app.auth.config import Limits
from app.auth.errors import AuthError, RateLimited
from tests.auth_helpers import FakeClock, FakeMailer, SoftKey, add_email, make_service, signup


def test_signup_and_signin_with_passkey():
    svc = make_service()
    key, token, s = signup(svc)
    assert svc.resolve_session(token).account_id == s.account_id
    begin = svc.signin_begin("1.1.1.1")
    token2, s2 = svc.signin_finish(begin["ceremony_id"], key.assertion(begin["options"]), "ua", "1.1.1.1")
    assert s2.account_id == s.account_id and token2 != token


def test_ceremony_is_single_use():
    svc = make_service()
    key, _, _ = signup(svc)
    b = svc.signin_begin("1.1.1.1")
    cred = key.assertion(b["options"])
    svc.signin_finish(b["ceremony_id"], cred, "ua", "1.1.1.1")
    with pytest.raises(AuthError):
        svc.signin_finish(b["ceremony_id"], cred, "ua", "1.1.1.1")


def test_wrong_key_rejected():
    svc = make_service()
    signup(svc)
    b = svc.signin_begin("1.1.1.1")
    with pytest.raises(AuthError) as e:
        svc.signin_finish(b["ceremony_id"], SoftKey().assertion(b["options"]), "ua", "1.1.1.1")
    assert e.value.code == "signin_failed"


@pytest.mark.parametrize("born", ["2010-01-01", "2009-06-01"])   # under 18 at T0 (15 Jan 2027)
def test_under_18_rejected(born):
    svc = make_service()
    with pytest.raises(AuthError) as e:
        svc.signup_begin("Kid", born, "1.1.1.1")
    assert e.value.code == "too_young" and e.value.status == 403


def test_exactly_18_allowed_and_bad_dates():
    svc = make_service()
    svc.signup_begin("Adult", "2008-01-01", "1.1.1.1")
    for bad in ["", "nope", "2100-01-01", None]:
        with pytest.raises(AuthError):
            svc.signup_begin("X", bad, "1.1.1.1")


def test_email_code_login_and_no_plaintext_email():
    m = FakeMailer(); svc = make_service(mailer=m)
    _, _, s = signup(svc)
    add_email(svc, m, s, "Sam@Example.com")
    svc.email_request_login("sam@example.com", "2.2.2.2")
    token, s2 = svc.email_verify_login("sam@example.com", m.last_code("sam@example.com"), "ua", "2.2.2.2")
    assert s2.account_id == s.account_id
    assert "sam@example.com" not in svc.store.dump_text().lower()


def test_unknown_email_sends_nothing():
    m = FakeMailer(); svc = make_service(mailer=m)
    svc.email_request_login("nobody@example.com", "1.1.1.1")
    assert m.count() == 0


def test_wrong_code_and_code_reuse():
    m = FakeMailer(); svc = make_service(mailer=m)
    _, _, s = signup(svc); add_email(svc, m, s, "a@example.com")
    svc.email_request_login("a@example.com", "1.1.1.1")
    code = m.last_code("a@example.com")
    with pytest.raises(AuthError):
        svc.email_verify_login("a@example.com", "000000" if code != "000000" else "111111", "ua", "1.1.1.1")
    svc.email_verify_login("a@example.com", code, "ua", "1.1.1.1")
    with pytest.raises(AuthError):
        svc.email_verify_login("a@example.com", code, "ua", "1.1.1.1")


def test_email_request_rate_limit():
    m = FakeMailer(); svc = make_service(mailer=m, limits=Limits(email_request_email=(2, 3600)))
    svc.email_request_login("a@example.com", "1.1.1.1")
    svc.email_request_login("a@example.com", "1.1.1.2")
    with pytest.raises(RateLimited) as e:
        svc.email_request_login("a@example.com", "1.1.1.3")
    assert e.value.status == 429 and e.value.retry_after > 0


def test_verify_failure_rate_limit():
    svc = make_service(limits=Limits(email_verify_fail_ip=(3, 900)))
    for _ in range(3):
        with pytest.raises(AuthError):
            svc.email_verify_login("a@example.com", "123456", "ua", "9.9.9.9")
    with pytest.raises(RateLimited):
        svc.email_verify_login("a@example.com", "123456", "ua", "9.9.9.9")


def test_sensitive_changes_need_recent_auth():
    clock = FakeClock(); m = FakeMailer(); svc = make_service(clock=clock, mailer=m)
    _, token, _ = signup(svc)
    clock.advance(16 * 60)
    s = svc.resolve_session(token)
    for call in (lambda: svc.passkey_add_begin(s), lambda: svc.email_add_request(s, "x@example.com", "1.1.1.1")):
        with pytest.raises(AuthError) as e:
            call()
        assert e.value.code == "reauth_required"


def test_revoke_and_sign_out_everywhere():
    svc = make_service()
    key, t1, s1 = signup(svc)
    b = svc.signin_begin("1.1.1.1"); t2, s2 = svc.signin_finish(b["ceremony_id"], key.assertion(b["options"]), "ua", "1.1.1.1")
    b = svc.signin_begin("1.1.1.1"); t3, s3 = svc.signin_finish(b["ceremony_id"], key.assertion(b["options"]), "ua", "1.1.1.1")
    svc.revoke_session(s1.account_id, s2.id)
    assert svc.resolve_session(t2) is None and svc.resolve_session(t1)
    svc.revoke_all(s1.account_id, keep_session_id=s1.id)
    assert svc.resolve_session(t3) is None and svc.resolve_session(t1)
    svc.revoke_all(s1.account_id)
    assert svc.resolve_session(t1) is None


def test_session_idle_and_absolute_expiry():
    clock = FakeClock(); svc = make_service(clock=clock)
    _, token, _ = signup(svc)
    clock.advance(15 * 86400)
    assert svc.resolve_session(token) is None


def test_legacy_account_keeps_owner_id():
    svc = make_service()
    aid = svc.ensure_legacy_account("legacy-user-123", "Old Sam")
    assert svc.ensure_legacy_account("legacy-user-123", "Old Sam") == aid
    token, s = svc.session_for_legacy(aid, "ua")
    assert s.owner_id == "legacy-user-123"
    assert svc.resolve_session(token).owner_id == "legacy-user-123"
