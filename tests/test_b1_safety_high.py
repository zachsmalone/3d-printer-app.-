"""Trust & Safety HIGH items: S-04 age gate (B-04), S-05 class-join guessing (B-05), S-02 text-length caps (B-02)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from app import config
from app.community import classrooms, safety
from app.community.store import USERS, AGE_BLOCKS
from tests.b1 import *

NEUTRAL_BAD = ("13", "thirteen", "age", "old enough", "young", "under")


# ---------------------------------------------------------------- S-04 age gate
def test_s04_age_gate_is_neutral_and_locks_the_session():
    c = TestClient(app)
    r = c.post("/api/me/signup", json={"display_name": "Kid", "dob": "2018-01-01"})
    assert r.status_code == 403
    text = r.text.lower()
    assert not any(w in text for w in NEUTRAL_BAD) and "class code" in text            # no threshold; points to the classroom route
    # retry in the same browser session with a different DOB: refused with the SAME neutral answer, nothing stored
    r2 = c.post("/api/me/signup", json={"display_name": "Kid", "dob": "2000-01-01"})
    assert r2.status_code == 403 and r2.json() == r.json()
    assert c.get("/api/me").json()["signed_up"] is False
    assert not any(u.get("display_name") == "Kid" for u in USERS.read().values())
    # same after the session cookie is dropped but the marker cookie stays (same device)
    d = TestClient(app); d.cookies.set("p3d_ag", c.cookies.get("p3d_ag"))
    assert d.post("/api/me/signup", json={"display_name": "Kid", "dob": "2000-01-01"}).status_code == 403
    # a different browser is unaffected (and an adult DOB works there)
    assert client(ADULT).get("/api/me").json()["signed_up"] is True


def test_s04_dob_never_stored_before_passing_and_lock_expires(monkeypatch):
    c = TestClient(app)
    c.post("/api/me/signup", json={"display_name": "Kid", "dob": "2017-05-05"})
    blob = json.dumps(USERS.read()) + json.dumps(AGE_BLOCKS.read()) + "".join(p.read_text() for p in config.DATA.glob("*.json"))
    assert "2017-05-05" not in blob
    real = time.time; monkeypatch.setattr(time, "time", lambda: real() + (config.AGE_LOCK_HOURS + 1) * 3600)
    c.cookies.delete("p3d_ag")
    assert c.post("/api/me/signup", json={"display_name": "Grown", "dob": "1990-01-01"}).status_code == 200


def test_s04_threshold_not_exposed_in_config_or_ui():
    assert "min_signup_age" not in client().get("/api/config").json()
    js = (config.STATIC / "community.js").read_text()
    assert "min_signup_age" not in js and "must be <b>" not in js


def test_s04_signup_attempts_rate_limited(monkeypatch):
    monkeypatch.setattr(config, "SIGNUP_ATTEMPTS_PER_HOUR_IP", 4)
    codes = [TestClient(app).post("/api/me/signup", json={"display_name": "x", "dob": "bad"}).status_code for _ in range(6)]
    assert codes[:4] == [400] * 4 and codes[4:] == [429, 429]


# ---------------------------------------------------------------- S-05 join guessing
def test_s05_guesses_limited_per_class_and_address_not_per_cookie():
    t, code, pw = make_class()
    codes = [join(TestClient(app), code, f"wrong-guess-{n}", "Robo9").status_code for n in range(8)]       # NEW cookie every time
    assert codes[:5] == [404] * 5 and codes[5] == 404 and codes[6:] == [429] * 2, codes                      # slow mode: one check per window, the rest are not evaluated
    assert t.get("/api/classrooms").json()["rooms"][0]["failed_joins_last_hour"] >= 5                      # teacher can see it happened
    classrooms._LOCKS.clear()


def test_s05_slow_mode_never_locks_the_class_out_the_right_password_gets_in(monkeypatch):
    """Kenji re-check: one prankster on a shared school address must not lock the class out."""
    t, code, pw = make_class()
    for n in range(5): join(TestClient(app), code, f"bad-guess-{n}", "Zed7")
    assert 0 < classrooms._locked_for(code, "testclient") <= classrooms.SLOW_BASE
    assert classrooms._locked_for(code, "10.9.9.9") == 0                                                    # other addresses unaffected
    assert join(TestClient(app), code, pw, "Zed7").status_code == 200                                        # Edge 5: the first check in slow mode is evaluated, so the RIGHT password gets in at once
    assert classrooms._locked_for(code, "testclient") == 0                                                   # and the slow-down is gone for the next student
    assert join(TestClient(app), code, pw, "Zed8").status_code == 200


def test_s05_a_student_with_the_right_password_gets_in_even_while_a_prankster_keeps_the_address_in_slow_mode(monkeypatch):
    """Same school address: wrong guesses are limited to one check per LOCKED_CHECK_S, but a correct password is never refused outright."""
    t, code, pw = make_class()
    for n in range(5): join(TestClient(app), code, f"bad-guess-{n}", "Zed7")
    assert join(TestClient(app), code, "still-wrong-1", "Zed7").status_code == 404                           # evaluated (and counted)
    assert join(TestClient(app), code, "still-wrong-2", "Zed7").status_code == 429                          # a second guess inside the window is not evaluated at all
    real = time.time; monkeypatch.setattr(time, "time", lambda: real() + classrooms.LOCKED_CHECK_S + 1)
    assert join(TestClient(app), code, pw, "Zed9").status_code == 200                                        # the student types the right password: in, within ~30 s
    assert classrooms._locked_for(code, "testclient") == 0


def test_s05_slow_mode_keeps_guessing_slow_and_backs_off(monkeypatch):
    t, code, pw = make_class()
    for n in range(5): join(TestClient(app), code, f"bad-guess-{n}", "Zed7")
    real = time.time; offset = [0]; monkeypatch.setattr(time, "time", lambda: real() + offset[0])
    waits = []
    for n in range(5):                                                                                       # an attacker who guesses at every slot
        offset[0] += classrooms._locked_for(code, "testclient") + 1
        assert join(TestClient(app), code, f"bad-again-{n}", "Zed7").status_code == 404                     # evaluated (wrong) ...
        waits.append(round(classrooms._locked_for(code, "testclient")))                                            # ... and the next slot is further away
    assert waits == sorted(waits) and waits[-1] <= classrooms.SLOW_MAX + 1 and waits[-1] > classrooms.SLOW_BASE * 3
    classrooms._LOCKS.clear()


def test_s05_teacher_can_unlock_joining_only_their_own_class():
    t, code, pw = make_class()
    for n in range(5): join(TestClient(app), code, f"bad-guess-{n}", "Zed7")
    assert join(TestClient(app), code, "wrong-once", "Zed7").status_code == 404
    assert join(TestClient(app), code, pw, "Zed7").status_code == 429                                          # inside the 30 s check window
    assert client(ADULT).post(f"/api/classrooms/{code}/unlock-joins").status_code == 404                    # another adult can't
    assert t.post(f"/api/classrooms/{code}/unlock-joins").status_code == 200
    assert join(TestClient(app), code, pw, "Zed7").status_code == 200
    assert t.get("/api/classrooms").json()["rooms"][0]["failed_joins_last_hour"] == 0


def test_s05_a_student_already_in_the_class_is_never_slowed_down():
    t, code, pw = make_class()
    s = student(code, pw, "Kiwi9")
    for n in range(5): join(TestClient(app), code, f"bad-guess-{n}", "Zed7")
    assert join(s, code, pw, "Kiwi9x").status_code == 200                                                    # same session, same class: rename works during slow mode
    classrooms._LOCKS.clear()


def test_s05_unknown_class_and_wrong_password_look_the_same():
    t, code, pw = make_class()
    a = join(TestClient(app), code, "nope-nope-1", "Pip11"); b = join(TestClient(app), "ZZZZZZ", "nope-nope-1", "Pip11")
    assert a.status_code == b.status_code == 404 and a.text == b.text
    classrooms._LOCKS.clear()


def test_s05_password_minimum_and_weak_list():
    t = client(ADULT)
    for bad in ("abc", "1234567", "password", "12345678", "aaaaaaaa", "x" * 65):
        assert t.post("/api/classrooms", json={"name": "P", "password": bad}).status_code == 400, bad
    assert t.post("/api/classrooms", json={"name": "P", "password": "plum-otter-42"}).status_code == 200


# ---------------------------------------------------------------- S-02 length caps
def _timed(fn):
    t0 = time.time(); r = fn(); return r, time.time() - t0


BIG = "a" * 100_000


def test_s02_long_text_rejected_fast_everywhere():
    a = client(ADULT); bid = photo_build(a)
    t, code, pw = make_class(a); s = student(code, pw, "Quill")
    pid = s.post(f"/api/classrooms/{code}/projects", json={"build_id": photo_build(s), "title": "P"}).json()["id"]
    cases = [
        ("signup", lambda: TestClient(app).post("/api/me/signup", json={"display_name": BIG, "dob": "1990-01-01"})),
        ("publish title", lambda: a.post("/api/showcase", json={"build_id": bid, "title": BIG, "accept_guidelines": True})),
        ("publish desc", lambda: a.post("/api/showcase", json={"build_id": bid, "title": "T", "description": BIG, "accept_guidelines": True})),
        ("publish tag", lambda: a.post("/api/showcase", json={"build_id": bid, "title": "T", "tags": [BIG], "accept_guidelines": True})),
        ("report details", lambda: a.post("/api/showcase/zo-pencil-cup/report", json={"reason": "other", "details": BIG})),
        ("class name", lambda: a.post("/api/classrooms", json={"name": BIG, "password": "plum-otter-42"})),
        ("class password", lambda: a.post("/api/classrooms", json={"name": "N", "password": BIG})),
        ("join nickname", lambda: join(client(), code, pw, BIG)),
        ("join password", lambda: join(client(), code, BIG, "Kiwi5")),
        ("feedback", lambda: t.post(f"/api/classrooms/{code}/projects/{pid}/feedback", json={"comment": BIG})),
        ("links", lambda: a.put("/api/me/links", json={"instagram": BIG})),
        ("build title", lambda: gen(a, title=BIG)),
        ("edit title", lambda: a.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")}, data={"title": BIG})),
    ]
    for name, fn in cases:
        r, dt = _timed(fn)
        assert r.status_code in (400, 413, 422) and dt < 1.5, (name, r.status_code, dt)


def test_s02_scan_itself_refuses_long_text_quickly_and_email_pattern_is_bounded():
    for payload in ("a" * 20000, "a@" * 10000, "1 " * 10000, "a." * 10000):
        r, dt = _timed(lambda: safety.scan(payload))
        assert r == "too_long" and dt < 0.2
    r, dt = _timed(lambda: safety.scan("a" * 1900)); assert dt < 0.5                       # worst plausible allowed input
    with pytest.raises(safety.ChatBlocked) as e: safety.check("x" * 5000, "t")
    assert e.value.status == 413


def test_s02_big_json_body_refused_before_parsing():
    c = client()
    big = json.dumps({"x": "y" * 400_000})
    r = c.post("/api/classrooms/join", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_s02_normal_text_still_works():
    a = client(ADULT); bid = photo_build(a)
    r = a.post("/api/showcase", json={"build_id": bid, "title": "T" * 80, "description": "d" * 500, "tags": ["x" * 30] * 8, "accept_guidelines": True})
    assert r.status_code == 200, r.text
