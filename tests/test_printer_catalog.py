import copy
import json
from urllib.parse import urlsplit
import pytest
from app import printers

IDS = ['ankermake_m5', 'anycubic_kobra3', 'anycubic_kobra3_max', 'anycubic_kobra_s1', 'anycubic_kobra_s1_max', 'anycubic_photon_mono_m5s', 'anycubic_photon_mono_m7', 'artillery_sidewinder_x4_plus', 'artillery_sidewinder_x4_pro', 'bambu_a1', 'bambu_a1_mini', 'bambu_h2c', 'bambu_h2d', 'bambu_h2s', 'bambu_p1p', 'bambu_p1s', 'bambu_p2s', 'bambu_x1c', 'bambu_x1e', 'biqu_b1', 'creality_cr10_se', 'creality_ender3_v3', 'creality_ender3_v3_ke', 'creality_ender3_v3_plus', 'creality_ender3_v3_se', 'creality_ender5_s1', 'creality_halot_mage', 'creality_hi', 'creality_k1', 'creality_k1_max', 'creality_k1_se', 'creality_k1c', 'creality_k2', 'creality_k2_plus', 'creality_k2_pro', 'creality_sparkx_i7', 'elegoo_centauri_carbon', 'elegoo_mars4', 'elegoo_mars5_ultra', 'elegoo_neptune4', 'elegoo_neptune4_max', 'elegoo_neptune4_plus', 'elegoo_neptune4_pro', 'elegoo_saturn3', 'elegoo_saturn4_ultra', 'flashforge_ad5x', 'flashforge_adventurer_5m', 'flashforge_adventurer_5m_pro', 'formlabs_form4', 'kingroon_kp3s_pro_v2', 'longer_lk5_pro', 'longer_orange_4k', 'monoprice_mp_voxel', 'phrozen_sonic_mini_8k_s', 'prusa_core_one', 'prusa_mini_plus', 'prusa_mk3s_plus', 'prusa_mk4', 'prusa_sl1s', 'prusa_xl', 'qidi_plus4', 'qidi_q1_pro', 'qidi_x_max3', 'raise3d_pro3', 'snapmaker_artisan', 'snapmaker_j1', 'sovol_sv06', 'sovol_sv06_plus', 'sovol_sv08', 'tronxy_x5sa_pro', 'twotrees_sk1', 'ultimaker_s5', 'voron_24_300', 'voron_24_350', 'voron_trident_300']

@pytest.mark.parametrize("pid", IDS)
def test_every_printer_loads(pid):
    profile = printers.load_printer(pid)
    assert printers.validate_profile(profile) is profile
    assert len(profile["settings"]["bed_size_mm"]["value"]) == 3


def test_exact_catalog_and_material_exclusion():
    assert printers.list_printers() == IDS
    assert "materials" not in printers.load_catalog()


def test_filters():
    assert len(printers.load_catalog(technology="FDM")) == 64
    assert len(printers.load_catalog(technology="Resin")) == 11
    with pytest.raises(printers.ProfileValidationError):
        printers.load_catalog(technology="SLA")


def test_manufacturer_sources_only():
    domains = ("bambulab.com", "creality.com", "prusa3d.com", "elegoo.com", "anycubic.com", "sovol3d.com", "qidi3d.com", "flashforge.com", "vorondesign.com", "formlabs.com", "phrozen3d.com", "ultimaker.com", "artillery3d.com", "snapmaker.com", "ankermake.com", "longer.net", "longer3d.com", "twotrees3d.com", "nice-cdn.com", "kingroon.com", "raise3d.com", "raise3d.cn", "biqu.equipment", "tronxy.cn", "monoprice.com")
    owners = ("/CrealityOfficial/", "/ELEGOO-3D/", "/VoronDesign/")
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
