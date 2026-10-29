"""Paid plans stay closed unless ZEIM_PLANS_ENABLED is on.

The flag defaults off and refuses checkout. Turning it on without a full Stripe
configuration still charges nothing. Hosted Checkout is covered in test_stripe_plans.py.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app import config
from app.community import badges
from app.community.store import USERS
from app.services import ai3d, stripe_billing as billing
from app.services import subscriptions as subs
from tests.b1 import ADULT, box_stl, client, gen, photo_build

_STRIPE_KEYS = (
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_PRICE_SEMI_PRO", "STRIPE_PRICE_PRO",
    "STRIPE_PRICE_FEE_SEMI_PRO", "STRIPE_PRICE_FEE_PRO",
)


@pytest.fixture(autouse=True)
def _clear_stripe_env(monkeypatch):
    for key in _STRIPE_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_catalog_is_honest():
    c = subs.catalog()
    assert c["payment_live"] is False
    assert c["plans_enabled"] is False
    assert c["stripe_mode"] == "off"
    assert c["stores_cards"] is False
    assert "about 1%" in c["fee_note"]
    assert "4¢" in c["fee_note"] and "6¢" in c["fee_note"]
    assert "processing" in c["processing_note"].lower()
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
    """ZEIM_PLANS_ENABLED=1 without a full Stripe configuration does not charge.

    A partial key, or the lack of one, must not raise and must not return a payment URL.
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


def test_stripe_keys_do_not_open_checkout_while_plans_are_off(monkeypatch):
    """Soft launch: a full Stripe test or live key still refuses while the flag is off."""
    monkeypatch.setenv("ZEIM_PLANS_ENABLED", "0")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_zeim")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setenv("STRIPE_PRICE_SEMI_PRO", "price_semi123")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro123")
    assert subs.plans_enabled() is False
    assert subs.payment_live() is False
    cat = subs.catalog()
    assert cat["stripe_mode"] == "live"
    assert cat["payment_live"] is False
    assert all(p["purchasable"] is False for p in cat["plans"])
    assert all(p["coming"] is True for p in cat["plans"] if p["id"] != "free")
    c = client(ADULT)
    r = c.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["checkout"] is False and body["coming"] is True
    assert "url" not in body
    assert "sk_live" not in r.text and "whsec" not in r.text
    assert "nothing was charged" in r.text.lower()
    assert "stripe" not in r.text.lower()
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


# Account badges and the cc0hort lifetime Pro comp. Collected here so the existing CI command runs them.
ROOT = Path(__file__).resolve().parents[1]
NOTE = "You believed in me, and you are part of the reason I made ZEIM."


def _earned(c):
    body = c.get("/api/me/badges").json()
    return {b["id"]: b for b in body["badges"] if b.get("earned")}


def _png():
    im = Image.new("RGB", (24, 24), (30, 40, 50))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _publish(c, title, **extra):
    body = {"build_id": photo_build(c), "title": title, "description": "a small lamp",
            "tags": ["lamp"], "accept_guidelines": True, "nsfw": False, "visibility": "public"}
    body.update(extra)
    r = c.post("/api/showcase", json=body)
    assert r.status_code == 200, r.text
    return r


@pytest.fixture(scope="module")
def hort():
    return client({"display_name": "Hort", "dob": "1991-04-04", "username": "cc0hort"})


def test_soft_launch_flags_stay_off():
    prod = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "ZEIM_COMING_SOON=0" in prod
    assert "ZEIM_PLANS_ENABLED=0" in prod
    assert "ZEIM_2D3D_ENABLED=0" in prod
    assert config.coming_soon_enabled() is False
    assert config.plans_enabled() is False
    assert config.ai3d_enabled() is False


def test_account_page_lines_the_badge_box_up_with_the_other_cards():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    acc = html[html.index('id="viewAccount"'):html.index('id="viewLearn"')]
    assert acc.index("accHandleCard") < acc.index("accBadgesCard")
    assert "acctop" in acc
    assert "No prizes." in acc
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    assert "#viewAccount .acctop" in css
    assert "grid-column:1 / -1" in css
    # The username is a seed, not a check painted into the page.
    assert "cc0hort" not in html
    assert "cc0hort" not in (ROOT / "static/badges.js").read_text(encoding="utf-8")
    assert "cc0hort" not in (ROOT / "static/community.js").read_text(encoding="utf-8")


