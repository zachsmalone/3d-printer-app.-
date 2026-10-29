"""Stripe Billing for optional Semi Pro and Pro plans.

ZEIM is the merchant for its own plans. Card numbers, CVC, expiry, and payment
methods stay on Stripe (hosted Checkout and the Stripe Customer). This module
stores only:

  * plan tier on the account (`free` / `semi_pro` / `pro`)
  * Stripe Customer id (`cus_...`) and Subscription id (`sub_...`)
  * subscription status, so feature gates can read the account

It does not use Connect, application fees, or destination charges. Creator tips
and Showcase sales are not charged here. The ~1% ZEIM service fee is a second
recurring line on the same subscription (nearest cent). Stripe's own processing
fee is disclosed and is not guessed as an extra line, because it depends on the
payment method.

Checkout omits `payment_method_types` so the Stripe Dashboard decides which
methods appear (card, Apple Pay, Google Pay, and optional PayPal / Cash App Pay).

Monthly renewal is Stripe Billing (`mode=subscription`). ZEIM does not run a
renewal cron. `invoice.paid`, `invoice.payment_failed`, and the subscription
events update the account.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import string
import time
from typing import Any
from urllib.parse import urlparse

import stripe

from ..community.identity import user_by_id
from ..community.store import USERS
from .entitlements import pro_comp

log = logging.getLogger("zeim.billing")

API_VERSION = "2026-09-30.endive"
FEE_BPS = 100  # 1% = 100 basis points. Applied only to the plan price.
PLAN_CENTS = {"semi_pro": 350, "pro": 550}
PAID_PLANS = frozenset(PLAN_CENTS)
GRANT_STATUS = frozenset({"active", "trialing", "past_due"})
KNOWN_STATUS = frozenset({
    "none", "active", "trialing", "past_due", "canceled", "unpaid",
    "incomplete", "incomplete_expired", "paused", "unknown",
})
_CUS = re.compile(r"^cus_[A-Za-z0-9]+$")
_SUB = re.compile(r"^sub_[A-Za-z0-9]+$")
_PRICE = re.compile(r"^price_[A-Za-z0-9]+$")
_USER = re.compile(r"^[A-Za-z0-9_\-]{6,80}$")
_STRIPE_HOSTS = frozenset({"checkout.stripe.com", "billing.stripe.com"})
_BILLING_KEYS = frozenset({
    "customer_id", "subscription_id", "status", "price_id",
    "livemode", "event_created", "cancel_at_period_end",
})

CHECKOUT_DISCLOSURE = (
    "Optional ZEIM plan. It renews every month until you cancel in Stripe. "
    "ZEIM adds a service fee of about 1% of the plan price, rounded to the nearest cent, "
    "as its own line. That fee helps fund hosting and applies only to this plan charge. "
    "Stripe's processing fee is separate: you cover it, and ZEIM does not keep it. "
    "ZEIM never takes a cut of creator tips or Showcase sales. "
    "ZEIM does not see or store your card — Stripe does."
)
TEST_DISCLOSURE_SUFFIX = " Stripe test mode: this does not charge a real card."

SUPPORT_NOTE = (
    "ZEIM stores the plan tier plus the Stripe Customer id and Subscription id. "
    "It does not store card numbers, CVC, expiry, or payment methods. "
    "ZEIM also does not store the email address (sign-in keeps only a hash). "
    "Ask the person for the email they typed at Stripe Checkout and search Customers "
    "in the Stripe Dashboard. Match Customer and Subscription metadata zeim_user_id "
    "to the user id in this list."
)
RECOVERY_NOTE = (
    "Sign in with a passkey, a password, or an email sign-in code (docs/auth.md). "
    "Older cookie accounts may still have a one-time recovery code. "
    "Canceling a plan or changing the card is the Stripe Customer Portal "
    "(Manage billing) or the Stripe Dashboard, not a password reset. "
    "The Stripe ids stay on this same account, so signing back in keeps the plan. "
    "A brand-new account does not inherit someone else's subscription."
)

_HANDLED = frozenset({
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
})


def service_fee_cents(plan_cents: int) -> int:
    """About 1% of the plan, rounded half-up to the nearest cent. Never a tip or sale."""
    if plan_cents <= 0:
        return 0
    return (int(plan_cents) * FEE_BPS + 5_000) // 10_000


def secret_key() -> str:
    return (os.environ.get("STRIPE_SECRET_KEY") or "").strip()


def webhook_secret() -> str:
    return (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()


def publishable_key() -> str:
    """Documented for Dashboard / Stripe.js. Hosted Checkout does not send it to the browser."""
    return (os.environ.get("STRIPE_PUBLISHABLE_KEY") or "").strip()


def key_mode(key: str | None = None) -> str:
    """'test', 'live', or 'off' from the secret key prefix. Restricted keys (rk_) count."""
    k = secret_key() if key is None else key
    if k.startswith(("sk_test_", "rk_test_")):
        return "test"
    if k.startswith(("sk_live_", "rk_live_")):
        return "live"
    return "off"


def plan_price_id(plan_id: str) -> str:
    env = {"semi_pro": "STRIPE_PRICE_SEMI_PRO", "pro": "STRIPE_PRICE_PRO"}.get(plan_id, "")
    return (os.environ.get(env) or "").strip() if env else ""


def fee_price_id(plan_id: str) -> str:
    env = {"semi_pro": "STRIPE_PRICE_FEE_SEMI_PRO", "pro": "STRIPE_PRICE_FEE_PRO"}.get(plan_id, "")
    return (os.environ.get(env) or "").strip() if env else ""


def stripe_mode() -> str:
    """'off' until a test or live secret, webhook secret, and both plan Price ids are set."""
    mode = key_mode()
    if mode == "off" or not webhook_secret():
        return "off"
    if not plan_price_id("semi_pro") or not plan_price_id("pro"):
        return "off"
    return mode


def price_matches(price: Any, cents: int) -> bool:
    """True when a Stripe Price is USD, monthly, and the expected amount in cents."""
    if isinstance(price, dict):
        currency = price.get("currency")
        amount = price.get("unit_amount")
        rec = price.get("recurring") or {}
        interval = rec.get("interval") if isinstance(rec, dict) else getattr(rec, "interval", None)
    else:
        currency = getattr(price, "currency", None)
        amount = getattr(price, "unit_amount", None)
        rec = getattr(price, "recurring", None)
        interval = getattr(rec, "interval", None) if rec is not None else None
    return currency == "usd" and amount == cents and interval == "month"


def checkout_disclosure(mode: str) -> str:
    text = CHECKOUT_DISCLOSURE
    if mode == "test":
        text += TEST_DISCLOSURE_SUFFIX
    return text


def _integration_id() -> str:
    suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
    return "zeimplan" + suffix


def _fee_line(plan_id: str) -> dict:
    cents = service_fee_cents(PLAN_CENTS[plan_id])
    configured = fee_price_id(plan_id)
    if configured:
        return {"price": configured, "quantity": 1}
    return {
        "quantity": 1,
        "price_data": {
            "currency": "usd",
            "unit_amount": cents,
            "recurring": {"interval": "month"},
            "product_data": {
                "name": "ZEIM service fee (about 1%)",
                "description": (
                    "Helps fund hosting. Charged only on this optional plan, "
                    "not on creator tips or Showcase sales."
                ),
                "metadata": {"purpose": "zeim_service_fee"},
            },
        },
    }


def build_checkout_params(user_id: str, plan_id: str, customer_id: str,
                          success_url: str, cancel_url: str, mode: str) -> dict:
    """Hosted Checkout session params. No card fields. No Connect application fee.

    `payment_method_types` is omitted on purpose so Dashboard payment-method
    settings (card, wallets, optional PayPal / Cash App Pay) apply.
    """
    if plan_id not in PLAN_CENTS:
        raise ValueError("unknown plan")
    meta = {"zeim_user_id": user_id, "plan": plan_id, "purpose": "zeim_plan"}
    params = {
        "mode": "subscription",
        "ui_mode": "hosted_page",
        "customer": customer_id,
        "client_reference_id": user_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "submit_type": "subscribe",
        "origin_context": "web",
        "line_items": [
            {"price": plan_price_id(plan_id), "quantity": 1},
            _fee_line(plan_id),
        ],
        "metadata": meta,
        "subscription_data": {
            "metadata": dict(meta),
            "description": "Optional ZEIM plan. Renews monthly. Helps fund hosting.",
        },
        "custom_text": {"submit": {"message": checkout_disclosure(mode)}},
        "integration_identifier": _integration_id(),
    }
    return params


def stripe_redirect(url: str) -> str:
    """Accept only Stripe-hosted Checkout or Customer Portal URLs."""
    try:
        parts = urlparse(url)
    except Exception:
        parts = None
    host = parts.hostname if parts else None
    if not parts or parts.scheme != "https" or host not in _STRIPE_HOSTS:
        raise ValueError("unexpected billing URL")
    return url


def client() -> stripe.StripeClient:
    key = secret_key()
    if not key:
        raise RuntimeError("Stripe secret key is not set")
    return stripe.StripeClient(key, stripe_version=API_VERSION)


def _return_urls(base: str) -> tuple[str, str]:
    root = base.rstrip("/")
    return root + "/?checkout=success#account", root + "/?checkout=cancel#account"


def _base_ok(mode: str, base: str) -> str | None:
    if mode == "live" and not (base or "").startswith("https://"):
        return (
            "Live checkout needs PHOTO3D_PUBLIC_BASE_URL set to the https site "
            "(https://zeimapp.com). Nothing was charged."
        )
    if not base:
        return "Checkout needs a public site address. Nothing was charged."
    return None


def open_checkout(user: dict, plan_id: str, base: str) -> dict:
    """Create a hosted Checkout Session. Persists the Customer id only — not a plan, not a card."""
    mode = stripe_mode()
    if mode == "off":
        return {
            "ok": False, "coming": True, "plan": plan_id,
            "message": (
                f"{'Semi Pro' if plan_id == 'semi_pro' else 'Pro'} is coming. "
                "Payment is not live yet — nothing was charged."
            ),
        }
    bad = _base_ok(mode, base)
    if bad:
        return {"ok": False, "plan": plan_id, "message": bad}
    user_id = str(user.get("id") or "")
    if not _USER.match(user_id):
        return {"ok": False, "plan": plan_id, "message": "This account cannot start checkout."}
    try:
        sc = client()
        price = sc.v1.prices.retrieve(plan_price_id(plan_id))
        if not price_matches(price, PLAN_CENTS[plan_id]):
            return {
                "ok": False, "plan": plan_id,
                "message": (
                    "The Stripe price for this plan is not the published monthly amount "
                    f"(${PLAN_CENTS[plan_id] / 100:.2f}). Nothing was charged."
                ),
            }
        fee_id = fee_price_id(plan_id)
        if fee_id:
            fee = sc.v1.prices.retrieve(fee_id)
            if not price_matches(fee, service_fee_cents(PLAN_CENTS[plan_id])):
                return {
                    "ok": False, "plan": plan_id,
                    "message": "The Stripe service-fee price does not match about 1%. Nothing was charged.",
                }
        customer_id = _existing_customer(user)
        if not customer_id:
            created = sc.v1.customers.create(
                params={"metadata": {"zeim_user_id": user_id, "purpose": "zeim_plan"}},
                options={"idempotency_key": f"zeim-cus-{user_id}"},
            )
            customer_id = getattr(created, "id", None) or ""
            if not _CUS.match(customer_id):
                return {"ok": False, "plan": plan_id, "message": "Stripe did not return a customer. Nothing was charged."}
        _remember_customer(user, customer_id, mode == "live")
        success, cancel = _return_urls(base)
        params = build_checkout_params(user_id, plan_id, customer_id, success, cancel, mode)
        _reject_connect(params)
        bucket = int(time.time()) // 600
        session = sc.v1.checkout.sessions.create(
            params=params,
            options={"idempotency_key": f"zeim-checkout-{user_id}-{plan_id}-{bucket}"},
        )
        url = stripe_redirect(getattr(session, "url", "") or "")
    except ValueError:
        log.warning("stripe checkout returned a non-Stripe URL")
        return {"ok": False, "plan": plan_id, "message": "Stripe returned an unexpected page. Nothing was charged."}
    except stripe.StripeError as e:
        log.warning("stripe checkout failed code=%s request=%s", getattr(e, "code", None), getattr(e, "request_id", None))
        return {"ok": False, "plan": plan_id, "message": "Stripe could not start checkout. Nothing was charged."}
    message = "Opening Stripe Checkout. ZEIM does not see or store your card. The plan renews monthly until you cancel."
    if mode == "test":
        message = "Stripe test mode — this does not charge a real card. " + message
    return {"ok": True, "url": url, "plan": plan_id, "stripe_mode": mode, "message": message}


def open_portal(user: dict, base: str) -> dict:
    """Stripe Customer Portal. The card form stays on Stripe."""
    mode = stripe_mode()
    if mode == "off":
        return {"ok": False, "coming": True, "message": "Billing is not live yet. Nothing was charged."}
    bad = _base_ok(mode, base)
    if bad:
        return {"ok": False, "message": bad}
    customer_id = _existing_customer(user)
    if not customer_id:
        return {"ok": False, "message": "No Stripe billing record on this account yet."}
    try:
        session = client().v1.billing_portal.sessions.create(params={
            "customer": customer_id,
            "return_url": base.rstrip("/") + "/#account",
        })
        url = stripe_redirect(getattr(session, "url", "") or "")
    except ValueError:
        log.warning("stripe portal returned a non-Stripe URL")
        return {"ok": False, "message": "Stripe returned an unexpected page. Nothing was charged."}
    except stripe.StripeError as e:
        log.warning("stripe portal failed code=%s request=%s", getattr(e, "code", None), getattr(e, "request_id", None))
        return {
            "ok": False,
            "message": (
                "Stripe could not open the billing portal. Nothing was charged. "
                "If the Customer Portal is not turned on in the Stripe Dashboard, that is why."
            ),
        }
    text = "Opening Stripe to manage this plan. ZEIM does not see or store your card."
    if mode == "test":
        text = "Stripe test mode. " + text
    return {"ok": True, "url": url, "portal": True, "stripe_mode": mode, "message": text}


def construct_event(payload: bytes, signature: str | None):
    """Verify the Stripe-Signature header. Raises SignatureVerificationError on failure."""
    secret = webhook_secret()
    key = secret_key()
    if not secret or key_mode(key) == "off":
        raise stripe.SignatureVerificationError(
            "Stripe webhook is not configured.",
            signature or "",
            payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload),
        )
    return client().construct_event(payload, signature, secret)


def apply_event(event: Any) -> dict:
    """Update the ZEIM account from a verified Stripe event. Idempotent. Stores no card data."""
    data = event if isinstance(event, dict) else event.to_dict()
    etype = str(data.get("type") or "")
    if etype not in _HANDLED:
        return {"ok": True, "ignored": True}
    if not _livemode_ok(bool(data.get("livemode"))):
        log.warning("stripe event livemode mismatch type=%s id=%s", etype, data.get("id"))
        return {"ok": True, "ignored": True}
    obj = ((data.get("data") or {}).get("object")) or {}
    if not isinstance(obj, dict):
        return {"ok": True, "ignored": True}
    purpose = str((obj.get("metadata") or {}).get("purpose") or "")
    if purpose and purpose not in ("zeim_plan", "zeim_service_fee"):
        return {"ok": True, "ignored": True}
    created = int(data.get("created") or 0)
    if etype.startswith("checkout.session."):
        return _apply_checkout(etype, obj, created, bool(data.get("livemode")))
    if etype.startswith("customer.subscription."):
        return _apply_subscription(etype, obj, created, bool(data.get("livemode")))
    if etype.startswith("invoice."):
        return _apply_invoice(etype, obj, created, bool(data.get("livemode")))
    return {"ok": True, "ignored": True}


def staff_accounts(user_id: str | None = None) -> dict:
    """Plan status for support. Whitelisted fields only — never card data, email, or date of birth."""
    want = user_id.strip() if isinstance(user_id, str) else ""
    rows = []
    for u in USERS.read().values():
        if not isinstance(u, dict):
            continue
        uid = str(u.get("id") or "")
        if want and uid != want:
            continue
        billing = u.get("billing") if isinstance(u.get("billing"), dict) else {}
        comp = bool(pro_comp(u))
        plan = "pro" if comp else (u.get("plan") if u.get("plan") in PAID_PLANS else "free")
        customer = billing.get("customer_id") if _CUS.match(str(billing.get("customer_id") or "")) else ""
        if not want and plan == "free" and not customer:
            continue
        status = billing.get("status") if billing.get("status") in KNOWN_STATUS else ("none" if not billing else "unknown")
        sub = billing.get("subscription_id") if _SUB.match(str(billing.get("subscription_id") or "")) else ""
        price = billing.get("price_id") if _PRICE.match(str(billing.get("price_id") or "")) else ""
        rows.append({
            "user_id": uid,
            "username": u.get("username") or "",
            "display_name": u.get("display_name") or "",
            "plan": plan,
            "comp": comp,
            "status": status,
            "stripe_customer_id": customer,
            "stripe_subscription_id": sub,
            "stripe_price_id": price,
            "livemode": bool(billing.get("livemode")),
            "cancel_at_period_end": bool(billing.get("cancel_at_period_end")),
        })
    rows.sort(key=lambda r: (r["plan"], r["user_id"]))
    return {
        "stripe_mode": stripe_mode(),
        "stores_cards": False,
        "accounts": rows,
        "support_note": SUPPORT_NOTE,
        "recovery_note": RECOVERY_NOTE,
    }


def _livemode_ok(livemode: bool) -> bool:
    mode = key_mode()
    if mode == "live":
        return livemode
    if mode == "test":
        return not livemode
    return False


def _reject_connect(params: dict) -> None:
    sub = params.get("subscription_data") or {}
    if "payment_method_types" in params or "application_fee_percent" in sub or "transfer_data" in sub or "on_behalf_of" in sub:
        raise RuntimeError("checkout params must not set Connect fees or a payment-method allowlist")


def _existing_customer(user: dict) -> str:
    billing = user.get("billing") if isinstance(user.get("billing"), dict) else {}
    cid = str(billing.get("customer_id") or "")
    return cid if _CUS.match(cid) else ""


def _ref(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        ident = value.get("id")
        return ident if isinstance(ident, str) and ident else None
    return None


def _price_ids(obj: dict) -> list[str]:
    items = ((obj.get("items") or {}).get("data")) or ((obj.get("lines") or {}).get("data")) or []
    found = []
    for item in items:
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        ident = price if isinstance(price, str) else _ref(price)
        if not ident:
            details = (item.get("pricing") or {}).get("price_details") or {}
            ident = details.get("price") if isinstance(details, dict) else None
        if isinstance(ident, str):
            found.append(ident)
    return found


def _plan_from_prices(price_ids: list[str]) -> str | None:
    hits = [plan for plan in ("semi_pro", "pro") if plan_price_id(plan) and plan_price_id(plan) in price_ids]
    if len(hits) == 1:
        return hits[0]
    return None


def _meta_plan(obj: dict) -> str | None:
    raw = str((obj.get("metadata") or {}).get("plan") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in ("semipro", "semi"):
        raw = "semi_pro"
    return raw if raw in PAID_PLANS else None


def _resolve_plan(obj: dict) -> str | None:
    priced = _plan_from_prices(_price_ids(obj))
    return priced or _meta_plan(obj)


def _user_ref(*objs: dict) -> str:
    for obj in objs:
        meta = (obj.get("metadata") or {}).get("zeim_user_id")
        if isinstance(meta, str) and _USER.match(meta):
            return meta
        ref = obj.get("client_reference_id")
        if isinstance(ref, str) and _USER.match(ref):
            return ref
    return ""


def _find(user_id: str = "", customer_id: str = "", subscription_id: str = ""):
    if user_id:
        sid, user = user_by_id(user_id)
        if user:
            return sid, user
    if not customer_id and not subscription_id:
        return None, None
    for sid, user in USERS.read().items():
        if not isinstance(user, dict):
            continue
        billing = user.get("billing") if isinstance(user.get("billing"), dict) else {}
        if customer_id and billing.get("customer_id") == customer_id:
            return sid, user
        if subscription_id and billing.get("subscription_id") == subscription_id:
            return sid, user
    return None, None


def _clean_billing(raw: dict) -> dict:
    out: dict[str, Any] = {}
    cid = raw.get("customer_id")
    if isinstance(cid, str) and _CUS.match(cid):
        out["customer_id"] = cid
    sub = raw.get("subscription_id")
    if isinstance(sub, str) and _SUB.match(sub):
        out["subscription_id"] = sub
    status = raw.get("status") or "none"
    out["status"] = status if status in KNOWN_STATUS else "unknown"
    price = raw.get("price_id")
    if isinstance(price, str) and _PRICE.match(price):
        out["price_id"] = price
    if "livemode" in raw:
        out["livemode"] = bool(raw.get("livemode"))
    if raw.get("event_created"):
        out["event_created"] = int(raw["event_created"])
    if "cancel_at_period_end" in raw:
        out["cancel_at_period_end"] = bool(raw.get("cancel_at_period_end"))
    return {k: v for k, v in out.items() if k in _BILLING_KEYS}


def _remember_customer(user: dict, customer_id: str, livemode: bool) -> None:
    sid, _ = user_by_id(str(user.get("id") or ""))
    if not sid or not _CUS.match(customer_id):
        return

    def f(d):
        row = d.get(sid)
        if not row:
            return
        billing = dict(row.get("billing") or {})
        existing = billing.get("customer_id")
        if existing and existing != customer_id:
            return
        if existing == customer_id:
            return
        billing["customer_id"] = customer_id
        billing.setdefault("status", "none")
        billing["livemode"] = livemode
        row["billing"] = _clean_billing(billing)

    USERS.update(f)


def _write(sid: str, event_created: int, billing_changes: dict, plan_action: str, plan: str | None) -> dict:
    """plan_action is 'set', 'clear', or 'keep'. Older events do not overwrite newer ones."""
    result: dict[str, Any] = {}

    def f(d):
        row = d.get(sid)
        if not row:
            result["missing"] = True
            return
        billing = dict(row.get("billing") or {})
        prev = int(billing.get("event_created") or 0)
        if event_created and prev and event_created < prev:
            result["stale"] = True
            return
        stored_cus = billing.get("customer_id")
        incoming = billing_changes.get("customer_id")
        if stored_cus and incoming and stored_cus != incoming:
            result["mismatch"] = True
            return
        # Empty ids must not wipe a Customer or Subscription we already stored.
        billing.update({k: v for k, v in billing_changes.items() if v not in ("", None)})
        if event_created:
            billing["event_created"] = event_created
        row["billing"] = _clean_billing(billing)
        if plan_action == "clear":
            row.pop("plan", None)
        elif plan_action == "set" and plan in PAID_PLANS:
            row["plan"] = plan
        result["ok"] = True
        result["plan"] = row.get("plan") or "free"

    USERS.update(f)
    return result or {"missing": True}


def _locate(obj: dict, customer_id: str = "", subscription_id: str = ""):
    return _find(_user_ref(obj), customer_id or (_ref(obj.get("customer")) or ""), subscription_id or (_ref(obj.get("id")) or ""))


def _apply_checkout(etype: str, obj: dict, created: int, livemode: bool) -> dict:
    if obj.get("mode") not in (None, "subscription"):
        return {"ok": True, "ignored": True}
    customer_id = _ref(obj.get("customer")) or ""
    subscription_id = _ref(obj.get("subscription")) or ""
    sid, _user = _find(_user_ref(obj), customer_id, subscription_id)
    if not sid:
        log.info("stripe checkout unmatched type=%s", etype)
        return {"ok": True, "unmatched": True}
    paid = etype == "checkout.session.async_payment_succeeded" or obj.get("payment_status") in ("paid", "no_payment_required")
    failed = etype == "checkout.session.async_payment_failed" or (etype == "checkout.session.completed" and not paid)
    plan = _resolve_plan(obj) if paid else None
    changes = {
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "livemode": livemode,
        "status": "active" if paid and plan else ("incomplete" if failed else "none"),
    }
    if plan:
        changes["price_id"] = plan_price_id(plan)
    action = "set" if paid and plan else "keep"
    result = _write(sid, created, changes, action, plan)
    log.info("stripe checkout type=%s plan_action=%s", etype, action)
    return {"ok": True, **result}


def _apply_subscription(etype: str, obj: dict, created: int, livemode: bool) -> dict:
    customer_id = _ref(obj.get("customer")) or ""
    subscription_id = _ref(obj.get("id")) or ""
    sid, _user = _find(_user_ref(obj), customer_id, subscription_id)
    if not sid:
        log.info("stripe subscription unmatched type=%s", etype)
        return {"ok": True, "unmatched": True}
    status = str(obj.get("status") or ("canceled" if etype.endswith(".deleted") else "unknown"))
    if etype.endswith(".deleted"):
        status = "canceled"
    plan = _resolve_plan(obj)
    grant = status in GRANT_STATUS and plan in PAID_PLANS and not etype.endswith(".deleted")
    changes = {
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "status": status,
        "livemode": livemode,
        "cancel_at_period_end": bool(obj.get("cancel_at_period_end")),
    }
    if plan:
        changes["price_id"] = plan_price_id(plan)
    action = "set" if grant else "clear"
    result = _write(sid, created, changes, action, plan if grant else None)
    log.info("stripe subscription type=%s status=%s grant=%s", etype, status, grant)
    return {"ok": True, **result}


def _invoice_subscription(obj: dict) -> str:
    sub = _ref(obj.get("subscription"))
    if sub:
        return sub
    parent = obj.get("parent") or {}
    details = parent.get("subscription_details") if isinstance(parent, dict) else None
    if isinstance(details, dict):
        return _ref(details.get("subscription")) or ""
    return ""


def _apply_invoice(etype: str, obj: dict, created: int, livemode: bool) -> dict:
    customer_id = _ref(obj.get("customer")) or ""
    subscription_id = _invoice_subscription(obj)
    sid, user = _find(_user_ref(obj), customer_id, subscription_id)
    if not sid:
        log.info("stripe invoice unmatched type=%s", etype)
        return {"ok": True, "unmatched": True}
    if etype == "invoice.payment_failed":
        # Keep the current tier during Stripe's retry window. Do not grant a new tier from a failure.
        changes = {"customer_id": customer_id, "subscription_id": subscription_id, "status": "past_due", "livemode": livemode}
        result = _write(sid, created, changes, "keep", None)
        log.info("stripe invoice payment_failed")
        return {"ok": True, **result}
    plan = _resolve_plan(obj)
    changes = {
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "status": "active",
        "livemode": livemode,
    }
    if plan:
        changes["price_id"] = plan_price_id(plan)
    # A paid renewal confirms the tier when the invoice lines map to one plan.
    action = "set" if plan else "keep"
    if action == "keep" and user and (user.get("plan") in PAID_PLANS):
        changes["status"] = "active"
    result = _write(sid, created, changes, action, plan)
    log.info("stripe invoice paid action=%s", action)
    return {"ok": True, **result}
