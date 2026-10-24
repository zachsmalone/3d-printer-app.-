"""E / Task 1: Send to… hand-off wiring (static checks; the browser flow is tests/ui_handoff_e.py)."""
from pathlib import Path
ST = Path(__file__).resolve().parent.parent / "static"

def test_handoff_loaded_once_as_a_module():
    h = (ST / "index.html").read_text()
    assert h.count('<script type="module" src="/static/handoff.js"></script>') == 1

def test_no_inline_handlers_and_matching_printer_kind_only():
    js = (ST / "handoff.js").read_text()
    assert "onclick=\"" not in js and "onsubmit=" not in js
    assert '"slicer" && k === "resin"' in js and '"torchc0" && k === "fdm"' in js

def test_three_limits_are_covered():
    js = (ST / "handoff.js").read_text()
    assert "sendToFab" in js                                  # Slicer: visible even when its panel is folded away
    assert "zeim.studio.return" in js and "zeim:open-build" in js and "zeim:open-build" in (ST / "app.js").read_text()
    assert "indexedDB" in js and "zeim:torchc0-ready" in (ST / "torchc0.js").read_text()

def test_print_dialog_open_in_torchc0_carries_the_model():
    pk = (ST / "printkind.js").read_text()
    assert "zeimHandoff?.openInTorch" in pk and "#selPanel #selSay" in pk

def test_cad_send_to_menu_and_safe_back_link():
    html, js = (ST / "cad.html").read_text(), (ST / "cad.js").read_text()
    assert 'id="cwSendTo"' in html and 'id="cwSendSlicer"' in html and 'id="cwSendTorch"' in html
    assert 'back.startsWith("/") && !back.startsWith("//")' in js

def test_lithophane_three_handoff_buttons_side_by_side():
    """After generate: Save work | Send to Slicer | Send to CAD (Task 1)."""
    h, js, css = (ST / "index.html").read_text(), (ST / "handoff.js").read_text(), (ST / "style.css").read_text()
    assert 'id="studioHandoff"' in h and 'id="btnSaveWork"' in h
    assert 'id="btnSendSlicer"' in h and 'id="btnSendCad"' in h
    assert "wireStudioHandoff" in js and "Save work" in h and "Send to CAD" in h
    assert ".handoffrow" in css and "flex" in css.split(".handoffrow")[1][:80]
    # Lithophane no longer injects the old Send to… menu button
    assert 'addBtn("btnSendTo"' not in js

def test_lithophane_has_no_multihead_or_slot_controls():
    """Nozzle / multi-head / filament-slot pickers belong only in the FDM Slicer."""
    create = (ST / "index.html").read_text().split('id="viewCreate"')[1].split('id="viewEdit"')[0]
    assert "expSlots" not in create and "spSlots" not in create and "spSlotOn" not in create
    assert "AMS" not in create and "CFS" not in create and "MMU" not in create
    exp = (ST / "exportpick.js").read_text()
    assert '$("#expSlots").hidden = true' in exp or "expSlots\").hidden = true" in exp
