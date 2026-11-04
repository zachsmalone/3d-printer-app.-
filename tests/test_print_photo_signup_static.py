"""Visitors without an account must be shown a way to add a print photo (the form used to vanish silently)."""
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "community.js").read_text()


def test_signed_out_visitors_get_a_signup_prompt():
    assert 'id="prAcct"' in JS and "Sign up to add a photo" in JS
    assert '$("#prAcct").onclick' in JS and "__prWantItem = id" in JS


def test_project_reopens_with_form_after_account_dialog_closes():
    assert '$("#dlgAccount").addEventListener("close"' in JS
    assert "await refreshMe()" in JS and "await openItem(id)" in JS
