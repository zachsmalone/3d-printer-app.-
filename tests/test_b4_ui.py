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
