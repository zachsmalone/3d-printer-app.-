"""Visibility + follow-opt-out rules. ONE place decides who may see what; every route calls it.

Levels (default PRIVATE for every build / upload / project):
  private   - only the owner (browser session that created it)
  followers - the owner + signed-in accounts that follow the owner's account (needs social = "on" on both sides)
  public    - anyone (and, for Showcase projects, listed in Trending / Free / For You / search)

Account options (users[sid]["privacy"]):
  profile  : public | followers | private   who can see the profile page / its link-outs / follower count
  social   : on | off                       "off" = fully opted out: cannot follow, cannot be followed, no follow
                                            button, no follower count or list. Existing follows are removed at once.
  default_visibility : visibility given to new builds / projects (teens: private by default, never "public")

Checks run on every request against live data, so a change takes effect immediately.
Denials are reported as 404 (not 403) so the existence of a private item is not leaked.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from .. import config
from .identity import Actor
from .store import USERS

LEVELS = ("private", "followers", "public")
SOCIAL = ("on", "off")


def is_minor(user: dict | None) -> bool:
    """Under ADULT_AGE (13-17 for anyone who could sign up). Computed live from the stored date of birth."""
    if not user or not user.get("dob"):
        return False
    from .identity import age_of
    return age_of(user) < config.ADULT_AGE


def clamp_for_minor(level: str) -> str:
    """The most open level a 13-17 account is allowed right now (launch posture: private only)."""
    if level == "public":
        if config.TEEN_PUBLIC_ENABLED:
            return "public"
        level = "followers"
    if level == "followers" and not config.TEEN_FOLLOWERS_ENABLED:
        return "private"
    return level


def defaults_for(user: dict | None, teen: bool) -> dict:
    return {"profile": "private" if teen else "public", "social": "on", "default_visibility": "private"}


def of(user: dict | None) -> dict:
    """Stored options over defaults (accounts created before privacy existed get the teen/adult defaults)."""
    teen = False
    if user and user.get("dob"):
        from .identity import age_of
        teen = age_of(user) < config.ADULT_AGE
    out = {**defaults_for(user, teen), **((user or {}).get("privacy") or {})}
    if teen:      # stored values from before the teen rules existed (or from a looser flag setting) can never be looser than allowed now
        out["profile"] = clamp_for_minor(out["profile"])
        out["default_visibility"] = clamp_for_minor(out["default_visibility"])
    return out


def social_on(user: dict | None) -> bool:
    return bool(user) and of(user)["social"] == "on"


def effective(visibility: str | None, owner_user: dict | None) -> str:
    """'followers' collapses to 'private' when the owner has opted out of following / has no account."""
    v = visibility if visibility in LEVELS else "private"
    if is_minor(owner_user):
        v = clamp_for_minor(v)
    if v == "followers" and not social_on(owner_user):
        return "private"
    return v


def can_view(actor: Actor, owner_sid: str | None, visibility: str | None, users: dict | None = None) -> bool:
    if owner_sid and actor.sid == owner_sid:
        return True
    if owner_sid is None:                 # curated / example content
        return (visibility or "public") == "public"
    users = USERS.read() if users is None else users
    ou = users.get(owner_sid)
    v = effective(visibility, ou)
    if v == "public":
        return True
    if v == "followers":
        me = users.get(actor.sid) if actor.sid else None
        return bool(me) and social_on(me) and ou["id"] in me.get("following", [])
    return False


def can_view_profile(actor: Actor, target_uid: str, users: dict | None = None) -> bool:
    users = USERS.read() if users is None else users
    owner_sid = next((s for s, u in users.items() if u["id"] == target_uid), None)
    if owner_sid is None:
        return False
    return can_view(actor, owner_sid, of(users[owner_sid])["profile"], users)


def can_follow(actor: Actor, target_user: dict | None, target_is_example=False) -> bool:
    if not actor.user or not social_on(actor.user):
        return False
    if target_is_example:
        return True
    if is_minor(target_user) and not config.TEEN_FOLLOWERS_ENABLED:      # nobody follows a teen at launch (adults or teens)
        return False
    return (bool(target_user) and social_on(target_user) and of(target_user)["profile"] != "private"
            and target_user["id"] != actor.user["id"])


def check_level(actor: Actor, level: str) -> str:
    """Validate a visibility a user asks for. Raises ValueError/PermissionError with a friendly message."""
    if level not in LEVELS:
        raise ValueError(f"visibility must be one of {list(LEVELS)}")
    if level != "private" and actor.is_teen and clamp_for_minor(level) != level:
        raise PermissionError("Accounts under 18 keep their projects Private for now. "
                              "Your work is still saved and you can download it any time.")
    if level != "private":
        if not actor.user:
            raise PermissionError("Create an account to share with followers or the public. Without one everything stays private.")
        if level == "followers" and not social_on(actor.user):
            raise PermissionError("You have opted out of following, so 'followers only' is unavailable. Turn following back on in Privacy settings, or choose Private/Public.")
    return level


def default_level(actor: Actor) -> str:
    if not actor.user:
        return "private"
    d = of(actor.user)["default_visibility"]
    if actor.is_teen:
        d = clamp_for_minor(d)
    return d if d in LEVELS and not (d == "followers" and not social_on(actor.user)) else "private"


def set_privacy(actor: Actor, body: dict) -> dict:
    if not actor.user:
        raise PermissionError("sign up first")
    cur = of(actor.user)
    new = dict(cur)
    if "profile" in body:
        if body["profile"] not in LEVELS:
            raise ValueError("profile must be public | followers | private")
        if actor.is_teen and clamp_for_minor(body["profile"]) != body["profile"]:
            raise PermissionError("Accounts under 18 keep their profile Private for now.")
        new["profile"] = body["profile"]
    if "social" in body:
        if body["social"] not in SOCIAL:
            raise ValueError("social must be on | off")
        new["social"] = body["social"]
    if "default_visibility" in body:
        if body["default_visibility"] not in LEVELS:
            raise ValueError("default_visibility must be private | followers | public")
        if actor.is_teen and clamp_for_minor(body["default_visibility"]) != body["default_visibility"]:
            raise PermissionError("Accounts under 18 keep their projects Private for now.")
        new["default_visibility"] = body["default_visibility"]
    if new["social"] == "off":
        if new["profile"] == "followers":
            new["profile"] = "private"            # nobody can follow, so 'followers' would mean private
        if new["default_visibility"] == "followers":
            new["default_visibility"] = "private"
    uid = actor.user["id"]

    def f(d):
        u = d[actor.sid]
        u["privacy"] = new
        if new["social"] == "off":                # opt out: remove follows in both directions, immediately
            u["following"] = []
            for other in d.values():
                if uid in other.get("following", []):
                    other["following"].remove(uid)
    USERS.update(f)
    return new


def followers_of(uid: str) -> list[dict]:
    """Followers who are adults (a teen's name is never listed on someone else's follower list)."""
    return [{"id": u["id"], "display_name": "@" + u["username"] if u.get("username") else "a ZEIM maker"} for u in USERS.read().values()
            if uid in u.get("following", []) and social_on(u) and not is_minor(u)]


def migrate_minors() -> dict:
    """One-time/idempotent: make existing 13-17 data match the current teen posture (runs at startup).
    Rewrites stored profile/default/project/build visibility down to what is allowed, and removes follows of teens."""
    from .. import config as cfg
    from .store import LISTINGS
    changed = {"users": 0, "projects": 0, "builds": 0, "follows": 0}
    users = USERS.read()
    minors = {sid for sid, u in users.items() if is_minor(u)}
    minor_ids = {users[s]["id"] for s in minors}

    def fu(d):
        for sid, u in d.items():
            pv = u.get("privacy")
            if sid in minors and pv:
                for k in ("profile", "default_visibility"):
                    if pv.get(k) and clamp_for_minor(pv[k]) != pv[k]:
                        pv[k] = clamp_for_minor(pv[k]); changed["users"] += 1
            if not cfg.TEEN_FOLLOWERS_ENABLED:
                keep = [x for x in u.get("following", []) if x not in minor_ids]
                if len(keep) != len(u.get("following", [])):
                    changed["follows"] += len(u["following"]) - len(keep); u["following"] = keep
    USERS.update(fu)

    def fl(items):
        for i in items:
            if i.get("owner_sid") in minors and clamp_for_minor(i.get("visibility", "private")) != i.get("visibility", "private"):
                i["visibility"] = clamp_for_minor(i["visibility"]); changed["projects"] += 1
    LISTINGS.update(fl)
    try:
        for m in cfg.OUT.glob("*/meta.json"):
            import json
            meta = json.loads(m.read_text())
            if meta.get("owner_sid") in minors and clamp_for_minor(meta.get("visibility", "private")) != meta.get("visibility", "private"):
                meta["visibility"] = clamp_for_minor(meta["visibility"])
                m.write_text(json.dumps(meta, indent=1, default=str)); changed["builds"] += 1
    except Exception:
        pass
    return changed


# ---- signed, expiring file links (so a slicer on the owner's PC can fetch a PRIVATE build without cookies) ----
_KEY_FILE = config.DATA / "link.key"


def _key() -> bytes:
    if not _KEY_FILE.exists():
        _KEY_FILE.write_text(secrets.token_hex(32))
        try:
            _KEY_FILE.chmod(0o600)
        except OSError:
            pass
    return _KEY_FILE.read_text().strip().encode()


LINK_TTL = 10 * 60          # slicer links only need to live long enough to open the file


def make_token(bid: str, name: str, ttl: int = LINK_TTL) -> str:
    """Signed, short-lived link bound to ONE build AND ONE file name (e.g. model.3mf): useless for anything else."""
    exp = int(time.time()) + ttl
    sig = hmac.new(_key(), f"{bid}.{name}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{exp}-{sig}"


def check_token(bid: str, name: str, token: str) -> bool:
    try:
        exp, sig = token.split("-", 1)
        if int(exp) < time.time():
            return False
    except ValueError:
        return False
    good = hmac.new(_key(), f"{bid}.{name}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(good, sig)
