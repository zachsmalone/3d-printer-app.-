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


GRAINS = {
    "showcase": ("grain-cherry.svg", "cherry"),
    "slicer": ("grain-cypress.svg", "cypress"),
    "torchc0": ("grain-maple.svg", "maple"),
    "cad": ("grain-wenge.svg", "wenge"),
    "lithophane": ("grain-beech.svg", "beech"),
    "account": ("grain-walnut.svg", "walnut"),
}


def test_each_section_has_its_own_faint_wood():
    """Original SVG tiles, one species per section, never on the FDM plate or resin preview."""
    for sec, (name, wood) in GRAINS.items():
        path = os.path.join(STATIC, "zt", name)
        text = open(path, encoding="utf-8").read()
        size = os.path.getsize(path)
        assert 400 < size < 6000, (name, size)
        assert f'data-wood="{wood}"' in text
        assert "<script" not in text.lower()
        assert "fonts.google" not in text and "fonts.gstatic" not in text
        assert 'href="http' not in text and "url(http" not in text
        assert text.count("http://") == 1 and "http://www.w3.org/2000/svg" in text
        for n in re.findall(r'(?:stroke-opacity|fill-opacity)="([0-9.]+)"', text):
            assert float(n) <= 0.16, (name, n)
        nums = [float(x) for x in re.search(r'feColorMatrix values="([^"]+)"', text).group(1).split()]
        assert len(nums) == 20 and nums[18] <= 0.16, name
        i = CSS.index(f'body[data-zsec="{sec}"]')
        assert name in CSS[i:i + 420], sec
    field = CSS[CSS.index("Faint wood on the page field"):CSS.index("Resin preview canvas")]
    assert "#viewEdit" not in field and "slicer" not in field
    plate = CSS[CSS.index('body[data-zsec="slicer"] .viewer'):CSS.index('body[data-zsec="slicer"] .ctxbar')]
    assert "grain-" not in plate
    assert "background-image:none!important" in plate
    resin = CSS[CSS.index("body[data-zsec] .rzView"):CSS.index("body[data-zsec] .rzView") + 180]
    assert "background-image:none!important" in resin
    # the old single fiber remains only as the fallback for sections without a named wood
    assert CSS.count("--washi-tex:url(\"/static/zt/grain-") == 6


def test_header_motto_sits_beside_the_logo_without_the_seal():
    bar = HTML[HTML.index('<header class="topbar">'):HTML.index("</header>")]
    brand = bar[bar.index('<a class="brand"'):bar.index("</a>") + 4]
    assert "Uno loco aedificamus" not in brand
    assert 'class="brand-motto"' in bar
    assert "Uno loco aedificamus" in bar and "We build in one place" in bar
    assert 'content:"\\7CBE"' not in CSS
    assert "body[data-zsec] .brand::after" not in CSS
    motto = CSS[CSS.index(".brand-motto"):CSS.index(".brand-motto") + 900]
    assert "var(--serif)" in motto and "var(--gold" in motto
    assert "padding:1px 0 0 22px" not in CSS
    assert "gap:8px" in CSS[CSS.index(".brandlock"):CSS.index(".brandlock") + 180]
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
