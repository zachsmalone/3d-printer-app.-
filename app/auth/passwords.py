"""Password hashing (Argon2id) and the rules for a password a person can remember.

The hash string is what we store. The password itself is never written to the
database, a log line, or an error message.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.auth.errors import AuthError

# OWASP minimum for Argon2id: 19 MiB, 2 iterations, parallelism 1.
_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)

_MIN = 10
_MAX = 128
_dummy: str | None = None


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def dummy_hash() -> str:
    """A real Argon2 hash of a throwaway string.

    Verifying against it makes "no such account" take about as long as "wrong password".
    """
    global _dummy
    if _dummy is None:
        _dummy = hash_password("zeim-dummy-not-a-password")
    return _dummy


def verify_password(stored: str, password: str) -> bool:
    try:
        return bool(_HASHER.verify(stored, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return bool(_HASHER.check_needs_rehash(stored))
    except (InvalidHashError, VerificationError):
        return False


def matches(stored: str | None, password: object) -> bool:
    """True only when `stored` is this password's hash.

    A missing hash still runs a verify against a dummy hash so a missing account
    is not faster than a wrong password. Oversized input skips the hash so a
    huge body cannot pin the CPU.
    """
    if not isinstance(password, str) or len(password) > _MAX:
        return False
    if stored:
        return verify_password(stored, password)
    verify_password(dummy_hash(), password or "x")
    return False


def check_password(password: object, *, username: str | None = None, email: str | None = None) -> str:
    """Return the password if it is acceptable to store. The message is safe to show."""
    if not isinstance(password, str) or len(password) > _MAX or any(ord(c) < 32 for c in password):
        raise AuthError("bad_password", "Use a password of 10 to 128 characters.", 422)
    if len(password) < _MIN:
        raise AuthError("bad_password", "Use at least 10 characters. A short phrase you can remember works well.", 422)
    low = password.casefold()
    if username and low == username.casefold():
        raise AuthError("bad_password", "Use a password that isn't your username.", 422)
    if email and low == email.casefold():
        raise AuthError("bad_password", "Use a password that isn't your email address.", 422)
    return password
