"""Batch 3: Projects is the saved-project list, and the stage bar keeps one project.

My Studio stays on Account at #account/studio. The top-bar name is Projects.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static/index.html").read_text(encoding="utf-8")
CAD = (ROOT / "static/cad.html").read_text(encoding="utf-8")
LIB = (ROOT / "static/studio-library.js").read_text(encoding="utf-8")
HAND = (ROOT / "static/handoff.js").read_text(encoding="utf-8")
COMM = (ROOT / "static/community.js").read_text(encoding="utf-8")
REPAIR = (ROOT / "static/repair.js").read_text(encoding="utf-8")
BRAND = (ROOT / "app/branding.py").read_text(encoding="utf-8")
WS = (ROOT / "static/ws-main.js").read_text(encoding="utf-8")
CADOPS = (ROOT / "app/core/cadops.py").read_text(encoding="utf-8")


def _slice(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_projects_opens_the_existing_library_and_does_not_move_it():
    nav = _slice(HTML, 'id="mainNav"', "</nav>")
    assert 'data-view="projects"' in nav
    assert nav.index('data-view="projects"') < nav.index('data-view="account"')
    assert "studio" not in re.findall(r'data-view="(\w+)"', nav)
    acc = _slice(HTML, 'id="viewAccount"', 'id="viewLearn"')
    studio = _slice(acc, 'id="meStudio"', "</section>")
    assert "My Studio" in studio and 'href="#account/studio"' in studio and 'id="studioLib"' in studio
    assert 'head === "projects"' in LIB
    assert 'nav: "projects"' in LIB
    assert '"#account/studio"' in LIB
    assert "Projects" in _slice(HTML, 'id="studioLibHelp"', "</p>")


def test_photo_and_slicer_are_not_named_studio_or_edit():
    assert "Edit a Studio build" not in HTML
    assert "Open it in Edit" not in HTML
    assert "Edit a 3D model" not in HTML
    edit = _slice(HTML, 'id="viewEdit"', 'id="viewShowcase"')
    assert ">FDM Slicer</h1>" in edit
    assert 'id="btnEditThis" hidden' in HTML
    assert 'id="editFromBuild"' in edit and "<div hidden>" in edit
    assert 'lithophane: "Photo"' in HAND
    assert 'lithophane: "Studio"' not in HAND
    assert '"create": "Photo"' in BRAND
    assert '"edit": "FDM Slicer"' in BRAND
    assert '=== "litho" ? "Lithophane" : "Photo"' in WS


def test_stage_bar_is_on_the_main_app_and_in_cad():
    assert 'id="projectFlow"' in HTML and 'aria-label="Project stages"' in HTML
    assert 'id="projectFlow"' in CAD
    assert "bindFlow" in COMM and "followFlow" in COMM
    assert "bindFlow" in (ROOT / "static/cad.js").read_text(encoding="utf-8")
    assert "projectFlow" in WS
    flow = (ROOT / "static/project-flow.js").read_text(encoding="utf-8")
    for label in ("Design", "Check & Repair", "Prepare", "Slice & Export"):
        assert label in flow


def test_repair_page_can_continue_into_the_slicer_as_a_copy():
    assert "Open in the FDM Slicer" in REPAIR
    assert "slicerUrlForNewProject" in REPAIR
    assert "new project from that file" in REPAIR
    page = (ROOT / "static/repair.html").read_text(encoding="utf-8")
    assert 'src="/static/repair.js"' in page


def test_body_identity_is_unchanged():
    """B1-6 stays open. Bodies are still numbered by centre, and a step still stores an index."""
    assert "sorted by" in CADOPS and "centre x" in CADOPS
    assert "sorted(parts, key=lambda b: tuple(np.round(b.bounds.mean(axis=0), 3))" in CADOPS
