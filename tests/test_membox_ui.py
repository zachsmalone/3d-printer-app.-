"""Memory box UI at 1280 and 390 px (real browser; skipped without Chromium)."""
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


def test_membox_ui_styles_base_export_1280_390():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    d = tempfile.mkdtemp(prefix="zeim-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local",
           "PHOTO3D_UPLOADS_PER_HOUR": "0"}  # 4 photos x 3 styles = 12 uploads per viewport, over the default 10/hour
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
            except OSError:
                time.sleep(0.25)
        shots = os.environ.get("MEMBOX_SHOTS", d + "/shots")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_membox.py"), f"http://127.0.0.1:{port}", shots],
                           cwd=ROOT, capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(20)
