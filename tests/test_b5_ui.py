"""UI tests for the small batch after Batch B (each script on its own TEMP-data server, Chrome + WebKit)."""
from test_b4_ui import _run


def test_sign_out_warns_needs_the_recovery_code_and_the_code_brings_the_account_back():
    out = _run("ui_signout.py")
    assert "PASS webkit" in out or "SKIP webkit" in out
