"""Identity. ZEIM accounts are 18+ only (owner decision 2026-10-12). Age is computed server-side from the date of birth
typed at sign-up; a refused sign-up stores nothing about the date.

Identity = an account record in users.json, keyed by an internal "account key" (historically the `p3d_sid` cookie value).
  * passkey / email-code sign-in (app/auth, docs/auth.md): when a live `zeim_session` is present, the account is the one
    whose `id` equals the session's auth `owner_id` (legacy id for upgraded cookie accounts, else the auth account id).
    Builds, Showcase items, follows and favourites then belong to that account on every device.
  * otherwise the old cookie login: `p3d_sid` -> account record (kept working; recovery codes still apply).
  * no accounts under MIN_SIGNUP_AGE (18). ZEIM is for adults only.
  * content is clean and safe for all, for everyone (see COMMUNITY_GUIDELINES.md)
  * an account is RESTRICTED (treated like signed out for sharing, its content shown to nobody else) while it is
    suspended by a moderator, or if it is a legacy account whose stored date of birth is under 18 (from the old 13+ rules)
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import Request, Response

from .. import config
from .store import USERS

COOKIE = "p3d_sid"


@dataclass
class Actor:
    sid: str                         # internal account key: every ownership check (owner_sid) uses it
    user: dict | None
    via: str = "cookie"              # "auth" when a passkey/email-code session picked this account
    auth_session: object = None      # app.auth.service.SessionInfo when via == "auth"

    @property
    def owner_id(self) -> str | None:
        """Stable account id (== auth SessionInfo.owner_id for signed-in passkey/email accounts)."""
        return self.user.get("id") if self.user else None

    @property
    def age(self):
        return age_of(self.user) if self.user and self.user.get("dob") else None

    @property
    def is_adult(self):
        """A signed-in account in good standing (18+, not suspended)."""
        return bool(self.user) and not restricted(self.user)


def underage(user: dict | None) -> bool:
    """Legacy account whose stored date of birth is under 18 (made under the old 13+ rules). New ones can't be created."""
    return bool(user) and bool(user.get("dob")) and age_of(user) < config.MIN_SIGNUP_AGE


def suspended(user: dict | None) -> bool:
    return bool(user) and bool(user.get("suspended"))


def restricted(user: dict | None) -> bool:
    """Suspended, or a legacy under-18 account: may not share, follow or send, and nobody else sees its content."""
    return suspended(user) or underage(user)


def age_of(user: dict, today: date | None = None) -> int:
    d = date.fromisoformat(user["dob"])
    t = today or datetime.now(timezone.utc).date()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


def cookie_args(request: Request) -> dict:
    """Flags for every cookie we set: HttpOnly, SameSite=Lax, and Secure whenever the page came over https (PHOTO3D_COOKIE_SECURE=true|false|auto)."""
    mode = config.COOKIE_SECURE
    secure = True if mode in ("1", "true", "yes", "on") else False if mode in ("0", "false", "no", "off") else request.url.scheme == "https"
    return {"httponly": True, "samesite": "lax", "secure": secure}


def _auth_service(request: Request):
    try:
        return getattr(request.app.state, "auth_service", None)
    except Exception:
        return None


def _new_record(uid: str, display_name: str, dob: str | None) -> dict:
    from .privacy import defaults_for
    u = {"id": uid, "display_name": (display_name or "").strip()[:40] or "ZEIM maker",
         "created": datetime.now(timezone.utc).isoformat(), "links": {}, "following": [], "auth_account": uid}
    if dob:
        u["dob"] = dob
    u["privacy"] = defaults_for(u)
    return u


def link_auth_account(account_id: str, display_name: str = "", dob: str | None = None,
                      username: str | None = None) -> tuple[str, dict]:
    """Give a passkey/email/password account (made through /api/auth sign-up, 18+ checked there) its ZEIM account record.
    Idempotent. The record lives under a fresh random account key that is never handed out as a cookie, so only a
    live auth session reaches it (signing out of the session really signs out). Returns (key, user).
    `username`, when set, is the name they chose at password sign-up. A failure then undoes the new record
    so a rejected name does not leave an account behind. Passkey sign-up leaves it empty and still gets a generated name."""
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("account id required")
    if dob is not None:
        try:
            date.fromisoformat(dob)
        except (TypeError, ValueError):
            dob = None
    key = "acct_" + secrets.token_urlsafe(24)
    made = {}

    def f(d):
        for k, u in d.items():
            if u.get("id") == account_id:
                made["k"], made["u"] = k, u
                return
        u = _new_record(account_id, display_name, dob)
        d[key] = u
        made["k"], made["u"], made["new"] = key, u, True
    USERS.update(f)
    if made.get("new"):
        from . import usernames
        try:
            usernames.assign_new(made["k"], made["u"], username)
        except Exception:
            if username:
                USERS.update(lambda d: d.pop(made["k"], None))
                raise
            import logging
            logging.getLogger("zeim").exception("username for new passkey account failed")
    return made["k"], made["u"]


