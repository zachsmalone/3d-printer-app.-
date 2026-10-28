"""CAD pointer feel: gates, Exit, and the same 180 ms ease as the beads."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cad_feel_js_suite():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(
        ["node", "--test", str(ROOT / "tests/js/cad-feel.test.mjs")],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


def test_exit_does_not_publish_and_feel_is_wired():
    html = (ROOT / "static/cad.html").read_text(encoding="utf-8")
    js = (ROOT / "static/cad.js").read_text(encoding="utf-8")
    css = (ROOT / "static/cad.css").read_text(encoding="utf-8")
    assert 'id="cwBack"' in html and 'aria-label="Exit workspace"' in html
    assert "does not send the model to Showcase" in html
    assert 'id="cwMarks"' in html and 'id="cwPick"' in html
    back = js.split('$("#cwBack")', 1)[1].split("view cube", 1)[0]
    assert "publish" not in back
    assert "takeExit" in back
    send = js.split('$("#cwSendShowcase")', 1)[1].split("cwToSlicer", 1)[0]
    assert "publish=" in send
    assert 'from "/static/cad-feel.js"' in js
    assert "pickChoice(" in js and "anchorClear(" in js
    assert "filletBlock(" in js and "faceOffsetBlock(" in js
    assert "extrudeBlock(" in js and "constraintBlock(" in js
    assert "measureBlock(" in js
    assert ".cw-cubewrap" in js and ".cw-chips" in js and ".cw-top" in js
    assert "transition:background .18s ease" in css
    assert "transition:transform .18s ease" in css
    assert "prefers-reduced-motion:reduce" in css
    assert ".pk-hover" in css and ".pk-press" in css and ".pk-sel" in css
