"""Load sourced reference data; does not select defaults or control printers.

Each setting carries value, unit, sources and a provenance note. Missing optional
settings stay missing. Source URL validation checks syntax, not factual truth.
"""
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIR = Path(__file__).resolve().parent / "data" / "printers"

PRINTER_FIELDS = {
    "bed_size_mm": ("mm", 3),
    "nozzle_diameter_mm": ("mm", 0),
    "filament_diameter_mm": ("mm", 0),
    "advertised_max_print_speed_mm_s": ("mm/s", 0),
    "max_acceleration_mm_s2": ("mm/s^2", 0),
    "max_nozzle_temperature_c": ("C", 0),
    "max_bed_temperature_c": ("C", 0),
    "retraction_length_mm": ("mm", 0),
    "retraction_speed_mm_s": ("mm/s", 0),
    "deretraction_speed_mm_s": ("mm/s", 0),
    "z_hop_mm": ("mm", 0),
}
MATERIAL_FIELDS = {
    "first_layer_nozzle_temperature_c": ("C", 0),
    "nozzle_temperature_c": ("C", 0),
    "first_layer_bed_temperature_c": ("C", 0),
    "bed_temperature_c": ("C", 0),
    "nozzle_temperature_range_c": ("C", 2),
    "bed_temperature_range_c": ("C", 2),
    "typical_max_volumetric_speed_range_mm3_s": ("mm^3/s", 2),
}

class ProfileValidationError(ValueError):
    """Reference data does not satisfy the documented schema."""

def validate_profile(profile, *, material=False):
    if not isinstance(profile, dict) or set(profile) != {"settings", "notes"}:
        raise ProfileValidationError("Expected settings and notes")
    notes = profile["notes"]
    if not isinstance(notes, list) or not notes or any(not isinstance(n, str) or not n.strip() for n in notes):
        raise ProfileValidationError("Expected nonempty text notes")
    settings = profile["settings"]
    allowed = MATERIAL_FIELDS if material else PRINTER_FIELDS
    if not isinstance(settings, dict) or not settings or set(settings) - set(allowed):
        raise ProfileValidationError("Empty or unknown settings")
    if not material and not {"bed_size_mm", "nozzle_diameter_mm"} <= set(settings):
        raise ProfileValidationError("Missing bed size or nozzle diameter")
    if material:
        if not ({"nozzle_temperature_c", "nozzle_temperature_range_c"} & set(settings)):
            raise ProfileValidationError("Missing nozzle temperature reference")
        if not ({"bed_temperature_c", "bed_temperature_range_c"} & set(settings)):
            raise ProfileValidationError("Missing bed temperature reference")
    for key, entry in settings.items():
        if not isinstance(entry, dict) or set(entry) != {"value", "unit", "sources", "note"}:
            raise ProfileValidationError(f"{key}: incomplete setting")
        unit, count = allowed[key]
        if entry["unit"] != unit:
            raise ProfileValidationError(f"{key}: incorrect unit")
        value = entry["value"]
        if count:
            if not isinstance(value, list) or len(value) != count:
                raise ProfileValidationError(f"{key}: invalid dimensions/range")
            values = value
        else:
            values = [value]
        for number in values:
            if type(number) not in (int, float) or not math.isfinite(number) or number <= 0:
                raise ProfileValidationError(f"{key}: expected finite positive numbers")
        if count == 2 and value[0] > value[1]:
            raise ProfileValidationError(f"{key}: reversed range")
        sources = entry["sources"]
        if not isinstance(sources, list) or not sources:
            raise ProfileValidationError(f"{key}: missing sources")
        for url in sources:
            if not isinstance(url, str) or any(c.isspace() for c in url):
                raise ProfileValidationError(f"{key}: invalid source URL")
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                valid = False
            if not valid:
                raise ProfileValidationError(f"{key}: expected HTTPS source URL")
        if not isinstance(entry["note"], str) or not entry["note"].strip():
            raise ProfileValidationError(f"{key}: missing provenance note")
    return profile

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProfileValidationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result

def _read(filename):
    with (DATA_DIR / filename).open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=_unique_object)

def load_printer(printer_id="creality_k1"):
    """Load a fresh validated profile; arbitrary paths are not accepted."""
    if printer_id != "creality_k1":
        raise ProfileValidationError("Unknown printer")
    return validate_profile(_read("creality_k1.json"))

def load_materials():
    """Return reference presets with provenance intact and no inferred values."""
    materials = _read("materials.json")
    if not isinstance(materials, dict) or set(materials) != {"PLA", "PETG", "TPU"}:
        raise ProfileValidationError("Expected PLA, PETG and TPU")
    for profile in materials.values():
        validate_profile(profile, material=True)
    return materials

def load_material(material):
    if material not in ("PLA", "PETG", "TPU"):
        raise ProfileValidationError("Unknown material")
    return load_materials()[material]
