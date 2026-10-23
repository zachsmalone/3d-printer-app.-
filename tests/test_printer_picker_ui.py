"""Printer picker (search + brand groups) in Chromium at 1280/390/320 against a TEMP-data server on a random free port."""
import os, subprocess, sys
from test_b1_ui import _spawn, ROOT


def test_printer_picker_search_and_brand_groups_in_chromium():
    p, u = _spawn("local")
    assert not u.endswith((":8765", ":8791"))
    try:
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "ui_printer_picker.py"), u], cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS chrome" in r.stdout, r.stdout + r.stderr
    finally:
        p.terminate(); p.wait(10)
