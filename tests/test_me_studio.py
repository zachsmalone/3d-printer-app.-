"""Me owns My Studio. Projects owns the saved-work list.

#account/studio stays on Account and does not render the list.
#projects and the old #studio bookmark open that list.
They do not open Lithophane. #create still opens the photo workspace.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "community.js").read_text(encoding="utf-8")
LIB = (ROOT / "static" / "studio-library.js").read_text(encoding="utf-8")


def _slice(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_me_owns_studio_and_projects_owns_the_list():
    nav = _slice(HTML, 'id="mainNav"', "</nav>")
    views = re.findall(r'data-view="(\w+)"', nav)
    assert "studio" not in views
    assert "projects" in views and "lithophane" in views and "account" in views
    acc = _slice(HTML, 'id="viewAccount"', 'id="viewLearn"')
    studio = _slice(acc, 'id="meStudio"', "</section>")
    assert "My Studio" in studio
    assert 'href="#projects"' in studio
    assert 'id="btnOpenProjects"' in studio
    assert "Open in Projects" in studio
    assert 'id="studioLib"' not in acc
    assert 'data-lib="open"' not in acc
    assert "This is Projects" not in acc
    assert 'href="#studio"' not in studio
    assert 'href="#lithophane"' not in studio
    assert "Open Studio" not in studio
    projects = _slice(HTML, 'id="viewProjects"', 'id="viewAccount"')
    assert 'id="studioLib"' in projects
    assert 'id="studioLibHelp"' in projects
    assert 'id="btnViewStudio"' in projects
    assert 'href="#account/studio"' in projects
    assert "View in My Studio" in projects
    assert 'id="btnLogin"' not in projects
    assert 'id="btnSettings"' in acc and 'id="dlgSettings"' not in acc


def test_selecting_the_library_is_not_the_lithophane_alias():
    assert 'studio: "lithophane"' not in JS
    assert 'create: "lithophane"' in JS
    assert "routeIntent" in JS and "arriveLibrary" in JS and "openFromLibrary" in JS
    assert "visitLibrary" in LIB
    assert 'raw === "lithophane"' in JS
    assert "LIBRARY_HASH" in LIB and '"#projects"' in LIB
    assert 'head === "studio"' in LIB
    assert 'head === "projects"' in LIB
    create = _slice(HTML, 'id="viewCreate"', 'id="viewShowcase"')
    assert 'id="studioFromMe"' in create and 'href="#projects"' in create
    assert 'id="lithoStudioNote"' in create and 'href="#projects"' in create
    assert "#account/studio" not in create
    assert 'id="btnCreatePhoto"' in HTML
    photo = HTML[HTML.index('id="btnCreatePhoto"') - 120:HTML.index('id="btnCreatePhoto"')]
    assert 'href="#create"' in photo
    assert "#studio" not in photo


def test_recent_builds_block_stays_off_the_lithophane_page():
    create = _slice(HTML, 'id="viewCreate"', 'id="viewEdit"')
    assert 'id="recentBuilds"' in create
    assert re.search(r'<section class="history" id="recentBuilds" hidden>', create)
    fn = JS[JS.index("function paintStudioHome"):JS.index("function paintStudioLibrary")]
    assert '$("#recentBuilds")' in fn
    assert "recent.hidden = true" in fn
    assert "STUDIO_FROM_ME" not in JS
