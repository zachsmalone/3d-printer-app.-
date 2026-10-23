"""Runs the node unit tests for the client-side G-code parser (static/gcode-parse.js)."""
import shutil, subprocess
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_gcode_parser_node():
    r = subprocess.run(["node", "--test", str(ROOT / "tests/js/gcode-parse.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
