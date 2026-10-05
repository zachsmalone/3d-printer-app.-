"""Teacher Live view (view-only roster). What the app stores per student: ticked steps per lesson (+ a last-tick time added for this), their builds
(title + created), joined time, and canned 'I need help' requests. NOT stored: a 'current step' pointer, per-page activity, thumbnails in the roster."""
import json
from datetime import datetime
from tests.b1 import client, make_class, student, photo_build, ADULT

KEYS = {"id", "nickname", "lesson", "model", "last_active", "hand"}


def _lid(c):
    return c.get("/api/learn/lessons").json()["lessons"][0]["id"]


def test_roster_has_only_the_agreed_fields_and_never_a_photo():
    t, code, pw = make_class()
    a = student(code, pw, "Fox"); photo_build(a)
    r = t.get(f"/api/classrooms/{code}/live"); assert r.status_code == 200
    rows = r.json()["students"]
    assert len(rows) == 1 and set(rows[0]) == KEYS and set(rows[0]["lesson"]) == {"title", "done_steps", "steps"}
    raw = r.text.lower()
    for bad in ("thumb", "source", "dob", "email", ".png", ".jpg", "ip"):
        assert bad not in raw.replace("steps", "").replace("description", ""), bad
    assert rows[0]["model"] and len(rows[0]["model"]) <= 40


def test_step_progress_and_last_activity_follow_what_the_student_ticks():
    t, code, pw = make_class()
    a = student(code, pw, "Fox"); lid = _lid(a)
    before = t.get(f"/api/classrooms/{code}/live").json()["students"][0]
    assert before["lesson"]["done_steps"] == 0
    a.post(f"/api/learn/lessons/{lid}/steps/0", json={"done": True}); a.post(f"/api/learn/lessons/{lid}/steps/1", json={"done": True})
    after = t.get(f"/api/classrooms/{code}/live").json()["students"][0]
    assert after["lesson"]["done_steps"] == 2 and after["lesson"]["steps"] >= 2
    assert datetime.fromisoformat(after["last_active"]) >= datetime.fromisoformat(before["last_active"])


def test_only_the_teacher_who_owns_the_class_can_read_it():
    t, code, pw = make_class(); a = student(code, pw, "Fox")
    other, _, _ = make_class(name="Other")
    assert other.get(f"/api/classrooms/{code}/live").status_code == 404          # another teacher
    assert a.get(f"/api/classrooms/{code}/live").status_code == 404              # a student of that class
    assert client().get(f"/api/classrooms/{code}/live").status_code == 404       # anonymous
    assert t.get("/api/classrooms/NOPE00/live").status_code == 404
    sid = t.get(f"/api/classrooms/{code}/live").json()["students"][0]["id"]
    assert other.post(f"/api/classrooms/{code}/students/{sid}/helped").status_code == 404
    assert a.post(f"/api/classrooms/{code}/students/{sid}/helped").status_code == 404


def test_hand_raise_uses_the_canned_request_and_the_teacher_clears_it_without_reordering_rows():
    t, code, pw = make_class()
    a, b, c = student(code, pw, "Ant"), student(code, pw, "Bee"), student(code, pw, "Cat")
    order = [r["nickname"] for r in t.get(f"/api/classrooms/{code}/live").json()["students"]]
    assert sorted(order) == ["Ant", "Bee", "Cat"] and not any(r["hand"] for r in t.get(f"/api/classrooms/{code}/live").json()["students"])
    assert c.post(f"/api/classrooms/{code}/requests", json={"kind": "need_help"}).status_code == 200
    rows = t.get(f"/api/classrooms/{code}/live").json()["students"]
    assert [r["nickname"] for r in rows] == order                                   # same order after a hand goes up
    assert [r["nickname"] for r in rows if r["hand"]] == ["Cat"]
    sid = [r["id"] for r in rows if r["hand"]][0]
    assert t.post(f"/api/classrooms/{code}/students/{sid}/helped").status_code == 200
    rows = t.get(f"/api/classrooms/{code}/live").json()["students"]
    assert [r["nickname"] for r in rows] == order and not any(r["hand"] for r in rows)
    r = c.post(f"/api/classrooms/{code}/requests", json={"kind": "make up my own words"}); assert r.status_code == 400        # free text is not possible


def test_removing_a_student_or_the_class_removes_them_from_the_roster_and_their_activity():
    from app.community.store import PROGRESS
    t, code, pw = make_class(); a = student(code, pw, "Fox"); lid = _lid(a)
    a.post(f"/api/learn/lessons/{lid}/steps/0", json={"done": True})
    sid = t.get(f"/api/classrooms/{code}/live").json()["students"][0]["id"]
    assert t.delete(f"/api/classrooms/{code}/students/{sid}").status_code == 200
    assert t.get(f"/api/classrooms/{code}/live").json()["students"] == []
    assert not [k for k in PROGRESS.read() if k.startswith(sid)]


def test_students_are_told_what_the_teacher_can_see():
    t, code, pw = make_class(); a = student(code, pw, "Fox")
    n = a.get("/api/learn/lessons").json()["classroom"]["notice"]
    assert "nickname" in n and "lesson step" in n and "model's name" in n and "cannot see your photos" in n
