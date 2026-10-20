"""Warm light is the default look and the violet gradient is gone; the colour pairs in static/style.css meet WCAG 2.x contrast in BOTH themes
(recomputed here from the CSS itself, so a later colour edit that breaks contrast fails a test)."""
import re
from pathlib import Path

CSS = (Path(__file__).parent.parent / "static" / "style.css").read_text(encoding="utf-8")


def tokens(block_start):
    i = CSS.index(block_start); j = CSS.index("}", i)
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9a-fA-F]{6})", CSS[i:j]))


LIGHT = tokens(":root{")
DARK = {**LIGHT, **tokens("html[data-theme=dark]{")}


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT = [("txt", "bg"), ("txt", "panel"), ("txt", "panel2"), ("mut", "bg"), ("mut", "panel"), ("mut", "panel2"), ("txt", "tint"), ("mut", "tint"),
        ("accink", "bg"), ("accink", "panel"), ("accink", "tint"), ("on-acc", "acc"), ("warm", "bg"), ("txt", "warmtint"),
        ("ok", "okbg"), ("bad", "badbg"), ("txt", "okbg"), ("txt", "badbg")]
NONTEXT = [("ctl", "bg"), ("ctl", "panel"), ("ctl", "panel2"), ("focus", "bg"), ("focus", "panel"), ("warm", "panel")]


import pytest


@pytest.mark.parametrize("theme,t", [("light", LIGHT), ("dark", DARK)])
def test_text_pairs_are_at_least_4_5_to_1(theme, t):
    bad = [(a, b, round(ratio(t[a], t[b]), 2)) for a, b in TEXT if ratio(t[a], t[b]) < 4.5]
    assert not bad, (theme, bad)


@pytest.mark.parametrize("theme,t", [("light", LIGHT), ("dark", DARK)])
def test_control_borders_and_focus_ring_are_at_least_3_to_1(theme, t):
    bad = [(a, b, round(ratio(t[a], t[b]), 2)) for a, b in NONTEXT if ratio(t[a], t[b]) < 3]
    assert not bad, (theme, bad)


def test_light_is_the_default_and_the_violet_gradient_and_old_brand_violet_are_gone():
    assert LIGHT["bg"].lower() == "#f7f7f8" and LIGHT["acc"].lower() == "#0066ff" and "color-scheme:light" in CSS[CSS.index(":root{"):].split("}")[0]
    assert "prefers-color-scheme:dark" not in CSS.replace(" ", "")          # dark only when the person chose it
    assert "#7c5cff" not in CSS.lower() and "linear-gradient(135deg,var(--acc)" not in CSS
    idx = (Path(__file__).parent.parent / "static" / "index.html").read_text()
    assert 't==="dark"' in idx[:idx.index("</head>")]          # saved choice wins; OS preference only when nothing is saved (inline head snippet)


def test_brand_logo_variants_icons_and_palette():
    root = Path(__file__).parent.parent / "static"
    idx = (root / "index.html").read_text()
    assert "/static/zeim-logo.png" in idx and "/static/zeim-logo-dark.png" in idx and "apple-touch-icon" in idx
    for f in ("zeim-logo.png", "zeim-logo-dark.png", "favicon.png", "favicon.ico", "apple-touch-icon.png"):
        assert (root / f).stat().st_size > 1000, f
    css = (root / "style.css").read_text()
    assert "html[data-theme=dark] .logo-dark{display:block" in css
    assert LIGHT["txt"].lower() == "#0a0a0a" and LIGHT["ctl"].lower() == "#8a8a8a" and LIGHT["mut"].lower() != "#8a8a8a"   # grey only for borders
