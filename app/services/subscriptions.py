"""Optional Semi Pro / Pro plans. Core ZEIM stays free forever.

ZEIM_PLANS_ENABLED defaults off. Paid plans stay visible as "coming later" and
checkout does not start a payment. Missing Stripe keys are normal and never an error.
ZEIM never takes a cut of creator tips or Showcase sales.

Prices (USD / month, subject to change before launch):
  Semi Pro  ~ $3.50
  Pro       ~ $5.50
"""
from __future__ import annotations

from .. import config
from ..community.store import USERS

# Honest catalog. payment_live=False until a real processor is wired.
PLANS = (
    {
        "id": "free",
        "name": "Free",
        "price_usd": 0,
        "price_label": "Free forever",
        "summary": "Everything you need to make, slice, and share. Stays free.",
        "includes": [
            "Photo → lithophane, relief, pop-art, bust, logo-to-3D",
            "CAD / Edit, Live Sculpt, Smart Fix",
            "FDM slicer and TorchC0 resin tools",
            "Showcase sharing (ZEIM never takes a cut of your tips or sales)",
        ],
    },
    {
        "id": "semi_pro",
        "name": "Semi Pro",
        "price_usd": 3.50,
        "price_label": "About $3.50 / month",
        "summary": "Extras for makers who use ZEIM a lot. Optional.",
        "includes": [
            "Everything in Free",
            "Higher daily caps on optional extras when those ship",
            "Early access to new Make tools marked Semi Pro",
        ],
        "coming": True,
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_usd": 5.50,
        "price_label": "About $5.50 / month",
        "summary": "All optional extras, including 2D→3D when Pro-gated after launch.",
        "includes": [
            "Everything in Semi Pro",
            "2D→3D (Figure / Bust) when Pro-only mode is on",
            "Highest caps on optional extras when those ship",
        ],
        "coming": True,
    },
)

PLAN_IDS = {p["id"] for p in PLANS}
PAID_IDS = {"semi_pro", "pro"}

# No payment processor is wired. Do not treat Stripe env vars as checkout:
# missing keys stay quiet, and a key sitting in the environment must not charge.
TIP_NOTE = (
    "ZEIM never takes a cut of creator tips or Showcase sales. "
    "It only earns from its own optional Semi Pro and Pro features."
)
CLOSED_NOTE = (
    "Paid plans are not available yet. Free stays free forever. "
    "Nothing on this page starts a payment."
)
OPEN_STUB_NOTE = (
    "Payment is not live yet. You can look at the plans below; "
    "choosing Semi Pro or Pro will say Coming until checkout is ready."
)


def plans_enabled() -> bool:
    return config.plans_enabled()


def payment_live() -> bool:
    """Always false in this build. Stripe keys, present or missing, do not flip this."""
    return False


def payment_note() -> str:
    if not plans_enabled():
        return CLOSED_NOTE
    return OPEN_STUB_NOTE


def _plan_public(plan: dict) -> dict:
    row = dict(plan)
    paid = plan["id"] in PAID_IDS
    # A buy button exists only when the flag is on AND a processor is actually live.
    row["purchasable"] = bool(paid and plans_enabled() and payment_live())
    if paid:
        row["coming"] = not row["purchasable"]
    else:
        row["coming"] = False
    return row


def catalog() -> dict:
    return {
        "payment_live": payment_live(),
        "plans_enabled": plans_enabled(),
        "payment_note": payment_note(),
        "tip_note": TIP_NOTE,
        "plans": [_plan_public(p) for p in PLANS],
        "currency": "USD",
    }


def normalize_plan(raw) -> str:
    s = str(raw or "free").strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("semipro", "semi"):
        s = "semi_pro"
    return s if s in PLAN_IDS else "free"


def plan_of(user: dict | None) -> str:
    if not user:
        return "free"
    return normalize_plan(user.get("plan"))


def public_plan(user: dict | None) -> dict:
    pid = plan_of(user)
    meta = next(p for p in PLANS if p["id"] == pid)
    return {
        "id": pid,
        "name": meta["name"],
        "price_label": meta["price_label"],
        "payment_live": payment_live(),
        "plans_enabled": plans_enabled(),
    }


def set_plan(sid: str, plan_id: str) -> dict:
    """Dev / test helper: set an account's plan in users.json. Not a checkout."""
    plan_id = normalize_plan(plan_id)
    out = {}

    def f(d):
        u = d.get(sid)
        if not u:
            raise KeyError("no account")
        if plan_id == "free":
            u.pop("plan", None)
        else:
            u["plan"] = plan_id
        out["user"] = u

    USERS.update(f)
    return public_plan(out["user"])


def _plan_name(plan_id: str) -> str:
    return next(p["name"] for p in PLANS if p["id"] == plan_id)


def start_checkout(actor, plan_id: str) -> dict:
    """Paid checkout is closed unless plans are enabled AND a processor is live.

    This build has no processor. The return value never includes a payment URL,
    and it never reads Stripe keys. `blocked` asks the route to answer 403.
    """
    plan_id = normalize_plan(plan_id)
    if plan_id == "free":
        return {
            "ok": True,
            "checkout": False,
            "plan": "free",
            "message": "You're on Free. Core ZEIM stays free forever.",
        }
    name = _plan_name(plan_id)
    if not plans_enabled():
        return {
            "ok": False,
            "coming": True,
            "checkout": False,
            "blocked": True,
            "plan": plan_id,
            "message": f"{name} is coming later. Payment is not available yet — nothing was charged.",
        }
    if not payment_live():
        return {
            "ok": False,
            "coming": True,
            "checkout": False,
            "plan": plan_id,
            "message": f"{name} is coming. Payment is not live yet — nothing was charged.",
        }
    # A future processor belongs here and must still require plans_enabled().
    # Do not report success without a real checkout session. Never store card data.
    return {
        "ok": False,
        "coming": True,
        "checkout": False,
        "plan": plan_id,
        "message": "Checkout is not available yet. Nothing was charged.",
    }