def test_award_logic_never_fakes_progress_and_is_idempotent():
    sid = "badge-logic-sid-0001"
    USERS.update(lambda d: d.__setitem__(sid, {
        "id": "badge-logic-user", "display_name": "Logic", "username": "LogicUser",
        "created": "2026-01-01T00:00:00+00:00", "links": {}, "following": [],
    }))
    rows = badges.for_owner(sid)["badges"]
    earnable = [b for b in rows if b["id"] not in ("official_og", "tester")]
    assert len(earnable) == 10
    assert all(not b["earned"] and b["how"] and "\n" not in b["how"] for b in earnable)
    blob = " ".join(b["how"] + b["name"] for b in earnable).lower()
    assert "prize" not in blob and "$" not in blob and "cash" not in blob
    assert badges.record(sid, "not_a_thing") == []
    assert badges.record("no-such-account", "fdm_slice") == []
    assert "first_slice" not in USERS.read()[sid].get("badges", {})

    assert badges.record(sid, "fdm_slice") == [{"id": "first_slice", "name": "First Slice"}]
    at = USERS.read()[sid]["badges"]["first_slice"]["earned_at"]
    assert badges.record(sid, "fdm_slice") == []
    assert USERS.read()[sid]["badges"]["first_slice"]["earned_at"] == at
    assert USERS.read()[sid]["badge_progress"]["fdm_slice"] == 2

    for n in range(1, 10):
        got = {b["id"] for b in badges.record(sid, "print_shared", count=n)}
        if n == 1:
            assert got == {"first_print"}
        else:
            assert "prints_10" not in got and "first_print" not in got
        assert "prints_10" not in USERS.read()[sid]["badges"]
    assert {b["id"] for b in badges.record(sid, "print_shared", count=10)} == {"prints_10"}
    at10 = USERS.read()[sid]["badges"]["prints_10"]["earned_at"]
    assert badges.record(sid, "print_shared", count=2) == []
    assert USERS.read()[sid]["badges"]["prints_10"]["earned_at"] == at10

    for event, badge_id, name in (
        ("export", "first_export", "First Export"),
        ("lithophane", "first_lithophane", "First Lithophane"),
        ("resin_slice", "first_resin", "First Resin slice"),
        ("cad_save", "first_cad", "First CAD model saved"),
        ("showcase", "first_showcase", "First Showcase publish"),
        ("remix", "first_remix", "First Remix"),
        ("challenge", "challenge_entrant", "Challenge Entrant"),
    ):
        assert badges.record(sid, event) == [{"id": badge_id, "name": name}]
        assert badges.record(sid, event) == []


def test_official_og_is_the_first_100_plus_cc0hort_and_permanent():
    users = {}
    for i in range(110):
        users[f"s{i:03d}"] = {
            "id": f"u{i:03d}",
            "username": f"Name{i}",
            "created": f"2020-01-{(i // 24) + 1:02d}T{i % 24:02d}:00:00+00:00",
        }
    users["s000"]["username"] = "cc0hort2"
    users["s109"]["username"] = "cc0hort"
    stats = badges.apply_seed(users)
    ordered = sorted(users, key=lambda sid: (users[sid]["created"], sid))
    assert ordered[0] == "s000" and ordered[-1] == "s109"
    for sid in ordered[:100]:
        assert "official_og" in users[sid]["badges"]
    for sid in ordered[100:-1]:
        assert "official_og" not in users[sid].get("badges", {})
    hort = users["s109"]
    assert "official_og" in hort["badges"]
    assert "tester" in hort["badges"]
    assert hort["entitlements"]["pro"]["kind"] == "comp"
    assert hort["entitlements"]["pro"]["price_usd"] == 0
    assert hort["entitlements"]["pro"]["card"] is False
    assert hort["entitlements"]["pro"]["expires_at"] is None
    assert "tester" not in users["s000"].get("badges", {})
    assert "pro" not in (users["s000"].get("entitlements") or {})
    assert stats["comp"] == 1 and stats["tester"] == 1

    at = users[ordered[0]]["badges"]["official_og"]["earned_at"]
    granted = hort["entitlements"]["pro"]["granted_at"]
    users[ordered[0]]["created"] = "2099-01-01T00:00:00+00:00"
    again = badges.apply_seed(users)
    assert users[ordered[0]]["badges"]["official_og"]["earned_at"] == at
    assert hort["entitlements"]["pro"]["granted_at"] == granted
    assert again["comp"] == 0 and again["tester"] == 0

    mixed = {"a": {"id": "a", "username": "Cc0Hort", "created": "2019-05-05T00:00:00+00:00"}}
    badges.apply_seed(mixed)
    assert mixed["a"]["entitlements"]["pro"]["kind"] == "comp"
    assert "tester" in mixed["a"]["badges"]


