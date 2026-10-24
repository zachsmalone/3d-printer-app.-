"""Public coming-soon gate. Default off so a normal visit gets the full ZEIM app."""
from __future__ import annotations

import os
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_gate_off_serves_the_app(monkeypatch):
    monkeypatch.setenv("ZEIM_COMING_SOON", "0")
    c = TestClient(app)
    page = c.get("/")
    assert page.status_code == 200
    assert 'id="mainNav"' in page.text
    assert 'id="dlgSettings"' in page.text
    assert "almost ready" not in page.text
    assert page.headers["cache-control"] == "no-cache"
    assert c.get("/healthz").json() == {"status": "ok"}
    cfg = c.get("/api/config")
    assert cfg.status_code == 200
    assert cfg.headers["content-type"].startswith("application/json")
    plans = c.get("/api/subscriptions/plans")
    assert plans.status_code == 200
    assert plans.headers["content-type"].startswith("application/json")


def test_gate_on_holds_visitors_and_keeps_healthz(monkeypatch):
    monkeypatch.setenv("ZEIM_COMING_SOON", "1")
    assert config.coming_soon_enabled() is True
    c = TestClient(app)
    page = c.get("/")
    assert page.status_code == 200
    assert "ZEIM is almost ready" in page.text
    assert "private for now" in page.text
    assert "We build in one place." in page.text
    assert "mainNav" not in page.text
    assert "dlgSettings" not in page.text
    low = page.text.lower()
    for banned in ("better than", "printables", "cults", "makerworld"):
        assert banned not in low
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert "no-store" in page.headers["cache-control"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in {k.lower() for k in page.headers}
    held = c.get("/api/subscriptions/plans")
    assert "text/html" in held.headers["content-type"]
    assert "almost ready" in held.text
    checkout = c.post("/api/subscriptions/checkout", json={"plan": "pro"})
    assert "almost ready" in checkout.text
    assert "stripe" not in checkout.text.lower()
    health = c.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


@pytest.mark.parametrize("raw, on", [
    (None, False),
    ("", False),
    ("0", False),
    ("false", False),
    ("off", False),
    ("1", True),
    ("true", True),
    ("YES", True),
    ("on", True),
])
def test_coming_soon_flag_parsing(monkeypatch, raw, on):
    if raw is None:
        monkeypatch.delenv("ZEIM_COMING_SOON", raising=False)
    else:
        monkeypatch.setenv("ZEIM_COMING_SOON", raw)
    assert config.coming_soon_enabled() is on


def test_coming_soon_copy_is_humble():
    text = open(os.path.join(ROOT, "static", "coming-soon.html"), encoding="utf-8").read()
    assert "ZEIM is almost ready" in text
    assert "private for now" in text
    assert "<script" not in text.lower()
    low = text.lower()
    for banned in ("better than", "printables", "cults", "makerworld", "stripe"):
        assert banned not in low


def test_caddy_selector_defaults_to_the_open_site():
    script = os.path.join(ROOT, "reports", "deploy", "caddy-run.sh")
    open_file = os.path.join(ROOT, "reports", "deploy", "Caddyfile")
    gate_file = os.path.join(ROOT, "reports", "deploy", "Caddyfile.coming-soon")
    subprocess.check_call(["sh", "-n", script])
    base = os.environ.copy()
    base["ZEIM_CADDY_PRINT_CONFIG"] = "1"
    base["CADDY_DIR"] = "/etc/caddy"
    base.pop("ZEIM_COMING_SOON", None)
    out = subprocess.check_output(["sh", script], env=base, text=True).strip()
    assert out == "/etc/caddy/Caddyfile"
    base["ZEIM_COMING_SOON"] = "0"
    out = subprocess.check_output(["sh", script], env=base, text=True).strip()
    assert out == "/etc/caddy/Caddyfile"
    base["ZEIM_COMING_SOON"] = "1"
    out = subprocess.check_output(["sh", script], env=base, text=True).strip()
    assert out == "/etc/caddy/Caddyfile.coming-soon"

    open_text = open(open_file, encoding="utf-8").read()
    gate_text = open(gate_file, encoding="utf-8").read()
    assert "reverse_proxy app:8765" in open_text
    assert "root *" not in open_text
    assert "handle /healthz" in gate_text
    assert "reverse_proxy app:8765" in gate_text
    assert "/srv/zeim-coming-soon" in gate_text
