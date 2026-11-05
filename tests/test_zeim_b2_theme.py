"""B2 production theme: self-hosted type, section accents, FDM wave only in the top banner."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")
CSS = open(os.path.join(STATIC, "zeim-b2.css"), encoding="utf-8").read()
HTML = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
JS = open(os.path.join(STATIC, "community.js"), encoding="utf-8").read()
CAD = open(os.path.join(STATIC, "cad.html"), encoding="utf-8").read()

FONTS = (
    "inter-latin-400-normal.woff2",
    "inter-latin-500-normal.woff2",
    "inter-latin-600-normal.woff2",
    "inter-latin-700-normal.woff2",
    "jetbrains-mono-latin-400-normal.woff2",
    "jetbrains-mono-latin-500-normal.woff2",
    "shippori-mincho-latin-600-normal.woff2",
    "shippori-mincho-latin-700-normal.woff2",
    "shippori-mincho-seal-600.woff2",
    "shippori-mincho-seal-700.woff2",
)


def test_stylesheet_loads_after_section_themes_and_sets_section_key():
    i = HTML.index('href="/static/zeim-themes.css"')
    j = HTML.index('href="/static/zeim-b2.css"')
    assert i < j
    assert '<body data-zsec="showcase">' in HTML
    assert "document.body.dataset.zsec = view" in JS
    assert "zeim-b2" not in CAD


def test_fonts_are_self_hosted_and_google_fonts_are_absent():
    assert "fonts.googleapis" not in CSS and "fonts.gstatic" not in CSS
    assert "fonts.googleapis" not in HTML and "fonts.gstatic" not in HTML
    for name in FONTS:
        path = os.path.join(STATIC, "fonts", name)
        assert os.path.getsize(path) > 500, name
        assert f"/static/fonts/{name}" in CSS
    assert "Shippori Mincho" in CSS and "JetBrains Mono" in CSS and 'font-family:"Inter"' in CSS
    for lic in ("LICENSE-inter.txt", "LICENSE-jetbrains-mono.txt", "LICENSE-shippori-mincho.txt"):
        assert os.path.getsize(os.path.join(STATIC, "fonts", lic)) > 200


def test_no_universal_background_image_reset():
    """themeA's element-wide background-image:none would strip a wave painted on .topbar."""
    assert "*:not(svg)" not in CSS
    assert re.search(r"body\s+\*", CSS) is None


def test_fdm_wave_is_only_on_the_topbar_pseudo_element():
    assert os.path.getsize(os.path.join(STATIC, "zt", "wave-dark.png")) > 1000
    assert os.path.getsize(os.path.join(STATIC, "zt", "wave-dark-bg.jpg")) > 1000
    assert CSS.count('url("/static/zt/wave-dark.png")') == 1
    rule = CSS[CSS.index('body[data-zsec="slicer"] .topbar::before'):]
    assert 'url("/static/zt/wave-dark.png")' in rule[:900]
    # plate, stage, and page edges are explicitly cleared
    for sel in (
        'body[data-zsec="slicer"] .viewer',
        'body[data-zsec="slicer"] #editViewer',
        'body[data-zsec="slicer"] main.zws::before',
        'body[data-zsec="slicer"] main.zws::after',
        'body[data-zsec="slicer"]::before',
        'body[data-zsec="slicer"]::after',
        'body[data-zsec="slicer"] .zt-wave',
    ):
        assert sel in CSS
    assert "background-image:none!important" in CSS[CSS.index('body[data-zsec="slicer"] .viewer'):CSS.index('body[data-zsec="slicer"] .viewer') + 280]


def test_header_motto_replaces_brush_writing_beside_the_seal():
    bar = HTML[HTML.index('<header class="topbar">'):HTML.index("</header>")]
    brand = bar[bar.index('<a class="brand"'):bar.index("</a>") + 4]
    assert "Uno loco aedificamus" not in brand
    assert 'class="brand-motto"' in bar
    assert "Uno loco aedificamus" in bar and "We build in one place" in bar
    assert 'content:"\\7CBE"' in CSS
    motto = CSS[CSS.index(".brand-motto"):CSS.index(".brand-motto") + 900]
    assert "var(--serif)" in motto and "var(--gold" in motto
    phone = CSS[CSS.index("@media (max-width:768px)"):]
    assert ".brand-motto-en{display:none}" in phone[:500]
    # the FDM wave rule is still the only wave, on the topbar pseudo-element
    assert CSS.count('url("/static/zt/wave-dark.png")') == 1
    assert 'body[data-zsec="slicer"] .topbar::before' in CSS


def test_showcase_and_account_accents_override_hard_coded_washes():
    assert 'body[data-zsec="showcase"]' in CSS and "#F4A7B9" in CSS
    assert 'body[data-zsec="account"]' in CSS and "--gold:#C9A227" in CSS
    assert 'body[data-zsec="account"] #viewAccount' in CSS
    assert "#shGo" in CSS  # search stays a neutral control, not the section fill
    assert 'body[data-zsec="torchc0"]' in CSS and 'body[data-zsec="lithophane"]' in CSS
