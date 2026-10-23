"""18+ first-visit gate: server switch, API (only a yes is stored, and only on an account) and the real page in Chromium."""
import os, subprocess, sys
from app import config
from tests.b1 import client, ADULT
from test_b1_ui import _spawn, ROOT


def test_gate_markup_is_served_and_only_the_test_switch_turns_it_off(monkeypatch):
    monkeypatch.setattr(config, "AGE_GATE", True)
    h = client().get("/").text
    assert 'id="ageGate"' in h and "/static/agegate.js" in h and 'data-agegate="off"' not in h
    assert h.index('id="ageGate"') < h.index('id="mainNav"')            # covers the page before anything else paints
    monkeypatch.setattr(config, "AGE_GATE", False)
    assert 'data-agegate="off"' in client().get("/").text


def test_default_is_on_outside_tests():
    r = subprocess.run([sys.executable, "-c", "from app import config; print(config.AGE_GATE)"], cwd=ROOT, capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if k != "PHOTO3D_AGE_GATE"})
    assert r.stdout.strip() == "True", r.stderr


def test_guest_yes_is_not_stored_on_the_server_and_no_is_refused():
    c = client()
    assert c.get("/api/me/adult").json() == {"signed_up": False, "confirmed": False}
    r = c.put("/api/me/adult", json={"adult": True}); assert r.status_code == 200 and r.json()["stored"] == "browser"
    assert c.get("/api/me/adult").json()["confirmed"] is False
    assert c.put("/api/me/adult", json={"adult": False}).status_code == 400          # a 'no' is never recorded
    assert c.put("/api/me/adult", json={}).status_code == 400


def test_signed_in_yes_is_kept_on_the_account():
    c = client(ADULT)
    assert c.get("/api/me/adult").json()["confirmed"] is False
    assert c.put("/api/me/adult", json={"adult": True}).json()["stored"] == "profile"
    assert c.get("/api/me/adult").json() == {"signed_up": True, "confirmed": True}


def test_gate_in_a_real_browser_phone_and_desktop():
    p, u = _spawn("local", {"PHOTO3D_AGE_GATE": "1"})
    assert not u.endswith((":8765", ":8791"))
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_agegate.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0 and "PASS chrome" in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)
