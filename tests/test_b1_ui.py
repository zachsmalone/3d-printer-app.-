"""Real-browser checks (headless Chrome via playwright). Skipped automatically when Chrome/playwright are not installed
(CI installs neither). Starts a throw-away server on a free port with temp data dirs; never touches :8765."""
import os, shutil, socket, subprocess, sys, tempfile, time
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAS_CHROME = bool(shutil.which("google-chrome") or shutil.which("chrome"))
try:
    import playwright  # noqa
    HAS_PW = True
except Exception:
    HAS_PW = False
pytestmark = pytest.mark.skipif(not (HAS_CHROME and HAS_PW), reason="needs Chrome + playwright")


@pytest.fixture(scope="module")
def live():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    d = tempfile.mkdtemp(prefix="zeim-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "local"}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
        except OSError:
            time.sleep(0.25)
    yield f"http://127.0.0.1:{port}"
    p.terminate(); p.wait(10)


def run(script, url):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", script), url], cwd=ROOT, capture_output=True, text=True, timeout=280)
    return r.returncode, r.stdout + r.stderr


def test_no_horizontal_scroll_and_nav_reachable_at_320_375_390_768(live):
    code, out = run("ui_mobile.py", live)
    assert code == 0, out


def test_photo_start_upload_camera_heic_errors_in_a_real_browser(live):
    code, out = run("ui_photo.py", live)
    assert code == 0, out


def test_teacher_send_switch_dialog_and_teen_print_hidden():
    import socket as _s, tempfile as _t
    s = _s.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    d = _t.mkdtemp(prefix="zeim-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": "shared"}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                _s.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
            except OSError:
                time.sleep(0.25)
        code, out = run("ui_send.py", f"http://127.0.0.1:{port}")
        assert code == 0, out
    finally:
        p.terminate(); p.wait(10)
