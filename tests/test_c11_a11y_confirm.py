"""Accessible confirm dialog replaces window.confirm for destructive deletes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_history_delete_uses_askConfirm_not_window_confirm():
    app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "askConfirm({" in app
    assert 'confirm("Delete this build' not in app
    assert "dlgConfirm" in (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="confirmOk"' in (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_delete_everything_also_uses_askConfirm():
    js = (ROOT / "static" / "community.js").read_text(encoding="utf-8")
    assert "askConfirm" in js and "Delete everything I made" in js
    assert "window.confirm" not in js
