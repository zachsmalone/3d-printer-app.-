"""Print time + filament cost estimate: grams / metres / time come from PrusaSlicer's G-code comments; the cost is
grams x the user's own price per kg (browser only, per material) and is always labelled an estimate. No payments."""
import os
import trimesh
from fastapi.testclient import TestClient

from app.main import app
from app.services import slice_engine as eng

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_gcode_stats_give_time_and_grams(tmp_path):
    g = tmp_path / "x.gcode"
    g.write_text("; filament used [mm] = 1234.5\n; filament used [g] = 3.70\n; total filament used [g] = 3.70\n"
                 "; estimated printing time (normal mode) = 1h 2m 3s\n")
    assert eng.parse_gcode_stats(g) == (3723, 3.7)


def test_slice_response_carries_the_numbers_the_cost_box_uses(tmp_path, monkeypatch):
    client = TestClient(app)
    stl = trimesh.creation.box(extents=(15, 15, 8)).export(file_type="stl")

    def fake_slice(model, profile, out_gcode, *, bounds_stl=None):
        out_gcode.write_text("; filament used [mm] = 2500.0\n; total filament used [g] = 7.45\n"
                             "; estimated printing time (normal mode) = 25m 10s\n")
        return eng.SliceResult(out_gcode, 1510, 7.45, (15.0, 15.0, 8.0), profile)

    monkeypatch.setattr(eng, "slice_model_path", fake_slice)
    r = client.post("/api/slice", data={"printer_id": "creality_k1", "nozzle": "0.4", "material": "PLA"},
                    files={"file": ("t.stl", stl, "application/sla")})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["filament_grams"] == 7.45 and b["print_time_seconds"] == 1510 and b["filament_mm"] == 2500.0
    assert b["settings"]["material"] == "PLA"
    assert not any(k for k in b if "price" in k or "cost" in k)          # the server never prices anything


def test_cost_box_is_an_estimate_kept_in_the_browser_and_never_a_payment():
    js = open(os.path.join(ROOT, "static", "cost.js"), encoding="utf-8").read()
    pj = open(os.path.join(ROOT, "static", "printer.js"), encoding="utf-8").read()
    assert "costHTML(r)" in pj and "wireCost()" in pj
    assert "Estimate" in js and "leaves out power, failed prints" in js and "stays in this browser" in js
    assert "localStorage" in js and "fetch(" not in js and "api(" not in js            # nothing sent to the server
    assert "grams / 1000 * perKg" in js
    for bad in ("stripe", "checkout", "pay now", "subscribe"):
        assert bad not in js.lower()


def test_cost_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_cost.py")
    assert "PASS webkit" in out, out
