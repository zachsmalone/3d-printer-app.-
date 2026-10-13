"""Sourced printer catalog and material references; no slicing or printer control."""
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIR = Path(__file__).resolve().parent / "data" / "printers"
PRINTER_FIELDS = {
    "bed_size_mm": ("mm", 3), "nozzle_diameter_mm": ("mm", 0),
    "filament_diameter_mm": ("mm", 0), "advertised_max_print_speed_mm_s": ("mm/s", 0),
    "max_acceleration_mm_s2": ("mm/s^2", 0), "max_nozzle_temperature_c": ("C", 0),
    "max_bed_temperature_c": ("C", 0), "retraction_length_mm": ("mm", 0),
    "retraction_speed_mm_s": ("mm/s", 0), "deretraction_speed_mm_s": ("mm/s", 0),
    "z_hop_mm": ("mm", 0), "brand": ("text", "text"), "model": ("text", "text"),
    "technology": ("enum", "technology"), "multi_color_system": ("system", "list"),
    "native_file_formats": ("format", "formats"), "official_slicer_name": ("text", "text"),
    "official_slicer_download_url": ("url", "url"),
}
MATERIAL_FIELDS = {
    "first_layer_nozzle_temperature_c": ("C", 0), "nozzle_temperature_c": ("C", 0),
    "first_layer_bed_temperature_c": ("C", 0), "bed_temperature_c": ("C", 0),
    "nozzle_temperature_range_c": ("C", 2), "bed_temperature_range_c": ("C", 2),
    "typical_max_volumetric_speed_range_mm3_s": ("mm^3/s", 2),
}

class ProfileValidationError(ValueError):
    """Malformed, unsourced or unsafe profile reference."""


def _url(url):
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise ProfileValidationError("Invalid URL")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
    except ValueError:
        raise ProfileValidationError("Expected HTTPS URL without credentials") from None


def validate_profile(profile, *, material=False):
    if not isinstance(profile, dict) or set(profile) != {"settings", "notes"}:
        raise ProfileValidationError("Expected settings and notes")
    if not isinstance(profile["notes"], list) or not profile["notes"] or any(not isinstance(n, str) or not n.strip() for n in profile["notes"]):
        raise ProfileValidationError("Expected text notes")
    settings = profile["settings"]
    allowed = MATERIAL_FIELDS if material else PRINTER_FIELDS
    if not isinstance(settings, dict) or not settings or set(settings) - set(allowed):
        raise ProfileValidationError("Empty or unknown settings")
    for key, entry in settings.items():
        if not isinstance(entry, dict) or set(entry) != {"value", "unit", "sources", "note"}:
            raise ProfileValidationError(f"{key}: incomplete setting")
        if not isinstance(entry["sources"], list) or not entry["sources"]:
            raise ProfileValidationError(f"{key}: missing sources")
        for source in entry["sources"]:
            _url(source)
        if not isinstance(entry["note"], str) or not entry["note"].strip():
            raise ProfileValidationError(f"{key}: missing provenance")
        unit, kind = allowed[key]
        if entry["unit"] != unit:
            raise ProfileValidationError(f"{key}: incorrect unit")
        value = entry["value"]
        if kind in ("text", "technology", "url"):
            if not isinstance(value, str) or not value.strip():
                raise ProfileValidationError(f"{key}: expected text")
            if kind == "technology" and value not in ("FDM", "Resin"):
                raise ProfileValidationError("Unknown technology")
            if kind == "url":
                _url(value)
        elif kind in ("list", "formats"):
            if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v.strip() for v in value):
                raise ProfileValidationError(f"{key}: expected nonempty text list")
            if len(value) != len(set(value)):
                raise ProfileValidationError(f"{key}: duplicate values")
            if kind == "formats" and any(not re.fullmatch(r"[a-z0-9]+(?:\.[a-z0-9]+)*", v) for v in value):
                raise ProfileValidationError("Formats use lowercase suffixes without leading dots")
        else:
            if kind and (not isinstance(value, list) or len(value) != kind):
                raise ProfileValidationError(f"{key}: invalid dimensions/range")
            values = value if kind else [value]
            if any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in values):
                raise ProfileValidationError(f"{key}: expected finite positive numbers")
            if kind == 2 and value[0] > value[1]:
                raise ProfileValidationError("Reversed range")
    if material:
        if not ({"nozzle_temperature_c", "nozzle_temperature_range_c"} & set(settings)) or not ({"bed_temperature_c", "bed_temperature_range_c"} & set(settings)):
            raise ProfileValidationError("Missing material temperature references")
    else:
        identity = {"brand", "model", "technology"}
        if identity & set(settings):
            if not identity | {"bed_size_mm"} <= set(settings):
                raise ProfileValidationError("Incomplete catalog identity or volume")
            if settings["technology"]["value"] == "Resin" and {"nozzle_diameter_mm", "max_nozzle_temperature_c", "max_bed_temperature_c"} & set(settings):
                raise ProfileValidationError("Resin profile cannot contain FDM nozzle/heatbed fields")
        elif not {"bed_size_mm", "nozzle_diameter_mm"} <= set(settings):
            raise ProfileValidationError("Missing legacy bed/nozzle")
    return profile


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProfileValidationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _read(filename):
    path = DATA_DIR / filename
    if path.is_symlink() or path.resolve().parent != DATA_DIR.resolve():
        raise ProfileValidationError("Invalid profile path")
    with path.open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=_unique_object)


def list_printers():
    """Return deterministic IDs, excluding the material reference document."""
    return sorted(path.stem for path in DATA_DIR.glob("*.json") if path.name != "materials.json" and re.fullmatch(r"[a-z][a-z0-9_]*", path.stem))


def load_printer(printer_id="creality_k1"):
    if not isinstance(printer_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", printer_id) or printer_id not in list_printers():
        raise ProfileValidationError("Unknown printer")
    return validate_profile(_read(printer_id + ".json"))


def load_catalog(*, technology=None):
    if technology not in (None, "FDM", "Resin"):
        raise ProfileValidationError("Unknown technology filter")
    catalog = {pid: load_printer(pid) for pid in list_printers()}
    if technology is not None:
        catalog = {pid: p for pid, p in catalog.items() if p["settings"].get("technology", {}).get("value") == technology}
    return catalog


MATERIAL_NAMES = ("PLA", "PETG", "TPU", "ABS", "ASA", "PC")   # every one sourced in materials.json; ABS/ASA/PC not K1-tested


def load_materials():
    materials = _read("materials.json")
    if not isinstance(materials, dict) or set(materials) != set(MATERIAL_NAMES):
        raise ProfileValidationError("Expected " + ", ".join(MATERIAL_NAMES))
    for profile in materials.values():
        validate_profile(profile, material=True)
    return materials


def load_material(material):
    if material not in MATERIAL_NAMES:
        raise ProfileValidationError("Unknown material")
    return load_materials()[material]