def account_for_session(session, service=None) -> tuple[str | None, dict | None]:
    """Auth SessionInfo -> (account key, user). Upgraded cookie accounts: the record whose id is the legacy id
    (None if it is gone: never invented). Passkey/email-born accounts: their record, made on first use if missing."""
    oid = getattr(session, "owner_id", None)
    if not oid:
        return None, None
    for k, u in USERS.read().items():
        if u.get("id") == oid:
            return k, u
    if getattr(session, "legacy_id", None):
        return None, None
    name = ""
    if service is not None:
        try:
            row = service.store.one("SELECT display_name FROM accounts WHERE id=?", (session.account_id,))
            name = (row["display_name"] if row else "") or ""
        except Exception:
            name = ""
    return link_auth_account(session.account_id, name)


def _legacy_record_upgraded(request: Request, user: dict) -> bool:
    """Has this legacy cookie account been upgraded to a real passkey account?
    True only when the auth service is mounted AND knows the account; an auth outage
    must not lock people out of their still-cookie accounts."""
    svc = _auth_service(request)
    if svc is None or not user or not user.get("id"):
        return False
    try:
        return svc.is_upgraded(user["id"])
    except Exception:
        return False


def auth_actor(request: Request) -> Actor | None:
    """The account of a live passkey/email session on this request, or None (no auth mounted / no or dead session)."""
    svc = _auth_service(request)
    if svc is None:
        return None
    tok = request.cookies.get(svc.cfg.cookie_name)
    if not tok:
        return None
    try:
        s = svc.resolve_session(tok)
    except Exception:
        import logging
        logging.getLogger("zeim.auth").exception("session lookup failed; using the browser cookie")
        return None
    if not s:
        return None
    key, user = account_for_session(s, svc)
    if not key:
        return None
    return Actor(key, user, via="auth", auth_session=s)


def adopt_guest_builds(request: Request, session) -> int:
    """Right after a passkey/email sign-in: builds this browser made while signed OUT follow the account.
    Never merges two accounts (a browser that has its own cookie account keeps it). Returns how many moved."""
    sid = request.cookies.get(COOKIE)
    if not sid or len(sid) < 16 or sid in USERS.read():
        return 0
    key, _u = account_for_session(session, _auth_service(request))
    if not key or key == sid:
        return 0
    from ..services.history import store
    n = len(store.list(sid))
    from . import ownership
    ownership.move_owner(sid, key)
    return n


def get_actor(request: Request, response: Response) -> Actor:
    a = auth_actor(request)
    if a is not None:
        return a
    sid = request.cookies.get(COOKIE)
    if sid and sid.startswith("acct_"):          # passkey-account keys are never valid as a browser cookie
        sid = None
    user = USERS.read().get(sid) if (sid and len(sid) >= 16) else None
    if user and _legacy_record_upgraded(request, user):
        # The cookie account this browser presents has been secured with a passkey:
        # the cookie is retired authority, not a fallback identity. Otherwise a copy of
        # the old cookie on another browser could silently restore the old identity
        # after a sign-out (or a revoked session) — the sign-out authority hole. The sid
        # is dropped too, so it can never act as an ownership key for the old builds.
        user, sid = None, None
    if not sid or len(sid) < 16:
        sid = secrets.token_urlsafe(24)
        response.set_cookie(COOKIE, sid, max_age=3600 * 24 * 365, **cookie_args(request))
    return Actor(sid, USERS.read().get(sid))


def session_only_cookie(request: Request, response: Response, sid: str):
    """Re-issue the session cookie WITHOUT an expiry, so a shared computer forgets it when the browser closes."""
    response.raw_headers[:] = [(k, v) for k, v in response.raw_headers if not (k.lower() == b"set-cookie" and v.startswith(COOKIE.encode() + b"="))]
    response.set_cookie(COOKIE, sid, **cookie_args(request))


AGE_COOKIE = "p3d_ag"
AGE_MESSAGE = "Sorry, ZEIM accounts are for adults 18 and over, so we can't create an account for you."


