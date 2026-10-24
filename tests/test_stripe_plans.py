"""Stripe Checkout for optional Semi Pro / Pro.

No network. Card fields are never persisted. A bad webhook signature is rejected.
"""
from __future__ import annotations

import json

import pytest
import stripe

from app.community.identity import user_by_id
from app.community.store import USERS
from app.services import ai3d, stripe_billing as billing
from app.services import subscriptions as subs
from tests.b1 import ADULT, client

SECRET = "whsec_test_secret"
PRICE_SEMI = "price_semi123"
PRICE_PRO = "price_pro123"
ENV = {
    "STRIPE_SECRET_KEY": "sk_test_zeim",
    "STRIPE_WEBHOOK_SECRET": SECRET,
    "STRIPE_PUBLISHABLE_KEY": "pk_test_zeim",
    "STRIPE_PRICE_SEMI_PRO": PRICE_SEMI,
    "STRIPE_PRICE_PRO": PRICE_PRO,
}
_STRIPE_KEYS = (
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_PRICE_SEMI_PRO", "STRIPE_PRICE_PRO",
    "STRIPE_PRICE_FEE_SEMI_PRO", "STRIPE_PRICE_FEE_PRO",
)


@pytest.fixture(autouse=True)
def _clear_stripe_env(monkeypatch):
    for key in _STRIPE_KEYS:
        monkeypatch.delenv(key, raising=False)


def _env(monkeypatch, **extra):
    for key, value in {**ENV, **extra}.items():
        monkeypatch.setenv(key, value)


def _signup():
    c = client(ADULT)
    me = c.get("/api/me").json()
    return c, me["id"]


def _sub_event(uid, typ="customer.subscription.updated", status="active", price=PRICE_PRO,
               created=1_700_000_000, livemode=False, **extra):
    obj = {
        "id": "sub_test123",
        "object": "subscription",
        "customer": "cus_test123",
        "status": status,
        "metadata": {"zeim_user_id": uid, "plan": extra.pop("meta_plan", "semi_pro"), "purpose": "zeim_plan"},
        "items": {"data": [{"price": {"id": price}}]},
        "cancel_at_period_end": extra.pop("cancel_at_period_end", False),
        "default_payment_method": "pm_card_visa",
        "card": {"last4": "4242", "cvc": "123"},
    }
    obj.update(extra)
    return {
        "id": "evt_" + typ.replace(".", "_") + str(created),
        "object": "event",
        "type": typ,
        "created": created,
        "livemode": livemode,
        "data": {"object": obj},
    }


def _post_event(c, event, secret=SECRET):
    body = json.dumps(event, separators=(",", ":"))
    header = stripe.WebhookSignature.generate_signature_header(body, secret)
    return c.post(
        "/api/subscriptions/webhook",
        content=body.encode(),
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )


def _user(uid):
    _sid, user = user_by_id(uid)
    return user


def test_fee_is_one_percent_nearest_cent_and_catalog_discloses_it():
    assert billing.service_fee_cents(350) == 4
    assert billing.service_fee_cents(550) == 6
    assert billing.service_fee_cents(0) == 0
    cat = subs.catalog()
    assert cat["payment_live"] is False and cat["stripe_mode"] == "off"
    assert cat["stores_cards"] is False
    assert "about 1%" in cat["fee_note"].lower() or "about 1%" in cat["fee_note"]
    assert "4¢" in cat["fee_note"] and "6¢" in cat["fee_note"]
    assert "processing" in cat["processing_note"].lower()
    assert "never takes a cut" in cat["tip_note"].lower()
    assert "paypal" in cat["processing_note"].lower() and "cash app" in cat["processing_note"].lower()
    fees = {p["id"]: p["fee_cents"] for p in cat["plans"]}
    assert fees["semi_pro"] == 4 and fees["pro"] == 6 and fees["free"] == 0
    assert all(p["coming"] for p in cat["plans"] if p["id"] != "free")


def test_modes_are_honest(monkeypatch):
    _env(monkeypatch)
    cat = subs.catalog()
    assert cat["stripe_mode"] == "test" and cat["payment_live"] is False
    assert "test mode" in cat["payment_note"].lower()
    assert all(not p["coming"] for p in cat["plans"] if p["id"] != "free")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_zeim")
    live = subs.catalog()
    assert live["stripe_mode"] == "live" and live["payment_live"] is True
    assert "test mode" not in live["payment_note"].lower()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_not_a_real_prefix")
    assert billing.stripe_mode() == "off"
    monkeypatch.setenv("STRIPE_SECRET_KEY", "rk_test_restricted")
    monkeypatch.delenv("STRIPE_PRICE_PRO", raising=False)
    assert billing.stripe_mode() == "off"


