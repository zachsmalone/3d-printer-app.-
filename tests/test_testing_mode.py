"""ZEIM_TESTING_MODE: lifts usage quotas/cooldowns; security limits and paid spend stay on."""
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import config
from app.community.identity import Actor
from app.core import ratelimit
from app.services import ai3d, uploadgate
from tests.b1 import client, ADULT

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    ratelimit.reset(); monkeypatch.setattr(config, "STORAGE_MODE", "json"); monkeypatch.setattr(config, "UPLOADS_PER_HOUR", 10)
    yield
    ratelimit.reset()


def test_default_is_off():
    import os
    assert os.environ.get("ZEIM_TESTING_MODE") in (None, "", "0") and config.TESTING_MODE is False
    assert os.environ.get("ZEIM_TESTING_ALLOW_PAID") in (None, "", "0") and config.TESTING_ALLOW_PAID is False
    assert config.testing_mode_notice() is None
    for name in (".env.example", ".env.production.example", ".env.staging.example"):
        text = (ROOT / name).read_text()
        assert "ZEIM_TESTING_MODE=0" in text
        assert "ZEIM_TESTING_MODE=1" not in text
    compose = (ROOT / "reports/deploy/docker-compose.yml").read_text()
    assert "ZEIM_TESTING_MODE: ${ZEIM_TESTING_MODE:-0}" in compose
    assert "ZEIM_TESTING_ALLOW_PAID: ${ZEIM_TESTING_ALLOW_PAID:-0}" in compose


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
    assert 'id="accTestingMode" hidden' in html and "CFG.testing_mode" in js
    assert "Testing mode is on for this server." in html
    assert "Sign-in limits, upload scanning, and payments stay on." in html
    assert "unlimited" not in html.lower()
    tab = open("static/ai3d.js").read()
    assert "no limits or pauses" not in tab
    assert "The pause between models is off." in tab


def test_notice_names_what_stays_on(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", False)
    line = config.testing_mode_notice()
    assert line and "ZEIM_TESTING_MODE is on" in line
    assert "Password guesses" in line and "payments stay on" in line
    assert "daily model cap is still on" in line
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)
    assert "daily model cap is off" in config.testing_mode_notice()


@pytest.mark.parametrize("on", [False, True])
def test_collection_hourly_cap(monkeypatch, on):
    monkeypatch.setattr(config, "TESTING_MODE", on)
    real = ratelimit.hit
    monkeypatch.setattr(ratelimit, "hit", lambda k, *a, **kw: False if k.startswith("col:") else real(k, *a, **kw))
    r = client(ADULT).post("/api/me/collections", json={"name": f"TmCap{int(on)}"})
    assert (r.status_code == 429) is (not on)


@pytest.mark.parametrize("on", [False, True])
def test_feedback_hourly_cap(monkeypatch, on):
    monkeypatch.setattr(config, "TESTING_MODE", on)
    real = ratelimit.hit
    monkeypatch.setattr(ratelimit, "hit", lambda k, *a, **kw: False if k.startswith("feedback:") else real(k, *a, **kw))
    r = client().post("/api/feedback", json={"message": "A note from the testing-mode check."})
    assert (r.status_code == 429) is (not on)


@pytest.mark.parametrize("on", [False, True])
def test_tip_label_hourly_cap(monkeypatch, on):
    monkeypatch.setattr(config, "TESTING_MODE", on)
    from app.api.community import _label_limit
    real = ratelimit.hit
    monkeypatch.setattr(ratelimit, "hit", lambda k, *a, **kw: False if k.startswith("tipai:") else real(k, *a, **kw))
    actor = Actor(sid="tm-label", user={"id": "tm-user"})
    if on:
        _label_limit(actor)
    else:
        with pytest.raises(HTTPException) as ei:
            _label_limit(actor)
        assert ei.value.status_code == 429