def _blk(sid: str) -> str:
    import hashlib
    return hashlib.sha256(("age:" + sid).encode()).hexdigest()[:24]


def _blk_ip(ip: str) -> str:
    import hashlib
    return hashlib.sha256(("ageip:" + ip).encode()).hexdigest()[:24]


def age_locked(sid: str, marker_cookie: str | None = None, ip: str = "") -> bool:
    """True if this browser session, this browser's marker cookie, or this network address got a "can't sign up" result recently."""
    import time
    from .store import AGE_BLOCKS
    blocks = AGE_BLOCKS.read()
    if blocks.get(_blk(sid), 0) > time.time() or (ip and config.AGE_IP_LOCK_MINUTES > 0 and blocks.get(_blk_ip(ip), 0) > time.time()):
        return True
    try:
        return bool(marker_cookie) and float(marker_cookie) > time.time()
    except ValueError:
        return False


def lock_age(sid: str, ip: str = "") -> float:
    import time
    from .store import AGE_BLOCKS
    until = time.time() + config.AGE_LOCK_HOURS * 3600
    ip_until = time.time() + config.AGE_IP_LOCK_MINUTES * 60
    lock_ip = False
    if ip and config.AGE_IP_LOCK_MINUTES > 0:     # soft IP limit: a shared home/office/library address is locked only after MANY refusals, briefly
        from ..core import ratelimit
        lock_ip = not ratelimit.hit("ageref:" + _blk_ip(ip), max(0, config.AGE_IP_LOCK_AFTER), config.AGE_IP_LOCK_MINUTES * 60)

    def f(d):
        now = time.time()
        for k in [k for k, v in d.items() if v < now]:      # forget expired locks
            del d[k]
        d[_blk(sid)] = until
        if lock_ip:
            d[_blk_ip(ip)] = ip_until              # hashed address, short: clearing cookies must not allow an instant retry
    AGE_BLOCKS.update(f)
    return until


def signup(actor: Actor, display_name: str, dob: str) -> dict:
    """Nothing about the date of birth is stored unless every check passes."""
    if actor.user:
        raise ValueError("account already exists for this browser")
    try:
        d = date.fromisoformat(dob)
    except ValueError:
        raise ValueError("date of birth must be YYYY-MM-DD")
    if d > datetime.now(timezone.utc).date() or d.year < 1900:
        raise ValueError("invalid date of birth")
    if age_of({"dob": dob}) < config.MIN_SIGNUP_AGE:
        raise PermissionError(AGE_MESSAGE)           # refused: nothing about the date is stored
    name = (display_name or "").strip()[:40]
    if not name:
        raise ValueError("display name required")
    user = {"id": secrets.token_hex(6), "display_name": name, "dob": dob,
            "created": datetime.now(timezone.utc).isoformat(), "links": {}, "following": []}
    from .privacy import defaults_for           # everyone: private by default
    user["privacy"] = defaults_for(user)
    USERS.update(lambda d_: d_.__setitem__(actor.sid, user))
    return user


def restrictions(actor: Actor) -> dict:
    return {"dm_from_strangers": False,          # DMs are not built
            "public_link_outs": bool(actor.user) and not restricted(actor.user),
            "suspended": suspended(actor.user)}


def _priv(u):
    from .privacy import of
    return of(u)


def _next_username_change(u: dict):
    from . import usernames
    return usernames.next_change(u)


def _username_starter(u: dict) -> bool:
    from . import usernames
    return usernames.is_starter(u)


def public_profile(actor: Actor) -> dict:
    u = actor.user
    if not u:
        return {"signed_up": False, "restrictions": restrictions(actor)}
    from ..services import subscriptions as _subs
    return {"signed_up": True, "id": u["id"], "display_name": u["display_name"], "username": u.get("username"),
            "username_next_change": _next_username_change(u),
            "username_starter": _username_starter(u),
            "suspended": suspended(u), "links": u.get("links", {}),
            "following": u.get("following", []), "privacy": _priv(u), "printer": u.get("printer"), "restrictions": restrictions(actor),
            "plan": _subs.public_plan(u),
            "recovery": {"has_code": bool(u.get("recovery")), "issued": u.get("recovery_issued")} if actor.is_adult else None}


def user_by_id(uid: str):
    for sid, u in USERS.read().items():
        if u["id"] == uid:
            return sid, u
    return None, None


def follower_count(uid: str) -> int:
    from .privacy import social_on
    return sum(1 for u in USERS.read().values() if uid in u.get("following", []) and social_on(u) and not restricted(u))
