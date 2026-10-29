"""An empty CAD workspace still shows its creation tools.

Hide-until-work is for the file-picker workspaces. CAD starts with nothing on the bed,
so Shapes, Sketch and Import have to be on the bar or a new design cannot begin.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAD_JS = (ROOT / "static/cad.js").read_text(encoding="utf-8")
CAD_CSS = (ROOT / "static/cad.css").read_text(encoding="utf-8")
CAD_HTML = (ROOT / "static/cad.html").read_text(encoding="utf-8")
FLOW = (ROOT / "static/project-flow.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static/style.css").read_text(encoding="utf-8")
INDEX = (ROOT / "static/index.html").read_text(encoding="utf-8")


def _hide_selectors():
    start = CAD_CSS.index("body.cadws:not(.has-work)")
    block = CAD_CSS[start:CAD_CSS.index("{display:none!important}", start)]
    return block


def test_empty_cad_keeps_the_tool_bar_and_locks_body_edits():
    hide = _hide_selectors()
    assert "#zws-tools" not in hide
    assert "cw-rail" not in hide
    assert "body.cadws:not(.has-work) #zws-tools" not in CAD_CSS
    assert "body.cadws:not(.has-work) .cw-main>.cw-rail" not in CAD_CSS
    assert "body.cadws #zws-tools," in CAD_CSS
    assert "display:flex!important" in CAD_CSS
    assert 'id="cwRail"' in CAD_HTML
    assert 'id="cwShowTools"' in CAD_HTML
    assert 'classList.toggle("tools-on", on)' in CAD_JS
    assert 'id: "shapes"' in CAD_JS and 'id: "sketch"' in CAD_JS and 'id: "import"' in CAD_JS
    assert "MODEL_TOOLS.map(t => toolBtn(t, S.tool, toolLocked(t.id)))" in CAD_JS
    assert 'id === "shapes" || id === "sketch" || id === "import"' in CAD_JS
    assert "return bodyCount() < 1" in CAD_JS
    assert 'b.dataset.tool === "import"' in CAD_JS
    assert "Make a solid first: Shapes, or Sketch then Extrude." in CAD_JS
    # The first paint of the model rail is not behind a has-work check.
    assert "if (cadHasWork()) renderRail" not in CAD_JS
    assert "\nrenderRail();" in CAD_JS


def test_steps_wait_for_an_open_file_and_the_slicer_bar_follows_the_model():
    assert "Export/Print" in FLOW
    assert '{ id: "repair"' not in FLOW
    assert "return !!(ctx && ctx.working)" in FLOW
    assert 'WORKSPACES = new Set(["slicer", "cad", "lithophane", "torchc0"])' in FLOW
    assert "working: cadHasWork()" in CAD_JS
    assert 'id="fdmFlow"' in INDEX
    assert "flowWorking" in (ROOT / "static/community.js").read_text(encoding="utf-8")
    barjs = (ROOT / "static/workspace-bar.js").read_text(encoding="utf-8")
    assert 'paintDevice(); paintWorkBars();' in barjs
    assert 'new MutationObserver(paintWorkBars)' in barjs
    assert 'sessionStorage.setItem("zeim.sliceNow", "1")' in CAD_JS
    assert 'plan.stage === "prepare" || plan.stage === "slice"' in CAD_JS
    assert "body[data-view=slicer] #projectFlow{display:none!important}" in STYLE
    assert "#viewEdit.has-model>#slicerBar{display:flex!important}" in STYLE
    assert "#viewEdit:not(.has-model)>#slicerBar{display:none!important}" in STYLE
    head = INDEX[INDEX.index('class="bed-head'):INDEX.index('class="bed-name"')]
    assert 'id="fdmFlow"' in head
    bar = INDEX[INDEX.index('id="slicerBar"'):INDEX.index('id="bedTools"')]
    for token in (
        'data-bed-label="Printer"',
        'data-bed-label="Filament"',
        'data-bed-label="Process"',
        'data-bed-label="Transform"',
        'data-bed-label="Import"',
        'id="slicerRepair"',
        'id="slicerSlice"',
        'id="slicerPreview"',
        'id="slicerSend"',
    ):
        assert token in bar
