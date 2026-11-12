"""Official multi-material add-ons: catalog rows, default units, and unit-count caps.

A printer that already names a unit still starts on that unit. A K1 starts on None
until the maker picks a CFS-C. Counts above the documented maximum are refused.
"""
from pathlib import Path

import pytest

from app.services import material_units as mu
from app.services import print_setup as ps
from tests.b1 import ADULT, client

ROOT = Path(__file__).resolve().parent.parent

CFS_C = "https://www.creality.com/products/cfs-c-smart-filament-system"
K2 = "https://www.creality.com/products/k2-series-3d-printer"
HI = "https://www.creality.com/products/creality-hi-combo"
LITE = "https://wiki.bambulab.com/en/ams-lite/manual/faq"
HUB = "https://wiki.bambulab.com/a1/manual/ams-connection-guide"
P1 = "https://wiki.bambulab.com/en/p1/manual/connect-ams"
FAQ = "https://wiki.bambulab.com/ams/manual/ams-2-pro-ams-ht-faq"
MULTI = "https://wiki.bambulab.com/ams/manual/multi-model-AMS-compatibility-guide"
X1E = "https://wiki.bambulab.com/en/x1/maintenance/x1e-ams-interface-board"
H2S = "https://wiki.bambulab.com/en/h2/manual/h2s-faq"
MMU = "https://www.prusa3d.com/downloads/manual/prusa3d_manual_mmu3_en_1_03.pdf"


def _units(pid):
    return {u["id"]: u for u in ps.printer_public(pid)["multi_material_units"]}


def test_k1_family_offers_one_cfs_c_and_starts_on_none():
    for pid in ("creality_k1", "creality_k1_se", "creality_k1c", "creality_k1_max"):
        row = ps.printer_public(pid)
        assert row["filament_slots"] == 1 and row["multi_color_system"] == []
        units = _units(pid)
        assert list(units) == ["cfs_c"]
        assert units["cfs_c"]["name"] == "CFS-C"
        assert units["cfs_c"]["slots_per_unit"] == 4 and units["cfs_c"]["max_units"] == 1
        assert units["cfs_c"]["default"] is False
        assert units["cfs_c"]["source"] == CFS_C


def test_k2_and_hi_offer_four_cfs_units():
    for pid in ("creality_k2", "creality_k2_pro", "creality_k2_plus"):
        unit = _units(pid)["cfs"]
        assert unit["slots_per_unit"] == 4 and unit["max_units"] == 4 and unit["source"] == K2
        assert unit["default"] is False and ps.printer_public(pid)["filament_slots"] == 1
    hi = _units("creality_hi")["cfs"]
    assert hi["slots_per_unit"] == 4 and hi["max_units"] == 4 and hi["source"] == HI


def test_a1_keeps_ams_lite_as_the_default_and_adds_the_hub_units():
    for pid in ("bambu_a1", "bambu_a1_mini"):
        row = ps.printer_public(pid)
        assert row["multi_color_system"] == ["AMS lite"] and row["filament_slots"] == 4
        units = _units(pid)
        assert units["ams_lite"]["default"] is True and units["ams_lite"]["max_units"] == 1
        assert units["ams_lite"]["source"] == LITE
        for key in ("ams", "ams_2_pro"):
            assert units[key]["max_units"] == 4 and units[key]["slots_per_unit"] == 4
            assert units[key]["source"] == HUB and units[key]["default"] is False
        assert units["ams_ht"]["slots_per_unit"] == 1 and units["ams_ht"]["max_units"] == 4
        assert "AMS lite" in row["multi_material_units"][0]["name"]


def test_listed_ams_printers_keep_ams_and_gain_the_newer_units():
    for pid in ("bambu_p1s", "bambu_x1c"):
        row = ps.printer_public(pid)
        assert row["multi_color_system"] == ["AMS"] and row["filament_slots"] == 4
        units = _units(pid)
        assert units["ams"]["default"] is True and units["ams"]["max_units"] == 4
        assert units["ams_2_pro"]["max_units"] == 4 and units["ams_2_pro"]["slots_per_unit"] == 4
        assert units["ams_ht"]["slots_per_unit"] == 1 and units["ams_ht"]["max_units"] == 4
        assert units["ams"]["source"] == FAQ


