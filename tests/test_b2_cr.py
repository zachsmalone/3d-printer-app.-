"""Education change requests CR-2 (purge), CR-3 (Showcase off for class students), CR-4 (seat reset), CR-5 (photo permission),
CR-11 (moderation basics), CR-15 (teacher recovery code)."""
import json, os, re
import pytest
from app import config
from app.community import classrooms
from app.community.store import CLASSROOMS, PROGRESS
from app.services.history import store
from tests import b1
from tests.b1 import client, make_class, student, join, gen, photo_build, ADULT, TEEN, ADMIN


def owned(sid):
    return [m["id"] for m in store.list(sid)]


def sid_of(c):
    return c.cookies.get("p3d_sid")


# ------------------------------------------------------------------------------------------------ CR-2
def test_cr2_removing_a_student_or_deleting_the_class_deletes_their_builds_and_photos():
    t, code, pw = make_class()
    a, b = student(code, pw, "Fox"), student(code, pw, "Owl")
    ba, bb = photo_build(a), photo_build(b)
    sa, sb = sid_of(a), sid_of(b)
    assert (store.dir(ba) / "meta.json").exists()
    src = list(store.dir(ba).glob("source.*"))
    assert src, "the build keeps the student's source photo - that is what must not outlive the student"
    sidp = [x["id"] for x in t.get("/api/classrooms").json()["rooms"][0]["students"] if x["nickname"] == "Fox"][0]
    assert t.delete(f"/api/classrooms/{code}/students/{sidp}").status_code == 200
    assert owned(sa) == [] and not store.dir(ba).exists()
    assert owned(sb) == [bb]                                   # the other student's stuff is untouched
    assert t.delete(f"/api/classrooms/{code}").status_code == 200
    assert owned(sb) == [] and not store.dir(bb).exists()


def test_cr2_student_can_delete_own_data_and_stays_in_the_class():
    t, code, pw = make_class()
    a = student(code, pw, "Fox")
    bid = photo_build(a)
    a.post(f"/api/learn/lessons/{a.get('/api/learn/lessons').json()['lessons'][0]['id']}/steps/0", json={"done": True})
    a.post(f"/api/classrooms/{code}/projects", json={"build_id": bid})
    assert len(t.get(f"/api/classrooms/{code}/projects").json()["projects"]) == 1
    r = a.delete("/api/me/class-data"); assert r.status_code == 200, r.text
    assert r.json()["builds"] == 1 and r.json()["projects"] == 1
    assert owned(sid_of(a)) == [] and not store.dir(bid).exists()
    assert t.get(f"/api/classrooms/{code}/projects").json()["projects"] == []
    assert PROGRESS.read().get(sid_of(a)) is None
    assert a.get("/api/learn/lessons").json()["classroom"]["code"] == code              # still in the class
    assert client().delete("/api/me/class-data").status_code == 404                     # not a student: nothing to erase here


