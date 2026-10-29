"""Expert FDM process fields are real PrusaSlicer keys. A beginner slice does not send them."""
from pathlib import Path

from app.services import slice_engine as eng

ROOT = Path(__file__).resolve().parents[1]


def _ini(opts):
    prof, _s = eng.profile_for("creality_k1", 0.4, opts)
    out = {}
    for line in prof.ini.splitlines():
        if " = " in line:
            k, v = line.split(" = ", 1)
            out[k] = v
    return out


def test_beginner_slice_does_not_invent_expert_keys():
    d = _ini({"preset": "standard"})
    for key in ("seam_position", "ironing", "skirts", "raft_layers", "travel_speed", "min_fan_speed", "infill_overlap"):
        assert key not in d


def test_expert_fields_reach_prusaslicer_keys():
    d = _ini({
        "preset": "standard",
        "seam": "rear",
        "ironing": "top",
        "ironing_flow": "15",
        "support_angle": "40",
        "support_spacing": "3",
        "skirt": "2",
        "skirt_distance": "4",
        "raft": "2",
        "travel_speed": "180",
        "first_layer_speed": "20",
        "fan_min": "40",
        "fan_max": "80",
        "fan_off_layers": "2",
        "infill_overlap": "20",
        "line_width": "0.45",
    })
    assert d["seam_position"] == "rear"
    assert d["ironing"] == "1" and d["ironing_type"] == "topmost" and d["ironing_flowrate"] == "15%"
    assert d["support_material_threshold"] == "40" and d["support_material_spacing"] == "3"
    assert d["skirts"] == "2" and d["skirt_distance"] == "4" and d["raft_layers"] == "2"
    assert d["travel_speed"] == "180" and d["first_layer_speed"] == "20"
    assert d["min_fan_speed"] == "40" and d["max_fan_speed"] == "80" and d["disable_fan_first_layers"] == "2"
    assert d["infill_overlap"] == "20%" and d["extrusion_width"] == "0.45"


def test_ironing_off_and_bad_values_are_explicit():
    assert _ini({"ironing": "off"})["ironing"] == "0"
    for bad in ({"seam": "scarf"}, {"fan_min": "80", "fan_max": "10"}, {"line_width": "2"}):
        try:
            eng.profile_for("creality_k1", 0.4, bad)
        except eng.SliceError:
            continue
        raise AssertionError(bad)


def test_process_sheet_tabs_and_form_fields():
    js = (ROOT / "static" / "printer.js").read_text(encoding="utf-8")
    for name in ("Quality", "Filament", "Strength", "Speed", "Cooling", "Support", "Infill", "Adhesion"):
        assert name in js
    for field in ("seam", "ironing", "ironing_flow", "support_angle", "support_spacing", "skirt", "raft",
                  "travel_speed", "first_layer_speed", "fan_min", "fan_max", "fan_off_layers", "infill_overlap", "line_width"):
        assert f'"{field}"' in js
    assert "mountSlicerPrinter" in js
    assert 'id="devicePick"' in (ROOT / "static" / "index.html").read_text(encoding="utf-8")
