"""Saved work lives on Account, and the stage bar keeps one project.

There is no Projects tab and no second list with a shorter title.
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


def test_account_owns_the_list_and_projects_is_not_a_second_page():
    nav = _slice(HTML, 'id="mainNav"', "</nav>")
    views = re.findall(r'data-view="(\w+)"', nav)
    assert "projects" not in views and "studio" not in views
    assert "account" in views
    assert 'id="viewProjects"' not in HTML
    assert "Open in Projects" not in HTML and "View in My Studio" not in HTML
    acc = _slice(HTML, 'id="viewAccount"', 'id="viewLearn"')
    assert 'id="studioLib"' in acc and 'id="studioLibHelp"' in acc
    assert "Open continues that project" in acc
    assert 'id="btnLogin"' in acc and 'id="btnAccount"' in acc
    assert HTML.count('id="studioLib"') == 1
    assert "This is Projects" not in HTML
    assert 'head === "projects"' in LIB
    assert 'view: "account"' in LIB
    assert 'nav: "account"' in LIB
    assert 'view: "projects"' not in LIB and 'nav: "projects"' not in LIB
    assert '"#account"' in LIB and '"#projects"' in LIB
    assert "ownership: true" in LIB


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


def test_repair_page_hands_off_on_the_server_and_says_when_the_project_is_new():
    assert "Open in the FDM Slicer" in REPAIR
    assert "slicerUrlForNewProject" in REPAIR
    assert "new project from that file" in REPAIR
    assert "/api/repair/" in REPAIR and "/slicer" in REPAIR
    assert "/api/edit/new" not in REPAIR
    assert "new File" not in REPAIR
    assert "rememberRepair" in REPAIR and "reuseRepair" in REPAIR
    assert "download_url" in REPAIR
    page = (ROOT / "static/repair.html").read_text(encoding="utf-8")
    assert 'src="/static/repair.js"' in page
    assert 'id="projectFlow"' in page and 'aria-label="Project stages"' in page
    assert 'data-view="repair"' in page
    flow = (ROOT / "static/project-flow.js").read_text(encoding="utf-8")
    assert "rememberRepair" in flow and "reuseRepair" in flow
    edit = (ROOT / "static/edit.js").read_text(encoding="utf-8")
    assert 'hash.startsWith("slicer")' in edit


def test_body_list_order_is_separate_from_stored_identity():
    """The on-screen list is still centre-sorted. A step stores a stable id, and a missing id is an error."""
    assert "sorted(parts, key=lambda b: tuple(np.round(b.bounds.mean(axis=0), 3))" in CADOPS
    assert "BODY_ATTR" in CADOPS
    assert "does not match any body" in CADOPS
    assert "share the same centre" in CADOPS
