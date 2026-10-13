"""All sign-up / sign-in / session logic. No HTTP in here, so every flow is unit-testable."""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from app.auth import security as sec
from app.auth.config import AuthConfig
from app.auth.errors import AuthError, RateLimited
from app.auth.mailer import Mailer, code_email
from app.auth.ratelimit import RateLimiter
from app.auth.store import AuthStore
from app.auth.webauthn_backend import WebAuthnBackend

log = logging.getLogger("zeim.auth")   # log lines carry fingerprints / ids only, never email addresses

_CRED_ID = re.compile(r"^[A-Za-z0-9_\-]{1,512}$")
_TOUCH_EVERY_S = 60                      # sliding-expiry write at most once a minute per session


@dataclass
class SessionInfo:
    id: str
    account_id: str
    legacy_id: Optional[str]
    label: str
    created_at: float
    last_seen_at: float
    authed_at: float
    auth_method: str
    idle_expires_at: float
    abs_expires_at: float

    @property
    def owner_id(self) -> str:
        """Id the rest of ZEIM should use for ownership checks (legacy id until migrated)."""
        return self.legacy_id or self.account_id


def default_signup_validator(cfg: AuthConfig, now: float) -> Callable:
    """Mirrors the current policy (display name + birth date, adults only). Replace with the shared
    function from the 18+ work via AuthService(signup_validator=...). Returns the cleaned name."""
    def validate(display_name: object, birth_date: object) -> str:
        name = display_name.strip() if isinstance(display_name, str) else ""
        if not 1 <= len(name) <= 40 or any(ord(c) < 32 for c in name):
            raise AuthError("bad_name", "Please choose a display name of 1 to 40 characters.", 422)
        try:
            born = date.fromisoformat(birth_date) if isinstance(birth_date, str) else None
        except ValueError:
            born = None
        today = date.fromtimestamp(now)
        if born is None or born > today:
            raise AuthError("bad_birth_date", "Please enter your birth date as YYYY-MM-DD.", 422)
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < cfg.min_age:
            raise AuthError("too_young", f"ZEIM accounts are for people aged {cfg.min_age} and over.", 403)
        return name
    return validate


