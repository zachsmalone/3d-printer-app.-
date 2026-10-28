"""Optional Semi Pro / Pro plans. Core ZEIM stays free forever.

Prices (USD / month):
  Semi Pro  $3.50
  Pro       $5.50

ZEIM_PLANS_ENABLED defaults off. Paid plans stay visible as Coming later and
checkout does not start a payment, even if Stripe keys are present. Missing
keys are normal and never an error. With the flag on, hosted Checkout runs
only when the secret key, webhook secret, and both Price ids are set.

ZEIM may add an honest ~1% service fee on those plan charges only (nearest cent:
4¢ and 6¢). Stripe's processing fee is separate and disclosed. ZEIM never takes
a cut of creator tips or Showcase sales.

When checkout is allowed, it is hosted by Stripe (no card data on ZEIM).
Webhooks write `plan` plus the Stripe Customer and Subscription ids. Feature
gates read `plan` (see `has_paid_plan`). Without the flag or without keys, the
UI stays an honest Coming.
"""
from __future__ import annotations

from .. import config
from ..community.store import USERS
from . import stripe_billing as billing

# Honest catalog. `coming` and `purchasable` follow the plans flag and Stripe config.
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
        "price_label": "$3.50 / month",
        "summary": "Extras for makers who use ZEIM a lot. Optional. Helps fund hosting.",
        "includes": [
            "Everything in Free",
            "Higher daily caps on optional extras when those ship",
            "Early access to new Make tools marked Semi Pro",
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_usd": 5.50,
        "price_label": "$5.50 / month",
        "summary": "All optional extras, including 2D→3D when Pro-gated after launch. Helps fund hosting.",
        "includes": [
            "Everything in Semi Pro",
            "2D→3D (Figure / Bust) when Pro-only mode is on",
            "Highest caps on optional extras when those ship",
        ],
    },
)

PLAN_IDS = {p["id"] for p in PLANS}
PAID_IDS = {"semi_pro", "pro"}

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
FEE_NOTE = (
    "ZEIM adds a service fee of about 1% of the plan price, rounded to the nearest cent "
    "(Semi Pro 4¢, Pro 6¢), on these plan charges only. It helps fund hosting. "
    "It is a separate line on the Stripe bill, not a cut of creator tips or Showcase sales."
)
PROCESSING_NOTE = (
    "Stripe's processing fee is separate from the plan price and from the ZEIM service fee. "
    "You cover it, and Stripe keeps it — ZEIM does not. "
    "The amount depends on the payment method, so ZEIM does not add a guessed processing charge. "
    "Card, Apple Pay, and Google Pay are offered when they are turned on for ZEIM's Stripe account. "
    "PayPal and Cash App Pay show up only if they are turned on in the Stripe Dashboard "
    "and Stripe allows them on a monthly plan."
)


def plans_enabled() -> bool:
    return config.plans_enabled()


def payment_live() -> bool:
    """True only when paid plans are explicitly on and the Stripe key is a live key.

    Test mode and a missing processor stay false. A live key with the plans flag
    off is also false: soft launch does not charge.
    """
    return plans_enabled() and billing.stripe_mode() == "live"


def _payment_note(mode: str) -> str:
    if not plans_enabled():
        return CLOSED_NOTE
    if mode == "test":
        return (
            "Stripe test mode. Choosing a plan opens Stripe's test checkout and does not charge a real card. "
            "ZEIM never sees or stores your card."
        )
    if mode == "live":
        return (
            "Choosing Semi Pro or Pro opens Stripe Checkout. The plan renews every month until you cancel in Stripe. "
            "ZEIM never sees or stores your card."
        )
    return OPEN_STUB_NOTE


def _renewal_note(mode: str) -> str:
    if not plans_enabled() or mode == "off":
        return (
            "When checkout is on, Semi Pro and Pro renew every month through Stripe "
            "until you cancel. ZEIM does not charge the card itself."
        )
    return (
        "This plan renews every month through Stripe until you cancel. "
        "ZEIM does not charge the card itself. Cancel or change the card in Stripe's billing portal. "
        "Stripe tells ZEIM when a payment succeeds, fails, or the plan ends, and that updates this account."
    )


