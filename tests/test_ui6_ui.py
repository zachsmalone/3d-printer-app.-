"""UI6 interface changes in Chromium at 1280/390/320 against a TEMP-data server on a random free port."""
import os, subprocess, sys
from test_b1_ui import _spawn, ROOT


def test_ui6_split_search_toolbar_icons_contrast_consent_in_chromium():
    p, u = _spawn("local")
    assert not u.endswith((":8765", ":8791"))
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_ui6.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=400)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)
