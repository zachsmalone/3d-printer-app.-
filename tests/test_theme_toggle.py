"""Static checks for the Dark mode toggle: no-flash inline head snippet on every page, CSP allows it, button markup is accessible."""
from pathlib import Path
from fastapi.testclient import TestClient
S = Path(__file__).parent.parent / "static"
SNIP = 'matchMedia("(prefers-color-scheme: dark)")'

def test_every_page_has_head_snippet_before_stylesheet():
    for f in ("index.html", "privacy.html", "terms.html", "COMMUNITY_GUIDELINES.html", "moderation.html"):
        h = (S / f).read_text()
        head = h[:h.index("</head>")]
        assert SNIP in head and "/static/theme.js" in head, f

def test_toggle_markup_accessible_and_last_in_topbar():
    h = (S / "index.html").read_text()
    bar = h[h.index('<header class="topbar">'):h.index("</header>")]
    tail = bar[bar.rindex("<button"):]
    assert 'id="themeToggle"' in tail and 'aria-pressed="false"' in tail and 'aria-label="Dark mode"' in tail

def test_theme_js_persists_and_sets_aria():
    js = (S / "theme.js").read_text()
    assert 'localStorage.theme = d ? "dark" : "light"' in js and '"aria-pressed"' in js

def test_csp_allows_inline_theme_snippet_and_pages_serve():
    from app.main import app, CSP
    import base64, hashlib, re
    h = (S / "index.html").read_text()
    body = re.search(r"<script>(.*?)</script>", h, re.S).group(1)
    assert base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() in CSP
    c = TestClient(app)
    assert c.get("/static/theme.js").status_code == 200

def test_css_has_toggle_target_and_dark_viewer():
    css = (S / "style.css").read_text()
    assert ".themetoggle{" in css and "width:44px;height:44px" in css and "--sunk:var(--sunk)" not in css
    assert "--stage1:#1b2232" in css


def test_nav_has_the_six_tabs_in_order_and_showcase_is_default():
    import re
    h = (S / "index.html").read_text()
    nav = h[h.index('id="mainNav"'):h.index("</nav>")]
    assert re.findall(r'data-view="(\w+)"', nav) == ["showcase", "slicer", "cad", "lithophane", "smartfix", "account"]
    assert '<main class="page" id="viewShowcase">' in h and 'id="viewCreate" hidden' in h
    acc = h[h.index('id="viewAccount"'):]
    acc = acc[:acc.index("</main>")]
    assert 'id="btnAccount"' in acc and 'id="btnSettings"' in acc and 'id="btnCreatePhoto"' in h