# ------------------------------------------------------------------------------------------------ CR-3
def _publish_one():
    pub = client(ADULT)
    bid = photo_build(pub)
    r = pub.post("/api/showcase", json={"build_id": bid, "title": "Pub", "description": "d", "tags": [], "accept_guidelines": True, "visibility": "public"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_cr3_class_students_cannot_use_showcase_until_the_teacher_turns_it_on_and_likes_are_a_second_switch():
    iid = _publish_one()
    t, code, pw = make_class()
    s = student(code, pw, "Fox")
    stranger = client()
    probes = [("get", "/api/showcase"), ("get", f"/api/showcase/{iid}"), ("get", f"/api/showcase/{iid}/thumb"), ("get", f"/api/showcase/{iid}/files/model.stl"),
              ("post", f"/api/showcase/{iid}/like"), ("post", f"/api/showcase/{iid}/report"), ("get", f"/p/{iid}")]
    for m, u in probes:
        r = getattr(s, m)(u, **({"json": {"reason": "other"}} if m == "post" else {}))
        assert r.status_code == 404, (u, r.status_code)
    assert "turned this off" in s.get("/api/showcase").text
    assert s.get("/api/me").json()["class_showcase"] == {"enabled": False, "likes": False}
    assert stranger.get("/api/showcase").status_code == 200 and stranger.get(f"/p/{iid}").status_code == 200       # non-class visitors unaffected
    assert stranger.get("/api/me").json()["class_showcase"] is None
    # likes cannot be switched on before Showcase
    assert t.put(f"/api/classrooms/{code}/showcase", json={"likes": True}).status_code == 400
    assert s.put(f"/api/classrooms/{code}/showcase", json={"enabled": True}).status_code == 404                 # students can't flip it
    assert t.put(f"/api/classrooms/{code}/showcase", json={"enabled": True}).status_code == 200
    r = s.get("/api/showcase"); assert r.status_code == 200 and any(i["id"] == iid for i in r.json()["items"])
    assert s.get(f"/p/{iid}").status_code == 200
    item = s.get(f"/api/showcase/{iid}").json(); assert item["can_like"] is False
    assert s.post(f"/api/showcase/{iid}/like", json={}).status_code == 403
    assert t.put(f"/api/classrooms/{code}/showcase", json={"likes": True}).status_code == 200
    assert s.get(f"/api/showcase/{iid}").json()["can_like"] is True
    assert s.post(f"/api/showcase/{iid}/like", json={}).status_code == 200
    # turning Showcase off again also turns likes off
    t.put(f"/api/classrooms/{code}/showcase", json={"enabled": False})
    room = t.get("/api/classrooms").json()["rooms"][0]
    assert room["showcase_enabled"] is False and room["likes_enabled"] is False
    assert s.get("/api/showcase").status_code == 404


# ------------------------------------------------------------------------------------------------ CR-4
def test_cr4_seat_reset_lets_the_student_back_in_with_one_time_code_and_keeps_progress_and_builds():
    t, code, pw = make_class()
    old = student(code, pw, "Fox")
    lid = old.get("/api/learn/lessons").json()["lessons"][0]["id"]
    old.post(f"/api/learn/lessons/{lid}/steps/0", json={"done": True})
    bid = photo_build(old)
    old.post(f"/api/classrooms/{code}/projects", json={"build_id": bid})
    new = client()                                                   # cookie dropped / other Chromebook
    assert join(new, code, pw, "Fox").status_code == 400             # still taken, as before
    other = client()
    sidp = [x["id"] for x in t.get("/api/classrooms").json()["rooms"][0]["students"]][0]
    r = t.post(f"/api/classrooms/{code}/students/{sidp}/reset"); assert r.status_code == 200, r.text
    seat = r.json()["seat_code"]; assert re.fullmatch(r"[A-Z2-9]{6}", seat) and r.json()["nickname"] == "Fox"
    # the old session lost the class at once, and its stuff is parked (not visible to it any more)
    assert old.get("/api/learn/lessons").json()["classroom"] is None
    assert old.get(f"/api/classrooms/{code}/projects").status_code == 404
    assert owned(sid_of(old)) == []
    # nobody else can take the seat: no code / wrong code
    assert join(other, code, pw, "Fox").status_code == 400
    assert join(other, code, pw, "Fox", seat_code="AAAAAA").status_code == 400
    # the right code, once
    r = join(new, code, pw, "Fox", seat_code=seat.lower()); assert r.status_code == 200, r.text
    assert r.json().get("seat_restored") is True
    L = {l["id"]: l for l in new.get("/api/learn/lessons").json()["lessons"]}
    assert L[lid]["done_steps"] == 1                                 # progress inherited
    assert len(owned(sid_of(new))) == 1                             # builds inherited
    assert new.get(f"/api/classrooms/{code}/projects").json()["projects"][0]["student"] == "Fox"
    assert join(client(), code, pw, "Fox", seat_code=seat).status_code == 400    # the code works exactly once
    assert owned(sid_of(old)) == []


def test_cr4_five_wrong_seat_codes_kill_the_code_and_it_expires():
    t, code, pw = make_class()
    student(code, pw, "Fox")
    sidp = t.get("/api/classrooms").json()["rooms"][0]["students"][0]["id"]
    seat = t.post(f"/api/classrooms/{code}/students/{sidp}/reset").json()["seat_code"]
    for _ in range(classrooms.SEAT_TRIES):
        assert join(client(), code, pw, "Fox", seat_code="ZZZZZZ").status_code == 400
    assert join(client(), code, pw, "Fox", seat_code=seat).status_code == 400            # dead now
    again = t.post(f"/api/classrooms/{code}/students/fox/reset"); assert again.status_code == 200      # teacher re-issues for the waiting seat (by nickname)
    assert join(client(), code, pw, "Fox", seat_code=again.json()["seat_code"]).status_code == 200


def test_cr4_expired_seat_code_is_refused(monkeypatch):
    t, code, pw = make_class()
    student(code, pw, "Fox")
    sidp = t.get("/api/classrooms").json()["rooms"][0]["students"][0]["id"]
    seat = t.post(f"/api/classrooms/{code}/students/{sidp}/reset").json()["seat_code"]
    real = classrooms.time.time
    monkeypatch.setattr(classrooms.time, "time", lambda: real() + classrooms.SEAT_TTL + 60)
    assert join(client(), code, pw, "Fox", seat_code=seat).status_code == 400


def test_cr4_removing_a_waiting_seat_erases_what_was_parked_and_students_cannot_reset_seats():
    t, code, pw = make_class()
    a = student(code, pw, "Fox"); bid = photo_build(a)
    sidp = t.get("/api/classrooms").json()["rooms"][0]["students"][0]["id"]
    assert a.post(f"/api/classrooms/{code}/students/{sidp}/reset").status_code == 404
    t.post(f"/api/classrooms/{code}/students/{sidp}/reset")
    assert (store.dir(bid) / "meta.json").exists()
    assert t.delete(f"/api/classrooms/{code}/students/fox").status_code == 200
    assert not store.dir(bid).exists()
    assert join(client(), code, pw, "Fox").status_code == 200                              # nickname free again


def test_cr4_shared_computer_join_sets_a_session_cookie_without_expiry():
    t, code, pw = make_class()
    s = client()
    r = join(s, code, pw, "Fox", shared_computer=True); assert r.status_code == 200
    cookies = [h for h in r.headers.get_list("set-cookie") if h.startswith("p3d_sid=")]
    assert len(cookies) == 1 and "max-age" not in cookies[0].lower() and "expires" not in cookies[0].lower(), cookies
    s2 = client()
    r = join(s2, code, pw, "Owl")
    c2 = [h for h in r.headers.get_list("set-cookie") if h.startswith("p3d_sid=")]
    assert c2 and "max-age" in c2[0].lower()                                                 # normal join keeps the long cookie