def test_cc0hort_pro_comp_works_with_plans_off_and_on(hort, monkeypatch):
    monkeypatch.setenv("ZEIM_PLANS_ENABLED", "0")
    for key in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_SEMI_PRO", "STRIPE_PRICE_PRO"):
        monkeypatch.delenv(key, raising=False)
    assert subs.plans_enabled() is False
    me = hort.get("/api/me").json()
    assert me["username"] == "cc0hort"
    sid = next(s for s, u in USERS.read().items() if u.get("id") == me["id"])
    user = USERS.read()[sid]
    assert user["entitlements"]["pro"]["kind"] == "comp"
    assert user["entitlements"]["pro"]["price_usd"] == 0
    assert user["entitlements"]["pro"]["card"] is False
    assert user["entitlements"]["pro"]["expires_at"] is None
    blob = json.dumps(user)
    assert "cus_" not in blob and "4242" not in blob
    assert subs.has_paid_plan(user, "pro")
    assert not subs.has_paid_plan(user, "semi_pro")
    assert ai3d.is_pro(type("A", (), {"user": user})())
    plan = hort.get("/api/subscriptions/me").json()
    assert plan["plans_enabled"] is False
    assert plan["plan"]["id"] == "pro"
    assert plan["plan"]["comp"] is True
    assert plan["plan"]["price_usd"] == 0
    assert plan["plan"]["card"] is False
    assert plan["plan"]["expires_at"] is None
    assert plan["plan"]["can_manage"] is False
    granted = user["entitlements"]["pro"]["granted_at"]
    badges.seed()
    assert USERS.read()[sid]["entitlements"]["pro"]["granted_at"] == granted

    other = client(ADULT)
    assert other.get("/api/subscriptions/me").json()["plan"]["id"] == "free"
    refused = other.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert refused.status_code == 403 and refused.json()["checkout"] is False

    r = hort.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 200, r.text
    assert r.json()["checkout"] is False and r.json()["comp"] is True
    assert "url" not in r.json()
    assert "stripe" not in r.text.lower()
    assert "nothing was charged" in r.text.lower()
    portal = hort.post("/api/subscriptions/portal")
    assert portal.status_code == 200 and portal.json()["checkout"] is False and "url" not in portal.json()

    monkeypatch.setenv("ZEIM_PLANS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_zeim")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setenv("STRIPE_PRICE_SEMI_PRO", "price_semi123")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro123")
    called = {}
    monkeypatch.setattr(billing, "open_checkout", lambda *a, **k: called.setdefault("hit", True))
    r = hort.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 200, r.text
    assert r.json()["checkout"] is False and "url" not in r.json()
    assert "hit" not in called
    assert subs.has_paid_plan(USERS.read()[sid], "pro")
    assert subs.plans_enabled() is True


def test_tester_badge_is_visible_only_to_cc0hort(hort):
    mine = hort.get("/api/me/badges").json()
    tester = next(b for b in mine["badges"] if b["id"] == "tester")
    assert tester["earned"] is True
    assert tester["label"] == "Thank you for being a tester"
    assert NOTE in tester["note"]
    assert tester["note"].startswith("cc0hort, thank you.")
    assert tester["note"].endswith("— Zach")
    assert "official_og" in _earned(hort)
    assert NOTE not in hort.get("/api/me").text

    hid = hort.get("/api/me").json()["id"]
    own_public = hort.get(f"/api/users/{hid}")
    assert own_public.status_code == 200
    assert all(b["id"] != "tester" for b in own_public.json().get("badges", []))
    assert NOTE not in own_public.text
    assert "Thank you for being a tester" not in own_public.text

    other = client({"display_name": "Other Maker", "dob": "1993-03-03"})
    oid = other.get("/api/me").json()["id"]
    osid = next(s for s, u in USERS.read().items() if u.get("id") == oid)
    USERS.update(lambda d: d[osid].setdefault("badges", {}).__setitem__(
        "tester", {"earned_at": "2020-01-01T00:00:00+00:00"}))
    theirs = other.get("/api/me/badges").json()
    assert all(b["id"] != "tester" for b in theirs["badges"])
    assert NOTE not in other.get("/api/me/badges").text
    assert "Thank you for being a tester" not in other.get("/api/me/badges").text
    pub = other.get(f"/api/users/{hid}")
    assert pub.status_code == 200
    assert all(b["id"] != "tester" for b in pub.json().get("badges", []))
    assert NOTE not in pub.text
    assert "Thank you for being a tester" not in pub.text
    assert "official_og" in {b["id"] for b in pub.json().get("badges", [])}


