"""Multi-object plate: 2D footprint bin-pack (fits / spacing / out-of-bed warning / 0-90 deg turns), copies with a count,
split overflow onto another plate, and a 4-object plate sliced as ONE PrusaSlicer plate with separate objects."""
import re

import numpy as np
import pytest
import trimesh

from app.core import arrange, plate
from tests.test_comm_features import U
from tests.test_print_core import HAVE_SLICER


def _overlap(a, b, gap=0.0):
    return (a["x"] < b["x"] + b["w"] + gap - 1e-6 and b["x"] < a["x"] + a["w"] + gap - 1e-6
            and a["y"] < b["y"] + b["d"] + gap - 1e-6 and b["y"] < a["y"] + a["d"] + gap - 1e-6)


def test_pack_fits_inside_the_bed():
    r = arrange.pack([(60, 40)] * 8, (220, 220), 5)
    assert r["fits"] and r["plates"] == 1 and not r["overflow"]
    for it in r["items"]:
        assert -110 - 1e-6 <= it["x"] and it["x"] + it["w"] <= 110 + 1e-6
        assert -110 - 1e-6 <= it["y"] and it["y"] + it["d"] <= 110 + 1e-6


@pytest.mark.parametrize("gap", [0, 5, 12.5])
def test_pack_keeps_the_spacing(gap):
    r = arrange.pack([(30, 20), (50, 50), (20, 70), (40, 10), (25, 25)], (220, 220), gap)
    its = r["items"]
    for i in range(len(its)):
        for j in range(i + 1, len(its)):
            assert not _overlap(its[i], its[j], gap), (gap, its[i], its[j])


def test_pack_out_of_bed_warns_and_spills_never_refuses():
    r = arrange.pack([(100, 100)] * 5, (220, 220), 5)
    assert not r["fits"] and r["plates"] == 2 and len(r["overflow"]) == 1
    big = arrange.pack([(300, 20), (20, 20)], (220, 220), 5)
    assert not big["fits"] and big["too_big"] == [0] and 0 in big["overflow"]
    assert all(it is not None for it in big["items"])


def test_pack_uses_90_degree_turns():
    # two 200 x 30 bars + a 30 x 200 bar fit a 220 bed only if the third is turned (or the first two)
    sizes = [(200, 30), (200, 30), (200, 30), (30, 200)]
    with_rot = arrange.pack(sizes, (220, 220), 5, rotate=True)
    assert with_rot["fits"] and any(it["rot"] == 90 for it in with_rot["items"])
    tall = arrange.pack([(30, 210)], (220, 100), 5, rotate=False)
    assert not tall["fits"]
    assert arrange.pack([(30, 210)], (220, 100), 5, rotate=True)["fits"]


def test_footprint_uses_the_hull_box():
    pts = np.array([[0, 0], [10, 0], [10, 5], [0, 5], [5, 2]])
    assert arrange.footprint(pts) == pytest.approx((0, 0, 10, 5))


def _boxes(n, s=(40, 30, 10)):
    ms = [trimesh.creation.box(s) for _ in range(n)]
    return trimesh.util.concatenate(ms), {"counts": [12] * n, "groups": list(range(n)), "hidden": [False] * n}


def test_plate_arrange_reports_overflow_and_turns_meshes():
    m, L = _boxes(2, (150, 30, 10))
    m2, rep = plate.apply(m, {"layout": L, "action": "arrange", "bed": [100, 200, 200], "gap": 5})
    a = rep["arrange"]
    assert a["fits"] and a["rotated"], a                              # 150 long only fits a 100-wide bed turned 90
    d = plate.describe(m2, rep["layout"], (100, 200, 200))
    assert all(not o["warnings"] for o in d["objects"]), d
    m, L = _boxes(6, (100, 100, 10))
    m3, rep = plate.apply(m, {"layout": L, "action": "arrange", "bed": [220, 220, 250], "gap": 5})
    assert not rep["arrange"]["fits"] and len(rep["arrange"]["overflow"]) == 2 and "didn't fit" in rep["message"]
    d = plate.describe(m3, rep["layout"], (220, 220, 250))
    assert sum(bool(o["warnings"]) for o in d["objects"]) == 2          # the spilled two are flagged, nothing blocks


def test_duplicate_with_count_then_arrange():
    m, L = _boxes(1)
    m2, rep = plate.apply(m, {"layout": L, "action": "duplicate", "sel": [0], "count": 3})
    assert len(rep["layout"]["counts"]) == 4
    m3, rep3 = plate.apply(m2, {"layout": rep["layout"], "action": "arrange", "gap": 5})
    assert rep3["arrange"]["fits"]
    assert all(not o["warnings"] for o in plate.describe(m3, rep3["layout"])["objects"])


