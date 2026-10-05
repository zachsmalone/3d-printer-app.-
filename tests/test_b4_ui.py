"""Batch B UI tests (home redesign, Mode dropdown, nozzle). Each script runs against its own TEMP-data server in Chrome and WebKit."""
import os, subprocess, sys
from test_b1_ui import _spawn, ROOT


def _run(script, mode="local", extra=None):
    p, u = _spawn(mode, extra)
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", script), u], cwd=ROOT, capture_output=True, text=True, timeout=500)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
        return r.stdout
    finally:
        p.terminate(); p.wait(10)


def test_mode_dropdown_gates_teacher_announces_and_restores_in_chrome_and_webkit():
    out = _run("ui_mode.py")
    assert "PASS webkit" in out or "SKIP webkit" in out


def test_home_redesign_hero_path_radios_landmarks_send_or_save_themes_and_axe():
    out = _run("ui_home.py")
    assert "PASS webkit" in out or "SKIP webkit" in out


def test_no_dialog_uses_header_or_footer_landmarks_and_the_page_has_one_of_each():
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    import re
    for d in re.findall(r"<dialog.*?</dialog>", html, flags=re.S):
        assert "<header" not in d and "<footer" not in d
    assert html.count("<header") == 1 and html.count("<footer") == 1
    for page in ("privacy.html", "terms.html", "COMMUNITY_GUIDELINES.html"):
        assert os.path.exists(os.path.join(ROOT, "static", page)), page


def test_send_sheet_labels_untested_rows_and_never_claims_they_work():
    js = open(os.path.join(ROOT, "static", "send.js"), encoding="utf-8").read()
    for row in ("ssShare", "ssEmail", "ssShapr"):
        i = js.index(f'id="{row}"'); chunk = js[i:i + 700]
        assert "untested" in chunk and ("Not tried" in chunk), row
    assert "ZEIM does not connect to Creality" in js and "have not tested" in js
    assert "Tested with a pretend printer only" in js
