"""Build-section chrome: Exit stays in front of docked tools, and FDM process settings use a half sheet."""
import re
from pathlib import Path

from app.services.print_setup import PATTERNS, SUPPORTS

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = (ROOT / "static" / "wslayout.js").read_text(encoding="utf-8")
MAIN = (ROOT / "static" / "ws-main.js").read_text(encoding="utf-8")
CAD = (ROOT / "static" / "cad-phone.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
CAD_CSS = (ROOT / "static" / "cad.css").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
PRINTER = (ROOT / "static" / "printer.js").read_text(encoding="utf-8")


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_exit_strip_is_reserved_and_above_a_drag():
    assert "function chromeBand(" in LAYOUT
    assert 'chromeBand(rr, ":scope > .wsbar", true)' in LAYOUT
    assert "p.dock" in LAYOUT
    assert "It stays off Exit" in LAYOUT
    # A drag paints under the workspace bar. 16 is the drag; 48 is the bar.
    assert ".zws-p.drag{opacity:.9;box-shadow:0 14px 34px rgba(0,0,0,.45);z-index:16;" in CSS
    assert "main.zws>.wsbar{position:absolute;z-index:48;" in CSS
    assert "pointer-events:none" in CSS
    assert "main.zws>.wsbar .btn,main.zws>.wsbar a{pointer-events:auto}" in CSS
    assert "z-index:50" in CAD_CSS
    assert "overflow:hidden" in _between(CAD_CSS, ".cw-main.zws{", "}")


def test_tool_rails_dock_instead_of_floating_over_exit():
    for src in (MAIN, CAD):
        assert "dock: true" in src
    assert 'el: "#vtools"' in MAIN and "lead: true" in MAIN
    assert 'edge: "right", t: 0.42' in MAIN
    assert "panels: []" in MAIN
    assert "#viewEdit .zws-p" in CSS
    assert "id=\"slicerDock\"" in HTML
    assert "data-xform=\"move\"" in HTML and "data-xform=\"rotate\"" in HTML and "data-xform=\"scale\"" in HTML
    assert "data-xform=\"clone\"" in HTML and "data-xform=\"delete\"" in HTML
    assert "focusXform" in MAIN


def test_process_sheet_groups_only_existing_slicer_choices():
    sheet = _between(HTML, 'id="processSheet"', "</main>")
    assert 'id="slicePanel"' in sheet
    assert 'id="processClose"' in sheet
    assert "70dvh" in CSS
    assert 'id="slicerBar"' in HTML
    assert 'id="procExpand"' in HTML
    for name in ("Quality", "Support", "Infill", "Adhesion"):
        assert name in PRINTER
    block = _between(PRINTER, "const PAT = {", "const PAT_LABEL")
    keys = set(re.findall(r'^\s*"?([A-Za-z0-9_]+)"?:\s*\{', block, re.M))
    assert keys == set(PATTERNS)
    sup = re.search(r"const SUP_META = \{([^}]+)\}", PRINTER)
    assert sup
    sup_keys = set(re.findall(r"^\s*([A-Za-z0-9_]+):", sup.group(1), re.M))
    assert sup_keys == set(SUPPORTS)
    # Visual choices still write the same fields the slicer already reads.
    assert 'fd.append("infill_pattern"' in PRINTER
    assert 'fd.append("brim"' in PRINTER
    assert 'id="spGo"' in PRINTER
    assert "Bambu" not in block
    layout = (ROOT / "static" / "wslayout.js").read_text(encoding="utf-8")
    assert "Reset layout" not in layout and "data-zws-reset" not in layout
    assert "zeim:fdm-slice" in PRINTER
    assert "body[data-view=slicer] .topbar .nav{position:static" in CSS
    assert "Quarter cubic, octet, cross, cross 3D, and TPMS" in PRINTER


def test_slice_is_not_covered_by_customise():
    # The labelled control joins the strip. A 60px hole was narrower than "Customise", so that button took Slice's hit.
    assert '":scope > .wsbar"' in LAYOUT and 'className = "ws-end"' in LAYOUT
    assert "padding:8px 60px 8px" not in CSS
    assert "main.zws>.wsbar>.ws-end{display:flex;flex:0 0 auto;" in CSS
    assert "main.zws>.wsbar>.ws-end>.zws-cust" in CSS and "position:static;z-index:auto;" in CSS
    assert "main:not(.zws)>.wsbar>.ws-end{display:none}" in CSS
    assert "main.zws>.wsbar .ws-go{margin-left:auto;flex:0 0 auto}" in CSS
    assert "main.zws>.wsbar{position:absolute;z-index:48;" in CSS


def test_primary_actions_do_not_become_showcase():
    edit = _between(HTML, 'id="viewEdit"', 'id="viewShowcase"')
    assert 'id="slicerSlice"' in edit and 'data-go="spGo"' in edit
    assert 'id="slicerRepair"' in edit and 'data-bed-act="repair"' in edit
    assert "body[data-view=slicer] #projectFlow{display:none!important}" in CSS
    assert 'data-big="fix"' in (ROOT / "static" / "edit.js").read_text(encoding="utf-8")
    bar = (ROOT / "static" / "workspace-bar.js").read_text(encoding="utf-8")
    assert 'data-bed-act=repair' in bar and "[data-big=fix]" in bar
    assert "sendToShowcase" not in edit
    assert 'data-ws-act="exit"' in edit
    litho = _between(HTML, 'id="viewCreate"', 'id="viewEdit"')
    assert 'data-go="btnSendSlicer"' in litho
    assert "Send to Showcase" in litho  # the existing publish control stays where it was
    torch = _between(HTML, 'id="viewTorch"', 'id="viewAi3d"')
    assert 'data-go="rzGo"' in torch
    assert "sendToShowcase" not in torch
