"""Visibility + follow-opt-out rules. ONE place decides who may see what; every route calls it.

Levels (default PRIVATE for every build / upload / project):
  private   - only the owner (browser session that created it)
  followers - the owner + signed-in accounts that follow the owner's account (needs social = "on" on both sides)
  public    - anyone (and, for Showcase projects, listed in Trending / Free / For You / search)

Account options (users[sid]["privacy"]):
  profile  : public | followers | private   who can see the profile page / its link-outs / follower count
  social   : on | off                       "off" = fully opted out: cannot follow, cannot be followed, no follow
                                            button, no follower count or list. Existing follows are removed at once.
  default_visibility : visibility given to new builds / projects (private by default)

Suspended accounts (and legacy under-18 accounts) are "restricted": their content is effectively private, they can't follow,
be followed or choose anything but Private.

Checks run on every request against live data, so a change takes effect immediately.
Denials are reported as 404 (not 403) so the existence of a private item is not leaked.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from .. import config
from .identity import Actor, restricted
from .store import USERS

LEVELS = ("private", "followers", "public")
SOCIAL = ("on", "off")


def defaults_for(user: dict | None = None) -> dict:
    return {"profile": "public", "social": "on", "default_visibility": "private"}


def of(user: dict | None) -> dict:
    """Stored options over defaults."""
    return {**defaults_for(user), **((user or {}).get("privacy") or {})}


def social_on(user: dict | None) -> bool:
    return bool(user) and of(user)["social"] == "on"


def effective(visibility: str | None, owner_user: dict | None) -> str:
    """'followers' collapses to 'private' when the owner has opted out of following / has no account."""
    v = visibility if visibility in LEVELS else "private"
    if restricted(owner_user):            # suspended / legacy under-18 account: nobody else sees its content
        return "private"
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
    if restricted(actor.user) or restricted(target_user):
        return False
    return (bool(target_user) and social_on(target_user) and of(target_user)["profile"] != "private"
            and target_user["id"] != actor.user["id"])


def check_level(actor: Actor, level: str) -> str:
    """Validate a visibility a user asks for. Raises ValueError/PermissionError with a friendly message."""
    if level not in LEVELS:
        raise ValueError(f"visibility must be one of {list(LEVELS)}")
    if level != "private" and restricted(actor.user):
        raise PermissionError("This account can't share right now. Your work is still saved and you can download it any time.")
    if level != "private":
        if not actor.user:
            raise PermissionError("Create an account to share with followers or the public. Without one everything stays private.")
        if level == "followers" and not social_on(actor.user):
            raise PermissionError("You have opted out of following, so 'followers only' is unavailable. Turn following back on in Privacy settings, or choose Private/Public.")
    return level


def default_level(actor: Actor) -> str:
    if not actor.user:
        return "private"
    if restricted(actor.user):
        return "private"
    d = of(actor.user)["default_visibility"]
    return d if d in LEVELS and not (d == "followers" and not social_on(actor.user)) else "private"


def set_privacy(actor: Actor, body: dict) -> dict:
    if not actor.user:
        raise PermissionError("sign up first")
    cur = of(actor.user)
    new = dict(cur)
    if "profile" in body:
        if body["profile"] not in LEVELS:
            raise ValueError("profile must be public | followers | private")
        new["profile"] = body["profile"]
    if "social" in body:
        if body["social"] not in SOCIAL:
            raise ValueError("social must be on | off")
        new["social"] = body["social"]
    if "default_visibility" in body:
        if body["default_visibility"] not in LEVELS:
            raise ValueError("default_visibility must be private | followers | public")
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
    """Followers in good standing (suspended / restricted accounts are not listed)."""
    return [{"id": u["id"], "display_name": "@" + u["username"] if u.get("username") else "a ZEIM maker"} for u in USERS.read().values()
            if uid in u.get("following", []) and social_on(u) and not restricted(u)]


def following_of(user: dict) -> list[dict]:
    """The people THIS account follows, by username (never the display name, which may be a real name), so it can manage them.
    An account that is gone, suspended or has turned following off is still listed (unnamed) so it can be unfollowed."""
    users = {u["id"]: u for u in USERS.read().values()}
    out = []
    for uid in dict.fromkeys(user.get("following", [])):
        u = users.get(uid)
        ok = bool(u) and not restricted(u) and social_on(u) and of(u)["profile"] != "private"
        out.append({"id": uid, "name": ("@" + u["username"]) if ok and u.get("username") else ("a ZEIM maker" if ok else "an account that's no longer available"),
                    "available": ok, "profile_url": f"/u/{uid}" if ok else None})
    return out


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
