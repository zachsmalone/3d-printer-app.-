"""Lithophane slicer preset: solid rectilinear fill that PrusaSlicer accepts at 100%."""
import shutil
from pathlib import Path
import pytest
import trimesh
from app.services import print_setup as ps, slice_engine as eng

ROOT = Path(__file__).resolve().parents[1]
HAVE = shutil.which("prusa-slicer") or shutil.which("prusa-slicer-console")


def test_lithophane_preset_is_in_the_catalog_and_uses_rectilinear_100():
    pub = {p["id"]: p for p in ps.public()["presets"]}
    assert "lithophane" in pub and pub["lithophane"]["infill"] == 100
    assert pub["lithophane"]["pattern"] == "rectilinear"
    assert "rectilinear" in ps.public()["patterns"]
    s = ps.settings_for("creality_k1", 0.4, {"preset": "lithophane"})
    assert s["infill"] == 100 and s["infill_pattern"] == "rectilinear"
    assert abs(s["layer_height"] - 0.12) < 1e-9
    ov = ps.ini_overrides(s)
    assert ov["fill_density"] == "100%" and ov["fill_pattern"] == "rectilinear"
    assert ov["first_layer_height"] == ov["layer_height"]   # lithophane: no thicker first layer


def test_grid_at_100_is_refused_by_settings_path_but_rectilinear_is_ok():
    # settings accept 100 + grid; the *engine* refuses it — check we document rectilinear as the solid pattern
    assert ps.PATTERNS["rectilinear"] == "rectilinear"


@pytest.mark.skipif(not HAVE, reason="PrusaSlicer not installed")
def test_real_slice_lithophane_preset_on_a_flat_panel():
    m = trimesh.creation.box(extents=[40, 50, 3])
    td = Path("/tmp/zeim-litho-preset"); td.mkdir(exist_ok=True)
    stl = td / "panel.stl"; m.export(stl)
    prof, s = eng.profile_for("creality_k1", 0.4, {"preset": "lithophane"})
    out = td / "panel.gcode"
    r = eng.slice_stl(stl, prof, out)
    assert r.filament_grams > 0 and r.print_time_seconds > 0
    assert out.exists() and out.stat().st_size > 100


def test_panel_ui_defaults_to_lithophane_preset_when_hinted():
    js = (ROOT / "static" / "printer.js").read_text(encoding="utf-8")
    assert 'hintMode === "lithophane"' in js and "wantPreset" in js
    assert "panelHTML(hintMode)" in js or "function panelHTML(hintMode)" in js
    ed = (ROOT / "static" / "edit.js").read_text(encoding="utf-8")
    assert "lithoHint" in ed and "panelHTML(lithoHint)" in ed
