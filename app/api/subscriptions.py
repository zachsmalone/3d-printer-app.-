"""Subscription plans API (stubs until payment is live)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..community.identity import Actor, get_actor
from ..services import subscriptions as subs

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


@router.get("/plans")
def plans():
    """Public catalog. No auth required — anyone can read what Free / Semi Pro / Pro mean."""
    return subs.catalog()


@router.get("/me")
def my_plan(actor: Actor = Depends(get_actor)):
    return {
        "signed_up": bool(actor.user),
        "plan": subs.public_plan(actor.user),
        "payment_live": subs.PAYMENT_LIVE,
        "payment_note": subs.PAYMENT_NOTE,
        "tip_note": subs.TIP_NOTE,
        "catalog": subs.catalog()["plans"],
    }


class CheckoutBody(BaseModel):
    plan: str = Field(..., max_length=32)


@router.post("/checkout")
def checkout(body: CheckoutBody, actor: Actor = Depends(get_actor)):
    """Start Semi Pro / Pro. Returns coming until payment is wired — never charges."""
    if not actor.user:
        raise HTTPException(401, "Make a free account first, then you can look at Semi Pro or Pro.")
    plan = subs.normalize_plan(body.plan)
    if plan not in subs.PLAN_IDS:
        raise HTTPException(400, "Unknown plan.")
    return subs.start_checkout(actor, plan)
