"""Subscription plans API (stubs until payment is live)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
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
    cat = subs.catalog()
    return {
        "signed_up": bool(actor.user),
        "plan": subs.public_plan(actor.user),
        "payment_live": cat["payment_live"],
        "plans_enabled": cat["plans_enabled"],
        "payment_note": cat["payment_note"],
        "tip_note": cat["tip_note"],
        "catalog": cat["plans"],
    }


class CheckoutBody(BaseModel):
    plan: str = Field(..., max_length=32)


@router.post("/checkout")
def checkout(body: CheckoutBody, actor: Actor = Depends(get_actor)):
    """Paid plans. With ZEIM_PLANS_ENABLED off (the default) this refuses and does not charge.

    Stripe keys are not read. A missing processor is not an error.
    """
    if not actor.user:
        raise HTTPException(401, "Make a free account first, then you can look at Semi Pro or Pro.")
    plan = subs.normalize_plan(body.plan)
    if plan not in subs.PLAN_IDS:
        raise HTTPException(400, "Unknown plan.")
    result = subs.start_checkout(actor, plan)
    blocked = bool(result.pop("blocked", False))
    if blocked:
        result["detail"] = result["message"]
        return JSONResponse(status_code=403, content=result)
    return result
