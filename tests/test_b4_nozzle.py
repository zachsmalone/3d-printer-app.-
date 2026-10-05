"""Nozzle it (reports/design/nozzle-it-spec.md): server side. Positive only, idempotent {"liked": bool}, no counts for class students / under-13 viewers,
can_like_reason, wording. Browser part: tests/ui_nozzle.py via test_b4_ui.py."""
import os, re
from app import config
from tests.b1 import client, make_class, student, photo_build, ADULT, TEEN


def _publish_one(with_owner=False):
    pub = client(ADULT)
    r = pub.post("/api/showcase", json={"build_id": photo_build(pub), "title": "Pub", "description": "d", "tags": [], "accept_guidelines": True, "visibility": "public"})
    assert r.status_code == 200, r.text
    return (r.json()["id"], pub) if with_owner else r.json()["id"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_press_is_idempotent_with_an_explicit_state_and_an_old_empty_body_still_toggles():
    iid = _publish_one(); v = client()
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
    v = client()
    for path in ("dislike", "downvote", "unlike"):
        assert v.post(f"/api/showcase/{iid}/{path}", json={}).status_code in (404, 405)
    r = owner.post(f"/api/showcase/{iid}/like", json={"liked": True})
    assert r.status_code == 403 and "nozzle" in r.json()["detail"].lower() and "like" not in r.json()["detail"].lower().replace("nozzle", "")


def test_can_like_reason_says_why_a_button_would_not_work():
    iid, owner = _publish_one(True)
    assert owner.get(f"/api/showcase/{iid}").json()["can_like_reason"] == "own"
    assert client().get(f"/api/showcase/{iid}").json()["can_like_reason"] == ""
    t, code, pw = make_class(); s = student(code, pw, "Fox")
    t.put(f"/api/classrooms/{code}/showcase", json={"enabled": True})
    it = s.get(f"/api/showcase/{iid}").json()
    assert it["can_like"] is False and it["can_like_reason"] == "class_off"
    r = s.post(f"/api/showcase/{iid}/like", json={"liked": True})
    assert r.status_code == 403 and "nozzles off" in r.json()["detail"]


def test_class_students_see_no_nozzle_or_download_numbers_even_on_adults_projects_but_can_still_nozzle_when_allowed():
    iid = _publish_one()
    v = client(); v.post(f"/api/showcase/{iid}/like", json={"liked": True})
    seen = client().get(f"/api/showcase/{iid}").json()
    assert seen["likes"] is not None and seen["likes"] >= 1                          # an ordinary visitor sees the number
    t, code, pw = make_class(); s = student(code, pw, "Fox")
    t.put(f"/api/classrooms/{code}/showcase", json={"enabled": True}); t.put(f"/api/classrooms/{code}/showcase", json={"likes": True})
    it = s.get(f"/api/showcase/{iid}").json()
    assert it["likes"] is None and it["downloads"] is None and it["counts_hidden"] is True and it["can_like"] is True
    assert all(x["likes"] is None and x["downloads"] is None for x in s.get("/api/showcase").json()["items"])
    r = s.post(f"/api/showcase/{iid}/like", json={"liked": True}).json()
    assert r["liked"] is True and r["likes"] is None                                  # works, but the response carries no number either
    assert s.get(f"/api/showcase/{iid}").json()["liked"] is True


def test_example_items_still_show_no_numbers():
    items = client().get("/api/showcase").json()["items"]
    ex = [i for i in items if i.get("example")]
    assert ex and all(i["likes"] is None for i in ex)


def test_project_page_and_teacher_list_say_nozzles_not_hearts():
    iid = _publish_one(); client().post(f"/api/showcase/{iid}/like", json={"liked": True})
    page = client().get(f"/p/{iid}").text
    assert "♥" not in page and "nozzle" in page
    t, code, pw = make_class(); s = student(code, pw, "Fox")
    t.put(f"/api/classrooms/{code}/showcase", json={"enabled": True})
    bid = photo_build(s)
    s.post(f"/api/classrooms/{code}/projects", json={"build_id": bid})
    listing = t.get(f"/api/classrooms/{code}/projects").text
    assert "♥" not in listing


def test_no_heart_like_or_downvote_wording_is_left_in_the_page():
    for f in ("index.html", "community.js", "app.js", "edit.js", "send.js", "COMMUNITY_GUIDELINES.html", "terms.html", "privacy.html"):
        src = open(os.path.join(ROOT, "static", f), encoding="utf-8").read()
        assert "♥" not in src and "❤" not in src and "👍" not in src and "👎" not in src, f
        assert not re.search(r"dislike|downvote|thumbs[- ]?(up|down)", src, re.I), f
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    assert not re.search(r">[^<]*\b(Like|Likes|Liked)\b[^<]*<", html)
