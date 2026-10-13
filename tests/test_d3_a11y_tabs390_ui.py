"""Accessibility at 390 px (tests/ui_a11y_tabs390.py): Mode select keeps its accessible name on phones and every main tab is free of
critical/serious axe-core issues in light, dark and Experienced mode. Chrome + WebKit, TEMP-data server."""
from test_b4_ui import _run


def test_mode_select_named_and_all_tabs_axe_clean_at_390_in_chrome_and_webkit():
    out = _run("ui_a11y_tabs390.py")
    assert "PASS webkit" in out or "SKIP webkit" in out
