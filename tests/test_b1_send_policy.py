"""SEND-1: who may get a build OUT of ZEIM (design-ios-send.md 2.2), enforced on the server.
Download always; class students also 'send to my teacher'; share/printer/slicer links only for adults; a class switch
(default OFF) can additionally allow 13+ signed-in students to share; under-13 / unknown-age never."""
import logging
import pytest
from app import config
from tests import b1
from tests.b1 import client, photo_build, make_class, join, student, ADULT, TEEN


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://zeim.example.org")


def caps(c):
    return c.get("/api/me").json()["send"]


def test_adult_gets_everything_teen_and_unknown_get_download_only(shared):
    a, t, anon = client(ADULT), client(TEEN), client()
    assert caps(a) == {"download": True, "teacher": False, "share": True, "printer": True, "links": True, "role": "adult"}
    for c, role in ((t, "teen"), (anon, "teen")):          # visitors who have not passed the age gate count as teens
        k = caps(c)
        assert k["role"] == role and k["download"] and not (k["share"] or k["printer"] or k["links"] or k["teacher"])


def test_class_student_default_off_download_and_teacher_only(shared):
    teacher, code, pw = make_class()
    s = student(code, pw, "Kiwi")
    k = caps(s)
    assert k["role"] == "student" and k["download"] and k["teacher"] and not (k["share"] or k["printer"] or k["links"])


def test_switch_on_allows_share_for_13plus_account_but_never_for_unknown_age(shared):
    teacher, code, pw = make_class()
    anon_student = student(code, pw, "Kiwi")
    teen_student = client(TEEN); assert join(teen_student, code, pw, "Mango").status_code == 200
    r = teacher.put(f"/api/classrooms/{code}/send", json={"enabled": True, "confirm": True}); assert r.status_code == 200
    assert caps(teen_student)["share"] is True and caps(teen_student)["teacher"] is True
    assert caps(teen_student)["links"] is False and caps(teen_student)["printer"] is False
    assert caps(anon_student)["share"] is False                    # no account = unknown age = treated as under 13, even with the switch on


def test_forged_requests_from_students_teens_and_unknown_are_refused(shared):
    a = client(ADULT); bid = photo_build(a)
    assert a.get(f"/api/print/{bid}/links").status_code == 200
    teacher, code, pw = make_class()
    teacher.put(f"/api/classrooms/{code}/send", json={"enabled": True, "confirm": True})
    stud = student(code, pw, "Kiwi")
    sb = photo_build(stud)
    teen, anon = client(TEEN), client()
    tb, ab = photo_build(teen), photo_build(anon)
    for c, b in ((stud, sb), (teen, tb), (anon, ab)):               # even with the class switch ON and own builds
        assert c.get(f"/api/print/{b}/links").status_code == 403
        assert c.post(f"/api/send/{b}", data={"printer_id": "x"}).status_code == 403
        assert c.get(f"/files/{b}/model.3mf").status_code == 200       # Download still works


def test_teacher_switch_default_off_persists_needs_confirm_and_is_teacher_only(shared):
    teacher, code, pw = make_class()
    row = lambda: [r for r in teacher.get("/api/classrooms").json()["rooms"] if r["code"] == code][0]
    assert row()["send_enabled"] is False
    assert teacher.put(f"/api/classrooms/{code}/send", json={"enabled": True}).status_code == 400     # no confirm
    assert row()["send_enabled"] is False
    assert student(code, pw, "Kiwi").put(f"/api/classrooms/{code}/send", json={"enabled": True, "confirm": True}).status_code == 404
    assert client(ADULT).put(f"/api/classrooms/{code}/send", json={"enabled": True, "confirm": True}).status_code == 404
    assert teacher.put(f"/api/classrooms/{code}/send", json={"enabled": True, "confirm": True}).status_code == 200
    assert row()["send_enabled"] is True and row()["send_changed"]
    assert teacher.put(f"/api/classrooms/{code}/send", json={"enabled": False}).status_code == 200
    assert row()["send_enabled"] is False


def test_switch_log_has_class_and_time_but_no_student_names(shared, caplog):
    teacher, code, pw = make_class()
    student(code, pw, "SecretNickname")
    with caplog.at_level(logging.INFO, logger="zeim.audit"):
        logging.getLogger("zeim.audit").propagate = True
        teacher.put(f"/api/classrooms/{code}/send", json={"enabled": True, "confirm": True})
    msgs = " ".join(r.getMessage() for r in caplog.records if r.name == "zeim.audit")
    assert code in msgs and "enabled=True" in msgs and "SecretNickname" not in msgs and "Ada" not in msgs


def test_local_mode_owner_keeps_working_but_minors_and_students_still_blocked(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")
    anon = client(); bid = photo_build(anon)
    assert caps(anon)["role"] == "adult" and anon.get("/api/print/" + bid + "/links").status_code == 200
    teen = client(TEEN); tb = photo_build(teen)
    assert teen.get(f"/api/print/{tb}/links").status_code == 403


def test_sharetest_page_is_hidden_adult_only_and_labelled_untested(shared):
    c = client()
    r = c.get("/sharetest")
    assert r.status_code == 200 and "UNTESTED" in r.text and "noindex" in r.headers["x-robots-tag"]
    assert "sharetest" not in open("static/index.html").read()                    # not linked from the app
    assert c.get("/api/sharetest/file.stl").status_code == 403                      # visitors/teens: no
    assert client(TEEN).get("/api/sharetest/file.3mf").status_code == 403
    a = client(ADULT)
    for fmt in ("stl", "obj", "3mf"):
        f = a.get(f"/api/sharetest/file.{fmt}"); assert f.status_code == 200 and len(f.content) > 100
    assert a.get("/api/sharetest/file.exe").status_code == 404