def test_p1p_x1e_p2s_h2s_and_mk3s_match_the_cited_pages():
    p1p = _units("bambu_p1p")["ams"]
    assert p1p["max_units"] == 4 and p1p["slots_per_unit"] == 4 and p1p["source"] == P1
    assert ps.printer_public("bambu_p1p")["filament_slots"] == 1
    x1e = _units("bambu_x1e")["ams"]
    assert x1e["max_units"] == 1 and x1e["source"] == X1E
    p2 = _units("bambu_p2s")
    assert p2["ams_2_pro"]["max_units"] == 4 and p2["ams_ht"]["max_units"] == 4
    assert p2["ams_ht"]["slots_per_unit"] == 1 and p2["ams_2_pro"]["source"] == MULTI
    h2 = _units("bambu_h2s")
    assert "ams_lite" not in h2
    assert h2["ams"]["source"] == H2S and h2["ams"]["max_units"] == 1
    assert h2["ams_2_pro"]["max_units"] == 4 and h2["ams_ht"]["max_units"] == 8
    assert h2["ams_ht"]["slots_per_unit"] == 1
    mmu = _units("prusa_mk3s_plus")["mmu3"]
    assert mmu["slots_per_unit"] == 5 and mmu["max_units"] == 1 and mmu["source"] == MMU
    assert mmu["default"] is False


def test_existing_listed_units_stay_the_default():
    assert ps.printer_public("prusa_mk4")["filament_slots"] == 5
    assert _units("prusa_mk4")["mmu3"]["default"] is True
    assert ps.printer_public("anycubic_kobra3")["filament_slots"] == 4
    assert _units("anycubic_kobra3")["ace_pro"]["default"] is True and _units("anycubic_kobra3")["ace_pro"]["max_units"] == 1


def test_slot_counts_follow_the_choice_and_stop_at_the_cap():
    assert mu.effective_slots("creality_k1", "none") == 1
    assert mu.effective_slots("creality_k1", "cfs_c", 1) == 4
    assert mu.effective_slots("creality_k2", "cfs", 4) == 16
    assert mu.effective_slots("bambu_a1", "ams", 4) == 16
    assert mu.effective_slots("bambu_a1", "ams_ht", 4) == 4
    assert mu.effective_slots("bambu_h2s", "ams_ht", 8) == 8
    assert mu.effective_slots("bambu_p2s", "ams_2_pro", 4) == 16
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("creality_k1", "cfs_c", 2)
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("creality_k2", "cfs", 5)
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("bambu_a1", "ams_lite", 2)
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("bambu_a1", "ams", 5)
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("bambu_h2s", "ams_ht", 9)
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("bambu_p1s", "ams_2_pro", 5)
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("creality_k1", "ams")
    with pytest.raises(mu.UnitError):
        mu.resolve_choice("bambu_x1e", "ams", 2)


def test_choice_is_saved_with_the_printer_and_a_nozzle_only_save_keeps_it():
    c = client(ADULT)
    saved = c.put("/api/me/printer", json={"printer_id": "creality_k1", "nozzle": 0.4, "unit_id": "cfs_c", "unit_count": 1})
    assert saved.status_code == 200
    assert saved.json()["unit_id"] == "cfs_c" and saved.json()["unit_count"] == 1
    assert c.get("/api/me/printer").json()["unit_id"] == "cfs_c"
    assert c.get("/api/me").json()["printer"]["unit_id"] == "cfs_c"
    again = c.put("/api/me/printer", json={"printer_id": "creality_k1", "nozzle": 0.6})
    assert again.status_code == 200 and again.json()["unit_id"] == "cfs_c"
    cleared = c.put("/api/me/printer", json={"printer_id": "creality_k1", "nozzle": 0.4, "unit_id": "none"})
    assert cleared.json()["unit_id"] == "none" and cleared.json()["unit_count"] == 1
    assert c.put("/api/me/printer", json={"printer_id": "creality_k2", "nozzle": 0.4, "unit_id": "cfs", "unit_count": 5}).status_code == 400
    assert c.put("/api/me/printer", json={"printer_id": "bambu_h2s", "nozzle": 0.4, "unit_id": "ams_ht", "unit_count": 8}).status_code == 200
    assert c.put("/api/me/printer", json={"printer_id": "bambu_h2s", "nozzle": 0.4, "unit_id": "ams_ht", "unit_count": 9}).status_code == 400


def test_anonymous_choice_is_checked_and_not_stored():
    a = client()
    r = a.put("/api/me/printer", json={"printer_id": "creality_k1", "nozzle": 0.4, "unit_id": "cfs_c", "unit_count": 1}).json()
    assert r["stored"] == "browser" and r["unit_id"] == "cfs_c"
    assert a.get("/api/me/printer").json()["printer_id"] == "creality_k1"
    assert "unit_id" not in a.get("/api/me/printer").json()
    assert a.put("/api/me/printer", json={"printer_id": "creality_k1", "nozzle": 0.4, "unit_id": "cfs_c", "unit_count": 3}).status_code == 400


def test_picker_and_slot_editor_follow_the_saved_unit():
    js = (ROOT / "static/printer.js").read_text(encoding="utf-8")
    slots = (ROOT / "static/partslots.js").read_text(encoding="utf-8")
    edit = (ROOT / "static/edit.js").read_text(encoding="utf-8")
    assert "Multi-material unit" in js and "spUnitNote" in js and "effectivePrinter" in js
    assert "function choiceFor" in slots and "Official add-ons" in js
    assert "effectivePrinter(row, P.pref)" in edit
