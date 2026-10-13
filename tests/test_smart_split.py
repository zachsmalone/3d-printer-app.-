"""Smart Split: auto bed-fit cuts + join options (magnet / dovetail / pin / glue). Fit is Simulated."""
import pytest
import trimesh

from app.core import meshedit, smartsplit
from app.services import print_setup as ps
from tests.b1 import client, ADULT


def box(x, y, z):
    return trimesh.creation.box(extents=(x, y, z))


def test_plan_cuts_empty_when_fits():
    assert smartsplit.plan_cuts((100, 100, 100), (220, 220, 250)) == []


def test_plan_cuts_for_oversize_axis():
    plan = smartsplit.plan_cuts((400, 80, 60), (220, 220, 250))
    assert plan and all(c["axis"] == "x" for c in plan)
    assert len(plan) >= 1


def test_already_fits_is_noop():
    out, rep = smartsplit.smart_split(box(40, 40, 40), {"printer_id": "creality_k1", "join": "glue"})
    assert rep["parts"] == 1 and rep["cuts"] == 0
    assert rep["verification"] == "Simulated"
    assert "Already fits" in rep["message"]


def test_auto_glue_split_fits_k1():
    out, rep = smartsplit.smart_split(box(300, 80, 60), {"printer_id": "creality_k1", "join": "glue"})
    assert rep["parts"] >= 2 and rep["verification"] == "Simulated"
    assert rep["fits_each"] is True
    assert out.is_watertight
    assert "Simulated" in rep["message"]
    assert rep["printer_id"] == "creality_k1"


def test_auto_uses_printer_picker_bed():
    # A1 mini is 180³ — a 200 mm bar needs a cut there but may fit a K1
    m = box(200, 40, 40)
    _, k1 = smartsplit.smart_split(m.copy(), {"printer_id": "creality_k1", "join": "glue"})
    _, mini = smartsplit.smart_split(m.copy(), {"printer_id": "bambu_a1_mini", "join": "glue"})
    assert k1["parts"] == 1  # 200 < 220-2
    assert mini["parts"] >= 2
    assert mini["bed_mm"][0] == pytest.approx(180)


@pytest.mark.parametrize("join", ["magnet", "pin", "dovetail", "glue"])
def test_join_options_simulated(join):
    out, rep = smartsplit.smart_split(box(300, 90, 50), {"printer_id": "creality_k1", "join": join})
    assert rep["verification"] == "Simulated"
    assert rep["join"] == join
    assert rep["parts"] >= 2
    assert out.is_watertight
    if join != "glue":
        assert rep["joins"] and rep["joins"][0]["join"] == join


def test_manual_cut_plane():
    out, rep = smartsplit.smart_split(
        box(100, 40, 40),
        {"mode": "manual", "axis": "x", "position": 0, "join": "glue", "printer_id": "creality_k1"},
    )
    assert rep["mode"] == "manual" and rep["parts"] == 2
    assert rep["verification"] == "Simulated"


def test_magnet_defaults_match_common_6x3():
    _, rep = smartsplit.smart_split(box(300, 80, 60), {"printer_id": "creality_k1", "join": "magnet"})
    j = rep["joins"][0]
    assert j["magnet_mm"] == [6.0, 3.0]
    assert j["clearance_mm"] == 0.25
    assert j["pockets"] >= 1


def test_refuses_unknown_join():
    with pytest.raises(smartsplit.SplitError, match="join must be"):
        smartsplit.smart_split(box(300, 40, 40), {"join": "velcro", "printer_id": "creality_k1"})


def test_via_meshedit_ops():
    out, rep = meshedit.apply(box(300, 60, 40), "smart_split", {"printer_id": "creality_k1", "join": "glue"})
    assert "smart_split" in meshedit.OPS
    assert rep["verification"] == "Simulated" and rep["parts"] >= 2
    assert meshedit.label("smart_split", {"mode": "auto", "join": "magnet"}) == "Smart Split (auto, join=magnet)"


def test_api_smart_split(tmp_path, monkeypatch):
    c = client(ADULT)
    stl = box(300, 80, 60).export(file_type="stl")
    r = c.post("/api/edit/new", files={"file": ("big.stl", stl, "model/stl")}, data={"units": "mm", "beginner": "false"})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    r2 = c.post(f"/api/edit/{bid}/op", json={"op": "smart_split", "params": {"mode": "auto", "join": "magnet", "printer_id": "creality_k1"}})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["report"]["verification"] == "Simulated"
    assert body["report"]["parts"] >= 2
    assert body["analysis"]["components"] >= 2


def test_specs_file_loads():
    sp = smartsplit.specs()
    assert "magnet_pockets" in sp and "dovetails" in sp and "alignment_pins" in sp
