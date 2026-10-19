"""CAD hints toggle + construction planes (front end): Node suite for static/cad-planes.js and wiring checks."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cad_planes_js_suite():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", "--test", str(ROOT / "tests/js/cad-planes.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


def test_hints_toggle_wired_and_accessible():
    html = (ROOT / "static/cad.html").read_text()
    js = (ROOT / "static/cad.js").read_text()
    css = (ROOT / "static/cad.css").read_text()
    assert 'id="cwHints" aria-pressed="true"' in html
    assert 'id="cwHint" role="status" aria-live="polite"' in html
    assert "Start with a sketch" not in html            # the big centre card is gone
    assert '$("#cwHint").hidden = !HINTS_ON' in js and "emptyHint()" in js
    assert "white-space:nowrap" in css.split(".cw-hint{", 1)[1].split("}", 1)[0]


def test_sketch_panel_offers_construction_planes():
    js = (ROOT / "static/cad.js").read_text()
    assert '["offset", "Offset"], ["mid", "Midplane"]' in js
    assert "startSketch(offsetPlane(" in js and "startSketch(midPlane(" in js


def test_cad_page_serves_planes_module():
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).get("/static/cad-planes.js")
    assert r.status_code == 200 and "export function midPlane" in r.text


def test_status_messages_show_even_with_hints_off():
    js = (ROOT / "static/cad.js").read_text()
    assert "h.hidden = !HINTS_ON && !always" in js and "const status = (t, s) => hint(t, s, true)" in js
    for m in ('status(r.ok ? "Solved" : "Over-constrained"', 'return status("Constraints"', 'status("Measure", measLabel.text)'):
        assert m in js, m
    assert 'hint(r.ok ? "Solved"' not in js
