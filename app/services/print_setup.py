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
PATTERNS = {"grid": "grid", "gyroid": "gyroid", "honeycomb": "honeycomb", "cubic": "cubic", "lines": "line", "lightning": "lightning", "rectilinear": "rectilinear"}  # rectilinear is the only pattern PrusaSlicer accepts at 100% fill
SUPPORTS = ("off", "auto", "everywhere")
MATERIALS = catalog.MATERIAL_NAMES             # PLA, PETG, TPU, ABS, ASA, PC (all sourced in materials.json)
FILAMENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "materials" / "filaments.json"
FILAMENT_ID = {"PLA": "pla", "PETG": "petg", "TPU": "tpu_95a", "ABS": "abs", "ASA": "asa", "PC": "pc"}
# Filament density for the grams estimate (g/cm3). ESTIMATES: real spools vary by brand and colour, so the UI says "about".
# PLA 1.24, PETG 1.27, ASA 1.07 and PC (Blend) 1.22 match Prusament's technical data sheets; ABS 1.04 and TPU 1.21 are typical
# generic values (Prusament TPU 95A's sheet says 1.25). PrusaSlicer turns filament length into grams with this number.
DENSITY_G_CM3 = {"PLA": 1.24, "PETG": 1.27, "TPU": 1.21, "ABS": 1.04, "ASA": 1.07, "PC": 1.22}
DEFAULT_DENSITY = DENSITY_G_CM3["PLA"]


def density_of(material: str) -> float:
    return DENSITY_G_CM3.get(material, DEFAULT_DENSITY)


def grams_note(material: str) -> str:
    return (f"Grams are an estimate using about {density_of(material):g} g/cm³ for {material}. "
            "Your filament brand and colour will change it a little.")


FUME_MATERIALS = ("ABS", "ASA", "PC")          # always warned; any other filament whose fumes are marked "Significant" is too
# Beginner presets. Layer height is a fraction of the nozzle so a preset means the same thing on every nozzle.
PRESETS = {
    "draft":      {"label": "Draft",      "help": "Fastest. Visible layers.",
                   "layer_frac": 0.70, "walls": 2, "top_bottom": 3, "infill": 10, "pattern": "lightning", "speed": 120},
    "standard":   {"label": "Standard",   "help": "Good everyday quality.",
                   "layer_frac": 0.50, "walls": 2, "top_bottom": 4, "infill": 15, "pattern": "grid", "speed": 80},
    "fine":       {"label": "Fine",       "help": "Smooth surfaces, slower.",
                   "layer_frac": 0.30, "walls": 3, "top_bottom": 6, "infill": 15, "pattern": "gyroid", "speed": 50},
    "strong":     {"label": "Strong",     "help": "Thicker walls and more infill.",
                   "layer_frac": 0.50, "walls": 4, "top_bottom": 5, "infill": 40, "pattern": "cubic", "speed": 60},
    # Solid fill for lit-from-behind photo prints. 100% rectilinear is accepted by PrusaSlicer at full density
    # (grid/line refuse 100%). Layer ~0.12 mm on a 0.4 mm nozzle. Untested on a real K1 until Zach prints.
    "lithophane": {"label": "Lithophane", "help": "Solid fill for a lit photo print (~0.12 mm layers). Untested on a real K1.",
                   "layer_frac": 0.30, "walls": 2, "top_bottom": 8, "infill": 100, "pattern": "rectilinear", "speed": 40},
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
            "materials": {m: {**material_temps(m), "warning": material_safety(m)} for m in mats}, "layer_fraction": [LAYER_MIN, LAYER_MAX],
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


@lru_cache(maxsize=1)
def filaments() -> dict:
    """data/materials/filaments.json by id (enclosure / fumes / food-safe notes)."""
    return {f["id"]: f for f in json.loads(FILAMENTS_PATH.read_text(encoding="utf-8"))["filaments"]}


def filament_info(material: str) -> dict:
    return filaments().get(FILAMENT_ID.get(material, str(material).lower()), {})


def material_safety(material: str) -> dict | None:
    """Ventilation + enclosure warning the maker must see before slicing ABS / ASA / PC (or any filament with significant fumes).
    None for everyday materials. Warn-then-allow: POST /api/slice asks once, then slices when the maker says they've read it."""
    f = filament_info(material)
    fumes = f.get("fumes") or ""
    if material not in FUME_MATERIALS and not fumes.lower().startswith("significant"):
        return None
    name = f.get("name") or material
    return {"material": material, "code": "ventilation_check",
            "title": f"{name} needs fresh air and an enclosure",
            "message": (f"{name} gives off fumes while it prints that you should not breathe in. "
                        "Print it in a well-ventilated room, not in a bedroom or a small closed space, and keep people and pets away from the printer while it runs. "
                        "Use a closed printer or an enclosure (it also helps against warping), but don't point a fan or draft at the print. "
                        "If you can't ventilate the room, pick PLA or PETG instead."),
            "enclosure": f.get("enclosure") or "", "fumes": fumes,
            "tested": f"ZEIM has not test-printed {name} on a Creality K1 yet. Temperatures are general Prusa guidance; check your filament's label.",
            "confirm": "I have good ventilation. Slice it"}


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
        raise SetupError("Material must be " + ", ".join(MATERIALS[:-1]) + " or " + MATERIALS[-1] + ".")
    t = material_temps(material)
    max_noz, max_bed = p["max_nozzle_c"] or 300, p["max_bed_c"] or 110
    temp_notes = []                       # reference temperature above what this printer can reach: capped, and the maker is told
    if "nozzle_temp" not in o and t["nozzle_c"] > max_noz:
        temp_notes.append(f"The {material} reference nozzle temperature is {t['nozzle_c']} °C, but the {p['name']} tops out at {max_noz} °C, "
                          f"so ZEIM used {max_noz} °C. {material} may not print well on this printer.")
    if "bed_temp" not in o and t["bed_c"] > max_bed:
        temp_notes.append(f"The {material} reference bed temperature is {t['bed_c']} °C, but the {p['name']} tops out at {max_bed} °C, "
                          f"so ZEIM used {max_bed} °C. Expect more warping; an enclosure and a brim help.")
    noz_c = _num(o.get("nozzle_temp", min(t["nozzle_c"], max_noz)), 150, max_noz, "Nozzle temperature", int)
    bed_c = _num(o.get("bed_temp", min(t["bed_c"], max_bed)), 0, max_bed, "Bed temperature", int)
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
            "first_layer_bed_temp": min(t["first_layer_bed_c"], max_bed) if "bed_temp" not in o else bed_c,
            "material_warning": material_safety(material), "temp_notes": temp_notes,
            "filament_density": density_of(material), "grams_note": grams_note(material)}


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
           "filament_type": s["material"], "filament_density": f"{s.get('filament_density') or density_of(s['material']):g}",
           "layer_height": f"{s['layer_height']:g}",
           # Lithophane: first layer matches the rest (sharper vertical detail). Others: thicker first layer for bed stick.
           "first_layer_height": (f"{s['layer_height']:g}" if s.get("preset") == "lithophane"
                                 else f"{min(max(s['layer_height'], s['nozzle'] * 0.5), s['nozzle'] * LAYER_MAX):g}"),
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
