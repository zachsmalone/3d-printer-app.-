"""Runs the Node test-suite for static/zeim-account.js (skipped if Node isn't installed)."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_account_controller_js_suite():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(["node", "--test", str(root / "tests/js/zeim-account.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