class AuthService:
    def __init__(self, config: AuthConfig, store: AuthStore, backend: WebAuthnBackend, mailer: Mailer,
                 clock: Callable[[], float] = time.time, signup_validator: Optional[Callable] = None,
                 on_account_created: Optional[Callable] = None):
        self.cfg, self.store, self.backend, self.mailer, self.clock = config, store, backend, mailer, clock
        self.limiter = RateLimiter(store, clock)
        self.validate_signup = signup_validator or default_signup_validator(config, clock())
        self._validator_is_default = signup_validator is None
        self.on_account_created = on_account_created
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="zeim-mail") if config.mail_async else None

    # ------------------------------------------------------------------ helpers
    def _ip(self, ip: Optional[str]) -> str:
        return sec.keyed_hash(self.cfg.pepper, "ip", ip or "unknown")

    def _ehash(self, email: str) -> str:
        return sec.keyed_hash(self.cfg.pepper, "email", email)

    def _signup_checker(self):
        if self._validator_is_default:   # keep the age check current if the clock moved (tests, long uptime)
            return default_signup_validator(self.cfg, self.clock())
        return self.validate_signup

    def _store_ceremony(self, kind: str, challenge: bytes, account_id: Optional[str] = None,
                        payload: Optional[dict] = None) -> str:
        cid = sec.new_token(18)
        now = self.clock()
        self.store.run("DELETE FROM ceremonies WHERE expires_at<?", (now,))
        self.store.run("INSERT INTO ceremonies(id, kind, challenge, account_id, payload, expires_at) VALUES(?,?,?,?,?,?)",
                       (cid, kind, challenge, account_id, json.dumps(payload) if payload else None,
                        now + self.cfg.challenge_ttl_s))
        return cid

    def _consume_ceremony(self, cid: object, kind: str, account_id: Optional[str] = None):
        """Single use: the row is deleted whether or not the rest of the ceremony succeeds."""
        gone = AuthError("ceremony_expired", "That took too long or was already used. Please start again.", 400)
        if not isinstance(cid, str) or not 10 <= len(cid) <= 64:
            raise gone
        with self.store.tx():
            row = self.store.one("SELECT * FROM ceremonies WHERE id=?", (cid,))
            self.store.run("DELETE FROM ceremonies WHERE id=?", (cid,))
        if (not row or row["kind"] != kind or row["expires_at"] < self.clock()
                or (account_id is not None and row["account_id"] != account_id)):
            raise gone
        return row

    def _new_session(self, account_id: str, ua: Optional[str], method: str) -> tuple:
        """Always a fresh random token (no session fixation). Returns (token, SessionInfo)."""
        now = self.clock()
        token, sid = sec.new_token(32), sec.new_token(9)
        label = sec.ua_label(ua)
        with self.store.tx():
            self.store.run("INSERT INTO sessions(id, account_id, token_hash, created_at, last_seen_at, authed_at,"
                           " idle_expires_at, abs_expires_at, label, auth_method) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (sid, account_id, sec.sha256_hex(token), now, now, now, now + self.cfg.session_idle_s,
                            now + self.cfg.session_max_s, label, method))
            live = self.store.all("SELECT id FROM sessions WHERE account_id=? AND revoked_at IS NULL"
                                  " AND abs_expires_at>? ORDER BY created_at DESC", (account_id, now))
            for old in live[self.cfg.max_sessions_per_account:]:      # cap: drop the oldest devices
                self.store.run("UPDATE sessions SET revoked_at=? WHERE id=?", (now, old["id"]))
        log.info("session created acct=%s method=%s", account_id, method)
        return token, self._session_by_id(sid)

    def _session_by_id(self, sid: str) -> SessionInfo:
        r = self.store.one("SELECT s.*, a.legacy_id FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.id=?", (sid,))
        return self._row_to_session(r)

    @staticmethod
    def _row_to_session(r) -> SessionInfo:
        return SessionInfo(r["id"], r["account_id"], r["legacy_id"], r["label"], r["created_at"], r["last_seen_at"],
                           r["authed_at"], r["auth_method"], r["idle_expires_at"], r["abs_expires_at"])

    # ------------------------------------------------------------------ sessions
    def resolve_session(self, token: Optional[str]) -> Optional[SessionInfo]:
        """Cookie value -> live session (sliding idle expiry, hard absolute expiry), else None."""
        if not token or not isinstance(token, str) or len(token) > 200:
            return None
        now = self.clock()
        r = self.store.one("SELECT s.*, a.legacy_id, a.disabled_at FROM sessions s JOIN accounts a ON a.id=s.account_id"
                           " WHERE s.token_hash=?", (sec.sha256_hex(token),))
        if not r or r["revoked_at"] is not None or r["disabled_at"] is not None:
            return None
        if now >= r["idle_expires_at"] or now >= r["abs_expires_at"]:
            self.store.run("DELETE FROM sessions WHERE id=?", (r["id"],))
            return None
        if now - r["last_seen_at"] >= _TOUCH_EVERY_S:
            idle = min(now + self.cfg.session_idle_s, r["abs_expires_at"])
            self.store.run("UPDATE sessions SET last_seen_at=?, idle_expires_at=? WHERE id=?", (now, idle, r["id"]))
            r = self.store.one("SELECT s.*, a.legacy_id FROM sessions s JOIN accounts a ON a.id=s.account_id WHERE s.id=?", (r["id"],))
        return self._row_to_session(r)

    def logout(self, session: SessionInfo) -> None:
        self.store.run("DELETE FROM sessions WHERE id=?", (session.id,))

    def revoke_session(self, account_id: str, session_id: str) -> None:
        if not self.store.run("DELETE FROM sessions WHERE id=? AND account_id=?", (session_id, account_id)):
            raise AuthError("not_found", "That device wasn't found.", 404)

    def revoke_all(self, account_id: str, keep_session_id: Optional[str] = None) -> int:
        """'Sign out everywhere'. With keep_session_id, every device *except* this one."""
        if keep_session_id:
            n = self.store.run("DELETE FROM sessions WHERE account_id=? AND id<>?", (account_id, keep_session_id))
        else:
            n = self.store.run("DELETE FROM sessions WHERE account_id=?", (account_id,))
        log.info("sessions revoked acct=%s count=%s", account_id, n)
        return n

    def _require_recent(self, session: SessionInfo) -> None:
        """Sensitive changes need a recent proof of identity (stolen-cookie protection)."""
        if self.clock() - session.authed_at > self.cfg.recent_auth_s:
            raise AuthError("reauth_required", "For your security, please sign in again to make this change.", 403)

    # ------------------------------------------------------------------ legacy accounts
    def ensure_legacy_account(self, legacy_id: str, display_name: str = "") -> str:
        """Give an existing cookie-only account an auth identity (so it can add a passkey / email)."""
        if not isinstance(legacy_id, str) or not 1 <= len(legacy_id) <= 200:
            raise AuthError("bad_account", "Account not recognised.", 400)
        with self.store.tx():
            r = self.store.one("SELECT id FROM accounts WHERE legacy_id=?", (legacy_id,))
            if r:
                return r["id"]
            aid = "acc_" + sec.new_token(12)
            self.store.run("INSERT INTO accounts(id, legacy_id, display_name, created_at) VALUES(?,?,?,?)",
                           (aid, legacy_id, display_name[:40], self.clock()))
        log.info("legacy account linked acct=%s", aid)
        return aid

    def is_upgraded(self, legacy_id: str) -> bool:
        """True once a legacy (cookie-only) account has a passkey or a verified email. The old
        recovery-code login should be refused/demoted for such accounts, or it bypasses strong login."""
        r = self.store.one("SELECT a.id, a.email_verified_at, (SELECT COUNT(*) FROM credentials c WHERE c.account_id=a.id) AS n"
                           " FROM accounts a WHERE a.legacy_id=?", (legacy_id,))
        return bool(r and (r["n"] or r["email_verified_at"]))

    def ephemeral_legacy_session(self, account_id: str) -> SessionInfo:
        """In-memory stand-in (NOT stored, no cookie) so a cookie-only account can run the add-passkey /
        add-email steps once. A real session is only minted when that step succeeds."""
        now = self.clock()
        return SessionInfo("legacy", account_id, None, "", now, now, now, "legacy",
                           now + 600, now + 600)

    def session_for_legacy(self, account_id: str, ua: Optional[str]) -> tuple:
        """Used right after a legacy account adds its first passkey/email: gives it a real session."""
        return self._new_session(account_id, ua, "legacy-upgrade")

    # ------------------------------------------------------------------ passkey sign-up
    def signup_begin(self, display_name: object, birth_date: object, ip: Optional[str]) -> dict:
        self.limiter.hit(f"signup_begin:{self._ip(ip)}", self.cfg.limits.signup_begin_ip)
        name = self._signup_checker()(display_name, birth_date)
        account_id = "acc_" + sec.new_token(12)
        options, challenge = self.backend.registration_options(
            user_id=account_id.encode(), user_name=name, display_name=name, exclude_ids=[])
        cid = self._store_ceremony("signup", challenge, account_id,
                                   {"name": name, "birth_date": birth_date})   # row is deleted when used / expired
        return {"ceremony_id": cid, "options": options}

    def signup_finish(self, ceremony_id: object, credential: object, passkey_name: object, ua: Optional[str]) -> tuple:
        row = self._consume_ceremony(ceremony_id, "signup")
        payload = json.loads(row["payload"])
        reg = self.backend.verify_registration(credential=self._cred(credential), challenge=bytes(row["challenge"]))
        now = self.clock()
        with self.store.tx():
            self.store.run("INSERT INTO accounts(id, display_name, created_at) VALUES(?,?,?)",
                           (row["account_id"], payload["name"], now))
            self._insert_credential(row["account_id"], reg, passkey_name)
        if self.on_account_created:
            self.on_account_created(row["account_id"], payload["name"], payload.get("birth_date"))
        token, session = self._new_session(row["account_id"], ua, "passkey-signup")
        return token, session

    # ------------------------------------------------------------------ passkey sign-in
    def signin_begin(self, ip: Optional[str]) -> dict:
        self.limiter.hit(f"signin_begin:{self._ip(ip)}", self.cfg.limits.signin_begin_ip)
        options, challenge = self.backend.authentication_options()
        return {"ceremony_id": self._store_ceremony("signin", challenge), "options": options}

    def signin_finish(self, ceremony_id: object, credential: object, ua: Optional[str], ip: Optional[str]) -> tuple:
        ipk = f"signin_fail:{self._ip(ip)}"
        self.limiter.check(ipk, self.cfg.limits.signin_fail_ip)
        fail = AuthError("signin_failed", "We couldn't sign you in with that passkey. Please try again or use an email code.", 401)
        try:
            row = self._consume_ceremony(ceremony_id, "signin")
            cred = self._cred(credential)
            cid = cred.get("id")
            if not isinstance(cid, str) or not _CRED_ID.match(cid):
                raise fail
            stored = self.store.one("SELECT c.*, a.disabled_at FROM credentials c JOIN accounts a ON a.id=c.account_id"
                                    " WHERE c.id=?", (cid,))
            if not stored or stored["disabled_at"] is not None:
                raise fail
            handle = (cred.get("response") or {}).get("userHandle")
            if handle:
                try:
                    if _b64d(handle) != stored["account_id"].encode():
                        raise fail
                except ValueError:
                    raise fail
            res = self.backend.verify_authentication(credential=cred, challenge=bytes(row["challenge"]),
                                                     public_key=bytes(stored["public_key"]),
                                                     sign_count=stored["sign_count"])
        except AuthError:
            self.limiter.record(ipk)
            raise
        self.store.run("UPDATE credentials SET sign_count=?, last_used_at=?, backed_up=? WHERE id=?",
                       (res.new_sign_count, self.clock(), int(res.backed_up), cid))
        return self._new_session(stored["account_id"], ua, "passkey")

    # ------------------------------------------------------------------ add / manage passkeys (signed in)
    def passkey_add_begin(self, session: SessionInfo) -> dict:
        self._require_recent(session)
        acct = self.store.one("SELECT display_name FROM accounts WHERE id=?", (session.account_id,))
        existing = [_b64d(r["id"]) for r in self.store.all("SELECT id FROM credentials WHERE account_id=?", (session.account_id,))]
        name = acct["display_name"] or "ZEIM account"
        options, challenge = self.backend.registration_options(
            user_id=session.account_id.encode(), user_name=name, display_name=name, exclude_ids=existing)
        return {"ceremony_id": self._store_ceremony("add", challenge, session.account_id), "options": options}

    def passkey_add_finish(self, session: SessionInfo, ceremony_id: object, credential: object, name: object) -> dict:
        self._require_recent(session)
        row = self._consume_ceremony(ceremony_id, "add", session.account_id)
        reg = self.backend.verify_registration(credential=self._cred(credential), challenge=bytes(row["challenge"]))
        with self.store.tx():
            if self.store.one("SELECT 1 FROM credentials WHERE id=?", (reg.id,)):
                raise AuthError("passkey_exists", "That passkey is already registered.", 409)
            self._insert_credential(session.account_id, reg, name)
        log.info("passkey added acct=%s", session.account_id)
        return {"id": reg.id}

    def rename_passkey(self, account_id: str, cred_id: str, name: object) -> None:
        if not self.store.run("UPDATE credentials SET name=? WHERE id=? AND account_id=?",
                              (_clean_label(name), cred_id, account_id)):
            raise AuthError("not_found", "That passkey wasn't found.", 404)

    def remove_passkey(self, session: SessionInfo, cred_id: str) -> None:
        self._require_recent(session)
        with self.store.tx():
            mine = self.store.all("SELECT id FROM credentials WHERE account_id=?", (session.account_id,))
            if cred_id not in {r["id"] for r in mine}:
                raise AuthError("not_found", "That passkey wasn't found.", 404)
            acct = self.store.one("SELECT email_hash FROM accounts WHERE id=?", (session.account_id,))
            if len(mine) == 1 and not acct["email_hash"]:
                raise AuthError("last_method", "That's your only way to sign in. Add another passkey or an email first.", 409)
            self.store.run("DELETE FROM credentials WHERE id=?", (cred_id,))
        log.info("passkey removed acct=%s", session.account_id)

    # ------------------------------------------------------------------ email one-time codes
    def _issue_code(self, purpose: str, email_hash: str, account_id: Optional[str]) -> str:
        code, salt, now = sec.generate_code(), sec.new_token(8), self.clock()
        with self.store.tx():
            self.store.run("UPDATE email_codes SET used_at=? WHERE purpose=? AND email_hash=? AND used_at IS NULL",
                           (now, purpose, email_hash))                       # a new code kills older ones
            self.store.run("INSERT INTO email_codes(purpose, email_hash, account_id, salt, code_hash, created_at, expires_at)"
                           " VALUES(?,?,?,?,?,?,?)",
                           (purpose, email_hash, account_id, salt,
                            sec.keyed_hash(self.cfg.pepper, "otp:" + salt + email_hash, code), now, now + self.cfg.otp_ttl_s))
            self.store.run("DELETE FROM email_codes WHERE expires_at<?", (now - 86400,))
        return code

    def _deliver(self, email: str, code: str) -> None:
        subject, text = code_email(code, self.cfg.otp_ttl_s // 60)
        def send():
            try:
                self.mailer.send(email, subject, text)
            except Exception as e:                                           # never log the address
                log.warning("code email failed fp=%s err=%s", sec.fingerprint(self._ehash(email)), type(e).__name__)
        if self._pool:
            self._pool.submit(send)      # sending off-thread keeps response time identical for known/unknown emails
        else:
            send()

    def email_request_login(self, email_raw: object, ip: Optional[str]) -> None:
        """Always returns None, whether or not the email belongs to an account (no enumeration)."""
        email = sec.normalize_email(email_raw)
        eh = self._ehash(email)
        self.limiter.hit(f"email_req:ip:{self._ip(ip)}", self.cfg.limits.email_request_ip)
        self.limiter.hit(f"email_req:em:{eh}", self.cfg.limits.email_request_email)
        acct = self.store.one("SELECT id FROM accounts WHERE email_hash=? AND email_verified_at IS NOT NULL"
                              " AND disabled_at IS NULL", (eh,))
        if not acct:
            log.info("login code requested for unknown email fp=%s", sec.fingerprint(eh))
            return
        self._deliver(email, self._issue_code("login", eh, acct["id"]))
        log.info("login code sent fp=%s", sec.fingerprint(eh))

    def _check_code(self, purpose: str, email: str, code_raw: object, ip: Optional[str],
                    account_id: Optional[str] = None) -> None:
        eh, ipk = self._ehash(email), self._ip(ip)
        lim = self.cfg.limits
        kem, kip = f"email_fail:em:{eh}", f"email_fail:ip:{ipk}"
        self.limiter.check(kem, lim.email_verify_fail_email)
        self.limiter.check(kip, lim.email_verify_fail_ip)
        bad = AuthError("bad_code", "That code didn't work. Check it, or ask for a new one.", 400)
        code = sec.normalize_code(code_raw)
        now = self.clock()
        with self.store.tx():
            sql = ("SELECT * FROM email_codes WHERE purpose=? AND email_hash=? AND used_at IS NULL AND expires_at>?"
                   + (" AND account_id=?" if account_id else "") + " ORDER BY id DESC LIMIT 1")
            row = self.store.one(sql, (purpose, eh, now) + ((account_id,) if account_id else ()))
            ok = False
            if row and code:
                good = sec.eq(sec.keyed_hash(self.cfg.pepper, "otp:" + row["salt"] + eh, code), row["code_hash"])
                if good:
                    ok = bool(self.store.run("UPDATE email_codes SET used_at=? WHERE id=? AND used_at IS NULL", (now, row["id"])))
                else:
                    burned = row["attempts"] + 1 >= self.cfg.otp_max_attempts
                    self.store.run("UPDATE email_codes SET attempts=attempts+1, used_at=? WHERE id=?",
                                   (now if burned else None, row["id"]))
            if not ok:
                self.limiter.record(kem)
                self.limiter.record(kip)
        if not ok:
            raise bad

    def email_verify_login(self, email_raw: object, code: object, ua: Optional[str], ip: Optional[str]) -> tuple:
        email = sec.normalize_email(email_raw)
        self._check_code("login", email, code, ip)
        acct = self.store.one("SELECT id FROM accounts WHERE email_hash=? AND email_verified_at IS NOT NULL"
                              " AND disabled_at IS NULL", (self._ehash(email),))
        if not acct:
            raise AuthError("bad_code", "That code didn't work. Check it, or ask for a new one.", 400)
        return self._new_session(acct["id"], ua, "email")

    def email_add_request(self, session: SessionInfo, email_raw: object, ip: Optional[str]) -> None:
        self._require_recent(session)
        email = sec.normalize_email(email_raw)
        self.limiter.hit(f"email_add:acct:{session.account_id}", self.cfg.limits.email_add_account)
        self.limiter.hit(f"email_req:ip:{self._ip(ip)}", self.cfg.limits.email_request_ip)
        self._deliver(email, self._issue_code("add", self._ehash(email), session.account_id))

    def email_add_verify(self, session: SessionInfo, email_raw: object, code: object, ip: Optional[str]) -> dict:
        self._require_recent(session)
        email = sec.normalize_email(email_raw)
        self._check_code("add", email, code, ip, account_id=session.account_id)
        eh = self._ehash(email)
        try:
            with self.store.tx():
                self.store.run("UPDATE accounts SET email_hash=?, email_hint=?, email_verified_at=? WHERE id=?",
                               (eh, sec.mask_email(email), self.clock(), session.account_id))
        except Exception as e:
            if "UNIQUE" in str(e):
                raise AuthError("email_in_use", "That email is already used by another ZEIM account.", 409)
            raise
        log.info("email added acct=%s fp=%s", session.account_id, sec.fingerprint(eh))
        return {"email_hint": sec.mask_email(email)}

    def remove_email(self, session: SessionInfo) -> None:
        self._require_recent(session)
        with self.store.tx():
            n = self.store.one("SELECT COUNT(*) AS n FROM credentials WHERE account_id=?", (session.account_id,))["n"]
            if n == 0:
                raise AuthError("last_method", "That's your only way to sign in. Add a passkey first.", 409)
            self.store.run("UPDATE accounts SET email_hash=NULL, email_hint=NULL, email_verified_at=NULL WHERE id=?",
                           (session.account_id,))

    # ------------------------------------------------------------------ account overview (Account page)
    def overview(self, session: SessionInfo) -> dict:
        a = self.store.one("SELECT display_name, email_hint FROM accounts WHERE id=?", (session.account_id,))
        keys = self.store.all("SELECT id, name, created_at, last_used_at, device_type, backed_up FROM credentials"
                              " WHERE account_id=? ORDER BY created_at", (session.account_id,))
        sess = self.store.all("SELECT id, label, created_at, last_seen_at, auth_method FROM sessions WHERE account_id=?"
                              " AND revoked_at IS NULL AND idle_expires_at>? AND abs_expires_at>? ORDER BY last_seen_at DESC",
                              (session.account_id, self.clock(), self.clock()))
        return {
            "display_name": a["display_name"],
            "email": {"hint": a["email_hint"]} if a["email_hint"] else None,
            "passkeys": [dict(k) | {"backed_up": bool(k["backed_up"])} for k in keys],
            "devices": [dict(s) | {"current": s["id"] == session.id} for s in sess],
            "recent_signin": self.clock() - session.authed_at <= self.cfg.recent_auth_s,
        }

    # ------------------------------------------------------------------ misc
    @staticmethod
    def _cred(credential: object) -> dict:
        if not isinstance(credential, dict) or len(json.dumps(credential)) > 20000:
            raise AuthError("bad_request", "That request wasn't understood.", 400)
        return credential

    def _insert_credential(self, account_id: str, reg, name: object) -> None:
        self.store.run("INSERT INTO credentials(id, account_id, public_key, sign_count, transports, name, device_type,"
                       " backed_up, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (reg.id, account_id, reg.public_key, reg.sign_count, ",".join(reg.transports),
                        _clean_label(name), reg.device_type, int(reg.backed_up), self.clock()))


def _clean_label(name: object) -> str:
    n = name.strip() if isinstance(name, str) else ""
    n = "".join(c for c in n if ord(c) >= 32)[:40]
    return n or "Passkey"


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