def _plate4(c, n=4, size=20):
    files = [("files", (f"p{i}.stl", trimesh.creation.box((size, size, 10)).export(file_type="stl"), "model/stl")) for i in range(n)]
    j = c.post("/api/edit/multi", files=files, data={"mode": "plate", "printer_id": "creality_k1"}).json()
    return j["projects"][0]


def test_api_arrange_with_printer_bed_and_split():
    c = U("Mp")
    pid = _plate4(c, 6, 100)
    r = c.post(f"/api/edit/{pid}/op", json={"op": "plate", "params": {"action": "arrange", "gap": 5, "printer_id": "creality_k1"}})
    assert r.status_code == 200, r.text
    j = r.json()
    rep = j.get("report") or {}
    assert rep["arrange"]["bed_mm"][:2] == [220.0, 220.0] and not rep["arrange"]["fits"]
    s = c.post(f"/api/edit/{pid}/plate/split", json={"gap": 5, "printer_id": "creality_k1"})
    assert s.status_code == 200, s.text
    s = s.json()
    assert s["split"] and s["new_project"] and s["moved"] == 2
    assert len(s["project"]["plate"]["objects"]) == 4 and all(not o["warnings"] for o in s["project"]["plate"]["objects"])
    new = c.get(f"/api/edit/{s['new_project']}").json()
    assert len(new["plate"]["objects"]) == 2 and all(not o["warnings"] for o in new["plate"]["objects"])
    again = c.post(f"/api/edit/{pid}/plate/split", json={"printer_id": "creality_k1"}).json()
    assert again["split"] is False


@pytest.mark.skipif(not HAVE_SLICER, reason="PrusaSlicer not installed")
def test_api_slices_a_4_object_plate_as_one_plate():
    c = U("Ms")
    pid = _plate4(c, 4, 20)
    r = c.post(f"/api/edit/{pid}/op", json={"op": "plate", "params": {"action": "arrange", "gap": 10, "printer_id": "creality_k1"}})
    assert r.status_code == 200, r.text
    objs = r.json()["plate"]["objects"]
    assert len(objs) == 4
    s = c.post("/api/slice", data={"model_id": pid, "printer_id": "creality_k1", "nozzle": "0.4"})
    assert s.status_code == 200, s.text
    j = s.json()
    assert j["plate_objects"] == 4
    g = c.get(j["gcode_url"]).text
    xs = [float(x) for x in re.findall(r"^G1 X([\d.]+) Y[\d.]+ E", g, re.M)]
    ys = [float(y) for y in re.findall(r"^G1 X[\d.]+ Y([\d.]+) E", g, re.M)]
    lo = np.min([o["min"][:2] for o in objs], axis=0); hi = np.max([o["max"][:2] for o in objs], axis=0)
    assert max(xs) - min(xs) >= hi[0] - lo[0] - 1 and max(ys) - min(ys) >= hi[1] - lo[1] - 1
    # ZEIM's layout is kept (--dont-arrange): no extrusion in the middle of the gap between neighbouring objects
    o = sorted(objs, key=lambda o: (o["min"][1], o["min"][0]))
    off = np.array([110, 110]) - (lo + hi) / 2                         # fit_to_printer centres the plate on the bed
    a, b = o[0], o[1]
    gx = (a["max"][0] + b["min"][0]) / 2 + off[0] if b["min"][0] > a["max"][0] else None
    if gx is not None:
        assert not any(abs(x - gx) < 1.0 and a["min"][1] + off[1] + 2 < y < a["max"][1] + off[1] - 2 for x, y in zip(xs, ys))


@pytest.mark.skipif(not HAVE_SLICER, reason="PrusaSlicer not installed")
def test_api_slice_skips_off_bed_objects_with_a_warning_instead_of_refusing():
    c = U("Mk")
    pid = _plate4(c, 6, 100)
    r = c.post(f"/api/edit/{pid}/op", json={"op": "plate", "params": {"action": "arrange", "gap": 5, "printer_id": "creality_k1"}})
    over = r.json()["report"]["arrange"]["overflow"]
    assert len(over) == 2
    s = c.post("/api/slice", data={"model_id": pid, "printer_id": "creality_k1", "nozzle": "0.4"})
    assert s.status_code == 200, s.text                                # warned, never blocked
    j = s.json()
    assert j["skipped_objects"] == [f"Object {i + 1}" for i in over] and j["plate_objects"] == 4
    assert "Split" in j["skipped_note"] and all(n in j["skipped_note"] for n in j["skipped_objects"])
    assert j["model_size_mm"][0] <= 220 and j["model_size_mm"][1] <= 220
    ok = c.post("/api/slice", data={"model_id": _plate4(c, 2, 20), "printer_id": "creality_k1", "nozzle": "0.4"}).json()
    assert ok["skipped_objects"] == [] and ok["skipped_note"] == ""
