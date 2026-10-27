"""Workspace layout keeps the strings the lithophane test locks, and grows remove plus edge resize."""
from pathlib import Path


def test_wslayout_keeps_layout_strings_and_adds_remove_resize():
    js = Path("static/wslayout.js").read_text(encoding="utf-8")
    for s in (
        "function watchObstacles()",
        "watchObstacles();",
        "undo the trial edges' classes",
        "chipPri",
        "layout does not minimise or hide another panel",
        "a core panel never steps aside",
    ):
        assert s in js
    assert "userSize" in js and 'data-dir="n"' in js and "Remove" in js and "interacting" in js
    assert 'classList.add("min", "auto-min")' not in js
    assert 'classList.add("auto-off")' not in js
    assert 'dataset.crowded = "1"' not in js
