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


def test_ios2_touch_targets_16px_inputs_safe_area_and_viewer_does_not_trap_scroll(live):
    code, out = run("ui_touch.py", live)
    assert code == 0, out


def _spawn(mode, extra=None):
    import socket as _s, tempfile as _t
    s = _s.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    d = _t.mkdtemp(prefix="zeim-ui-")
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "PHOTO3D_DATA": d + "/d", "PHOTO3D_OUT": d + "/o", "PHOTO3D_MODE": mode, **(extra or {})}
    p = subprocess.Popen([sys.executable, "-m", "app.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            _s.create_connection(("127.0.0.1", port), timeout=0.3).close(); break
        except OSError:
            time.sleep(0.25)
    return p, f"http://127.0.0.1:{port}"


def test_send_sheet_rows_per_audience_share_states_and_printer_honesty_in_a_real_browser():
    p1, u1 = _spawn("local", {"PHOTO3D_SEND_SHARE": "1"}); p2, u2 = _spawn("shared")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_sendsheet.py"), u1, u2], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0, r.stdout + r.stderr
    finally:
        for p in (p1, p2):
            p.terminate(); p.wait(10)


def test_ren_qa_findings_in_a_real_browser_phone_viewport():
    """QA-1 (Print/Send open the right model, both directions), QA-2, QA-3, QA-4, QA-5 and the Edit drop zone at the 5-build cap."""
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_qa.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)


def test_no_file_input_lists_bare_extensions_so_ios_does_not_grey_files_out():
    """iOS Safari greys out files whose type it can't map from `accept=".stl,.obj,.3mf"`. Photo inputs may use image/* (+ image extensions)."""
    import re
    img = {"heic", "heif", "png", "jpg", "jpeg", "webp", "gif", "bmp"}
    for fn in ("index.html", "app.js", "edit.js", "photo.js", "send.js", "community.js"):
        src = open(os.path.join(ROOT, "static", fn)).read()
        for m in re.finditer(r"""accept\s*=\s*["']([^"']*)["']""", src):
            for tok in [t.strip().lower() for t in m.group(1).split(",") if t.strip()]:
                assert "/" in tok or tok.lstrip(".") in img, f"{fn}: accept token {tok!r} would grey files out on iOS"
    assert 'id="editFile" accept' not in open(os.path.join(ROOT, "static", "index.html")).read()


def test_edit_file_picker_accepts_models_by_name_in_chrome_and_webkit():
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_files.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr
        assert "PASS chrome" in r.stdout
    finally:
        p.terminate(); p.wait(10)


def test_start_up_errors_are_visible_and_a_clean_session_has_no_page_errors_in_chrome_and_webkit():
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_boot.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS webkit" in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)


def test_print_dialog_puts_creality_cloud_first_on_phones_and_demotes_desktop_slicers_chrome_and_webkit():
    p1, u1 = _spawn("local", {"PHOTO3D_SEND_SHARE": "1"}); p2, u2 = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_creality.py"), u1, u2], cwd=ROOT, capture_output=True, text=True, timeout=500)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS webkit" in r.stdout, r.stdout + r.stderr
    finally:
        for p in (p1, p2):
            p.terminate(); p.wait(10)


def test_photo_permission_box_in_studio_and_edit_in_a_real_browser():
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_cr5.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)


def test_credits_page_and_showcase_credit_at_phone_width_in_chrome_and_webkit():
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_credits.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)


def test_refusals_are_inline_persistent_and_keep_typed_text_in_chrome_and_webkit():
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_inline.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)
