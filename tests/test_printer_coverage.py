"""Printer coverage: every catalog profile is sourced, sane and carries a firmware field; pause command follows it."""
import collections, copy
import pytest
from app import printers
from app.api.printsetup import OPEN_IN
from app.services import gcode_pause as gp, print_setup as ps

CAT = printers.load_catalog()
BRANDS = {"Bambu Lab", "Prusa", "Creality", "ELEGOO", "Anycubic", "Flashforge", "QIDI", "Sovol", "Artillery", "Voron", "Snapmaker",
          "AnkerMake", "Longer", "Phrozen", "Formlabs", "Two Trees", "Tronxy", "Kingroon", "Monoprice", "Raise3D", "UltiMaker", "BIQU"}


def v(p, k):
    return p["settings"].get(k, {}).get("value")


def test_every_requested_brand_is_covered_including_longer_fdm_and_resin():
    have = {v(p, "brand") for p in CAT.values()}
    assert BRANDS <= have, BRANDS - have
    longer = {v(p, "technology") for p in CAT.values() if v(p, "brand") == "Longer"}
    assert longer == {"FDM", "Resin"}


@pytest.mark.parametrize("pid", sorted(CAT))
def test_profile_sourced_sane_and_has_firmware(pid):
    p = CAT[pid]; s = p["settings"]
    assert all(e["sources"] and all(u.startswith("https://") for u in e["sources"]) for e in s.values())
    assert v(p, "firmware") in printers.FIRMWARES and s["firmware"]["note"].strip()
    x, y, z = v(p, "bed_size_mm")
    resin = v(p, "technology") == "Resin"
    assert (v(p, "firmware") == "resin") == resin
    if resin:
        assert 30 <= x <= 400 and 30 <= y <= 400 and 50 <= z <= 600
        if v(p, "xy_resolution_um"):
            assert all(5 <= r <= 100 for r in v(p, "xy_resolution_um"))
    else:
        assert 100 <= x <= 1000 and 100 <= y <= 1000 and 100 <= z <= 1000
        if v(p, "nozzle_diameter_mm"): assert 0.2 <= v(p, "nozzle_diameter_mm") <= 1.2
        if v(p, "max_nozzle_temperature_c"): assert 200 <= v(p, "max_nozzle_temperature_c") <= 500
        if v(p, "max_bed_temperature_c"): assert 50 <= v(p, "max_bed_temperature_c") <= 150
    if v(p, "layer_height_range_mm"):
        lo, hi = v(p, "layer_height_range_mm"); assert 0 < lo < hi <= 1


def test_firmware_required_and_validated():
    p = copy.deepcopy(CAT["longer_lk5_pro"]); del p["settings"]["firmware"]
    with pytest.raises(printers.ProfileValidationError): printers.validate_profile(p)
    for bad in ("RepRap", "resin"):
        p = copy.deepcopy(CAT["longer_lk5_pro"]); p["settings"]["firmware"]["value"] = bad
        with pytest.raises(printers.ProfileValidationError): printers.validate_profile(p)
    p = copy.deepcopy(CAT["longer_orange_4k"]); p["settings"]["firmware"]["value"] = "marlin"
    with pytest.raises(printers.ProfileValidationError): printers.validate_profile(p)


@pytest.mark.parametrize("pid,fw,cmd,src", [
    ("twotrees_sk1", "klipper", "PAUSE", "profile"), ("kingroon_kp3s_pro_v2", "klipper", "PAUSE", "profile"),
    ("biqu_b1", "marlin", "M600", "profile"), ("prusa_core_one", "prusa", "M601", "profile"), ("bambu_p1s", "bambu", "M400 U1", "profile"),
    ("creality_k1", "klipper", "PAUSE", "profile"), ("sovol_sv06", "marlin", "M600", "guess"), ("elegoo_neptune4", "klipper", "PAUSE", "guess"),
    ("longer_lk5_pro", "unknown", None, "none"), ("raise3d_pro3", "unknown", None, "none"), ("tronxy_x5sa_pro", "unknown", None, "none"),
    ("longer_orange_4k", "resin", None, "profile"), ("not_a_printer", "unknown", None, "none")])
def test_pause_command_per_firmware(pid, fw, cmd, src):
    f = gp.firmware_for(pid)
    assert (f["firmware"], f["command"], f["source"]) == (fw, cmd, src) and f["note"]
    assert cmd is None or cmd in gp.COMMANDS


def test_catalog_api_exposes_firmware_and_generic_open_in():
    pub = {p["id"]: p for p in ps.public()["printers"]}
    assert pub["longer_orange_4k"]["xy_resolution_um"] == [31.5, 10.5] and pub["longer_lk5_pro"]["firmware"] == "unknown"
    assert {"3mf", "stl"} <= {o["format"] for o in OPEN_IN} and {"other3mf", "otherstl"} <= {o["id"] for o in OPEN_IN}


def coverage():
    c = collections.Counter((v(p, "brand"), v(p, "technology")) for p in CAT.values())
    return dict(sorted(c.items()))
