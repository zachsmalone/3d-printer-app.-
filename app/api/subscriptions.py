"""Optional Semi Pro / Pro. Checkout and the Customer Portal are hosted by Stripe.

ZEIM never receives card numbers or CVC. Plan status is written by the webhook.
"""
from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import config
from ..community.identity import Actor, get_actor
from ..core import ratelimit
from ..services import stripe_billing as billing
from ..services import subscriptions as subs
from . import guards
from .textcap import ip as client_ip

log = logging.getLogger("zeim.billing")
router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def _base(request: Request) -> str:
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


def _me_body(actor: Actor) -> dict:
    cat = subs.catalog()
    return {
        "signed_up": bool(actor.user),
        "plan": subs.public_plan(actor.user),
        "payment_live": cat["payment_live"],
        "stripe_mode": cat["stripe_mode"],
        "payment_note": cat["payment_note"],
        "fee_note": cat["fee_note"],
        "processing_note": cat["processing_note"],
        "renewal_note": cat["renewal_note"],
        "tip_note": cat["tip_note"],
        "stores_cards": False,
        "catalog": cat["plans"],
    }


def _known_plan(raw: str) -> str:
    text = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if text in ("semipro", "semi"):
        text = "semi_pro"
    if text not in subs.PLAN_IDS:
        raise HTTPException(400, "Unknown plan.")
    return text


@router.get("/plans")
def plans():
    """Public catalog. No auth required — anyone can read what Free / Semi Pro / Pro mean."""
    return subs.catalog()


@router.get("/me")
def my_plan(actor: Actor = Depends(get_actor)):
    return _me_body(actor)


@router.get("/admin")
def admin_plans(request: Request, user_id: str = Query("", max_length=80)):
    """Support view: plan tier and Stripe ids. Header X-Admin-Token, same as moderation.

    Does not return card data, email, or date of birth.
    """
    if not config.ADMIN_TOKEN:
        raise HTTPException(403, "Admin token is not set.")
    if not guards.is_admin(request):
        raise HTTPException(403, "bad admin token")
    return billing.staff_accounts(user_id or None)


class CheckoutBody(BaseModel):
    plan: str = Field(..., max_length=32)


@router.post("/checkout")
def checkout(body: CheckoutBody, request: Request, actor: Actor = Depends(get_actor)):
    """Start Semi Pro / Pro on Stripe Checkout, or say Coming when Stripe is not configured."""
    if not actor.user:
        raise HTTPException(401, "Make a free account first, then you can look at Semi Pro or Pro.")
    return subs.start_checkout(actor, _known_plan(body.plan), _base(request))


@router.post("/portal")
def portal(request: Request, actor: Actor = Depends(get_actor)):
    """Stripe Customer Portal: cancel, switch plan, or replace the card. The card stays on Stripe."""
    if not actor.user:
        raise HTTPException(401, "Make a free account first, then you can look at Semi Pro or Pro.")
    return subs.open_portal(actor, _base(request))


@router.post("/webhook")
async def webhook(request: Request):
    """Stripe subscription lifecycle. Signature required. This is what marks an account paid."""
    if not ratelimit.hit("stripewh:" + client_ip(request), 300, 60):
        raise HTTPException(429, "Too many webhook calls.")
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = billing.construct_event(payload, signature)
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid Stripe signature.")
    except Exception:
        log.warning("stripe webhook rejected")
        raise HTTPException(400, "Invalid Stripe event.")
    try:
        billing.apply_event(event)
    except Exception:
        log.exception("stripe webhook apply failed")
        raise HTTPException(500, "Could not record the Stripe event.")
    return {"ok": True}
