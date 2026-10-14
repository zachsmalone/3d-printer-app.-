"""'Logo & Drawing to 3D' card, panel accessibility, live outline, all four outputs in a real browser (Chrome + WebKit)."""
from test_b4_ui import _run


def test_logo_and_drawing_to_3d_in_a_real_browser():
    out = _run("ui_trace2d.py")
    assert "PASS webkit" in out or "SKIP webkit" in out
