"""Subscription plan stubs: honest Coming until payment is live."""
from __future__ import annotations

from app.services import subscriptions as subs
from tests.b1 import client, ADULT


def test_catalog_is_honest():
    c = subs.catalog()
    assert c["payment_live"] is False
    assert "never takes a cut" in c["tip_note"].lower()
    ids = {p["id"] for p in c["plans"]}
    assert ids == {"free", "semi_pro", "pro"}
    prices = {p["id"]: p["price_usd"] for p in c["plans"]}
    assert prices["free"] == 0
    assert abs(prices["semi_pro"] - 3.5) < 1e-6
    assert abs(prices["pro"] - 5.5) < 1e-6


def test_plans_api():
    c = client()
    r = c.get("/api/subscriptions/plans")
    assert r.status_code == 200
    j = r.json()
    assert j["payment_live"] is False
    assert len(j["plans"]) == 3


def test_me_and_checkout_coming():
    c = client()
    r = c.get("/api/subscriptions/me")
    assert r.status_code == 200
    assert r.json()["plan"]["id"] == "free"

    r = c.post("/api/subscriptions/checkout", json={"plan": "semi_pro"})
    assert r.status_code == 401

    c = client(ADULT)
    r = c.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("coming") is True or j.get("ok") is False
    assert "not live" in j["message"].lower() or "coming" in j["message"].lower()
    me = c.get("/api/subscriptions/me").json()
    assert me["plan"]["id"] == "free"


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
