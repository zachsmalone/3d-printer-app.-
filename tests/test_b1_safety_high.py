"""Trust & Safety HIGH items: S-04 age gate (B-04), S-02 text-length caps (B-02)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from app import config
from app.community import safety
from app.community.store import USERS, AGE_BLOCKS
from tests.b1 import *

NEUTRAL_BAD = ("13", "thirteen", "age", "old enough", "young", "under")


# ---------------------------------------------------------------- S-04 age gate
def test_s04_age_gate_is_neutral_and_locks_the_session():
    c = TestClient(app)
    r = c.post("/api/me/signup", json={"display_name": "Kid", "dob": "2018-01-01"})
    assert r.status_code == 403
    text = r.text.lower()
    assert not any(w in text for w in NEUTRAL_BAD) and "without an account" in text    # no threshold; points to using ZEIM without an account
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






# ---------------------------------------------------------------- S-02 length caps
def _timed(fn):
    t0 = time.time(); r = fn(); return r, time.time() - t0


BIG = "a" * 100_000


def test_s02_long_text_rejected_fast_everywhere():
    a = client(ADULT); bid = photo_build(a)
    cases = [
        ("signup", lambda: TestClient(app).post("/api/me/signup", json={"display_name": BIG, "dob": "1990-01-01"})),
        ("publish title", lambda: a.post("/api/showcase", json={"build_id": bid, "title": BIG, "accept_guidelines": True, "nsfw": False})),
        ("publish desc", lambda: a.post("/api/showcase", json={"build_id": bid, "title": "T", "description": BIG, "accept_guidelines": True, "nsfw": False})),
        ("publish tag", lambda: a.post("/api/showcase", json={"build_id": bid, "title": "T", "tags": [BIG], "accept_guidelines": True, "nsfw": False})),
        ("report details", lambda: a.post("/api/showcase/zo-pencil-cup/report", json={"reason": "other", "details": BIG})),
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
    r = c.post("/api/me/signup", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_s02_normal_text_still_works():
    a = client(ADULT); bid = photo_build(a)
    r = a.post("/api/showcase", json={"build_id": bid, "title": "T" * 80, "description": "d" * 500, "tags": ["x" * 30] * 8, "accept_guidelines": True, "nsfw": False})
    assert r.status_code == 200, r.text
