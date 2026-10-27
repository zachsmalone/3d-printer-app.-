"""My Studio is a section on Me. #studio still opens the existing Studio page.
Recent builds ("Pick up where you left off") stay on that Studio page, not on Lithophane."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "community.js").read_text(encoding="utf-8")


def _slice(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_studio_is_a_me_section_and_not_a_new_tab():
    nav = _slice(HTML, 'id="mainNav"', "</nav>")
    views = re.findall(r'data-view="(\w+)"', nav)
    assert "studio" not in views
    assert "lithophane" in views and "account" in views
    acc = _slice(HTML, 'id="viewAccount"', "</main>")
    studio = _slice(acc, 'id="meStudio"', "</section>")
    assert "My Studio" in studio and 'href="#studio"' in studio and 'id="btnMyStudio"' in studio
    assert "Open Studio" in studio
    assert "btnSettings" not in studio
    assert 'id="btnSettings"' in acc and 'id="dlgSettings"' not in acc


def test_lithophane_tab_points_at_me_and_studio_routes_stay():
    create = _slice(HTML, 'id="viewCreate"', 'id="viewShowcase"')
    assert 'id="studioFromMe"' in create and 'href="#account"' in create
    assert 'id="lithoStudioNote"' in create and 'href="#studio"' in create
    assert 'studio: "lithophane"' in JS and 'create: "lithophane"' in JS
    assert 'show(v, fromMe ? "account"' in JS
    assert 'raw === "lithophane"' in JS
    assert "ai3d_enabled" in JS and "/api/subscriptions/me" in JS


def test_recent_builds_belong_to_studio_not_the_shared_lithophane_page():
    create = _slice(HTML, 'id="viewCreate"', 'id="viewEdit"')
    assert 'id="recentBuilds"' in create
    assert 'Pick up where you left off' in create
    assert re.search(r'<section class="history" id="recentBuilds" hidden>', create)
    fn = JS[JS.index("function paintStudioHome"):JS.index("function route")]
    assert '$("#recentBuilds")' in fn
    assert "recent.hidden = !fromMe" in fn
    assert "STUDIO_FROM_ME" in JS and 'studio: "lithophane"' in JS
