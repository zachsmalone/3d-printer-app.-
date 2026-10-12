"""Originals-first Showcase in Chrome + WebKit (tests/ui_originals.py against a TEMP-data server using the fixture library)."""
from test_b4_ui import _run


def test_originals_cards_filters_download_and_class_hiding_in_chrome_and_webkit():
    out = _run("ui_originals.py")
    assert "PASS webkit" in out or "SKIP webkit" in out
