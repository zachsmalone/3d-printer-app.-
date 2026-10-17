import io

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.core import printcheck
from app.main import app


def test_tolerance_hole_grows_and_peg_shrinks():
    assert printcheck.tolerance("fdm", "normal", 6, "hole")["adjusted_mm"] == 6.25
    assert printcheck.tolerance("fdm", "normal", 6, "peg")["adjusted_mm"] == 5.75
    assert printcheck.tolerance("resin", "tight", 6, "hole")["adjusted_mm"] == 6.05
    for bad in (("laser", "normal", 6, "hole"), ("fdm", "snug", 6, "hole"), ("fdm", "normal", 0, "hole"), ("fdm", "normal", 6, "pin"), ("fdm", "normal", float("nan"), "hole")):
        with pytest.raises(ValueError):
            printcheck.tolerance(*bad)


def test_bed_fit_cases():
    f = printcheck.fits_bed(trimesh.creation.box((100, 100, 50)), (220, 220, 250))
    assert f["fits_as_is"] and not f["suggest_split"]
    turned = printcheck.fits_bed(trimesh.creation.box((100, 100, 210)), (220, 220, 200))     # too tall as-is, fits lying down
    assert not turned["fits_as_is"] and turned["fits_any_axis_orientation"] and not turned["suggest_split"]
    big = printcheck.fits_bed(trimesh.creation.box((500, 400, 300)), (220, 220, 250))
    assert big["suggest_split"] and not big["fits_any_axis_orientation"] and max(big["overhang_past_bed_mm"]) > 0


def test_run_reports_issues():
    r = printcheck.run(trimesh.creation.box((40, 40, 0.4)), (220, 220, 250))
    assert not r["ok"] and any("Thin walls" in i for i in r["issues"]) and r["approximate"]
    ok = printcheck.run(trimesh.creation.box((20, 20, 20)), (220, 220, 250))
    assert ok["ok"] and ok["issues"] == []
    with pytest.raises(ValueError):
        printcheck.run(trimesh.creation.box((5, 5, 5)), (220, 220, 250), "laser")


def test_endpoints():
    c = TestClient(app)
    t = c.get("/api/edit/tolerance?process=fdm&fit=loose&nominal=8")
    assert t.status_code == 200 and t.json()["adjusted_mm"] == 8.4
    assert c.get("/api/edit/tolerance?process=x").status_code == 400
    stl = trimesh.creation.box((20, 20, 20)).export(file_type="stl")
    j = c.post("/api/edit/new", files={"file": ("b.stl", io.BytesIO(stl), "model/stl")}).json()
    bid = j["id"] if "id" in j else j["project"]["id"]
    r = c.get(f"/api/edit/{bid}/printcheck")
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["bed"]["fits_as_is"]
    assert c.get(f"/api/edit/{bid}/printcheck?process=x").status_code == 400
