"""Chosen printer + nozzle -> slicer settings. ONE place that turns the sourced catalog (app/printers.py) and the
user's slicer panel into PrusaSlicer config keys, used by every slicing path (POST /api/slice and /api/print/slice).

Rules: bed size, nozzle and retraction come from the catalog JSON (every value sourced there). Line width and layer
height are scaled to the nozzle: line width = 1.125 x nozzle, layer height clamped to 25-75 % of the nozzle.
Temperatures come from materials.json and are clamped to the printer's sourced max temperatures."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app import printers as catalog

SPECS_PATH = Path(__file__).resolve().parents[2] / "data" / "nozzles" / "nozzle-specs.json"
# Catalog printer -> family key in nozzle-specs.json printer_nozzle_availability (and its manufacturer_profile brand).
FAMILY = {"creality_k1": "Creality K1 family", "creality_k1_max": "Creality K1 family", "creality_k1c": "Creality K1 family"}
BRAND_FAMILY = {"Bambu Lab": "Bambu Lab", "Prusa": "Prusa", "Prusa Research": "Prusa"}
PROFILE_BRAND = {"Creality K1 family": "Creality", "Bambu Lab": "Bambu Lab", "Prusa": "Prusa"}
ADVANCED_NOTE = "Advanced: calibrate before use"


@lru_cache(maxsize=1)
def specs() -> dict:
    return json.loads(SPECS_PATH.read_text(encoding="utf-8"))

DEFAULT_PRINTER = "creality_k1"
DEFAULT_NOZZLE = 0.4
NOZZLES = (0.2, 0.4, 0.6, 0.8, 1.0)       # sizes with sourced specs in data/nozzles/nozzle-specs.json
LAYER_MIN, LAYER_MAX = 0.25, 0.75            # fraction of the nozzle
LINE_WIDTH_FACTOR = 1.125
PATTERNS = {"grid": "grid", "gyroid": "gyroid", "honeycomb": "honeycomb", "cubic": "cubic", "lines": "line", "lightning": "lightning"}
SUPPORTS = ("off", "auto", "everywhere")
MATERIALS = ("PLA", "PETG", "TPU")
# Beginner presets. Layer height is a fraction of the nozzle so a preset means the same thing on every nozzle.
PRESETS = {
    "draft":    {"label": "Draft",    "help": "Fastest. Visible layers.",           "layer_frac": 0.70, "walls": 2, "top_bottom": 3, "infill": 10, "pattern": "lightning", "speed": 120},
    "standard": {"label": "Standard", "help": "Good everyday quality.",             "layer_frac": 0.50, "walls": 2, "top_bottom": 4, "infill": 15, "pattern": "grid", "speed": 80},
    "fine":     {"label": "Fine",     "help": "Smooth surfaces, slower.",           "layer_frac": 0.30, "walls": 3, "top_bottom": 6, "infill": 15, "pattern": "gyroid", "speed": 50},
    "strong":   {"label": "Strong",   "help": "Thicker walls and more infill.",     "layer_frac": 0.50, "walls": 4, "top_bottom": 5, "infill": 40, "pattern": "cubic", "speed": 60},
}
DEFAULT_PRESET = "standard"
PRESET_PUBLIC = ("label", "help", "layer_frac", "walls", "top_bottom", "infill", "pattern", "speed")


class SetupError(ValueError):
    pass


def _v(p, key, default=None):
    return p["settings"].get(key, {}).get("value", default)


@lru_cache(maxsize=1)
def _catalog():
    return catalog.load_catalog()


def family_of(pid: str):
    p = _catalog()[pid]
    return FAMILY.get(pid) or BRAND_FAMILY.get(_v(p, "brand"))


def nozzle_spec(n: float) -> dict:
    return specs()["nozzles"][f"{n:.1f}"]


def nozzle_options(pid: str) -> list[dict]:
    """Nozzle sizes this printer supports, each marked profiled (manufacturer-documented) or 'Advanced: calibrate'.
    Families in nozzle-specs.json list their sizes; a printer with no family data gets every sourced size, and only
    its stock nozzle counts as profiled. 1.0 mm is always Advanced."""
    p = _catalog()[pid]
    if _v(p, "technology") == "Resin":
        return []
    fam = family_of(pid)
    av = specs()["printer_nozzle_availability"].get(fam or "", {})
    sizes = [float(x) for x in (av.get("available_sizes") or av.get("documented_sizes") or [f"{x:.1f}" for x in NOZZLES])]
    stock = float(av.get("shipped_default_mm") or _v(p, "nozzle_diameter_mm") or 0.4)
    documented = {float(x) for x in (av.get("documented_official_profiles") or av.get("documented_sizes") or [])} | {stock}
    out = []
    for n in sorted(set(sizes) & set(NOZZLES)):
        sp = nozzle_spec(n)
        mp = (sp.get("manufacturer_profile") or {}).get(PROFILE_BRAND.get(fam, ""), {})
        profiled = n in documented and n != 1.0 and bool(fam or n == stock)
        out.append({"mm": n, "profiled": profiled, "advanced": not profiled, "note": "" if profiled else ADVANCED_NOTE,
                    "stock": n == stock, "use_case": sp.get("use_case", ""),
                    "layer_height_mm": sp["layer_height_mm"], "line_width_mm": sp["line_width_mm"],
                    "manufacturer": {k: v for k, v in mp.items() if k != "printers"} if mp else None,
                    "manufacturer_name": PROFILE_BRAND.get(fam) if mp else None})
    return out


def nozzle_option(pid: str, n: float):
    return next((o for o in nozzle_options(pid) if o["mm"] == n), None)


def printer_public(pid: str) -> dict:
    p = _catalog()[pid]
    resin = _v(p, "technology") == "Resin"
    return {"id": pid, "name": f"{_v(p, 'brand')} {_v(p, 'model')}", "brand": _v(p, "brand"), "model": _v(p, "model"),
            "technology": _v(p, "technology"), "bed_mm": _v(p, "bed_size_mm"),
            "stock_nozzle_mm": None if resin else _v(p, "nozzle_diameter_mm"),
            "nozzles": [] if resin else [o["mm"] for o in nozzle_options(pid)],
            "nozzle_options": nozzle_options(pid), "nozzle_family": family_of(pid),
            "max_nozzle_c": _v(p, "max_nozzle_temperature_c"), "max_bed_c": _v(p, "max_bed_temperature_c"),
            "official_slicer": _v(p, "official_slicer_name"), "official_slicer_url": _v(p, "official_slicer_download_url"),
            "native_formats": _v(p, "native_file_formats") or []}


def public() -> dict:
    mats = catalog.load_materials()
    return {"default": {"printer_id": DEFAULT_PRINTER, "nozzle": DEFAULT_NOZZLE}, "nozzles": list(NOZZLES),
            "printers": [printer_public(pid) for pid in sorted(_catalog(), key=lambda k: printer_public(k)["name"])],
            "patterns": list(PATTERNS), "supports": list(SUPPORTS),
            # the preset's own numbers too, so the Advanced fields start from the preset the maker picked (not from Standard's numbers)
            "presets": [{"id": k, **{x: v[x] for x in PRESET_PUBLIC}} for k, v in PRESETS.items()], "default_preset": DEFAULT_PRESET,
            "materials": {m: material_temps(m) for m in mats}, "layer_fraction": [LAYER_MIN, LAYER_MAX],
            "nozzle_validation": specs()["scope"]["validation"], "advanced_note": ADVANCED_NOTE}


def resolve(printer_id=None, nozzle=None) -> tuple[str, float | None]:
    """Validated (printer_id, nozzle). Resin printers have no nozzle (None). Empty values mean the K1 at 0.4 mm."""
    pid = printer_id or DEFAULT_PRINTER
    if pid not in _catalog():
        raise SetupError("Unknown printer. Pick one from the list.")
    if printer_public(pid)["technology"] == "Resin":
        return pid, None
    if nozzle in (None, ""):
        return pid, DEFAULT_NOZZLE
    try:
        n = round(float(nozzle), 2)
    except (TypeError, ValueError):
        raise SetupError("Nozzle size must be a number.") from None
    sizes = printer_public(pid)["nozzles"]
    if n not in sizes:
        raise SetupError(f"The {printer_public(pid)['name']} takes a " + ", ".join(f"{x:g}" for x in sizes) + " mm nozzle.")
    return pid, n


def material_temps(material: str) -> dict:
    s = catalog.load_material(material)["settings"]
    val = lambda k: s.get(k, {}).get("value")
    noz = val("nozzle_temperature_c") or round(sum(val("nozzle_temperature_range_c")) / 2)
    bed = val("bed_temperature_c") or round(sum(val("bed_temperature_range_c")) / 2)
    return {"nozzle_c": noz, "first_layer_nozzle_c": val("first_layer_nozzle_temperature_c") or noz,
            "bed_c": bed, "first_layer_bed_c": val("first_layer_bed_temperature_c") or bed}


def layer_range(nozzle: float) -> tuple[float, float]:
    """25-75 % of the nozzle, narrowed further by the sourced min/max in nozzle-specs.json."""
    sp = nozzle_spec(nozzle)["layer_height_mm"]
    return round(max(nozzle * LAYER_MIN, sp["min"]), 3), round(min(nozzle * LAYER_MAX, sp["max"]), 3)


def preset_layer(nozzle: float, preset: str = DEFAULT_PRESET) -> float:
    """A preset's layer height on this nozzle: the sourced recommended layer scaled by the preset (Standard = recommended), kept in range.
    static/printer.js presetLayer() uses the same formula so the Advanced field shows what Beginner would slice with."""
    lo, hi = layer_range(nozzle)
    rec = nozzle_spec(nozzle)["layer_height_mm"]["recommended"]          # sourced starting value; presets scale around it
    return round(min(max(rec * PRESETS[preset]["layer_frac"] / 0.5, lo), hi), 3)


def line_width(nozzle: float) -> float:
    return float(nozzle_spec(nozzle)["line_width_mm"]["recommended"])


def _num(v, lo, hi, name, cast=float):
    try:
        x = cast(v)
    except (TypeError, ValueError):
        raise SetupError(f"{name} must be a number.") from None
    if not (lo <= x <= hi):
        raise SetupError(f"{name} must be between {lo:g} and {hi:g}.")
    return x


def settings_for(printer_id=None, nozzle=None, opts: dict | None = None) -> dict:
    """Normalised slicer settings (preset first, then explicit Advanced values). Raises SetupError for bad input."""
    pid, n = resolve(printer_id, nozzle)
    p = printer_public(pid)
    if n is None:
        raise SetupError(f"The {p['name']} is a resin printer. Slice it in {p['official_slicer'] or 'its own slicer'}; download the STL or 3MF below.")
    o = {k: v for k, v in (opts or {}).items() if v not in (None, "")}
    preset = o.get("preset") or DEFAULT_PRESET
    if preset not in PRESETS:
        raise SetupError("Unknown preset.")
    pr = PRESETS[preset]
    lo, hi = layer_range(n)
    layer = preset_layer(n, preset)
    if "layer_height" in o:
        layer = _num(o["layer_height"], lo, hi, f"Layer height for a {n:g} mm nozzle")
    material = o.get("material", "PLA")
    if material not in MATERIALS:
        raise SetupError("Material must be PLA, PETG or TPU.")
    t = material_temps(material)
    max_noz, max_bed = p["max_nozzle_c"] or 300, p["max_bed_c"] or 110
    noz_c = _num(o.get("nozzle_temp", t["nozzle_c"]), 150, max_noz, "Nozzle temperature", int)
    bed_c = _num(o.get("bed_temp", t["bed_c"]), 0, max_bed, "Bed temperature", int)
    pattern = o.get("infill_pattern", pr["pattern"])
    if pattern not in PATTERNS:
        raise SetupError("Unknown infill pattern.")
    supports = o.get("supports", "off")
    if supports not in SUPPORTS:
        raise SetupError("Supports must be off, auto or everywhere.")
    return {"printer_id": pid, "printer": p["name"], "nozzle": n, "preset": preset, "material": material,
            "layer_height": layer, "line_width": line_width(n),
            "nozzle_profiled": bool((nozzle_option(pid, n) or {}).get("profiled")),
            "max_volumetric_speed": _mvs(pid, n, material),
            "walls": _num(o.get("walls", pr["walls"]), 1, 10, "Walls", int),
            "top_bottom": _num(o.get("top_bottom", pr["top_bottom"]), 0, 20, "Top/bottom layers", int),
            "infill": _num(o.get("infill", pr["infill"]), 0, 100, "Infill", int), "infill_pattern": pattern,
            "supports": supports, "brim": _num(o.get("brim", 0), 0, 30, "Brim width"),
            "speed": _num(o.get("speed", pr["speed"]), 10, min(500, float(p.get("max_speed") or 500)), "Speed", int),
            "nozzle_temp": noz_c, "bed_temp": bed_c,
            "first_layer_nozzle_temp": max(noz_c, min(t["first_layer_nozzle_c"], max_noz)) if "nozzle_temp" not in o else noz_c,
            "first_layer_bed_temp": min(t["first_layer_bed_c"], max_bed) if "bed_temp" not in o else bed_c}


def _mvs(pid, n, material):
    """Manufacturer max volumetric speed for this nozzle + material when published (e.g. Creality K1 0.2 mm)."""
    m = (nozzle_option(pid, n) or {}).get("manufacturer") or {}
    return m.get(f"{material.lower()}_max_volumetric_speed_mm3_s")


def ini_overrides(s: dict) -> dict:
    """PrusaSlicer config keys for normalised settings (+ the printer's sourced bed, nozzle and retraction)."""
    p = _catalog()[s["printer_id"]]
    x, y, z = _v(p, "bed_size_mm")
    out = {"bed_shape": f"0x0,{x:g}x0,{x:g}x{y:g},0x{y:g}", "max_print_height": f"{z:g}",
           "nozzle_diameter": f"{s['nozzle']:g}", "filament_diameter": f"{_v(p, 'filament_diameter_mm', 1.75):g}",
           "filament_type": s["material"], "layer_height": f"{s['layer_height']:g}",
           "first_layer_height": f"{min(max(s['layer_height'], s['nozzle'] * 0.5), s['nozzle'] * LAYER_MAX):g}",
           "extrusion_width": f"{s['line_width']:g}", "first_layer_extrusion_width": f"{s['line_width']:g}",
           "perimeters": str(s["walls"]), "top_solid_layers": str(s["top_bottom"]), "bottom_solid_layers": str(s["top_bottom"]),
           "fill_density": f"{s['infill']}%", "fill_pattern": PATTERNS[s["infill_pattern"]],
           "support_material": "0" if s["supports"] == "off" else "1",
           "support_material_auto": "0" if s["supports"] == "off" else "1",
           "support_material_buildplate_only": "1" if s["supports"] == "auto" else "0",
           "brim_width": f"{s['brim']:g}", "perimeter_speed": str(s["speed"]), "infill_speed": str(s["speed"]),
           "external_perimeter_speed": str(max(10, int(s["speed"] * 0.7))), "solid_infill_speed": str(s["speed"]),
           "top_solid_infill_speed": str(max(10, int(s["speed"] * 0.6))),
           "temperature": str(s["nozzle_temp"]), "first_layer_temperature": str(s["first_layer_nozzle_temp"]),
           "bed_temperature": str(s["bed_temp"]), "first_layer_bed_temperature": str(s["first_layer_bed_temp"])}
    if s.get("max_volumetric_speed"):
        out["max_volumetric_speed"] = f"{s['max_volumetric_speed']:g}"
    for key, ini_key in (("retraction_length_mm", "retract_length"), ("retraction_speed_mm_s", "retract_speed"), ("z_hop_mm", "retract_lift")):
        if _v(p, key) is not None:
            out[ini_key] = f"{_v(p, key):g}"
    return out


def bed_of(printer_id: str) -> tuple[float, float, float]:
    return tuple(float(v) for v in _v(_catalog()[printer_id], "bed_size_mm"))