def test_real_actions_award_and_a_plain_publish_is_not_a_remix():
    litho = client({"display_name": "Litho Maker", "dob": "1990-06-06"})
    made = gen(litho, mode="lithophane")
    assert made.status_code == 200, made.text
    assert "first_lithophane" in {b["id"] for b in made.json().get("badges_new", [])}
    assert "first_lithophane" in _earned(litho)
    assert "first_slice" not in _earned(litho)

    exporter = client({"display_name": "Export Maker", "dob": "1990-07-07"})
    bid = photo_build(exporter)
    assert "first_lithophane" not in _earned(exporter)
    down = exporter.get(f"/files/{bid}/model.stl")
    assert down.status_code == 200
    assert down.headers.get("x-zeim-badges", "").startswith("first_export|")
    assert "first_export" in _earned(exporter)
    again = exporter.get(f"/files/{bid}/model.stl")
    assert "x-zeim-badges" not in {k.lower() for k in again.headers}

    author = client({"display_name": "Show Maker", "dob": "1988-08-08"})
    pub = _publish(author, "Plain lamp", license_id="cc-by-4.0")
    new_ids = {b["id"] for b in pub.json().get("badges_new", [])}
    assert "first_showcase" in new_ids and "first_remix" not in new_ids

    remixer = client({"display_name": "Remix Maker", "dob": "1987-09-09"})
    rem = _publish(remixer, "Remixed lamp", remix_of=pub.json()["id"], license_id="cc-by-4.0")
    rem_ids = {b["id"] for b in rem.json().get("badges_new", [])}
    assert "first_showcase" in rem_ids and "first_remix" in rem_ids

    photo = remixer.post(
        f"/api/showcase/{rem.json()['id']}/prints",
        files={"photo": ("p.png", _png(), "image/png")},
        data={"caption": "It printed", "photo_ack": "true", "nsfw": "no"},
    )
    assert photo.status_code == 200, photo.text
    assert {b["id"] for b in photo.json().get("badges_new", [])} == {"first_print"}
    assert "prints_10" not in _earned(remixer)

    entered = remixer.post("/api/challenges/ch_2026_12/enter", json={"item_id": rem.json()["id"]})
    assert entered.status_code == 200, entered.text
    assert "challenge_entrant" in {b["id"] for b in entered.json().get("badges_new", [])}
    assert entered.json()["prize_free"] is True

    cad = client({"display_name": "Cad Maker", "dob": "1986-01-01"})
    made_cad = cad.post("/api/cad/new", json={
        "op": "cad_shape", "title": "Tiny cup",
        "params": {"kind": "cylinder", "dims": {"diameter": 20, "height": 4}},
    })
    assert made_cad.status_code == 200, made_cad.text
    assert "first_cad" in {b["id"] for b in made_cad.json().get("badges_new", [])}

    resin = client({"display_name": "Resin Maker", "dob": "1985-02-02"})
    prepped = resin.post(
        "/api/resin/prepare",
        data={"hollow": "false", "supports": "false", "tilt_deg": "0"},
        files={"file": ("cube.stl", box_stl(), "model/stl")},
    )
    assert prepped.status_code == 200, prepped.text
    assert "first_resin" in {b["id"] for b in prepped.json().get("badges_new", [])}

    slice_src = (ROOT / "app/api/slice.py").read_text(encoding="utf-8")
    print_src = (ROOT / "app/api/printing.py").read_text(encoding="utf-8")
    assert "fdm_slice" in slice_src and "badges.merge" in slice_src
    assert "fdm_slice" in print_src


def test_guest_badges_are_empty():
    assert client().get("/api/me/badges").json() == {"signed_up": False, "badges": [], "unseen": []}
