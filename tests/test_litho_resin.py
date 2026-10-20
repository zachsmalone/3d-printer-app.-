"""Lithophane 'Resin' printer type: thinner walls + finer detail defaults beside filament (starting suggestions)."""
from pathlib import Path

from PIL import Image

from app.core import autotune as at

ROOT = Path(__file__).resolve().parent.parent
IM = Image.new("RGB", (800, 600), (128, 128, 128))


def test_resin_defaults_are_thinner_and_finer_than_filament():
    fil, _ = at.autotune(IM, "lithophane", 100, "standard")
    res, notes = at.autotune(IM, "lithophane", 100, "standard", "resin")
    assert (fil["min_thickness"], fil["max_thickness"]) == (0.8, 3.2)          # filament unchanged
    assert res["min_thickness"] == 0.5 and 2.5 <= res["max_thickness"] <= 3.0
    assert res["resolution"] > fil["resolution"]
    assert any(n["label"] == "Printer type" and "suggestion" in n["why"] for n in notes)
    for p in at.PRESETS:
        lo = at.autotune(IM, "lithophane", 100, p, "resin")[0]
        assert 0.5 <= lo["min_thickness"] < lo["max_thickness"] <= 3.0


def test_unknown_material_falls_back_and_other_modes_ignore_it():
    assert at.autotune(IM, "lithophane", 100, "standard", "wood")[0] == at.autotune(IM, "lithophane", 100, "standard")[0]
    assert at.autotune(IM, "relief", 100, "standard", "resin")[0] == at.autotune(IM, "relief", 100, "standard")[0]


def test_resin_option_is_wired_into_ui_and_api():
    html = (ROOT / "static" / "index.html").read_text()
    assert 'id="lithMaterial"' in html and 'value="resin"' in html and 'value="filament"' in html and 'for="lithMaterial"' in html
    js = (ROOT / "static" / "app.js").read_text()
    assert 'fd.append("material"' in js and "resin: { thk: [[0.5, 2.5], [0.5, 2.8], [0.6, 3.0]]" in js and "#lithMatBox" in js
    api = (ROOT / "app" / "api" / "builds.py").read_text()
    assert 'material: str = Form("filament")' in api and "'material'" in api and "material must be filament or resin" in api
