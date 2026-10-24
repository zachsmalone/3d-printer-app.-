"""Optional Semi Pro / Pro plans. Core ZEIM stays free forever.

Payment is not live yet: the UI and API are real stubs that return honest "coming"
status. ZEIM never takes a cut of creator tips or Showcase sales — it earns only
from its own optional Semi Pro / Pro features when payment ships.

Prices (USD / month, subject to change before launch):
  Semi Pro  ~ $3.50
  Pro       ~ $5.50
"""
from __future__ import annotations

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

# Payment processor is not wired. Do not claim checkout works.
PAYMENT_LIVE = False
PAYMENT_NOTE = (
    "Payment is not live yet. You can look at the plans below; "
    "choosing Semi Pro or Pro will say Coming until checkout is ready."
)
TIP_NOTE = (
    "ZEIM never takes a cut of creator tips or Showcase sales. "
    "It only earns from its own optional Semi Pro and Pro features."
)


def catalog() -> dict:
    return {
        "payment_live": PAYMENT_LIVE,
        "payment_note": PAYMENT_NOTE,
        "tip_note": TIP_NOTE,
        "plans": list(PLANS),
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
        "payment_live": PAYMENT_LIVE,
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


def start_checkout(actor, plan_id: str) -> dict:
    """Stub checkout. Always honest: payment is not live."""
    plan_id = normalize_plan(plan_id)
    if plan_id == "free":
        return {"ok": True, "plan": "free", "message": "You're on Free. Core ZEIM stays free forever."}
    if not PAYMENT_LIVE:
        return {
            "ok": False,
            "coming": True,
            "plan": plan_id,
            "message": (
                f"{next(p['name'] for p in PLANS if p['id'] == plan_id)} is coming. "
                "Payment is not live yet — nothing was charged."
            ),
        }
    # Future: hand off to Stripe (or similar). Never claim success without a real session.
    return {"ok": False, "coming": True, "plan": plan_id, "message": "Checkout is not available yet."}
