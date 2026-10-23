"""Select mode UI (tests/ui_selectmode.py) against its own TEMP-data server: trace on the sample at 390 px, get a model of only that region."""
import os
from test_b4_ui import _run


def test_select_mode_trace_snaps_and_builds_only_the_region_in_chrome():
    shots = os.environ.get("ZEIM_SELECT_SHOTS", "")
    out = _run("ui_selectmode.py") if not shots else _run_shots(shots)
    assert "PASS chrome" in out


def _run_shots(d):
    import subprocess, sys
    from test_b1_ui import _spawn, ROOT
    p, u = _spawn("local")
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_selectmode.py"), u, d], cwd=ROOT, capture_output=True, text=True, timeout=500)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
        return r.stdout
    finally:
        p.terminate(); p.wait(10)


def test_selectmode_is_its_own_module_and_app_js_only_hooks_in():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "static", "index.html"), encoding="utf-8").read()
    assert "/static/selectmode.js" in html and "/static/selectmode.css" in html
    app = open(os.path.join(root, "static", "app.js"), encoding="utf-8").read()
    assert "window.zeimSelect" in app and "zeim:build" in app
