import copy
import json
from urllib.parse import urlsplit
import pytest
from app import printers

IDS = ['anycubic_kobra3', 'anycubic_photon_mono_m5s', 'bambu_a1', 'bambu_a1_mini', 'bambu_p1s', 'bambu_x1c', 'creality_ender3_v3', 'creality_ender3_v3_se', 'creality_k1', 'creality_k1_max', 'creality_k1c', 'elegoo_mars4', 'elegoo_neptune4', 'elegoo_neptune4_pro', 'elegoo_saturn3', 'prusa_core_one', 'prusa_mini_plus', 'prusa_mk4']

@pytest.mark.parametrize("pid", IDS)
def test_every_printer_loads(pid):
    profile = printers.load_printer(pid)
    assert printers.validate_profile(profile) is profile
    assert len(profile["settings"]["bed_size_mm"]["value"]) == 3


def test_exact_catalog_and_material_exclusion():
    assert printers.list_printers() == IDS
    assert "materials" not in printers.load_catalog()


def test_filters():
    assert len(printers.load_catalog(technology="FDM")) == 15
    assert len(printers.load_catalog(technology="Resin")) == 3
    with pytest.raises(printers.ProfileValidationError):
        printers.load_catalog(technology="SLA")


def test_manufacturer_sources_only():
    domains = ("bambulab.com", "creality.com", "prusa3d.com", "elegoo.com", "anycubic.com")
    owners = ("/CrealityOfficial/", "/ELEGOO-3D/")
    for profile in printers.load_catalog().values():
        for item in profile["settings"].values():
            for url in item["sources"]:
                host = urlsplit(url).hostname
                assert any(host == d or host.endswith("." + d) for d in domains) or (host == "github.com" and urlsplit(url).path.startswith(owners))


@pytest.mark.parametrize("pid", ["elegoo_saturn3", "elegoo_mars4", "anycubic_photon_mono_m5s"])
def test_resin_has_no_fdm_fields(pid):
    assert not {"nozzle_diameter_mm", "max_nozzle_temperature_c", "max_bed_temperature_c"} & set(printers.load_printer(pid)["settings"])


@pytest.mark.parametrize("bad", ["../secrets", "materials", "/tmp/test", "unknown", None])
def test_path_allowlist(bad):
    with pytest.raises(printers.ProfileValidationError):
        printers.load_printer(bad)


@pytest.mark.parametrize("key,value", [("sources", []), ("sources", ["http://bad.example"]), ("sources", ["https://user:pass@example.com"]), ("unit", "inches"), ("value", True), ("value", float("nan")), ("value", -1)])
def test_bad_numeric_entry(key, value):
    profile = printers.load_printer()
    profile["settings"]["nozzle_diameter_mm"][key] = value
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


@pytest.mark.parametrize("field,value", [("brand", ""), ("model", None), ("technology", "Laser"), ("native_file_formats", ["STL"]), ("native_file_formats", [".goo"]), ("multi_color_system", []), ("official_slicer_download_url", "javascript:alert(1)")])
def test_bad_metadata(field, value):
    profile = printers.load_printer("bambu_a1")
    profile["settings"][field]["value"] = value
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


def test_resin_rejects_nozzle():
    profile = printers.load_printer("elegoo_mars4")
    profile["settings"]["nozzle_diameter_mm"] = printers.load_printer()["settings"]["nozzle_diameter_mm"]
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


def test_no_format_or_multicolor_fallback():
    profile = printers.load_printer("creality_ender3_v3_se")
    assert "native_file_formats" not in profile["settings"]
    assert "multi_color_system" not in profile["settings"]


def test_native_resin_suffix():
    assert printers.load_printer("anycubic_photon_mono_m5s")["settings"]["native_file_formats"]["value"] == ["pm5s"]


def test_k1_legacy_values_preserved():
    profile = printers.load_printer()
    assert profile["settings"]["retraction_length_mm"]["value"] == 0.8
    assert profile["settings"]["bed_size_mm"]["value"] == [220, 220, 250]


def test_fresh_load():
    profile = printers.load_printer()
    profile["settings"]["model"]["value"] = "changed"
    assert printers.load_printer()["settings"]["model"]["value"] == "K1"


def test_duplicate_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(printers, "DATA_DIR", tmp_path)
    (tmp_path / "test.json").write_text('{"settings": {}, "settings": {}}')
    with pytest.raises(printers.ProfileValidationError):
        printers.load_printer("test")


def test_symlink_escape(tmp_path, monkeypatch):
    folder = tmp_path / "catalog"
    folder.mkdir()
    external = tmp_path / "external.json"
    external.write_text(json.dumps(printers.load_printer()))
    (folder / "escape.json").symlink_to(external)
    monkeypatch.setattr(printers, "DATA_DIR", folder)
    with pytest.raises(printers.ProfileValidationError):
        printers.load_printer("escape")
