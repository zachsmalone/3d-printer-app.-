import json
import pytest
from app import printers


def test_load_printer():
    profile = printers.load_printer()
    assert profile["settings"]["bed_size_mm"]["value"] == [220, 220, 250]
    assert profile["settings"]["nozzle_diameter_mm"]["value"] == 0.4
    assert profile["settings"]["retraction_length_mm"]["value"] == 0.8


def test_load_materials():
    profiles = printers.load_materials()
    assert set(profiles) == {"PLA", "PETG", "TPU", "ABS", "ASA", "PC"}
    for profile in profiles.values():
        for entry in profile["settings"].values():
            assert entry["sources"]
    assert printers.load_material("TPU")["settings"]["nozzle_temperature_range_c"]["value"] == [220, 240]


@pytest.mark.parametrize("bad", ["../secrets", "zeim", ""])
def test_unknown_printer(bad):
    with pytest.raises(printers.ProfileValidationError):
        printers.load_printer(bad)


def test_unknown_material():
    with pytest.raises(printers.ProfileValidationError):
        printers.load_material("NYLON")              # in filaments.json for reference, but not a sourced slicer material


@pytest.mark.parametrize("field,value", [
    ("sources", []), ("sources", ["http://example.org"]),
    ("sources", ["https://"]), ("sources", ["https://user:pass@example.org"]),
    ("sources", ["https://example.org/bad url"]), ("value", True),
    ("value", float("nan")), ("value", float("inf")), ("value", -1),
    ("value", None), ("unit", "inches"), ("note", "")])
def test_invalid_entry(field, value):
    profile = printers.load_printer()
    profile["settings"]["nozzle_diameter_mm"][field] = value
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


def test_missing_source_field():
    profile = printers.load_printer()
    del profile["settings"]["nozzle_diameter_mm"]["sources"]
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


def test_unknown_field():
    profile = printers.load_printer()
    profile["settings"]["guessed_speed"] = profile["settings"]["nozzle_diameter_mm"]
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


def test_missing_core_field():
    profile = printers.load_printer()
    del profile["settings"]["bed_size_mm"]
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


@pytest.mark.parametrize("value", [[220, 220], [220, 0, 250], "220x220x250"])
def test_invalid_bed(value):
    profile = printers.load_printer()
    profile["settings"]["bed_size_mm"]["value"] = value
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile)


def test_reversed_range():
    profile = printers.load_material("TPU")
    profile["settings"]["nozzle_temperature_range_c"]["value"] = [240, 220]
    with pytest.raises(printers.ProfileValidationError):
        printers.validate_profile(profile, material=True)


def test_no_inferred_values():
    for profile in printers.load_materials().values():
        assert "print_speed_mm_s" not in profile["settings"]
        assert "retraction_length_mm" not in profile["settings"]


def test_fresh_results():
    printers.load_printer()["settings"]["nozzle_diameter_mm"]["value"] = 99
    assert printers.load_printer()["settings"]["nozzle_diameter_mm"]["value"] == 0.4


def test_duplicate_json_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(printers, "DATA_DIR", tmp_path)
    (tmp_path / "creality_k1.json").write_text('{"settings": {}, "settings": {}}')
    with pytest.raises(printers.ProfileValidationError):
        printers.load_printer()


def test_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(printers, "DATA_DIR", tmp_path)
    (tmp_path / "creality_k1.json").write_text('{')
    with pytest.raises(json.JSONDecodeError):
        printers.load_printer()
