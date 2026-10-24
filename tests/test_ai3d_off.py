"""2D→3D (TripoSR) is off unless ZEIM_2D3D_ENABLED=1. Core tools stay usable."""
from __future__ import annotations

import pytest

from app import config
from app.services import ai3d
from tests.b1 import ADULT, SAMPLE, client, gen


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    ai3d.reset()
    monkeypatch.setenv("ZEIM_2D3D_ENABLED", "0")
    monkeypatch.setattr(config, "AI3D_FAKE", True)
    monkeypatch.setattr(config, "TESTING_MODE", True)
    yield
    ai3d.reset()


def _post(c):
    return c.post(
        "/api/ai3d/jobs",
        files={"file": ("s.png", open(SAMPLE, "rb").read(), "image/png")},
        data={"mode": "figure", "photo_ack": "true", "title": "Tango"},
    )


def test_jobs_do_not_run_when_disabled(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("the 2D to 3D engine must not run")

    monkeypatch.setattr(ai3d, "engine_call", boom)
    c = client(ADULT)
    before = set(ai3d.JOBS)
    r = _post(c)
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "unavailable"
    assert "nothing was started" in detail["message"].lower()
    assert "stripe" not in r.text.lower()
    assert set(ai3d.JOBS) == before
    status = c.get("/api/ai3d/status").json()
    assert status["enabled"] is False
    assert status["plan"]["allowed"] is False
    assert status["plan"]["reason"] == "unavailable"
    assert status["engine"]["ready"] is False
    cfg = c.get("/api/config").json()
    assert cfg["ai3d_enabled"] is False


def test_testing_mode_does_not_turn_2d3d_back_on():
    assert config.TESTING_MODE is True
    assert config.ai3d_enabled() is False
    r = _post(client(ADULT))
    assert r.status_code == 403
    assert ai3d.plan(type("A", (), {"sid": "x", "user": {"plan": "pro"}})())["allowed"] is False


def test_flag_on_reports_ready_but_off_is_the_default(monkeypatch):
    monkeypatch.delenv("ZEIM_2D3D_ENABLED", raising=False)
    assert config.ai3d_enabled() is False
    monkeypatch.setenv("ZEIM_2D3D_ENABLED", "1")
    assert config.ai3d_enabled() is True
    status = client(ADULT).get("/api/ai3d/status").json()
    assert status["enabled"] is True
    assert status["engine"]["installed"] is True
    assert status["plan"]["allowed"] is True


@pytest.mark.parametrize("raw, on", [
    (None, False),
    ("", False),
    ("0", False),
    ("false", False),
    ("off", False),
    ("1", True),
    ("true", True),
    ("yes", True),
    ("on", True),
])
def test_2d3d_flag_parsing(monkeypatch, raw, on):
    if raw is None:
        monkeypatch.delenv("ZEIM_2D3D_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ZEIM_2D3D_ENABLED", raw)
    assert config.ai3d_enabled() is on


def test_ui_hides_the_tab_and_does_not_post_when_off():
    community = open("static/community.js", encoding="utf-8").read()
    page = open("static/ai3d.js", encoding="utf-8").read()
    html = open("static/index.html", encoding="utf-8").read()
    assert "ai3d_enabled" in community
    assert 'b.hidden = !on' in community
    assert '[data-view="ai3d"]' in community
    assert "2D to 3D is coming later." in community
    assert "2D to 3D is coming later." in page
    assert page.find("status.enabled === false") < page.find('"/api/ai3d/jobs"')
    assert 'data-view="lithophane"' in html
    assert 'data-view="slicer"' in html
    assert 'data-view="cad"' in html
    assert 'id="viewShowcase"' in html


def test_free_core_still_works_while_2d3d_is_off():
    c = client(ADULT)
    page = c.get("/")
    assert page.status_code == 200
    assert 'id="mainNav"' in page.text
    assert 'data-view="lithophane"' in page.text
    assert 'id="dlgSettings"' in page.text
    built = gen(c, mode="lithophane")
    assert built.status_code == 200, built.text
    assert built.json().get("id")
    settings = c.get("/api/settings")
    assert settings.status_code == 200
    assert c.get("/api/config").json()["ai3d_enabled"] is False
