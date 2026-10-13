"""WebAuthn verification, isolated behind a tiny interface.

Production uses py_webauthn (pip: webauthn>=2.1,<3) - we do NOT hand-roll attestation/assertion
verification. Tests use a fake backend, and `tests/test_webauthn_real.py` drives the real library
with a software authenticator (skipped when the library isn't installed).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from app.auth.errors import AuthError


@dataclass
class RegisteredCredential:
    id: str                 # base64url credential id
    public_key: bytes
    sign_count: int
    transports: list = field(default_factory=list)
    device_type: str = ""
    backed_up: bool = False


@dataclass
class AuthResult:
    new_sign_count: int
    device_type: str = ""
    backed_up: bool = False


class WebAuthnBackend(Protocol):
    def registration_options(self, *, user_id: bytes, user_name: str, display_name: str,
                             exclude_ids: list) -> tuple: ...           # (options dict for the browser, challenge bytes)

    def verify_registration(self, *, credential: dict, challenge: bytes) -> RegisteredCredential: ...

    def authentication_options(self) -> tuple: ...                      # (options dict, challenge bytes)

    def verify_authentication(self, *, credential: dict, challenge: bytes, public_key: bytes,
                              sign_count: int) -> AuthResult: ...


_REG_FAIL = AuthError("passkey_failed", "We couldn't verify that passkey. Please try again.", 400)
_AUTH_FAIL = AuthError("signin_failed", "We couldn't sign you in with that passkey. Please try again or use an email code.", 401)


class PyWebAuthnBackend:
    """Adapter for py_webauthn 2.x. Imports lazily so the rest of the package works without it."""

    def __init__(self, rp_id: str, rp_name: str, origins: tuple):
        self.rp_id, self.rp_name, self.origins = rp_id, rp_name, list(origins)

    def registration_options(self, *, user_id, user_name, display_name, exclude_ids):
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (AttestationConveyancePreference, AuthenticatorSelectionCriteria,
                                              PublicKeyCredentialDescriptor, ResidentKeyRequirement,
                                              UserVerificationRequirement)
        opts = generate_registration_options(
            rp_id=self.rp_id, rp_name=self.rp_name, user_id=user_id, user_name=user_name,
            user_display_name=display_name,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,          # discoverable: sign in without typing a name
                user_verification=UserVerificationRequirement.PREFERRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=i) for i in exclude_ids],
        )
        return json.loads(options_to_json(opts)), opts.challenge

    def verify_registration(self, *, credential, challenge):
        from webauthn import verify_registration_response
        from webauthn.helpers import bytes_to_base64url
        try:
            v = verify_registration_response(credential=credential, expected_challenge=challenge,
                                             expected_rp_id=self.rp_id, expected_origin=self.origins,
                                             require_user_verification=False)
        except Exception:
            raise _REG_FAIL
        transports = credential.get("response", {}).get("transports") or []
        return RegisteredCredential(
            id=bytes_to_base64url(v.credential_id), public_key=v.credential_public_key, sign_count=v.sign_count,
            transports=[t for t in transports if isinstance(t, str)][:6],
            device_type=getattr(v.credential_device_type, "value", str(v.credential_device_type)),
            backed_up=bool(v.credential_backed_up))

    def authentication_options(self):
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import UserVerificationRequirement
        opts = generate_authentication_options(rp_id=self.rp_id,
                                               user_verification=UserVerificationRequirement.PREFERRED)
        return json.loads(options_to_json(opts)), opts.challenge

    def verify_authentication(self, *, credential, challenge, public_key, sign_count):
        from webauthn import verify_authentication_response
        try:
            v = verify_authentication_response(credential=credential, expected_challenge=challenge,
                                               expected_rp_id=self.rp_id, expected_origin=self.origins,
                                               credential_public_key=public_key,
                                               credential_current_sign_count=sign_count,
                                               require_user_verification=False)
        except Exception:
            raise _AUTH_FAIL
        return AuthResult(new_sign_count=v.new_sign_count,
                          device_type=getattr(v.credential_device_type, "value", str(v.credential_device_type)),
                          backed_up=bool(v.credential_backed_up))
