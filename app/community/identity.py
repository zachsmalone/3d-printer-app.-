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


def get_actor(request: Request, response: Response) -> Actor:
    sid = request.cookies.get(COOKIE)
    if not sid or len(sid) < 16:
        sid = secrets.token_urlsafe(24)
        response.set_cookie(COOKIE, sid, max_age=3600 * 24 * 365, httponly=True, samesite="lax")
    return Actor(sid, USERS.read().get(sid))


def signup(actor: Actor, display_name: str, dob: str) -> dict:
    if actor.user:
        raise ValueError("account already exists for this browser")
    try:
        d = date.fromisoformat(dob)
    except ValueError:
        raise ValueError("date of birth must be YYYY-MM-DD")
    if d > datetime.now(timezone.utc).date() or d.year < 1900:
        raise ValueError("invalid date of birth")
    if age_of({"dob": dob}) < config.MIN_SIGNUP_AGE:
        raise PermissionError(f"Accounts need age {config.MIN_SIGNUP_AGE}+. Younger learners can use the "
                              "education center with a classroom code from their teacher - no account needed.")
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


def public_profile(actor: Actor) -> dict:
    u = actor.user
    if not u:
        return {"signed_up": False, "restrictions": restrictions(actor)}
    return {"signed_up": True, "id": u["id"], "display_name": u["display_name"],
            "age_group": "adult" if actor.is_adult else "teen", "links": u.get("links", {}),
            "following": u.get("following", []), "privacy": _priv(u), "restrictions": restrictions(actor)}


def user_by_id(uid: str):
    for sid, u in USERS.read().items():
        if u["id"] == uid:
            return sid, u
    return None, None


def follower_count(uid: str) -> int:
    from .privacy import is_minor, social_on
    return sum(1 for u in USERS.read().values() if uid in u.get("following", []) and social_on(u) and not is_minor(u))
