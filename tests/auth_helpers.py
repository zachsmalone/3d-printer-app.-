"""Test doubles: fake clock, fake mailer, fake WebAuthn backend + a software 'authenticator'."""
import base64
import os
import re
import secrets

from app.auth.config import AuthConfig, Limits
from app.auth.errors import AuthError
from app.auth.service import AuthService
from app.auth.store import AuthStore
from app.auth.webauthn_backend import AuthResult, RegisteredCredential

T0 = 1_800_000_000.0   # a fixed "now" (Jan 2027)


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class FakeClock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, to, subject, text):
        if self.fail:
            raise RuntimeError("smtp down")
        self.sent.append((to, subject, text))

    def last_code(self, to=None):
        msgs = [m for m in self.sent if to is None or m[0] == to]
        return re.search(r"\b(\d{6})\b", msgs[-1][2]).group(1)

    def count(self, to=None):
        return len([m for m in self.sent if to is None or m[0] == to])


class FakeBackend:
    """Stands in for py_webauthn: checks the challenge echo + that the right 'key' signed."""

    def registration_options(self, *, user_id, user_name, display_name, exclude_ids):
        ch = os.urandom(32)
        self.last_reg = {"user_id": user_id, "exclude_ids": list(exclude_ids), "user_name": user_name}
        return {"challenge": b64(ch), "excludeCredentials": [b64(i) for i in exclude_ids]}, ch

    def verify_registration(self, *, credential, challenge):
        if credential.get("challenge") != b64(challenge) or not credential.get("id"):
            raise AuthError("passkey_failed", "We couldn't verify that passkey. Please try again.", 400)
        return RegisteredCredential(id=credential["id"], public_key=credential["pk"].encode(), sign_count=0,
                                    transports=["internal"], device_type="multi_device", backed_up=True)

    def authentication_options(self):
        ch = os.urandom(32)
        return {"challenge": b64(ch)}, ch

    def verify_authentication(self, *, credential, challenge, public_key, sign_count):
        if credential.get("challenge") != b64(challenge) or credential.get("pk") != public_key.decode():
            raise AuthError("signin_failed", "We couldn't sign you in with that passkey.", 401)
        new = credential.get("counter", sign_count + 1)
        if sign_count and new <= sign_count:
            raise AuthError("signin_failed", "We couldn't sign you in with that passkey.", 401)   # cloned authenticator
        return AuthResult(new_sign_count=new, device_type="multi_device", backed_up=True)


class SoftKey:
    """A pretend passkey: remembers its id + 'private key' and answers ceremonies."""

    def __init__(self, user_handle=None):
        self.id = b64(secrets.token_bytes(16))
        self.pk = b64(secrets.token_bytes(16))
        self.counter = 0
        self.user_handle = user_handle

    def register(self, options):
        return {"id": self.id, "pk": self.pk, "challenge": options["challenge"], "response": {"transports": ["internal"]}}

    def assertion(self, options, **over):
        self.counter += 1
        cred = {"id": self.id, "pk": self.pk, "challenge": options["challenge"], "counter": self.counter,
                "response": {"userHandle": b64(self.user_handle) if self.user_handle else None}}
        cred.update(over)
        return cred


def make_service(clock=None, mailer=None, backend=None, limits=None, **cfg):
    clock = clock or FakeClock()
    cfgobj = AuthConfig(rp_id="zeim.test", origins=("https://zeim.test",), pepper=b"p" * 40, mail_async=False,
                        limits=limits or Limits(), **cfg)
    svc = AuthService(cfgobj, AuthStore(":memory:"), backend or FakeBackend(), mailer or FakeMailer(), clock=clock)
    return svc


def signup(svc, name="Sam", born="1990-05-01", key=None, ip="1.1.1.1", ua="Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/120.0 Safari/537.36"):
    key = key or SoftKey()
    begin = svc.signup_begin(name, born, ip)
    token, session = svc.signup_finish(begin["ceremony_id"], key.register(begin["options"]), "My laptop", ua)
    key.user_handle = session.account_id.encode()
    return key, token, session


def add_email(svc, mailer, session, email, ip="1.1.1.1"):
    svc.email_add_request(session, email, ip)
    # the service mails the normalised (lower-case) address
    return svc.email_add_verify(session, email, mailer.last_code(email.strip().lower()), ip)
