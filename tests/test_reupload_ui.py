"""UI check for re-upload protection at 1280px and 390px (own TEMP-data server with the duplicate check ON)."""
from test_b4_ui import _run
from test_b1_ui import LEGACY_LOGIN


def test_reupload_offer_refusal_and_report_a_copy_at_1280_and_390():
    out = _run("ui_reupload.py", extra={**LEGACY_LOGIN, "PHOTO3D_DUPLICATE_CHECK": "1"})
    assert "PASS webkit" in out or "SKIP webkit" in out