def test_checkout_params_are_hosted_subscription_without_connect_or_card_fields(monkeypatch):
    _env(monkeypatch)
    params = billing.build_checkout_params(
        "acc_user123", "semi_pro", "cus_test123",
        "https://zeimapp.com/?checkout=success#account",
        "https://zeimapp.com/?checkout=cancel#account",
        "test",
    )
    assert params["mode"] == "subscription" and params["ui_mode"] == "hosted_page"
    assert "payment_method_types" not in params
    assert "allowed_payment_method_types" not in params
    sub = params["subscription_data"]
    assert "application_fee_percent" not in sub and "transfer_data" not in sub and "on_behalf_of" not in sub
    blob = json.dumps(params).lower()
    for banned in ("cvc", "last4", "payment_method", "application_fee", "on_behalf_of"):
        assert banned not in blob
    assert params["line_items"][0] == {"price": PRICE_SEMI, "quantity": 1}
    fee = params["line_items"][1]["price_data"]
    assert fee["unit_amount"] == 4 and fee["recurring"]["interval"] == "month"
    assert "about 1%" in fee["product_data"]["name"].lower()
    text = params["custom_text"]["submit"]["message"].lower()
    assert "about 1%" in text and "processing" in text and "tips" in text and "test mode" in text
    assert params["metadata"]["zeim_user_id"] == "acc_user123"
    assert params["integration_identifier"].startswith("zeimplan")
    assert params["integration_identifier"][-8:].isalpha() and params["integration_identifier"][-8:].islower()
    monkeypatch.setenv("STRIPE_PRICE_FEE_PRO", "price_feepro123")
    pro = billing.build_checkout_params("acc_user123", "pro", "cus_test123", "https://zeimapp.com/a", "https://zeimapp.com/b", "live")
    assert pro["line_items"][1] == {"price": "price_feepro123", "quantity": 1}
    assert "test mode" not in pro["custom_text"]["submit"]["message"].lower()


def test_redirect_allowlist():
    assert billing.stripe_redirect("https://checkout.stripe.com/c/pay/cs_test_x").startswith("https://")
    assert billing.stripe_redirect("https://billing.stripe.com/p/session/test").startswith("https://")
    for bad in ("http://checkout.stripe.com/c/pay/x", "https://evil.example/checkout.stripe.com", "https://checkout.stripe.com.evil/x", ""):
        with pytest.raises(ValueError):
            billing.stripe_redirect(bad)


class _Sessions:
    def __init__(self, root):
        self.root = root

    def create(self, params=None, options=None):
        self.root.sessions += 1
        self.root.session_params = params
        return type("S", (), {"url": self.root.url, "id": "cs_test_abc"})()


class _API:
    """Stand-in StripeClient. v1.prices / customers / checkout.sessions only."""

    def __init__(self, amounts, url="https://checkout.stripe.com/c/pay/cs_test_abc"):
        self.amounts = amounts
        self.url = url
        self.customer_params = None
        self.session_params = None
        self.sessions = 0
        self.v1 = self
        self.prices = self
        self.customers = self
        self.checkout = type("Checkout", (), {"sessions": _Sessions(self)})()

    def retrieve(self, price_id, params=None, options=None):
        return {"id": price_id, "currency": "usd", "unit_amount": self.amounts[price_id], "recurring": {"interval": "month"}}

    def create(self, params=None, options=None):
        self.customer_params = params
        return type("C", (), {"id": "cus_test123"})()


def test_open_checkout_checks_price_and_stores_customer_id_only(monkeypatch):
    _env(monkeypatch)
    _c, uid = _signup()
    sid, user = user_by_id(uid)
    api = _API({PRICE_SEMI: 350})
    monkeypatch.setattr(billing, "client", lambda: api)
    out = billing.open_checkout(user, "semi_pro", "http://localhost:8765")
    assert out["ok"] is True and out["url"].startswith("https://checkout.stripe.com/")
    assert "test mode" in out["message"].lower()
    assert api.sessions == 1
    assert api.customer_params["metadata"]["zeim_user_id"] == uid
    assert "email" not in api.customer_params and "payment_method" not in api.customer_params
    assert "payment_method_types" not in api.session_params
    saved = _user(uid)
    assert saved.get("plan") in (None, "free")
    assert saved["billing"]["customer_id"] == "cus_test123"
    assert saved["billing"].keys() <= billing._BILLING_KEYS
    assert "4242" not in json.dumps(saved)
    # Wrong Dashboard amount must not open Checkout.
    api.amounts[PRICE_SEMI] = 999
    api.sessions = 0
    again = billing.open_checkout(_user(uid), "semi_pro", "http://localhost:8765")
    assert again["ok"] is False and api.sessions == 0 and "Nothing was charged" in again["message"]
    del sid


