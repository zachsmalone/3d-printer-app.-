"""Nozzle it (reports/design/nozzle-it-spec.md): server side. Positive only, idempotent {"liked": bool}, no counts on non-public items,
can_like_reason, wording. Browser part: tests/ui_nozzle.py via test_b4_ui.py."""
import os, re
from app import config
from tests.b1 import client, photo_build, ADULT, SUSPENDED, UNDER18


def _publish_one(with_owner=False):
    pub = client(ADULT)
    r = pub.post("/api/showcase", json={"build_id": photo_build(pub), "title": "Pub", "description": "d", "tags": [], "accept_guidelines": True, "nsfw": False, "visibility": "public"})
    assert r.status_code == 200, r.text
    return (r.json()["id"], pub) if with_owner else r.json()["id"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def V(n="Viewer"):
    return client({"display_name": n, "dob": "1990-01-01"})


def test_a_signed_out_visitor_cannot_nozzle_and_gets_a_plain_401():
    iid = _publish_one(); anon = client()
    r = anon.post(f"/api/showcase/{iid}/like", json={"liked": True})
    assert r.status_code == 401 and r.json()["detail"] == "Make a free account to nozzle projects."
    assert anon.get(f"/api/showcase/{iid}").json()["liked"] is False and client().get(f"/api/showcase/{iid}").status_code == 200   # looking still works
    assert anon.post("/api/showcase/zo-pencil-cup/like", json={}).status_code == 401
    # a private / unknown project is still a plain 404, not a hint that it exists
    assert anon.post("/api/showcase/nope123/like", json={}).status_code == 404


def test_press_is_idempotent_with_an_explicit_state_and_an_old_empty_body_still_toggles():
    iid = _publish_one(); v = V()
    a = v.post(f"/api/showcase/{iid}/like", json={"liked": True}).json()
    b = v.post(f"/api/showcase/{iid}/like", json={"liked": True}).json()          # a double tap sends the same wish twice: still one nozzle
    assert a["liked"] and b["liked"] and a["likes"] == b["likes"]
    c = v.post(f"/api/showcase/{iid}/like", json={"liked": False}).json()
    assert not c["liked"] and c["likes"] == a["likes"] - 1
    d = v.post(f"/api/showcase/{iid}/like", json={}).json()                         # old client: toggle
    assert d["liked"] and d["likes"] == a["likes"]
    assert v.post(f"/api/showcase/{iid}/like").json()["liked"] is False


def test_there_is_no_dislike_route_and_the_owner_cannot_nozzle_their_own_project():
    iid, owner = _publish_one(True)
    v = V()
    for path in ("dislike", "downvote", "unlike"):
        assert v.post(f"/api/showcase/{iid}/{path}", json={}).status_code in (404, 405)
    r = owner.post(f"/api/showcase/{iid}/like", json={"liked": True})
    assert r.status_code == 403 and "nozzle" in r.json()["detail"].lower() and "like" not in r.json()["detail"].lower().replace("nozzle", "")


def test_can_like_reason_says_why_a_button_would_not_work():
    iid, owner = _publish_one(True)
    assert owner.get(f"/api/showcase/{iid}").json()["can_like_reason"] == "own"
    assert client().get(f"/api/showcase/{iid}").json()["can_like_reason"] == ""
    assert V().get(f"/api/showcase/{iid}").json()["can_like_reason"] == ""             # no "class_off" reason any more (school features removed)



def test_no_example_items_remain():
    items = client().get("/api/showcase").json()["items"]
    assert items and not [i for i in items if i.get("example")]


def test_project_page_says_nozzles_not_hearts():
    iid = _publish_one(); V().post(f"/api/showcase/{iid}/like", json={"liked": True})
    page = client().get(f"/p/{iid}").text
    assert "♥" not in page and "nozzle" in page


def test_no_heart_like_or_downvote_wording_is_left_in_the_page():
    for f in ("index.html", "community.js", "app.js", "edit.js", "send.js", "COMMUNITY_GUIDELINES.html", "terms.html", "privacy.html"):
        src = open(os.path.join(ROOT, "static", f), encoding="utf-8").read()
        assert "♥" not in src and "❤" not in src and "👍" not in src and "👎" not in src, f
        assert not re.search(r"dislike|downvote|thumbs[- ]?(up|down)", src, re.I), f
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    assert not re.search(r">[^<]*\b(Like|Likes|Liked)\b[^<]*<", html)
