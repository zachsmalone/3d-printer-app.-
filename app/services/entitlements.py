"""Server-side plan comps. A comp is not a Stripe subscription and not a UI check.

Lifetime Pro for a named account is stored on that account (`entitlements.pro`):
kind comp, $0, no card, no expiry. Feature gates read it even while
ZEIM_PLANS_ENABLED is off, and still read it after paid plans turn on.
The seed looks up the username. It does not hardcode a check in the page.
"""
from __future__ import annotations

from datetime import datetime, timezone

# The tester this seed is for. Matching is the username, ignoring case.
TESTER_USERNAME = "cc0hort"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pro_comp(user: dict | None) -> dict | None:
    """The lifetime Pro comp on this account, or None.

    A comp counts only when it is kind `comp`, plan Pro, price 0, no card,
    and no expiry. Anything else is ignored so a partial record cannot grant Pro.
    """
    if not isinstance(user, dict):
        return None
    ent = user.get("entitlements")
    if not isinstance(ent, dict):
        return None
    pro = ent.get("pro")
    if not isinstance(pro, dict):
        return None
    if pro.get("kind") != "comp":
        return None
    if str(pro.get("plan") or "pro") != "pro":
        return None
    if pro.get("expires_at"):
        return None
    if pro.get("price_usd", 0) not in (0, 0.0):
        return None
    if pro.get("card"):
        return None
    return pro


def grant_pro_comp(user: dict, *, now: str | None = None) -> bool:
    """Attach lifetime Pro to this account dict. Idempotent: a second call keeps granted_at.

    Caller must already be inside the user-store update. Returns True only the first time.
    """
    if pro_comp(user):
        return False
    ent = user.get("entitlements")
    if not isinstance(ent, dict):
        ent = {}
        user["entitlements"] = ent
    ent["pro"] = {
        "kind": "comp",
        "plan": "pro",
        "price_usd": 0,
        "card": False,
        "expires_at": None,
        "source": "seed",
        "granted_at": now or _now(),
    }
    return True
