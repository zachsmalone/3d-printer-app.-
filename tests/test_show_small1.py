"""Showcase small upgrades: AI-made label + filter, 'Printed by the community' badge, optional tip link."""
import os

import pytest

from app.community import tips
from app.community.store import ENGAGEMENT, LISTINGS, MODERATION, PREFS, PRINTS
from tests.b1 import client, photo_build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, PRINTS, MODERATION)}
    yield
    for s, was in snap.items():
        s.write(was)


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def publish(c, title="Pub", **extra):
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d", "tags": ["lamp"],
                                      "accept_guidelines": True, "nsfw": False, "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---- AI-made ----
def test_ai_label_and_filter():
    c = U("Aim")
    a = publish(c, "AiOne", ai_made=True)
    b = publish(c, "HandOne")
    assert a["ai_made"] is True and b["ai_made"] is False
    ids = lambda ai: {i["id"] for i in c.get(f"/api/showcase?tab=free&ai={ai}").json()["items"]}
    assert a["id"] in ids("show") and b["id"] in ids("show")
    assert a["id"] not in ids("hide") and b["id"] in ids("hide")
    assert a["id"] in ids("only") and b["id"] not in ids("only")
    assert c.get("/api/showcase?tab=free&ai=bogus").status_code == 400


def test_ai_toggle_owner_only_and_ai3d_build_locked():
    c, o = U("Ait"), U("Other")
    b = publish(c, "Later")
    assert c.put(f"/api/showcase/{b['id']}/ai", json={"ai_made": True}).json()["ai_made"] is True
    assert o.put(f"/api/showcase/{b['id']}/ai", json={"ai_made": False}).status_code == 404
    LISTINGS.update(lambda l: [i.__setitem__("mode", "ai3d") for i in l if i["id"] == b["id"]])
    assert c.put(f"/api/showcase/{b['id']}/ai", json={"ai_made": False}).status_code == 400


def test_ai3d_build_is_labelled_automatically():
    """Builds from the 2D->3D tab (meta ai=True / mode ai3d) get the label at publish time."""
    src = open(os.path.join(ROOT, "app/community/catalog.py")).read()
    assert 'bool(bmeta.get("ai")) or mode == "ai3d"' in src


# ---- printed by the community ----
def test_printed_badge_only_after_approved_print():
    c = U("Pb")
    a = publish(c, "Printme")
    assert a["community_printed"] is False
    PRINTS.update(lambda l: l.append({"id": "sp1", "item_id": a["id"], "owner_sid": "x", "status": "pending", "created": 1, "caption": ""}))
    assert U("V1").get(f"/api/showcase/{a['id']}").json()["community_printed"] is False
    PRINTS.update(lambda l: [p.__setitem__("status", "approved") for p in l if p["id"] == "sp1"])
    j = U("V2").get(f"/api/showcase/{a['id']}").json()
    assert j["community_printed"] is True


def test_badge_copy_is_calm_no_counts():
    js = open(os.path.join(ROOT, "static/community.js")).read()
    i = js.index("function provHTML")
    body = js[i:js.index("function tipHTML")]
    assert "Printed by the community" in body and "AI-made" in body
    assert "prints_count" not in body and "length" not in body
    assert "#i-chip" in body and "#i-printer" in body


# ---- tip link ----
@pytest.mark.parametrize("bad", ["http://x.com", "javascript:alert(1)", "https://", "https://localhost/a", "https://127.0.0.1/",
                                 "https://u:p@x.com/", "https://x.com/a b", 'https://x.com/"><b>', "ftp://x.com", "https://x" ,
                                 "https://" + "a" * 300 + ".com"])
def test_tip_rejects(bad):
    with pytest.raises(ValueError):
        tips.check(bad)


def test_tip_accepts():
    assert tips.check(" https://ko-fi.com/maker ") == "https://ko-fi.com/maker"
    assert tips.check("") == "" and tips.check(None) == ""


def test_tip_publish_set_clear_and_owner_only():
    c, o = U("Tipper"), U("Nosy")
    assert c.post("/api/showcase", json={"build_id": photo_build(c), "title": "T", "description": "", "tags": [],
                                         "accept_guidelines": True, "nsfw": False, "tip_url": "http://x.com"}).status_code == 400
    a = publish(c, "Tipped", tip_url="https://example.com/tip")
    assert a["tip_url"] == "https://example.com/tip"
    assert o.get(f"/api/showcase/{a['id']}").json()["tip_url"] == "https://example.com/tip"
    assert o.put(f"/api/showcase/{a['id']}/tip", json={"tip_url": "https://evil.com"}).status_code == 404
    assert c.put(f"/api/showcase/{a['id']}/tip", json={"tip_url": "javascript:1"}).status_code == 400
    assert c.put(f"/api/showcase/{a['id']}/tip", json={"tip_url": ""}).json()["tip_url"] == ""


def test_tip_link_rendering_is_quiet():
    js = open(os.path.join(ROOT, "static/community.js")).read()
    body = js[js.index("function tipHTML"):]
    body = body[:body.index("\n}\n")]
    assert 'rel="noopener nofollow noreferrer"' in body and "^https:" in body
    low = js.lower()
    for nag in ("please tip", "don't forget to tip", "tip now"):
        assert nag not in low
