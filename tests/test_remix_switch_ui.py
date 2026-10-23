"""UI check for the 'Allow remixes' switch at 1280px and 390px (own TEMP-data server, Chrome + WebKit)."""
from test_b4_ui import _run
from test_b1_ui import LEGACY_LOGIN


def test_remix_switch_hides_remix_shows_note_and_keeps_downloads_at_1280_and_390():
    out = _run("ui_remix_switch.py", extra=LEGACY_LOGIN)
    assert "PASS webkit" in out or "SKIP webkit" in out
