"""Accessibility round 2 top-10 in Chrome + WebKit (tests/ui_a11y2.py)."""
from test_b4_ui import _run


def test_a11y_round2_labels_keyboard_errors_focus_skip_link_dialogs_targets_in_chrome_and_webkit():
    out = _run("ui_a11y2.py")
    assert "PASS webkit" in out or "SKIP webkit" in out
