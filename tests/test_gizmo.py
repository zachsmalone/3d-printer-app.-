"""On-model beads call the transform steps ZEIM already stores."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATH = (ROOT / "static" / "gizmo-math.js").read_text(encoding="utf-8")
VIEW = (ROOT / "static" / "gizmo-view.js").read_text(encoding="utf-8")
PLATE = (ROOT / "static" / "plate.js").read_text(encoding="utf-8")
EDIT = (ROOT / "static" / "edit.js").read_text(encoding="utf-8")
CAD = (ROOT / "static" / "cad.js").read_text(encoding="utf-8")
MAIN = (ROOT / "static" / "ws-main.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_gizmos_reuse_the_existing_steps():
    assert 'action: "transform"' in MATH
    assert 'op: "translate"' in MATH and 'op: "rotate"' in MATH and 'op: "scale"' in MATH
    assert 'op: "body_transform"' in MATH
    assert "pivot: \"base\"" in MATH
    assert 'plateOp(action, rest)' in PLATE
    assert 'op: "translate"' not in PLATE
    assert "doOp(spec.op, spec.params" in EDIT
    assert 'op: "body_transform"' in CAD
    assert "addOp(\"body_transform\"" in CAD


def test_docked_row_still_focuses_fields_and_selects_the_beads():
    assert 'data-xform="move"' in HTML and 'data-xform="rotate"' in HTML and 'data-xform="scale"' in HTML
    assert "focusXform" in MAIN
    assert 'new CustomEvent("zeim:xform"' in MAIN
    assert "addEventListener(\"zeim:xform\"" in PLATE
    assert "addEventListener(\"zeim:xform\"" in EDIT
    assert "id=\"slicerDock\"" in HTML
    assert "Bambu" not in MATH and "Prusa" not in MATH and "Orca" not in MATH


def test_beads_stay_clear_of_chrome_and_ease_under_the_pointer():
    assert "overlapsChrome" in MATH
    assert "CHROME" in VIEW and ".wsbar" in VIEW and ".objdock" in VIEW and ".proc-sheet" in VIEW
    assert ".cw-top" in VIEW and ".cw-chips" in VIEW and ".zws-p" in VIEW
    assert ".zg-handle" in CSS
    assert "transition:transform .18s ease" in CSS
    assert "prefers-reduced-motion:reduce" in CSS
    assert "cursor:grab" in CSS
    assert ".zg{position:absolute;inset:0;z-index:2;" in CSS
    # The workspace bar stays above a bead. 48 is the bar; 2 is the bead layer, under the busy veil.
    assert "main.zws>.wsbar{position:absolute;z-index:48;" in CSS
    assert ".busy{position:absolute;inset:0;" in CSS and "z-index:3}" in CSS
