"""3D G-code preview (static/gcodeview.js + gcode-worker.js) in Chromium: see tests/ui_gcode_preview.py.
Chromium only: WebKit is not installed on the build box (the 2D fallback keeps its WebKit test in ui_layers.py)."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_gcode_preview_files_are_original_and_wired():
    for f in ("gcode-parse.js", "gcode-worker.js", "gcodeview.js"):
        s = open(os.path.join(ROOT, "static", f), encoding="utf-8").read()
        assert "GPL" not in s and "AGPL" not in s, f
    pj = open(os.path.join(ROOT, "static", "printer.js"), encoding="utf-8").read()
    assert "wireGcodePreview(r.downloads.gcode" in pj and "gcDispose()" in pj


def test_gcode_preview_in_chromium():
    from test_b4_ui import _run
    out = _run("ui_gcode_preview.py")
    assert "PASS chrome" in out, out


def test_gcode_tools_code_pause_markers_in_chromium():
    from test_b4_ui import _run
    out = _run("ui_gcode_tools.py")
    assert "PASS chrome" in out, out