def test_ai3d_pause_lifts_and_daily_cap_stays_until_allow_paid(monkeypatch):
    monkeypatch.setattr(config, "ai3d_enabled", lambda: True)
    monkeypatch.setattr(config, "AI3D_PRO_ONLY", False)
    monkeypatch.setattr(config, "AI3D_DAILY_CAP", 5)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_MIN", 5)
    monkeypatch.setattr(config, "AI3D_COOLDOWN_STEP_MIN", 0)
    monkeypatch.setattr(config, "TESTING_MODE", False)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)   # does nothing unless testing mode is also on
    ai3d.reset()

    class A:
        sid = "tm-ai3d"
        user = {"plan": "free"}

    now = time.time()
    ai3d.mark_done(A, now=now)
    held = ai3d.plan(A)
    assert held["allowed"] is False and held["reason"] == "cooldown" and held["testing_mode"] is False

    monkeypatch.setattr(config, "TESTING_MODE", True)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", False)
    monkeypatch.setattr(config, "AI3D_DAILY_CAP", 1)
    paused = ai3d.plan(A)
    assert paused["testing_mode"] is True and paused["allow_paid"] is False
    assert paused["wait_s"] == 0 and paused["allowed"] is False and paused["reason"] == "cap"
    assert paused["cap"] == 1

    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)
    open_cap = ai3d.plan(A)
    assert open_cap["allowed"] is True and open_cap["cap"] == 0 and open_cap["allow_paid"] is True
    ai3d.reset()


def test_password_guesses_stay_limited_in_testing_mode(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)
    from app.auth.config import Limits
    from app.auth.errors import AuthError, RateLimited
    from tests.auth_helpers import make_service
    svc = make_service(limits=Limits(password_login_fail_ip=(2, 900)))
    svc.password_register("Sam", "1990-05-01", "TmGuess", "correct horse battery", None, "ua", "1.1.1.1")
    for _ in range(2):
        with pytest.raises(AuthError):
            svc.password_login("TmGuess", "wrong password", "ua", "9.9.9.9")
    with pytest.raises(RateLimited) as ei:
        svc.password_login("TmGuess", "wrong password", "ua", "9.9.9.9")
    assert ei.value.status == 429


def test_malware_scan_still_refuses_in_testing_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TESTING_MODE", True)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)
    monkeypatch.setattr(uploadgate, "AUDIT_LOG", tmp_path / "uploads.log.jsonl")
    monkeypatch.setattr(uploadgate, "scan_bytes", lambda data: (False, "Eicar-Test-Signature", "infected"))
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.effect_mandelbrot((32, 32), (-2, -1.5, 1, 1.5), 20).convert("RGB").save(buf, "PNG")
    with pytest.raises(uploadgate.GateError) as ei:
        uploadgate.gate(buf.getvalue(), "sid-tm")
    assert ei.value.status == 415


def test_report_limit_stays_on_in_testing_mode(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)
    monkeypatch.setattr(config, "REPORT_LIMIT_PER_MIN", 2)
    from app.api.community import report_limit
    actor = Actor(sid="tm-report", user={"id": "tm-report"})
    req = Request({"type": "http", "headers": [], "client": ("8.8.4.4", 1)})
    report_limit(req, actor)
    report_limit(req, actor)
    with pytest.raises(HTTPException) as ei:
        report_limit(req, actor)
    assert ei.value.status_code == 429


def test_testing_mode_does_not_open_checkout(monkeypatch):
    monkeypatch.setattr(config, "TESTING_MODE", True)
    monkeypatch.setattr(config, "TESTING_ALLOW_PAID", True)
    monkeypatch.setenv("ZEIM_PLANS_ENABLED", "1")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
    from app.services import subscriptions as subs
    assert subs.payment_live() is False
    r = client(ADULT).post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout"] is False
    assert "url" not in body
    assert "nothing was charged" in r.text.lower() or "not live" in r.text.lower()
    assert "sk_test" not in r.text