def test_live_checkout_refuses_a_non_https_site(monkeypatch):
    _env(monkeypatch, STRIPE_SECRET_KEY="sk_live_zeim")
    _c, uid = _signup()
    _sid, user = user_by_id(uid)
    called = {}
    monkeypatch.setattr(billing, "client", lambda: called.setdefault("yes", True))
    out = billing.open_checkout(user, "pro", "http://zeim.test")
    assert out["ok"] is False and "https" in out["message"] and "yes" not in called


def test_webhook_rejects_a_bad_signature(monkeypatch):
    _env(monkeypatch)
    c, uid = _signup()
    event = _sub_event(uid)
    bad = _post_event(c, event, secret="whsec_wrong")
    assert bad.status_code == 400
    assert _user(uid).get("plan") in (None, "free")
    missing = c.post("/api/subscriptions/webhook", content=b"{}", headers={"Content-Type": "application/json"})
    assert missing.status_code == 400


def test_webhook_sets_plan_for_gating_and_ignores_card_fields(monkeypatch):
    _env(monkeypatch)
    c, uid = _signup()
    ok = _post_event(c, _sub_event(uid, price=PRICE_PRO, meta_plan="semi_pro"))
    assert ok.status_code == 200, ok.text
    me = c.get("/api/subscriptions/me").json()
    assert me["plan"]["id"] == "pro"          # price id wins over metadata
    assert me["plan"]["status"] == "active"
    assert me["plan"]["can_manage"] is True
    assert "cus_" not in json.dumps(me["plan"])
    user = _user(uid)
    assert user["billing"]["customer_id"] == "cus_test123"
    assert user["billing"]["subscription_id"] == "sub_test123"
    dumped = json.dumps(user)
    for banned in ("4242", "pm_card", "cvc", "last4"):
        assert banned not in dumped
    assert subs.has_paid_plan(user, "pro") and ai3d.is_pro(type("A", (), {"user": user})())
    assert not subs.has_paid_plan(user, "semi_pro")

    failed = _post_event(c, _sub_event(uid, typ="invoice.payment_failed", created=1_700_000_100, status="open"))
    assert failed.status_code == 200
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "pro"

    invoice = {
        "id": "evt_inv",
        "object": "event",
        "type": "invoice.payment_failed",
        "created": 1_700_000_200,
        "livemode": False,
        "data": {"object": {
            "id": "in_test",
            "object": "invoice",
            "customer": "cus_test123",
            "subscription": "sub_test123",
            "metadata": {"zeim_user_id": uid, "purpose": "zeim_plan"},
            "default_payment_method": "pm_card_visa",
        }},
    }
    assert _post_event(c, invoice).status_code == 200
    me = c.get("/api/subscriptions/me").json()
    assert me["plan"]["id"] == "pro" and me["plan"]["status"] == "past_due"
    assert "pm_card" not in json.dumps(_user(uid))
    blank = {
        "id": "evt_inv_blank", "object": "event", "type": "invoice.payment_failed",
        "created": 1_700_000_250, "livemode": False,
        "data": {"object": {
            "id": "in_blank", "object": "invoice", "customer": "cus_test123",
            "metadata": {"zeim_user_id": uid, "purpose": "zeim_plan"},
        }},
    }
    assert _post_event(c, blank).status_code == 200
    assert _user(uid)["billing"]["subscription_id"] == "sub_test123"

    stale = _post_event(c, _sub_event(uid, typ="customer.subscription.deleted", created=1_700_000_050))
    assert stale.status_code == 200
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "pro"

    ended = _post_event(c, _sub_event(uid, typ="customer.subscription.deleted", status="canceled", created=1_700_000_300))
    assert ended.status_code == 200
    me = c.get("/api/subscriptions/me").json()
    assert me["plan"]["id"] == "free"
    assert _user(uid)["billing"]["customer_id"] == "cus_test123"
    assert _user(uid)["billing"]["status"] == "canceled"
    assert not ai3d.is_pro(type("A", (), {"user": _user(uid)})())


