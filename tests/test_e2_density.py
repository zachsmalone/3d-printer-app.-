"""E2 K1 slicer polish: the grams estimate uses the chosen material's density (PLA 1.24, PETG 1.27, ABS 1.04, TPU 1.21 ...),
not PLA's for everything, on both slicing paths, and says it is an estimate."""
import tempfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from tests.b1 import client
from tests.test_print_core import box_bytes, fake_engine, ini_dict, HAVE_SLICER  # noqa: F401  (fixture re-used)
from app.services import print_setup as ps, slice_engine as eng, slicer

EXPECTED = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21, "ASA": 1.07, "PC": 1.22}


@pytest.mark.parametrize("m,d", EXPECTED.items())
def test_profile_for_writes_the_materials_density(m, d):
    prof, s = eng.profile_for("creality_k1", 0.4, {"material": m})
    assert float(ini_dict(prof.ini)["filament_density"]) == d and s["filament_density"] == d
    assert "estimate" in s["grams_note"] and f"{d:g} g/cm³" in s["grams_note"] and m in s["grams_note"]


def test_non_pla_materials_never_report_pla_density():
    for m in ("PETG", "ABS", "TPU", "ASA", "PC"):
        assert ps.density_of(m) != ps.density_of("PLA"), m
    assert set(ps.DENSITY_G_CM3) == set(ps.MATERIALS)                       # every selectable material has its own estimate


@pytest.mark.parametrize("m", ["PETG", "TPU"])
def test_slice_api_uses_material_density_and_labels_grams_as_estimate(fake_engine, m):
    j = client().post("/api/slice", files={"file": ("m.stl", box_bytes(10, 10, 10))}, data={"printer_id": "creality_k1", "material": m}).json()
    assert ini_dict(fake_engine[-1]["ini"])["filament_density"] == f"{EXPECTED[m]:g}"
    assert j["filament_density_g_cm3"] == EXPECTED[m] and "estimate" in j["grams_note"]


def test_legacy_build_slice_path_uses_material_density_too(monkeypatch):
    seen = []
    def fake_run(engine, ini, stl, out, timeout=0, center=(110, 110)):
        seen.append(ini.read_text()); out.write_text("; total filament used [g] = 2.00\n;LAYER_CHANGE\n")
    monkeypatch.setattr(slicer, "status", lambda: {"available": True, "path": "/usr/bin/fake", "version": "fake"})
    monkeypatch.setattr(eng, "run_engine", fake_run)
    from app.core.geometry import Model
    m = trimesh.creation.box((10, 10, 10)); model = Model.__new__(Model)
    model.solid = lambda: (np.asarray(m.vertices), np.asarray(m.faces))
    r = slicer.slice_model(model, Path(tempfile.mkdtemp()), printer_id="creality_k1", nozzle=0.4, opts={"material": "ABS"})
    assert r["ok"] and ini_dict(seen[-1])["filament_density"] == "1.04" and r["filament_density"] == 1.04
    assert "ABS" in r["stats_note"] and "1.04 g/cm³" in r["stats_note"] and "estimate" in r["stats_note"]
    r = slicer.slice_model(model, Path(tempfile.mkdtemp()))                  # no material chosen: PLA, said so
    assert ini_dict(seen[-1])["filament_density"] == "1.24" and "PLA" in r["stats_note"]


def test_panel_says_grams_are_about():
    js = (Path(__file__).resolve().parent.parent / "static/printer.js").read_text()
    assert '"about " + r.filament_grams' in js and "r.grams_note" in js


@pytest.mark.skipif(not HAVE_SLICER, reason="PrusaSlicer not installed")
def test_real_prusaslicer_grams_follow_the_density():
    d = Path(tempfile.mkdtemp()); stl = d / "c.stl"; trimesh.creation.box((20, 20, 10)).export(stl)
    g = {}
    for m in ("PLA", "ABS"):
        prof, _ = eng.profile_for("creality_k1", 0.4, {"material": m})
        g[m] = eng.slice_stl(stl, prof, d / f"{m}.gcode").filament_grams
    assert g["PLA"] > 0 and g["ABS"] > 0
    assert abs(g["ABS"] / g["PLA"] - 1.04 / 1.24) < 0.02, g                  # same model, same path: grams scale with density only
