"""Education CR-1: settings / printers. Run with the rest: python -m pytest -q tests"""
import io, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest, trimesh
from PIL import Image
from fastapi.testclient import TestClient
from app import config
from app.main import app
from app.community import moderation
from app.core import ratelimit
from tests.b1 import *


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")


def test_default_mode_is_shared_without_env():
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != "PHOTO3D_MODE"}
    out = subprocess.run([sys.executable, "-c", "from app import config; print(config.MODE)"], env=env,
                         cwd=os.path.dirname(os.path.dirname(__file__)), capture_output=True, text=True)
    assert out.stdout.strip() == "shared", out


def test_cr1_shared_mode_settings_and_send_locked(shared):
    anon, adult = client(), client(ADULT)
    body = {"public_base_url": "https://evil.example", "printers": [{"name": "P", "type": "octoprint", "url": "http://10.0.0.5", "api_key": "k"}]}
    assert anon.put("/api/settings", json=body).status_code == 403          # (b) brand-new anonymous session
    assert adult.put("/api/settings", json=body).status_code == 403         # accounts cannot rewrite server-wide settings either
    assert anon.put("/api/settings", json=body, headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert anon.put("/api/settings", json=body, headers=ADMIN).status_code == 200
    # printer URLs are not shown to anonymous visitors, but are to admin
    pr = anon.get("/api/settings").json()["printers"][0]
    assert "url" not in pr and "api_key" not in pr
    assert anon.get("/api/settings", headers=ADMIN).json()["printers"][0]["url"] == "http://10.0.0.5"
    pid = anon.get("/api/settings", headers=ADMIN).json()["printers"][0]["id"]
    # anonymous visitor cannot send either (no adult account / admin token)
    abid = photo_build(anon)
    assert anon.post(f"/api/send/{abid}", data={"printer_id": pid}).status_code == 403
    # accounts connect/disconnect is server-wide too
    assert anon.delete("/api/accounts/reddit").status_code == 403
    assert anon.get("/api/accounts/reddit/connect", follow_redirects=False).status_code == 403
    anon.put("/api/settings", json={"printers": [], "public_base_url": ""}, headers=ADMIN)


def test_cr1_local_mode_unchanged(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")
    c = client()
    assert c.put("/api/settings", json={"printers": [], "public_base_url": ""}).status_code == 200
    assert c.get("/api/settings").status_code == 200



def test_cr1_base_url_and_printer_url_validated(shared):
    c = client()
    for bad in ("javascript:alert(1)", "ftp://x.example", "https://user:pw@x.example", "https://x.example/path?q=1", "//x.example", "not a url"):
        assert c.put("/api/settings", json={"public_base_url": bad, "printers": []}, headers=ADMIN).status_code == 400, bad
    assert c.put("/api/settings", json={"public_base_url": "https://zeim.example:8443/", "printers": []}, headers=ADMIN).status_code == 200
    assert c.put("/api/settings", json={"printers": [{"name": "x", "type": "octoprint", "url": "file:///etc/passwd"}]}, headers=ADMIN).status_code == 400
    c.put("/api/settings", json={"public_base_url": "", "printers": []}, headers=ADMIN)


def test_b06_oauth_callback_escapes_input():
    c = client()
    r = c.get("/api/accounts/tiktok/callback", params={"error": "<script>alert(1)</script>"})
    assert r.status_code == 400 and "<script>" not in r.text and "&lt;script&gt;" in r.text
    r = c.get("/api/accounts/tiktok/callback", params={"code": "x", "state": "<img src=x onerror=1>"})
    assert "<img" not in r.text
