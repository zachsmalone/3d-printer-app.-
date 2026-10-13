"""Small, dependency-free helpers: hashing, token/code generation, email handling, UA labels."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Optional

from app.auth.errors import AuthError

_EMAIL_RE = re.compile(r"^[a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9\-]+(?:\.[a-z0-9\-]+)+$")


def new_token(nbytes: int = 32) -> str:
    """URL-safe random secret (session tokens, ceremony ids)."""
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def keyed_hash(pepper: bytes, purpose: str, value: str) -> str:
    """HMAC-SHA256 with domain separation: the same value hashed for different purposes never collides."""
    return hmac.new(pepper, purpose.encode() + b"\0" + value.encode(), hashlib.sha256).hexdigest()


def eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def generate_code() -> str:
    """6-digit one-time code from a CSPRNG."""
    return f"{secrets.randbelow(10 ** 6):06d}"


def normalize_code(raw: object) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    digits = raw.replace(" ", "").replace("-", "")
    return digits if len(digits) == 6 and digits.isdigit() else None


def normalize_email(raw: object) -> str:
    bad = AuthError("bad_email", "That doesn't look like a valid email address.", 400)
    if not isinstance(raw, str):
        raise bad
    e = raw.strip().lower()
    if not e or len(e) > 254 or ".." in e or not _EMAIL_RE.match(e):
        raise bad
    domain = e.split("@", 1)[1]
    if any(l.startswith("-") or l.endswith("-") or not l for l in domain.split(".")):
        raise bad
    return e


def mask_email(email: str) -> str:
    """j***@e***.com : a hint for the account owner, useless to anyone else."""
    local, domain = email.split("@", 1)
    host, _, tld = domain.rpartition(".")
    return f"{local[0]}***@{host[0]}***.{tld}"


def fingerprint(hex_hash: str) -> str:
    """Short non-reversible tag for log lines (never log the address itself)."""
    return hex_hash[:8]


def ua_label(ua: Optional[str]) -> str:
    """'Chrome on Mac'. Only this coarse label is stored, never the full User-Agent or the IP."""
    u = ua or ""
    if "Edg/" in u or "EdgA/" in u:
        browser = "Edge"
    elif "OPR/" in u or "Opera" in u:
        browser = "Opera"
    elif "Firefox/" in u or "FxiOS/" in u:
        browser = "Firefox"
    elif "CriOS/" in u or "Chrome/" in u:
        browser = "Chrome"
    elif "Safari/" in u and "Version/" in u:
        browser = "Safari"
    else:
        browser = ""
    if "iPhone" in u:
        os_ = "iPhone"
    elif "iPad" in u:
        os_ = "iPad"
    elif "Android" in u:
        os_ = "Android"
    elif "Windows" in u:
        os_ = "Windows"
    elif "Mac OS X" in u or "Macintosh" in u:
        os_ = "Mac"
    elif "CrOS" in u:
        os_ = "ChromeOS"
    elif "Linux" in u:
        os_ = "Linux"
    else:
        os_ = ""
    if browser and os_:
        return f"{browser} on {os_}"
    return browser or os_ or "Unknown device"
