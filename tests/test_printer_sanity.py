"""Printer catalog sanity (49 new profiles, 2026-10-14): every setting is sourced, and the numbers a slice depends on
are in a believable range. Every FDM printer must produce a PrusaSlicer config for every material and nozzle it offers
(temperatures capped to what that printer can reach); every resin printer is refused with its own slicer named."""
import json
from urllib.parse import urlsplit

import pytest

from app import printers
from app.services import print_setup as ps

IDS = printers.list_printers()


def _s(pid):
    return printers.load_printer(pid)["settings"]


def test_catalog_is_the_full_expansion():
    assert len(IDS) == 67
    assert len({_s(p)["brand"]["value"] for p in IDS}) == 15


@pytest.mark.parametrize("pid", IDS)
def test_every_setting_has_an_https_source(pid):
    for key, item in _s(pid).items():
        assert item["sources"], f"{pid}.{key} has no source"
        for url in item["sources"]:
            u = urlsplit(url)
            assert u.scheme == "https" and u.hostname and "." in u.hostname, f"{pid}.{key}: {url}"


@pytest.mark.parametrize("pid", IDS)
def test_limits_are_believable(pid):
    s = _s(pid)
    x, y, z = s["bed_size_mm"]["value"]
    assert all(50 <= v <= 1000 for v in (x, y, z)), (pid, x, y, z)
    if s["technology"]["value"] == "Resin":
        assert not {"nozzle_diameter_mm", "max_nozzle_temperature_c", "max_bed_temperature_c"} & set(s)
        assert max(x, y) <= 400          # resin vats are small
        return
    if "nozzle_diameter_mm" in s:
        assert 0.2 <= s["nozzle_diameter_mm"]["value"] <= 1.0
    if "max_nozzle_temperature_c" in s:
        assert 240 <= s["max_nozzle_temperature_c"]["value"] <= 450
    if "max_bed_temperature_c" in s:
        assert 50 <= s["max_bed_temperature_c"]["value"] <= 150


@pytest.mark.parametrize("pid", IDS)
def test_every_fdm_printer_builds_a_config_and_resin_is_refused(pid):
    p = ps.printer_public(pid)
    if p["technology"] == "Resin":
        with pytest.raises(ps.SetupError, match="resin printer"):
            ps.settings_for(pid, 0.4)
        return
    assert p["nozzles"], pid
    for n in p["nozzles"]:
        for material in ps.MATERIALS:
            s = ps.settings_for(pid, n, {"material": material})
            ini = ps.ini_overrides(s)
            x, y, z = ps.bed_of(pid)
            assert ini["bed_shape"] == f"0x0,{x:g}x0,{x:g}x{y:g},0x{y:g}" and ini["max_print_height"] == f"{z:g}"
            assert int(ini["temperature"]) <= (p["max_nozzle_c"] or 300)
            assert int(ini["bed_temperature"]) <= (p["max_bed_c"] or 110)


def test_low_bed_printer_caps_hot_material_and_says_so():
    s = ps.settings_for("elegoo_neptune4_max", 0.4, {"material": "ABS"})     # Elegoo: max hot bed 85 °C
    assert s["bed_temp"] == 85 and any("85 °C" in n for n in s["temp_notes"])


def test_picker_groups_by_brand_in_name_order():
    j = ps.public()
    brands = [p["brand"] for p in j["printers"]]
    # sorted by "Brand Model", so each brand is one contiguous run (one <optgroup> each)
    runs = [b for i, b in enumerate(brands) if i == 0 or brands[i - 1] != b]
    assert len(runs) == len(set(brands))
    js = open("static/printer.js", encoding="utf-8").read()
    assert "<optgroup label=" in js
