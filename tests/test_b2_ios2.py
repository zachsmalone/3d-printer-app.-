"""IOS-2 static guards (run everywhere, no browser)."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda p: open(os.path.join(ROOT, p), encoding="utf-8").read()


def test_viewport_fit_cover_and_16px_inputs_and_pan_y_strips_exist():
    assert "viewport-fit=cover" in rd("static/index.html")
    css = rd("static/style.css")
    assert "font-size:16px;min-height:44px" in css and "env(safe-area-inset-bottom)" in css and "env(safe-area-inset-top)" in css
    assert "touch-action:pan-y" in css and "100dvh" in css
    assert "html{height:100%}body{min-height:100%}" in css  # body must not become the scroller
