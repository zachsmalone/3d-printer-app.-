"""Node tests for browser draft saves (static/worksave.js)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_worksave_node():
    r = subprocess.run(["node", "--test", str(ROOT / "tests/js/worksave.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
