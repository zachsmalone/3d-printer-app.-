"""Batch 2 layout: node tests for placement, identity, breakpoints, and headless Chrome geometry."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_layout_batch2_node():
    r = subprocess.run(
        ["node", "--test", str(ROOT / "tests/js/layout-batch2.test.mjs")],
        capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
