"""Account owns saved work and identity. There is no Projects tab.

#projects, #studio, and #account/studio open Account, where the list is.
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


def test_account_owns_saved_work_and_there_is_no_projects_tab():
    nav = _slice(HTML, 'id="mainNav"', "</nav>")
    views = re.findall(r'data-view="(\w+)"', nav)
    assert "studio" not in views and "projects" not in views
    assert "lithophane" in views and "account" in views
    assert views.count("account") == 1
    assert 'id="viewProjects"' not in HTML
    assert "Open in Projects" not in HTML
    assert "Return to Projects" not in HTML
    assert "View in My Studio" not in HTML
    acc = _slice(HTML, 'id="viewAccount"', 'id="viewLearn"')
    studio = _slice(acc, 'id="meStudio"', "</section>")
    assert "Saved work" in studio
    assert 'id="studioLib"' in studio and 'id="studioLibHelp"' in studio
    assert "Open continues that project" in studio
    assert 'href="#projects"' not in acc and 'href="#studio"' not in studio
    assert 'href="#lithophane"' not in studio
    assert HTML.count('id="studioLib"') == 1
    assert 'id="btnLogin"' in acc and 'id="btnAccount"' in acc
    assert 'id="btnSettings"' in acc and 'id="dlgSettings"' not in acc
    assert acc.index('id="btnLogin"') < acc.index('id="meStudio"')
    assert acc.index('id="meStudio"') < acc.index('id="btnSettings"')


def test_selecting_the_library_is_not_the_lithophane_alias():
    assert 'studio: "lithophane"' not in JS
    assert 'create: "lithophane"' in JS
    assert "routeIntent" in JS and "arriveLibrary" in JS and "openFromLibrary" in JS
    assert "visitLibrary" in LIB
    assert 'raw === "lithophane"' in JS
    assert "LIBRARY_HASH" in LIB and '"#account"' in LIB
    assert '"#projects"' in LIB and '"/#account/studio"' in LIB
    assert 'head === "studio"' in LIB
    assert 'head === "projects"' in LIB
    assert 'view: "account"' in LIB
    assert 'view: "projects"' not in LIB
    create = _slice(HTML, 'id="viewCreate"', 'id="viewShowcase"')
    assert 'id="studioFromMe"' in create and 'href="#account"' in create
    assert "Return to Account" in create
    assert 'id="lithoStudioNote"' in create and 'href="#account"' in create
    assert "#account/studio" not in create
    assert "#projects" not in create
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
