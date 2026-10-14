"""Calibration wizard (Zach, 2026-10-13): four simple test prints for the picked printer + nozzle + filament.

  first_layer  five thin squares (corners + middle)  -> bed level / Z offset, first-layer squish
  temp_tower   stacked bands, each printed 5 °C cooler -> best nozzle temperature for THIS spool
  flow         an open-top cup with a two-line wall   -> flow (PrusaSlicer `extrusion_multiplier`)
  retraction   two thin pillars with a gap            -> stringing (`retract_length`, `retract_speed`, `temperature`)

Every test gives plain-words steps, what good and bad look like, and the real PrusaSlicer setting names it tunes
(from data/smartfix/smartfix-map.json). Numbers are starting points (estimates), never K1- or device-tested by ZEIM.
Models are generated here (no user data); slicing goes through the normal engine (`slice_engine.profile_for`), and the
temperature tower gets one `M104 S<temp>` per band at the matching ;LAYER_CHANGE (ZEIM post-processes its own G-code
output; PrusaSlicer itself runs unmodified)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import trimesh

from app.services import print_setup as ps

TESTS = ("first_layer", "temp_tower", "flow", "retraction")
ESTIMATE = "Starting points only (estimates). ZEIM has not tested these on your printer; your filament box's range wins."
SMARTFIX_MAP = Path(__file__).resolve().parents[2] / "data" / "smartfix" / "smartfix-map.json"
BAND_H = 8.0               # temperature tower: mm per band
BASE_H = 1.0
RESIN_SAFETY = ("Resin safety: wear nitrile gloves and eye protection, print in a ventilated room, "
                "and wash and cure parts with IPA (isopropyl alcohol) away from food areas.")


class CalibrationError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@lru_cache(maxsize=1)
def smartfix_map() -> dict:
    """slicer_key -> mapping (prusa_key, application_mode, adjustment, verification) from the Smart Fix map (PR #25)."""
    d = json.loads(SMARTFIX_MAP.read_text(encoding="utf-8"))
    return {m["slicer_key"]: m for m in d["mappings"]}


def _setting(slicer_key: str) -> dict:
    m = smartfix_map()[slicer_key]
    return {"key": m["prusa_key"], "verified": m["verification"], "confirm": m["application_mode"] == "user_confirmation"}


# --------------------------------------------------------------------------- models (all mm, Z up, sitting on z=0)
def _box(x0, y0, z0, x1, y1, z1) -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return b


def _union(parts) -> trimesh.Trimesh:
    m = trimesh.boolean.union(parts, engine="manifold") if len(parts) > 1 else parts[0]
    m.merge_vertices()
    return m


def first_layer_model(bed, first_layer_h: float) -> trimesh.Trimesh:
    """Five squares one first-layer thick: four corners + middle, inside ~70 % of the bed."""
    x, y = bed[0], bed[1]
    side = round(min(30.0, x / 6, y / 6), 1)
    sx, sy = x * 0.7, y * 0.7                      # overall footprint (centred on the bed by the slicer)
    pts = [(0, 0), (sx - side, 0), (0, sy - side), (sx - side, sy - side), ((sx - side) / 2, (sy - side) / 2)]
    return trimesh.util.concatenate([_box(px, py, 0, px + side, py + side, first_layer_h) for px, py in pts])


def temp_tower_model(bands: int) -> trimesh.Trimesh:
    """Base, one block per band with a thin neck between bands, a 45° overhang on each band, and a separate
    pillar (7 mm gap) so each band also shows its stringing."""
    parts = [_box(0, 0, 0, 42, 12, BASE_H)]
    for i in range(bands):
        z0 = BASE_H + i * BAND_H
        parts.append(_box(6, 1, z0, 30, 11, z0 + BAND_H - 1.0))            # main block
        parts.append(_box(8, 2, z0 + BAND_H - 1.0, 28, 10, z0 + BAND_H))  # neck: a visible line between bands
        # 45° overhang on the left: grows out from x=6 at the band's bottom to x=1 at 5 mm up, then straight
        h = BAND_H - 1.0
        wedge = trimesh.convex.convex_hull(np.array([
            [6, 1, z0], [6, 11, z0], [6, 1, z0 + h], [6, 11, z0 + h],
            [1, 1, z0 + 5], [1, 11, z0 + 5], [1, 1, z0 + h], [1, 11, z0 + h]]))
        parts.append(wedge)
    top = BASE_H + bands * BAND_H
    parts.append(_box(37, 4, BASE_H, 41, 8, top))                         # stringing pillar (gap 30 -> 37 = 7 mm)
    return _union(parts)


def flow_wall(nozzle: float, layer: float) -> tuple[float, float]:
    """(line width, expected two-line wall thickness) — PrusaSlicer spacing = width - layer*(1 - pi/4)."""
    w = ps.line_width(nozzle)
    spacing = w - layer * (1 - np.pi / 4)
    return w, round(w + spacing, 2)


def flow_model(wall: float) -> trimesh.Trimesh:
    """20 x 20 x 15 mm open-top cup with a two-line wall and a 1 mm floor."""
    outer = _box(0, 0, 0, 20, 20, 15)
    inner = _box(wall, wall, 1.0, 20 - wall, 20 - wall, 15.5)
    m = trimesh.boolean.difference([outer, inner], engine="manifold")
    m.merge_vertices()
    return m


def retraction_model(bed) -> trimesh.Trimesh:
    """Two 5 x 5 x 25 mm pillars on a thin base strip, gap 40 mm (less on a tiny bed)."""
    gap = min(40.0, bed[0] * 0.4)
    length = gap + 10
    return _union([_box(0, 0, 0, length, 6, 0.6), _box(0.5, 0.5, 0, 5.5, 5.5, 25.6), _box(length - 5.5, 0.5, 0, length - 0.5, 5.5, 25.6)])


# --------------------------------------------------------------------------- plan
def _context(printer_id, nozzle, material):
    try:
        pid, n = ps.resolve(printer_id, None if nozzle in (None, "") else float(nozzle))
    except (ps.SetupError, ValueError) as e:
        raise CalibrationError(str(e) if isinstance(e, ps.SetupError) else "Nozzle must be a number like 0.4.")
    p = ps.printer_public(pid)
    material = material or "PLA"
    if material not in ps.MATERIALS:
        raise CalibrationError("Material must be " + ", ".join(ps.MATERIALS[:-1]) + " or " + ps.MATERIALS[-1] + ".")
    return pid, n, p, material


def temp_bands(p: dict, material: str) -> list[int]:
    """Hottest at the bottom, 5 °C cooler per band. Centre on the sourced reference temperature (or the middle of the
    sourced range), from +10 down to -15; never above the printer's sourced maximum, never below 170 °C."""
    t = ps.material_temps(material)
    rng = ps.catalog.load_material(material)["settings"].get("nozzle_temperature_range_c", {}).get("value")
    top = (max(rng) if rng else t["nozzle_c"] + 10)
    low = (min(rng) - 5 if rng else t["nozzle_c"] - 15)
    cap = p["max_nozzle_c"] or 300
    top = min(top, cap)
    bands = [v for v in range(int(top), int(low) - 1, -5) if v >= 170]
    return bands[:7] if len(bands) >= 3 else [min(cap, t["nozzle_c"]) - 5 * i for i in range(3)]


def plan(printer_id=None, nozzle=None, material=None) -> dict:
    pid, n, p, material = _context(printer_id, nozzle, material)
    base = {"printer_id": pid, "printer": p["name"], "material": material, "estimate_note": ESTIMATE}
    if n is None:
        slicer = p["official_slicer"] or "your resin printer's own slicer"
        return {**base, "resin": True, "nozzle": None, "tests": [],
                "message": f"The {p['name']} is a resin printer. These calibration prints are for filament printers. "
                           f"For resin, print the exposure test that comes with {slicer} and follow its steps.",
                "safety": RESIN_SAFETY}
    s = ps.settings_for(pid, n, {"material": material})
    ini = ps.ini_overrides(s)
    first_h = float(ini["first_layer_height"])
    bands = temp_bands(p, material)
    w, wall = flow_wall(n, s["layer_height"])
    retract = ini.get("retract_length")
    smf = smartfix_map()
    r_step = smf["retraction_distance"]["adjustment"]["step_mm"]
    r_max = smf["retraction_distance"]["adjustment"]["max_change_mm"]
    s_step = smf["retraction_speed"]["adjustment"]["step_mm_s"]
    start_r = float(retract) if retract else 0.8
    ladder = [round(start_r + r_step * 2 * i, 2) for i in range(int(r_max / (r_step * 2)) + 1)]
    tests = [
        {"id": "first_layer", "title": "1. First layer",
         "why": "Almost every failed print starts with a bad first layer. This checks that your bed is level and the nozzle is the right height.",
         "prints": f"Five thin squares, {first_h:g} mm thick: one in each corner and one in the middle. About 5 minutes.",
         "steps": ["Clean the bed with soap and water or IPA (no finger marks).",
                   "Run your printer's bed levelling / auto-calibration first if it has one.",
                   "Print it and watch the first lines go down. Don't walk away.",
                   "Look at all five squares when it's done, and run a finger over them."],
         "good": ["Lines are slightly flattened and touch each other, no gaps.", "The surface feels smooth and even in all five squares."],
         "bad": [{"see": "Round lines with gaps between them, or lines that don't stick", "means": "Nozzle too high", "do": "Lower the Z offset a little (about 0.02 to 0.05 mm) on the printer, then print again."},
                 {"see": "Rough, wavy or see-through squares, or the nozzle scrapes", "means": "Nozzle too low", "do": "Raise the Z offset a little (about 0.02 to 0.05 mm), then print again."},
                 {"see": "Some squares good, others bad", "means": "Bed not level", "do": "Run the bed levelling again (or adjust the knobs on that corner), then print again."}],
         "settings": [_setting("z_offset"), _setting("first_layer_speed"), _setting("bed_temperature")],
         "values": {"first_layer_height_mm": first_h, "bed_temp_c": s["first_layer_bed_temp"]}},
        {"id": "temp_tower", "title": "2. Temperature tower",
         "why": "Every spool is a little different. This finds the nozzle temperature that looks best for this filament.",
         "prints": f"A tower of {len(bands)} blocks, {BAND_H:g} mm each. The bottom block prints at {bands[0]} °C and each block above is 5 °C cooler, down to {bands[-1]} °C.",
         "steps": ["Slice it in ZEIM: the temperature changes are added for you. (In another slicer, add a temperature change every "
                   f"{BAND_H:g} mm starting at {BASE_H:g} mm.)",
                   "Print it with the same filament you want to tune.",
                   "Write the temperatures on the blocks with a marker as you go (bottom = hottest).",
                   "Compare the blocks: overhang on the left, surface, and strings to the little pillar."],
         "good": ["Clean, sharp overhang on the left.", "Smooth walls and few or no strings to the pillar.", "Layers don't split when you gently bend the tower."],
         "bad": [{"see": "Lots of strings, blobs or a droopy overhang", "means": "Too hot", "do": "Pick a cooler block."},
                 {"see": "Rough, dull walls or layers that split apart easily", "means": "Too cold", "do": "Pick a hotter block."}],
         "pick": "Use the temperature of the best-looking block as your nozzle temperature (PrusaSlicer `temperature`).",
         "settings": [_setting("nozzle_temperature")],
         "values": {"bands_c": bands, "band_height_mm": BAND_H, "base_mm": BASE_H}},
        {"id": "flow", "title": "3. Flow",
         "why": "Checks that the printer pushes out the right amount of plastic. Too little leaves gaps; too much makes blobs and rough tops.",
         "prints": f"An open-top cup, 20 × 20 × 15 mm, with a wall exactly two lines thick (about {wall:g} mm).",
         "steps": ["Print it. ZEIM slices it with 2 walls and no infill.",
                   "With calipers, measure the wall in the middle of each of the four sides and average the four numbers.",
                   f"New flow = current flow × {wall:g} ÷ your average. Example: 1.00 × {wall:g} ÷ {round(wall * 1.05, 2):g} ≈ {round(1 / 1.05, 2):g}.",
                   "No calipers? Look at the walls in good light instead (see below)."],
         "good": [f"The wall measures about {wall:g} mm.", "Walls look solid with no gaps between the two lines."],
         "bad": [{"see": "Wall thinner than expected, gaps or see-through spots", "means": "Under-extrusion", "do": "Raise flow a little (for example 1.00 → 1.03), and check the filament isn't tangled or wet."},
                 {"see": "Wall thicker than expected, blobs, rough or bulging sides", "means": "Over-extrusion", "do": "Lower flow a little (for example 1.00 → 0.97)."}],
         "pick": "Change flow (PrusaSlicer `extrusion_multiplier`) in small steps. Only change it after the temperature test.",
         "settings": [_setting("flow_ratio")],
         "values": {"expected_wall_mm": wall, "line_width_mm": w, "layer_height_mm": s["layer_height"]}},
        {"id": "retraction", "title": "4. Retraction (stringing)",
         "why": "Retraction pulls the filament back a little before the nozzle moves, so it doesn't leave thin hairs.",
         "prints": "Two thin pillars with a gap between them. About 15 minutes.",
         "steps": ["Do this after the temperature tower, at your new temperature.",
                   (f"Print it once at the starting retraction ({start_r:g} mm, from your printer profile)." if retract else
                    "Print it once at your printer maker's retraction setting (their slicer profile). ZEIM has no sourced value for this "
                    f"printer, so it slices with {start_r:g} mm, a common start for direct-drive printers (an estimate; bowden printers usually need more)."),
                   "Look at the gap between the pillars.",
                   f"If there are strings, raise the retraction length by {r_step * 2:g} mm and print again. Try the values in order: "
                   + ", ".join(f"{v:g} mm" for v in ladder) + ". Stop at the first one with clean gaps."],
         "good": ["No strings, or only a few very thin ones that brush off.", "Pillars are solid with no missing layers."],
         "bad": [{"see": "Lots of strings between the pillars", "means": "Not enough retraction, or too hot", "do": f"Raise retraction by {r_step * 2:g} mm, or lower the temperature by 5 °C."},
                 {"see": "Gaps or thin layers in the pillars, or clicking from the extruder", "means": "Too much retraction", "do": "Go back to the previous value."},
                 {"see": "Fuzzy hairs whatever you change", "means": "Wet filament", "do": "Dry the filament (follow the box), then test again."}],
         "pick": f"Use the lowest retraction length that gives clean gaps (PrusaSlicer `retract_length`). Retraction speed (`retract_speed`) can go up {s_step:g} mm/s at a time if strings stay.",
         "settings": [_setting("retraction_distance"), _setting("retraction_speed"), _setting("nozzle_temperature"), _setting("travel_avoid_crossing_perimeters")],
         "values": {"start_retract_mm": start_r, "ladder_mm": ladder, "from_profile": bool(retract)}},
    ]
    return {**base, "resin": False, "nozzle": n, "tests": tests, "material_warning": s.get("material_warning"),
            "temp_notes": s.get("temp_notes") or [], "order_note": "Do them in order: first layer, temperature, flow, then retraction."}


def model_for(test: str, printer_id=None, nozzle=None, material=None) -> trimesh.Trimesh:
    if test not in TESTS:
        raise CalibrationError("Unknown calibration test.", 404)
    pid, n, p, material = _context(printer_id, nozzle, material)
    if n is None:
        raise CalibrationError(f"The {p['name']} is a resin printer: use the exposure test in its own slicer.")
    s = ps.settings_for(pid, n, {"material": material})
    bed = ps.bed_of(pid)
    if test == "first_layer":
        return first_layer_model(bed, float(ps.ini_overrides(s)["first_layer_height"]))
    if test == "temp_tower":
        return temp_tower_model(len(temp_bands(p, material)))
    if test == "flow":
        return flow_model(flow_wall(n, s["layer_height"])[1])
    return retraction_model(bed)


def slice_opts(test: str, material: str) -> dict:
    """Slicer panel values for each test (everything else = the Standard preset)."""
    o = {"material": material}
    if test == "flow":
        o.update(walls="2", infill="0", top_bottom="3")
    if test == "retraction":
        o.update(infill="15")
    if test == "temp_tower":
        o.update(infill="15", walls="2")
    return o


_LAYER = re.compile(r"^;Z:\s*([\d.]+)")


def add_temperature_bands(gcode: Path, bands: list[int], band_h: float = BAND_H, base: float = BASE_H) -> int:
    """Insert `M104 S<t>` once per band, right after the ;Z: comment of the first layer at or above the band's start.
    Returns how many were inserted. Band 0 (hottest) starts at the first layer above the base."""
    lines = gcode.read_text(errors="ignore").splitlines(keepends=True)
    out, done = [], 0
    for line in lines:
        out.append(line)
        m = _LAYER.match(line)
        if m and done < len(bands):
            z = float(m.group(1))
            if z > base + done * band_h + 1e-6:
                out.append(f"M104 S{bands[done]} ; ZEIM temperature tower band {done + 1}: {bands[done]} C\n")
                done += 1
    gcode.write_text("".join(out))
    return done
