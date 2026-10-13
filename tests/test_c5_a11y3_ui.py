"""Accessibility round 3 leftovers (tests/ui_a11y3.py): names for every control incl. dialogs + Edit tools, real Settings tabs,
aria-pressed Showcase lists, a describing 3D-preview label, and the keyboard photo-pick + Build path re-checked. Chrome + WebKit."""
import os, re

from test_b4_ui import _run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_a11y_round3_names_tabs_pressed_viewer_label_keyboard_build_in_chrome_and_webkit():
    out = _run("ui_a11y3.py")
    assert "PASS webkit" in out or "SKIP webkit" in out


def test_static_dialog_fields_have_label_for_and_settings_uses_tab_roles():
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    for i in ("s_layer", "s_fill", "s_brim", "set_base", "pub_vis", "pub_title", "pub_desc", "pub_tags"):
        assert f'<label for="{i}"' in html, i
    tl = re.search(r'<div class="tabs" role="tablist"[^>]*>(.*?)</div>', html, re.S)
    assert tl and tl.group(1).count('role="tab"') == 2 and 'aria-selected="true"' in tl.group(1)
    assert html.count('role="tabpanel"') == 2
    assert 'id="shTabs" role="group" aria-label=' in html
    assert re.search(r'id="btnToggleP13n">[^<]+</button>', html)          # never an empty button, even before the dialog fills it
