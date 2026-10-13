"""Auth settings. Fails closed: production refuses to start without an explicit RP id, origins and pepper."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    """(max events, window seconds). Sliding windows, stored in SQLite so all workers share them."""
    signup_begin_ip: tuple = (10, 3600)
    signin_begin_ip: tuple = (60, 300)
    signin_fail_ip: tuple = (10, 900)
    email_request_email: tuple = (5, 3600)
    email_request_ip: tuple = (20, 3600)
    email_verify_fail_email: tuple = (10, 900)
    email_verify_fail_ip: tuple = (30, 900)
    email_add_account: tuple = (5, 3600)


@dataclass(frozen=True)
class AuthConfig:
    rp_id: str
    origins: tuple
    pepper: bytes
    db_path: str = "data/auth.sqlite3"
    rp_name: str = "ZEIM"
    secure_cookies: bool = True
    session_idle_s: int = 14 * 86400
    session_max_s: int = 30 * 86400
    max_sessions_per_account: int = 20
    recent_auth_s: int = 15 * 60          # sensitive changes need a sign-in this recent
    challenge_ttl_s: int = 300
    otp_ttl_s: int = 600
    otp_max_attempts: int = 5
    min_age: int = 18
    trust_proxy: bool = False
    mail_async: bool = True
    limits: Limits = field(default_factory=Limits)

    @property
    def cookie_name(self) -> str:
        # __Host- prefix = browser enforces Secure + Path=/ + no Domain. Not usable over plain http (dev).
        return "__Host-zeim_session" if self.secure_cookies else "zeim_session"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "AuthConfig":
        e = os.environ if env is None else env
        dev = e.get("ZEIM_ENV", "").lower() == "dev"
        rp_id = e.get("ZEIM_RP_ID") or ("localhost" if dev else "")
        origins = tuple(o.strip() for o in (e.get("ZEIM_ORIGINS") or ("http://localhost:8000" if dev else "")).split(",") if o.strip())
        pepper = (e.get("ZEIM_AUTH_PEPPER") or ("dev-only-pepper-do-not-use-in-production!!" if dev else "")).encode()
        if not rp_id:
            raise ConfigError("ZEIM_RP_ID is required (your site's domain, e.g. zeim.example).")
        if not origins:
            raise ConfigError("ZEIM_ORIGINS is required (comma-separated, e.g. https://zeim.example).")
        if len(pepper) < 32:
            raise ConfigError("ZEIM_AUTH_PEPPER must be a secret of at least 32 characters.")
        for o in origins:
            if not dev and not o.startswith("https://"):
                raise ConfigError(f"Origin {o!r} must be https:// outside dev mode.")
        secure = not (dev and e.get("ZEIM_INSECURE_COOKIES") == "1")
        return cls(rp_id=rp_id, origins=origins, pepper=pepper, db_path=e.get("ZEIM_AUTH_DB", "data/auth.sqlite3"),
                   rp_name=e.get("ZEIM_RP_NAME", "ZEIM"), secure_cookies=secure,
                   trust_proxy=e.get("ZEIM_TRUST_PROXY") == "1")
