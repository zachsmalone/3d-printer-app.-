"""ZEIM_TESTING_MODE: lifts usage quotas/cooldowns for everyone; security limits stay on."""
import time
import pytest
from app import config
from app.core import ratelimit
from app.services import uploadgate
from tests.b1 import client, ADULT


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ratelimit.reset(); monkeypatch.setattr(config, "STORAGE_MODE", "json"); monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 10)
    yield
    ratelimit.reset()


def test_default_is_off():
    import importlib, os
    assert os.environ.get("ZEIM_TESTING_MODE") in (None, "", "0") and config.TESTING_MODE is False


def _uploads(n, sid):
    now = time.time()
    return [uploadgate._allowed(sid, now) for _ in range(n)]


def test_off_upload_quota_is_ten_per_hour(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", False)
    got = _uploads(11, "s-off"); assert all(got[:10]) and got[10] is False


def test_on_upload_quota_lifted(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True)
    assert all(_uploads(50, "s-on"))


@pytest.mark.parametrize("on", [False, True])
def test_config_exposes_flag(monkeypatch, on):
    monkeypatch.setattr(config, "TESTING_MODE", on)
    assert client().get("/api/config").json()["testing_mode"] is on


@pytest.mark.parametrize("on", [False, True])
def test_rename_wait(monkeypatch, on):
    monkeypatch.setattr(config, "TESTING_MODE", on)
    a = client(ADULT)
    assert a.put("/api/me/username", json={"username": f"Tm_First_{int(on)}"}).status_code == 200
    assert a.put("/api/me/username", json={"username": f"Tm_Second_{int(on)}"}).status_code == (200 if on else 429)


@pytest.mark.parametrize("on", [False, True])
def test_doctor_hourly_cap(monkeypatch, on):
    monkeypatch.setattr(config, "TESTING_MODE", on)
    real = ratelimit.hit
    monkeypatch.setattr(ratelimit, "hit", lambda k, *a, **kw: False if k.startswith("doctor") else real(k, *a, **kw))
    r = client().post("/api/doctor/diagnose", data={"problems": "", "text": "stringing"})
    assert (r.status_code == 429) is (not on)


def test_security_limits_stay_on_in_testing_mode(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True); monkeypatch.setattr(config, "ADMIN_TOKEN", "right-token")
    from app.api import guards
    from starlette.requests import Request
    req = lambda t: Request({"type": "http", "headers": [(b"x-admin-token", t.encode())], "client": ("9.9.9.9", 1)})
    for _ in range(config.ADMIN_FAIL_LIMIT):
        assert guards.is_admin(req("wrong")) is False
    with pytest.raises(Exception):
        guards.is_admin(req("right-token"))
    monkeypatch.setattr(config, "SIGNUP_ATTEMPTS_PER_HOUR_IP", 0)
    assert client().post("/api/me/signup", json=ADULT).status_code == 429


def test_account_note_present():
    html = open("static/index.html").read(); js = open("static/community.js").read()
    assert 'id="accTestingMode" hidden' in html and "Testing mode: limits off" in html and "CFG.testing_mode" in js
