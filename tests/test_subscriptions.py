"""Paid plans stay closed unless ZEIM_PLANS_ENABLED is on, and even then nothing is charged."""
from __future__ import annotations

import pytest

from app.services import subscriptions as subs
from tests.b1 import ADULT, client, gen


def test_catalog_is_honest():
    c = subs.catalog()
    assert c["payment_live"] is False
    assert c["plans_enabled"] is False
    assert "never takes a cut" in c["tip_note"].lower()
    assert "nothing on this page starts a payment" in c["payment_note"].lower()
    ids = {p["id"] for p in c["plans"]}
    assert ids == {"free", "semi_pro", "pro"}
    prices = {p["id"]: p["price_usd"] for p in c["plans"]}
    assert prices["free"] == 0
    assert abs(prices["semi_pro"] - 3.5) < 1e-6
    assert abs(prices["pro"] - 5.5) < 1e-6
    for plan in c["plans"]:
        assert plan["purchasable"] is False
        if plan["id"] != "free":
            assert plan["coming"] is True


def test_plans_api():
    c = client()
    r = c.get("/api/subscriptions/plans")
    assert r.status_code == 200
    j = r.json()
    assert j["payment_live"] is False
    assert j["plans_enabled"] is False
    assert len(j["plans"]) == 3
    assert all(p["purchasable"] is False for p in j["plans"])


def test_disabled_plans_have_no_checkout_path():
    c = client()
    r = c.get("/api/subscriptions/me")
    assert r.status_code == 200
    assert r.json()["plan"]["id"] == "free"
    assert r.json()["plans_enabled"] is False

    r = c.post("/api/subscriptions/checkout", json={"plan": "semi_pro"})
    assert r.status_code == 401

    c = client(ADULT)
    for plan in ("semi_pro", "pro", "Semi Pro"):
        r = c.post("/api/subscriptions/checkout", json={"plan": plan})
        assert r.status_code == 403, r.text
        body = r.json()
        assert body["checkout"] is False
        assert body["coming"] is True
        assert body["ok"] is False
        assert "url" not in body
        assert "session" not in body
        assert "location" not in {k.lower() for k in r.headers}
        low = r.text.lower()
        assert "stripe" not in low
        assert "checkout.stripe.com" not in low
        assert "nothing was charged" in low
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "free"


def test_enabling_the_flag_still_does_not_charge_without_stripe(monkeypatch):
    """ZEIM_PLANS_ENABLED=1 is reversible, but this build has no processor.

    A Stripe key, or the lack of one, must not raise and must not return a payment URL.
    """
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("ZEIM_PLANS_ENABLED", "1")
    assert subs.plans_enabled() is True
    assert subs.payment_live() is False
    cat = subs.catalog()
    assert cat["plans_enabled"] is True
    assert all(p["purchasable"] is False for p in cat["plans"])

    c = client(ADULT)
    r = c.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout"] is False
    assert body.get("coming") is True
    assert "url" not in body and "blocked" not in body
    assert "stripe" not in r.text.lower()
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "free"

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_not_a_real_secret")
    assert subs.payment_live() is False
    r = c.post("/api/subscriptions/checkout", json={"plan": "semi_pro"})
    assert r.status_code == 200, r.text
    assert r.json()["checkout"] is False
    assert "url" not in r.json()
    assert "sk_test" not in r.text
    assert "whsec" not in r.text
    assert c.get("/api/subscriptions/me").json()["plan"]["id"] == "free"


@pytest.mark.parametrize("raw, enabled", [
    (None, False),
    ("", False),
    ("0", False),
    ("false", False),
    ("off", False),
    ("no", False),
    ("1", True),
    ("true", True),
    ("yes", True),
    ("on", True),
])
def test_plans_flag_parsing(monkeypatch, raw, enabled):
    if raw is None:
        monkeypatch.delenv("ZEIM_PLANS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ZEIM_PLANS_ENABLED", raw)
    assert subs.plans_enabled() is enabled


def test_plans_ui_does_not_offer_checkout_unless_purchasable():
    js = open("static/community.js", encoding="utf-8").read()
    account = open("static/zeim-account.js", encoding="utf-8").read()
    assert js.count("<h4>Plans</h4>") >= 1
    assert account.count("<h4>Plans</h4>") >= 1
    assert "Coming later" in js
    assert "p.purchasable" in js
    assert js.count("/api/subscriptions/checkout") == 1
    assert js.find("p.purchasable") < js.find("/api/subscriptions/checkout")
    assert "button[data-plan]" in js


def test_free_core_still_works_while_plans_are_disabled(monkeypatch):
    monkeypatch.setenv("ZEIM_PLANS_ENABLED", "0")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    c = client(ADULT)
    page = c.get("/")
    assert page.status_code == 200
    assert 'id="mainNav"' in page.text
    assert 'id="dlgSettings"' in page.text
    assert 'id="btnSettings"' in page.text
    assert "ZEIM is almost ready" not in page.text
    settings = c.get("/api/settings")
    assert settings.status_code == 200, settings.text
    assert "mode" in settings.json()
    built = gen(c, mode="lithophane")
    assert built.status_code == 200, built.text
    assert built.json().get("id")
    me = c.get("/api/subscriptions/me").json()
    assert me["plan"]["id"] == "free"
    assert me["plans_enabled"] is False


def test_normalize_plan():
    assert subs.normalize_plan("Semi Pro") == "semi_pro"
    assert subs.normalize_plan("PRO") == "pro"
    assert subs.normalize_plan("nope") == "free"


def test_live_sculpt_strings_present():
    """Sanity: Live Sculpt UI copy is in cad.js (no fake payment claims)."""
    text = open("static/cad.js").read()
    assert "Live Sculpt" in text
    assert "Saving stroke" in text
    assert "previewDab" in text