def test_semi_pro_and_cancel_at_period_end(monkeypatch):
    _env(monkeypatch)
    c, uid = _signup()
    event = _sub_event(uid, price=PRICE_SEMI, status="active", cancel_at_period_end=True, created=50)
    assert billing.apply_event(event)["ok"] is True
    me = c.get("/api/subscriptions/me").json()
    assert me["plan"]["id"] == "semi_pro" and me["plan"]["cancel_at_period_end"] is True
    assert not ai3d.is_pro(type("A", (), {"user": _user(uid)})())


def test_paid_checkout_session_grants_and_unpaid_does_not(monkeypatch):
    _env(monkeypatch)
    _c, uid = _signup()
    unpaid = {
        "id": "evt_cs1", "object": "event", "type": "checkout.session.completed",
        "created": 10, "livemode": False,
        "data": {"object": {
            "id": "cs_test", "object": "checkout.session", "mode": "subscription",
            "payment_status": "unpaid", "customer": "cus_test123", "subscription": "sub_test123",
            "client_reference_id": uid, "metadata": {"zeim_user_id": uid, "plan": "pro", "purpose": "zeim_plan"},
        }},
    }
    billing.apply_event(unpaid)
    assert _user(uid).get("plan") in (None, "free")
    paid = dict(unpaid)
    paid["id"] = "evt_cs2"
    paid["created"] = 11
    paid["type"] = "checkout.session.async_payment_succeeded"
    paid["data"] = {"object": dict(unpaid["data"]["object"], payment_status="paid")}
    billing.apply_event(paid)
    assert _user(uid)["plan"] == "pro"


def test_customer_mismatch_does_not_move_a_plan(monkeypatch):
    _env(monkeypatch)
    _c, uid = _signup()
    billing.apply_event(_sub_event(uid, created=5))
    other = _sub_event(uid, created=6)
    other["data"]["object"]["customer"] = "cus_other999"
    result = billing.apply_event(other)
    assert result.get("mismatch") is True
    assert _user(uid)["billing"]["customer_id"] == "cus_test123"
    assert _user(uid)["plan"] == "pro"


def test_admin_sees_plan_status_without_card_data(monkeypatch):
    _env(monkeypatch)
    c, uid = _signup()
    billing.apply_event(_sub_event(uid, price=PRICE_SEMI, created=8))
    assert c.get("/api/subscriptions/admin").status_code == 403
    assert c.get("/api/subscriptions/admin", headers={"X-Admin-Token": "nope"}).status_code == 403
    ok = c.get("/api/subscriptions/admin", headers={"X-Admin-Token": "t0k"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["stores_cards"] is False
    assert "passkey" in body["recovery_note"].lower()
    assert "password reset" in body["recovery_note"].lower()
    assert "email" in body["support_note"].lower()
    row = next(a for a in body["accounts"] if a["user_id"] == uid)
    assert row["plan"] == "semi_pro"
    assert row["stripe_customer_id"] == "cus_test123"
    assert row["stripe_subscription_id"] == "sub_test123"
    assert "dob" not in row and "card" not in row and "last4" not in row
    sid, user = user_by_id(uid)

    def poison(d):
        d[sid]["billing"]["last4"] = "4242"
        d[sid]["billing"]["card"] = {"number": "4242424242424242"}
        d[sid]["dob"] = "1985-05-05"

    USERS.update(poison)
    again = c.get("/api/subscriptions/admin", headers={"X-Admin-Token": "t0k"}, params={"user_id": uid}).json()
    dumped = json.dumps(again)
    assert "4242" not in dumped and "1985" not in dumped
    assert again["accounts"][0]["plan"] == "semi_pro"
    del user


def test_checkout_api_comes_until_configured_and_redirects_only_to_stripe(monkeypatch):
    c, _uid = _signup()
    r = c.post("/api/subscriptions/checkout", json={"plan": "nope"})
    assert r.status_code == 400
    r = c.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 200 and r.json()["coming"] is True
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "free"
    _env(monkeypatch)

    def fake(user, plan_id, base):
        return {
            "ok": True, "url": "https://checkout.stripe.com/c/pay/cs_test_x",
            "plan": plan_id, "stripe_mode": "test",
            "message": "Stripe test mode — this does not charge a real card.",
        }

    monkeypatch.setattr(billing, "open_checkout", fake)
    r = c.post("/api/subscriptions/checkout", json={"plan": "semi_pro"})
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "free"
    monkeypatch.setattr(billing, "open_portal", lambda user, base: {
        "ok": True, "url": "https://billing.stripe.com/p/session/test", "portal": True, "message": "portal",
    })
    # No customer yet, so the real portal would refuse; the patch is what the route calls.
    opened = c.post("/api/subscriptions/portal")
    assert opened.json()["url"].startswith("https://billing.stripe.com/")
