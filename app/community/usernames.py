"""Unique usernames (the name a model is credited to).

* 3-20 characters: letters, digits and underscore, starting with a letter. Unique ignoring case.
* No email-like or phone-like strings, nothing the chat filter blocks, no reserved words (staff, admin, zeim ...).
* Under-18 accounts ALWAYS start from a generated nickname (friendly, never a real name) and may change it only to a name that passes all of the above.
* A username is separate from the display name; neither is ever an email address, and email is never part of any public response.
All of it is enforced here on the server; the pages only show the message.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from .. import config
from . import safety
from .store import USERS

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
RESERVED = {"admin", "administrator", "moderator", "mod", "staff", "support", "system", "zeim", "teacher", "official", "root", "owner", "help",
            "anonymous", "null", "undefined", "nasa", "creality", "prusa", "bambu"}
ADJ = ["Sunny", "Bright", "Happy", "Brave", "Calm", "Clever", "Cosmic", "Gentle", "Jolly", "Kind", "Lucky", "Merry", "Nimble", "Quick", "Quiet", "Shiny",
       "Silver", "Snowy", "Speedy", "Sparkly", "Swift", "Tiny", "Witty", "Zesty", "Golden", "Misty", "Fuzzy", "Breezy", "Cheery", "Dapper"]
NOUN = ["Otter", "Panda", "Falcon", "Maple", "Comet", "Robin", "Koala", "Pebble", "Acorn", "Beetle", "Cricket", "Dolphin", "Ember", "Fox", "Gecko", "Heron",
        "Ibis", "Jaguar", "Kiwi", "Lemur", "Moth", "Newt", "Owl", "Puffin", "Quokka", "Raven", "Sparrow", "Turtle", "Willow", "Yak"]


class UsernameError(ValueError):
    pass


class UsernameWait(UsernameError):
    """A rename was asked for before the waiting period is over."""


def _norm(name: str) -> str:
    return (name or "").strip()


def check_shape(name: str) -> str:
    """Raises UsernameError with a kind message unless the NAME itself is acceptable (shape, reserved words, phone-like, chat filter)."""
    n = _norm(name)
    if "@" in n or "." in n or "://" in n:
        raise UsernameError("Please don't use an email address or a link as a username.")
    if not NAME_RE.match(n):
        raise UsernameError("Use 3 to 20 letters, numbers or underscores, starting with a letter.")
    if sum(ch.isdigit() for ch in n) >= 7:
        raise UsernameError("Please don't use a phone number as a username.")
    if n.lower() in RESERVED or any(n.lower().startswith(r) and r in ("admin", "zeim", "staff", "moderator") for r in RESERVED):
        raise UsernameError("That name is saved for ZEIM. Please pick another.")
    try:
        safety.filter_only(n, "Username")
    except Exception as e:                                # the chat filter's own (kind) message
        raise UsernameError((getattr(e, "payload", None) or {}).get("message") or "That name isn't allowed. Please pick another.")
    return n


def _taken(users: dict, name: str, except_sid: str | None = None) -> bool:
    """Taken = someone's current username OR a name someone used to have (old names stay reserved so a credit can never be taken over)."""
    low = name.lower()
    return any((u.get("username") or "").lower() == low or low in u.get("username_history", []) for s, u in users.items() if s != except_sid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def next_change(u: dict) -> str | None:
    """ISO time when this account may rename itself again, or None if it may do so now (a first rename is always free)."""
    last = u.get("username_changed")
    if not last:
        return None
    try:
        due = datetime.fromisoformat(last) + timedelta(days=config.USERNAME_CHANGE_DAYS)
    except ValueError:
        return None
    return due.isoformat() if due > _now() else None


def generate(users: dict | None = None) -> str:
    users = USERS.read() if users is None else users
    for _ in range(200):
        n = f"{secrets.choice(ADJ)}{secrets.choice(NOUN)}{secrets.randbelow(900) + 100}"
        try:
            check_shape(n)
        except UsernameError:
            continue
        if not _taken(users, n):
            return n
    raise UsernameError("Couldn't make a name just now. Please try again.")


def suggestions(n: int = 3) -> list[str]:
    users = USERS.read(); out = []
    while len(out) < n:
        c = generate(users)
        if c not in out:
            out.append(c)
    return out


def assign_new(sid: str, user: dict, chosen: str | None, minor: bool) -> str:
    """At sign-up. Minors always get a generated nickname; an adult may supply their own (it must pass every check)."""
    name = None
    if chosen and not minor:
        name = check_shape(chosen)

    def f(d):
        nonlocal name
        if name is not None:
            if _taken(d, name, sid):
                raise UsernameError("That name is taken. Please pick another.")
        else:
            name = generate(d)
        d[sid]["username"] = name
        d[sid]["username_changed"] = None
    USERS.update(f)
    user["username"] = name
    return name


def change(sid: str, new: str) -> str:
    """Rename. Only the letter case of your own current name is always free; anything else is allowed once per USERNAME_CHANGE_DAYS (90).
    The name you leave stays reserved for you (username_history), and credits follow the account, so old credits show the new name."""
    n = check_shape(new)

    def f(d):
        if sid not in d:
            raise KeyError(sid)
        u = d[sid]
        cur = u.get("username") or ""
        if n.lower() == cur.lower():
            u["username"] = n                                  # just the capital letters
            return
        if _taken(d, n, sid):
            raise UsernameError("That name is taken. Please pick another.")
        due = next_change(u)
        if due:
            raise UsernameWait("You can change your username again on " + due[:10] + ".")
        if cur and cur.lower() not in u.setdefault("username_history", []):
            u["username_history"].append(cur.lower())
        u["username"] = n
        u["username_changed"] = _now().isoformat()
    USERS.update(f)
    return n


def migrate() -> int:
    """Give every existing account that has no username one: adults keep their display name if it is a valid free username, everyone else
    (all under-18 accounts included, whose display name might be a real name) gets a generated nickname. Safe to run again."""
    from . import identity as idn
    changed = []

    def f(d):
        for sid, u in d.items():
            if u.get("username"):
                continue
            adult = idn.age_of(u) >= config.ADULT_AGE
            cand = re.sub(r"[^A-Za-z0-9_]", "", (u.get("display_name") or "").replace(" ", "_"))[:20]
            ok = None
            if adult:
                try:
                    c = check_shape(cand)
                    if not _taken(d, c, sid):
                        ok = c
                except UsernameError:
                    pass
            u["username"] = ok or generate(d)
            u["username_changed"] = None
            changed.append(sid)
    USERS.update(f)
    return len(changed)


def ensure(sid: str) -> str | None:
    u = USERS.read().get(sid)
    if not u:
        return None
    if not u.get("username"):
        migrate()
        u = USERS.read().get(sid)
    return u.get("username")
