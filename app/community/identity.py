"""Identity + teen-safe posture. Age is computed server-side from the stored date of birth.

Local MVP identity = session cookie (`p3d_sid`) -> account record; no passwords yet (real auth is
a roadmap item). Rules:
  * no accounts under MIN_SIGNUP_AGE (13); under-13s learn via a teacher's classroom code (no PII)
  * 13-17 = "teen": safer defaults - DMs from strangers OFF (DMs are a stub anyway), public
    profile link-outs hidden, cannot create classrooms
  * the site is family-friendly only for everyone (see COMMUNITY_GUIDELINES.md)
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
    sid: str
    user: dict | None

    @property
    def age(self):
        return age_of(self.user) if self.user else None

    @property
    def is_adult(self):
        return self.age is not None and self.age >= config.ADULT_AGE

    @property
    def is_teen(self):
        return self.age is not None and self.age < config.ADULT_AGE


def age_of(user: dict, today: date | None = None) -> int:
    d = date.fromisoformat(user["dob"])
    t = today or datetime.now(timezone.utc).date()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


def cookie_args(request: Request) -> dict:
    """Flags for every cookie we set: HttpOnly, SameSite=Lax, and Secure whenever the page came over https (PHOTO3D_COOKIE_SECURE=true|false|auto)."""
    mode = config.COOKIE_SECURE
    secure = True if mode in ("1", "true", "yes", "on") else False if mode in ("0", "false", "no", "off") else request.url.scheme == "https"
    return {"httponly": True, "samesite": "lax", "secure": secure}


def get_actor(request: Request, response: Response) -> Actor:
    sid = request.cookies.get(COOKIE)
    if not sid or len(sid) < 16:
        sid = secrets.token_urlsafe(24)
        response.set_cookie(COOKIE, sid, max_age=3600 * 24 * 365, **cookie_args(request))
    return Actor(sid, USERS.read().get(sid))


def session_only_cookie(request: Request, response: Response, sid: str):
    """Re-issue the session cookie WITHOUT an expiry, so a shared computer forgets it when the browser closes."""
    response.raw_headers[:] = [(k, v) for k, v in response.raw_headers if not (k.lower() == b"set-cookie" and v.startswith(COOKIE.encode() + b"="))]
    response.set_cookie(COOKIE, sid, **cookie_args(request))


AGE_COOKIE = "p3d_ag"
AGE_MESSAGE = ("We can't create an account for you right now. If you're learning with a class, ask your teacher for "
               "the class code and password - you don't need an account for that.")


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
    if ip and config.AGE_IP_LOCK_MINUTES > 0:     # Edge 5: a shared school address is locked only after several refusals, never after one
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
        raise PermissionError(AGE_MESSAGE)           # neutral: never states the age limit
    name = (display_name or "").strip()[:40]
    if not name:
        raise ValueError("display name required")
    user = {"id": secrets.token_hex(6), "display_name": name, "dob": dob,
            "created": datetime.now(timezone.utc).isoformat(), "links": {}, "following": []}
    from .privacy import defaults_for           # teens: private profile; everyone: private by default
    user["privacy"] = defaults_for(user, age_of(user) < config.ADULT_AGE)
    USERS.update(lambda d_: d_.__setitem__(actor.sid, user))
    return user


def restrictions(actor: Actor) -> dict:
    teen = actor.is_teen
    return {"dm_from_strangers": False,          # DMs not built; rule documented: never from strangers for teens
            "public_link_outs": not teen,        # teens' social link-outs are not shown publicly
            "can_create_classroom": actor.is_adult}


def _priv(u):
    from .privacy import of
    return of(u)


def _next_username_change(u: dict):
    from . import usernames
    return usernames.next_change(u)


def public_profile(actor: Actor) -> dict:
    u = actor.user
    if not u:
        return {"signed_up": False, "restrictions": restrictions(actor)}
    return {"signed_up": True, "id": u["id"], "display_name": u["display_name"], "username": u.get("username"),
            "username_next_change": _next_username_change(u),
            "age_group": "adult" if actor.is_adult else "teen", "links": u.get("links", {}),
            "following": u.get("following", []), "privacy": _priv(u), "restrictions": restrictions(actor),
            "recovery": {"has_code": bool(u.get("recovery")), "issued": u.get("recovery_issued")} if actor.is_adult else None}


def user_by_id(uid: str):
    for sid, u in USERS.read().items():
        if u["id"] == uid:
            return sid, u
    return None, None


def follower_count(uid: str) -> int:
    from .privacy import is_minor, social_on
    return sum(1 for u in USERS.read().values() if uid in u.get("following", []) and social_on(u) and not is_minor(u))
