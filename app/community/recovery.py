"""Adult account recovery (CR-15). Accounts are cookie-bound; clearing browser data used to lose the account.
An adult account gets a one-time RECOVERY CODE when it is made (shown once; only a hash is stored). Entering it in a new browser moves
the account - classes, builds, progress - to that browser and the old browser loses it. The code is single-use: using it issues a new one.
Not real authentication (see ROADMAP): whoever holds the code IS the account holder, so the page says to keep it like a password."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timezone

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
from .identity import Actor
from .store import LISTINGS, PREFS, USERS

_audit = logging.getLogger("zeim.audit")


def _norm(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _hash(code: str) -> str:
    return hashlib.sha256(("recover:" + _norm(code)).encode()).hexdigest()       # 80 random bits: a fast hash is enough


def _new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def issue(sid: str) -> str:
    """Make (or replace) the recovery code of the adult account in this browser. The old code stops working. Returns the code ONCE."""
    code = _new_code()

    def f(d):
        if sid not in d:
            raise KeyError(sid)
        d[sid]["recovery"] = _hash(code)
        d[sid]["recovery_issued"] = datetime.now(timezone.utc).isoformat()
    USERS.update(f)
    return code


def _too_many(sid: str, ip: str) -> bool:
    from ..core import ratelimit
    from .. import config
    return ratelimit.count(f"recfail:{sid}", 600) >= config.RECOVERY_FAIL_LIMIT or ratelimit.count(f"recfail-ip:{ip}", 600) >= config.RECOVERY_FAIL_LIMIT * 3


def _fail(sid: str, ip: str):
    from ..core import ratelimit
    ratelimit.hit(f"recfail:{sid}", 10 ** 6, 600)
    ratelimit.hit(f"recfail-ip:{ip}", 10 ** 6, 600)


class Locked(Exception):
    pass


def recover(actor: Actor, code: str, ip: str = "-") -> tuple[dict, str]:
    """Re-bind the account that owns `code` to THIS browser. -> (user, NEW recovery code). Raises Locked (too many wrong tries),
    KeyError (wrong code), ValueError (this browser can't take an account over)."""
    if _too_many(actor.sid, ip):
        raise Locked()
    if len(code or "") > 40 or len(_norm(code)) != 16:
        _fail(actor.sid, ip); raise KeyError("code")
    want = _hash(code)
    users = USERS.read()
    old = next((sid for sid, u in users.items() if u.get("recovery") and hmac.compare_digest(u["recovery"], want)), None)
    if old is None:
        _fail(actor.sid, ip); raise KeyError("code")
    if old == actor.sid:
        raise ValueError("This browser already has that account.")
    if actor.user:
        raise ValueError("This browser already has an account. Use a browser that doesn't, such as a private window.")
    new_code = _new_code()

    def move_user(d):
        u = d.pop(old, None)
        if u is None or actor.sid in d:
            raise ValueError("Please try again.")
        u["recovery"] = _hash(new_code); u["recovery_issued"] = datetime.now(timezone.utc).isoformat()
        d[actor.sid] = u
        return u
    user = USERS.update(move_user)

    from . import ownership
    ownership.move_owner(old, actor.sid)                        # builds / Edit projects + lesson checklist follow the account

    def move_listings(l):
        for i in l:
            if i.get("owner_sid") == old:
                i["owner_sid"] = actor.sid
    LISTINGS.update(move_listings)
    PREFS.update(lambda d: d.__setitem__(actor.sid, d.pop(old)) if old in d else None)
    _audit.info("account recovered: user=%s at=%s", user["id"], datetime.now(timezone.utc).isoformat())
    return user, new_code