def _purchasable(plan_id: str, mode: str) -> bool:
    return plan_id in PAID_IDS and plans_enabled() and mode in ("test", "live")


def catalog() -> dict:
    mode = billing.stripe_mode()
    plans = []
    for p in PLANS:
        row = dict(p)
        if p["id"] in PAID_IDS:
            cents = billing.PLAN_CENTS[p["id"]]
            row["fee_cents"] = billing.service_fee_cents(cents)
            row["purchasable"] = _purchasable(p["id"], mode)
            row["coming"] = not row["purchasable"]
        else:
            row["fee_cents"] = 0
            row["purchasable"] = False
            row["coming"] = False
        plans.append(row)
    return {
        "payment_live": payment_live(),
        "plans_enabled": plans_enabled(),
        "stripe_mode": mode,
        "payment_note": _payment_note(mode),
        "fee_note": FEE_NOTE,
        "processing_note": PROCESSING_NOTE,
        "renewal_note": _renewal_note(mode),
        "tip_note": TIP_NOTE,
        "plans": plans,
        "currency": "USD",
        "stores_cards": False,
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


def has_paid_plan(user: dict | None, *which: str) -> bool:
    """Feature gate. True only for a webhook-maintained paid tier (or the dev helper)."""
    plan = plan_of(user)
    if plan not in PAID_IDS:
        return False
    return plan in which if which else True


def public_plan(user: dict | None) -> dict:
    pid = plan_of(user)
    meta = next(p for p in PLANS if p["id"] == pid)
    billing_row = (user or {}).get("billing") if isinstance((user or {}).get("billing"), dict) else {}
    status = billing_row.get("status") if billing_row.get("status") in billing.KNOWN_STATUS else "none"
    mode = billing.stripe_mode()
    customer_id = str(billing_row.get("customer_id") or "")
    return {
        "id": pid,
        "name": meta["name"],
        "price_label": meta["price_label"],
        "payment_live": payment_live(),
        "plans_enabled": plans_enabled(),
        "stripe_mode": mode,
        "status": status,
        "cancel_at_period_end": bool(billing_row.get("cancel_at_period_end")),
        "can_manage": customer_id.startswith("cus_") and mode in ("test", "live") and plans_enabled(),
    }


def set_plan(sid: str, plan_id: str) -> dict:
    """Dev / test helper: set an account's plan in users.json. Not a checkout and not used by the browser."""
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


def start_checkout(actor, plan_id: str, base_url: str = "") -> dict:
    """Hosted Stripe Checkout when plans are enabled and Stripe is configured.

    The flag defaults off and refuses (the route answers 403). A flag without
    keys stays Coming and does not charge. Card data is never stored here.
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
    user = actor.user or {}
    mode = billing.stripe_mode()
    if mode == "off":
        out = billing.open_checkout(user, plan_id, base_url)
        out["checkout"] = False
        out["coming"] = True
        return out
    current = plan_of(user)
    row = user.get("billing") if isinstance(user.get("billing"), dict) else {}
    status = row.get("status") or ""
    if row.get("subscription_id") and status in billing.GRANT_STATUS:
        if current == plan_id:
            return {
                "ok": True,
                "checkout": False,
                "plan": plan_id,
                "stripe_mode": mode,
                "message": (
                    f"You're already on {name}. It renews monthly until you cancel in Stripe."
                ),
            }
        portal = billing.open_portal(user, base_url)
        if portal.get("ok"):
            portal["message"] = (
                "You already have a plan. Stripe will open so you can switch or cancel. "
                "ZEIM does not see your card."
            )
        return portal
    return billing.open_checkout(user, plan_id, base_url)


def open_portal(actor, base_url: str) -> dict:
    if not actor.user:
        return {"ok": False, "checkout": False, "message": "Make a free account first."}
    if not plans_enabled():
        return {
            "ok": False,
            "coming": True,
            "checkout": False,
            "message": "Billing is not available yet. Nothing was charged.",
        }
    return billing.open_portal(actor.user, base_url)
