"""Regression: files picked or dropped on the Slicer page must load (or say why), never silently vanish.
Real headless browser; skipped when playwright's Chromium is not installed. Never touches :8765."""
import os, socket, subprocess, sys, tempfile, time
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        HAS = os.path.exists(_p.chromium.executable_path)
except Exception:
    HAS = False
pytestmark = pytest.mark.skipif(not HAS, reason="needs playwright Chromium")


def test_slicer_import_pick_multi_drop_and_empty_file():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    d = tempfile.mkdtemp(prefix="zeim-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local"}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
            except OSError:
                time.sleep(0.25)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_slicer_import.py"), f"http://127.0.0.1:{port}"],
                           cwd=ROOT, capture_output=True, text=True, timeout=280)
        assert r.returncode == 0, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)
