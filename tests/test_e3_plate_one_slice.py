"""E3 gap-check: 'Parts of one print' (POST /api/edit/multi mode=plate) -> ONE project -> ONE slice with every part on it,
through both slicing paths (Edit panel POST /api/slice and the Print dialog POST /api/slice/{bid}). Real PrusaSlicer when installed."""
import re

import pytest
import trimesh

from tests.test_comm_features import U
from tests.test_print_core import HAVE_SLICER


def _plate(c, n=3):
    files = [("files", (f"p{i}.stl", trimesh.creation.box((20, 20, 10 + 5 * i)).export(file_type="stl"), "model/stl")) for i in range(n)]
    j = c.post("/api/edit/multi", files=files, data={"mode": "plate", "printer_id": "creality_k1"}).json()
    assert j["mode"] == "plate" and len(j["projects"]) == 1 and j["plate"]["fits"] and j["plate"]["parts"] == n
    return j["projects"][0], j["plate"]


@pytest.mark.skipif(not HAVE_SLICER, reason="PrusaSlicer not installed")
def test_plate_of_parts_slices_once_with_every_part_on_both_paths():
    c = U("Pe")
    pid, plate = _plate(c)
    r = c.post("/api/slice", data={"model_id": pid, "printer_id": "creality_k1", "nozzle": "0.4"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["model_size_mm"][:2] == plate["footprint_mm"][:2] and j["scaled_pct"] is None   # the arrangement is sliced as laid out
    g = c.get(j["gcode_url"]).text
    xs = [float(x) for x in re.findall(r"^G1 X([\d.]+) Y[\d.]+ E", g, re.M)]
    assert max(xs) - min(xs) >= plate["footprint_mm"][0] - 1                                   # extrusion spans all three parts
    assert g.count(";LAYER_CHANGE") == round(20 / 0.2)                                          # tallest part (20 mm) at 0.2 mm
    legacy = c.post(f"/api/slice/{pid}", data={"layer_height": "0.2", "fill_density": "15"}).json()
    assert legacy["ok"] and legacy["layers"] == g.count(";LAYER_CHANGE")
    assert float(legacy["stats"]["filament_g"]) == pytest.approx(j["filament_grams"], rel=0.02)  # same plate, same answer
