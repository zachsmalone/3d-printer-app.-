"""FDM and Lithophane work views share one layout. Landing pages, Showcase, Account, and CAD stay put."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
BAR = (ROOT / "static" / "workspace-bar.js").read_text(encoding="utf-8")
FLOW = (ROOT / "static" / "project-flow.js").read_text(encoding="utf-8")
LEAVE = (ROOT / "static" / "bed-leave.js").read_text(encoding="utf-8")
CAD = (ROOT / "static" / "cad.html").read_text(encoding="utf-8")


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_steps_show_only_while_a_file_is_open_and_the_leave_menu_stays():
    assert "return !!(ctx && ctx.working)" in FLOW
    assert "The row shows only while a file is open" in FLOW
    for label in ("Design", "Prepare", "Export/Print"):
        assert label in FLOW
    assert "#viewEdit:not(.has-model) #fdmFlow,#viewCreate:not(.has-model) #lithoFlow{display:none!important}" in CSS
    for label in ("Stay", "Save & leave", "Reset bed", "Abandon work"):
        assert label in LEAVE
    assert 'data-ws-act="exit"' in HTML


def test_fdm_and_litho_work_chrome_keeps_existing_tools():
    edit = _between(HTML, 'id="viewEdit"', 'id="viewShowcase"')
    litho = _between(HTML, 'id="viewCreate"', 'id="viewEdit"')
    assert 'id="fdmEditLitho"' in edit and ">Edit Litho</button>" in edit
    assert 'id="lithoSlicerSwitch"' in litho and ">Slicer</button>" in litho
    assert 'id="fdmPlus"' in edit and 'id="lithoPlus"' in litho
    assert 'alt="ZEIM"' in edit and 'alt="ZEIM"' in litho
    assert 'id="fdmFoot"' in edit and 'id="lithoFoot"' in litho
    assert ">Generate</button>" in litho and 'id="slicerSlice"' in edit
    assert 'id="fdmPreview"' in edit and ">Preview</h2>" in edit
    assert 'id="lithoPreview"' in litho and ">Preview</h2>" in litho
    assert "Back to Prepare" in edit and "Back to Prepare" in litho
    assert "Download STL" in edit and "Download STL" in litho
    for label in ("Position", "Sizing", "Rotate", "Arrange", "Adjust", "Shape", "Frame &amp; Base", "View", "Photo", "Light", "Print", "Collapse"):
        assert label in litho
    for token in (
        'data-bed-label="Filament"',
        'data-bed-label="Process"',
        "Process Parameters",
        'data-bed-label="Transform"',
        'data-bed-label="Import"',
        'id="slicerRepair"',
        'id="slicerPreview"',
        'id="slicerSend"',
        'data-xform="move"',
        'data-xform="rotate"',
        'data-xform="scale"',
    ):
        assert token in edit
    assert 'id="fdmFlow"' in edit and 'id="lithoFlow"' in litho
    assert "openWorkPreview" in BAR and "lithoSourceId" in BAR
    assert "Generic 0.4" not in HTML


def test_other_sections_do_not_pick_up_the_work_chrome():
    assert 'id="fdmFoot"' not in CAD and 'id="lithoFoot"' not in CAD
    assert "wl-switch" not in CAD
    showcase = _between(HTML, 'id="viewShowcase"', 'id="viewTorch"')
    account = _between(HTML, 'id="viewAccount"', 'id="viewLearn"')
    assert "wl-foot" not in showcase and "wl-foot" not in account
    assert 'id="fdmEditLitho"' not in showcase and 'id="lithoSlicerSwitch"' not in account
