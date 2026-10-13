"""Real py_webauthn round-trip with a software authenticator (no browser)."""
import pytest

pytest.importorskip("webauthn")

from app.auth.errors import AuthError
from app.auth.webauthn_backend import PyWebAuthnBackend
from tests.auth_helpers import make_service
from tests.softauth import SoftAuthenticator, selfcheck_assertion, selfcheck_registration

RP, ORIGIN = "zeim.test", "https://zeim.test"


def backend():
    return PyWebAuthnBackend(RP, "ZEIM", (ORIGIN,))


def test_real_signup_and_signin_round_trip():
    svc = make_service(backend=backend())
    auth = SoftAuthenticator(RP, ORIGIN)
    b = svc.signup_begin("Sam", "1990-01-01", "1.1.1.1")
    cred = auth.create(b["options"])
    selfcheck_registration(cred, RP, b["options"]["challenge"], ORIGIN)
    token, s = svc.signup_finish(b["ceremony_id"], cred, "laptop", "ua")
    auth.user_handle = s.account_id.encode()
    b = svc.signin_begin("1.1.1.1")
    token2, s2 = svc.signin_finish(b["ceremony_id"], auth.get(b["options"]), "ua", "1.1.1.1")
    assert s2.account_id == s.account_id


def test_real_rejects_wrong_origin_and_bad_signature():
    from cryptography.hazmat.primitives.asymmetric import ec
    be = backend()
    auth = SoftAuthenticator(RP, ORIGIN)
    opts, ch = be.registration_options(user_id=b"acc_x", user_name="Sam", display_name="Sam", exclude_ids=[])
    with pytest.raises(AuthError):
        be.verify_registration(credential=auth.create(opts, origin="https://evil.example"), challenge=ch)
    reg = be.verify_registration(credential=auth.create(opts), challenge=ch)
    opts, ch = be.authentication_options()
    with pytest.raises(AuthError):
        be.verify_authentication(credential=auth.get(opts, sign_with=ec.generate_private_key(ec.SECP256R1())),
                                 challenge=ch, public_key=reg.public_key, sign_count=0)
    res = be.verify_authentication(credential=auth.get(opts), challenge=ch, public_key=reg.public_key, sign_count=0)
    assert res.new_sign_count == 2
