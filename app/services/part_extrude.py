"""Per-part filament slots into one PrusaSlicer run.

A print whose parts all use one slot is left alone. The caller slices the same
STL, with the same profile, as it does today.

When parts use more than one slot and the printer has a multi-material unit,
the slice is a 3MF whose volumes (or objects) name those slots, and the
profile's own filament settings are repeated once per used slot. A catalog
profile is one nozzle. The unit is one nozzle plus a filament changer, which
PrusaSlicer calls single-extruder multi-material, and that mode needs a wipe
tower. The tower uses PrusaSlicer's own width when the bed can hold it.

No multi-material unit, or a profile ZEIM cannot read as one nozzle or as
exactly the slots in use, slices as one colour. The part slots stay on the
model. Nothing here has been printed.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.core import meshparts, part3mf
from app.core.partslots import PRINT_NOTE
from app.services import editproj
from app.services import filament_slots as fslots
from app.services.history import store
from app.services.print_setup import density_of, export_slot_count, material_temps, printer_public
from app.services.slice_engine import merge_ini

NO_UNIT = (
    "This printer has no multi-material unit. "
    "ZEIM sliced this as one colour. The part slots stay on the model."
)
ONE_EXTRUDER = (
    "This printer profile has one extruder. "
    "ZEIM sliced this as one colour. The part slots stay on the model."
)
OUTSIDE = (
    "A part is assigned to a slot this printer does not have. "
    "ZEIM sliced this as one colour. The part slots stay on the model."
)
MESH = (
    "These part slots do not match the mesh on the bed. "
    "ZEIM sliced this as one colour. The part slots stay on the model."
)
PAINT = (
    "Paint-on supports are sliced as one colour. "
    "The part slots stay on the model."
)

# PrusaSlicer 2.9 keys that are one value per extruder. A single value is that
# profile's setting, repeated. A list that is already the right length is kept.
_COMMA = (
    "nozzle_diameter", "filament_diameter", "filament_density",
    "temperature", "first_layer_temperature", "bed_temperature", "first_layer_bed_temperature",
    "retract_length", "retract_speed", "retract_lift", "retract_before_wipe",
    "retract_length_toolchange", "retract_restart_extra", "retract_restart_extra_toolchange",
    "deretract_speed", "min_fan_speed", "max_fan_speed", "disable_fan_first_layers",
    "max_volumetric_speed", "filament_max_volumetric_speed",
    "extrusion_width", "first_layer_extrusion_width",
)
_SEMI = ("filament_type", "filament_colour", "extruder_colour")
# PrusaSlicer's own wipe-tower defaults (2.8/2.9 --help-fff). Used when they fit this bed.
_TOWER_W = 60.0
_TOWER_BRIM = 2.0
_TOWER_X = 180.0
_TOWER_Y = 140.0


def _fallback(reason: str, message: str) -> dict:
    return {"mode": "fallback", "reason": reason, "message": message, "parts": [], "header_extra": ""}


def _ini_map(text: str) -> dict[str, str]:
    out = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _bits(value: str, sep: str) -> list[str]:
    return [part.strip() for part in (value or "").split(sep) if part.strip()]


def _fit(value: str, n: int, sep: str) -> str | None:
    bits = _bits(value, sep)
    if len(bits) == n:
        return sep.join(bits)
    if len(bits) == 1:
        return sep.join([bits[0]] * n)
    return None


def _hex(value, default: str = "#FFFFFF") -> str:
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text.startswith("#"):
        text = "#" + text
    if len(text) == 9:
        text = text[:7]
    if len(text) == 7 and all(c in "0123456789abcdefABCDEF" for c in text[1:]):
        return text.upper()
    return default


def _assigned(parts) -> list[int]:
    """Distinct slots in part order. A missing slot is slot 1, the same as the 3MF export."""
    found = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        slot = part.get("slot")
        if type(slot) is not int or slot < 1:
            slot = 1
        if slot not in found:
            found.append(slot)
    return found


def _meta(model_id: str):
    try:
        meta = store.get(model_id)
    except Exception:
        return None
    if not isinstance(meta, dict) or meta.get("kind") != "edit":
        return None
    return meta


def _capability(printer_id: str, unit_id, unit_count) -> tuple[int, bool]:
    try:
        count = int(export_slot_count(printer_id, unit_id or "", "" if unit_count is None else str(unit_count)))
    except Exception:
        count = 1
    if count < 1:
        count = 1
    return count, count > 1


def _nozzle_count(keys: dict[str, str]) -> int:
    """1 when the profile is one nozzle and one filament. N when both lists match. 0 when they do not."""
    nozzles = _bits(keys.get("nozzle_diameter", ""), ",")
    filaments = _bits(keys.get("filament_diameter", ""), ",")
    if len(nozzles) == 1 and len(filaments) == 1:
        return 1
    if len(nozzles) >= 2 and len(nozzles) == len(filaments):
        return len(nozzles)
    return 0


def _by_slot(plan: dict | None) -> tuple[dict, dict]:
    plan = plan or {}
    slots = list(plan.get("slots") or [])
    mats = list(plan.get("materials") or [])
    cols = list(plan.get("colours") or plan.get("colour_of_filament") or [])
    materials, colours = {}, {}
    for i, slot in enumerate(slots):
        try:
            key = int(slot)
        except (TypeError, ValueError):
            continue
        if i < len(mats) and mats[i]:
            materials[key] = str(mats[i])
        if i < len(cols) and cols[i]:
            colours[key] = _hex(cols[i])
    return materials, colours


def _tower(bed_x: float, bed_y: float) -> dict[str, str]:
    """Wipe tower on this bed. PrusaSlicer's 180,140 corner is kept when the tower fits."""
    width = _TOWER_W
    span = width + _TOWER_BRIM
    if span + 1 >= bed_x or span + 1 >= bed_y:
        width = max(15.0, min(bed_x, bed_y) - _TOWER_BRIM - 4.0)
        span = width + _TOWER_BRIM
    x = _TOWER_X if _TOWER_X + span <= bed_x else max(0.0, bed_x - span)
    y = _TOWER_Y if _TOWER_Y + span <= bed_y else max(0.0, bed_y - span)
    out = {"wipe_tower": "1", "wipe_tower_x": f"{x:g}", "wipe_tower_y": f"{y:g}"}
    if width != _TOWER_W:
        out["wipe_tower_width"] = f"{width:g}"
    return out


def _temps(keys: dict[str, str], materials: list[str], primary: str, max_noz: float) -> dict[str, str]:
    """Nozzle temperature per slot. The profile's own numbers stay on the profile's material."""
    nozzle = _bits(keys.get("temperature", ""), ",")
    first = _bits(keys.get("first_layer_temperature", ""), ",")
    bed = _bits(keys.get("bed_temperature", ""), ",")
    bed_first = _bits(keys.get("first_layer_bed_temperature", ""), ",")
    nozzle_s = nozzle[0] if nozzle else "210"
    first_s = first[0] if first else nozzle_s
    bed_s = bed[0] if bed else "60"
    bed_first_s = bed_first[0] if bed_first else bed_s
    nozzles, firsts = [], []
    for material in materials:
        if material == primary:
            nozzles.append(nozzle_s)
            firsts.append(first_s)
            continue
        try:
            temps = material_temps(material)
            nozzles.append(str(min(int(temps["nozzle_c"]), int(max_noz))))
            firsts.append(str(min(int(temps["first_layer_nozzle_c"]), int(max_noz))))
        except Exception:
            nozzles.append(nozzle_s)
            firsts.append(first_s)
    # One bed. Every extruder keeps this profile's bed temperature.
    return {
        "temperature": ",".join(nozzles),
        "first_layer_temperature": ",".join(firsts),
        "bed_temperature": ",".join([bed_s] * len(materials)),
        "first_layer_bed_temperature": ",".join([bed_first_s] * len(materials)),
    }


def _densities(keys: dict[str, str], materials: list[str], primary: str) -> str:
    base = _bits(keys.get("filament_density", ""), ",")
    fallback = base[0] if base else f"{density_of(primary):g}"
    out = []
    for material in materials:
        if material == primary:
            out.append(fallback)
            continue
        try:
            out.append(f"{density_of(material):g}")
        except Exception:
            out.append(fallback)
    return ",".join(out)


def _expand(ini: str, *, n: int, materials: list[str], colours: list[str],
            bed_x: float, bed_y: float, max_noz: float) -> str | None:
    keys = _ini_map(ini)
    count = _nozzle_count(keys)
    if count == 0:
        return None
    overrides: dict[str, str] = {}
    if count == 1:
        for key in _COMMA:
            if key not in keys:
                continue
            fitted = _fit(keys[key], n, ",")
            if fitted is None:
                return None
            overrides[key] = fitted
        for key in _SEMI:
            if key not in keys:
                continue
            fitted = _fit(keys[key], n, ";")
            if fitted is None:
                return None
            overrides[key] = fitted
        offsets = keys.get("extruder_offset", "0x0")
        fitted = _fit(offsets, n, ",")
        if fitted is None:
            # "0x0" is one extruder. A comma inside a coordinate is not a second extruder.
            if "," not in offsets:
                fitted = ",".join([offsets] * n)
            else:
                return None
        overrides["extruder_offset"] = fitted
        overrides["single_extruder_multi_material"] = "1"
        overrides.update(_tower(bed_x, bed_y))
    elif count == n:
        semm = keys.get("single_extruder_multi_material", "0").strip() in ("1", "true", "True")
        if semm:
            overrides.update(_tower(bed_x, bed_y))
    else:
        return None
    primary = _bits(keys.get("filament_type", "PLA"), ";")
    primary_name = primary[0] if primary else "PLA"
    overrides["filament_type"] = ";".join(materials)
    overrides["filament_colour"] = ";".join(colours)
    overrides["extruder_colour"] = ";".join(colours)
    overrides["filament_density"] = _densities(keys, materials, primary_name)
    overrides.update(_temps(keys, materials, primary_name, max_noz))
    if count == n:
        # This profile already lists one value per extruder. Do not replace those
        # nozzle or filament diameters with a copy of the first.
        for key in ("nozzle_diameter", "filament_diameter", "extruder_offset"):
            overrides.pop(key, None)
        if "temperature" in keys and len(_bits(keys["temperature"], ",")) == n:
            overrides.pop("temperature", None)
            overrides.pop("first_layer_temperature", None)
        if "bed_temperature" in keys and len(_bits(keys["bed_temperature"], ",")) == n:
            overrides.pop("bed_temperature", None)
            overrides.pop("first_layer_bed_temperature", None)
    return merge_ini(ini, overrides)


def _place(mesh, bed_x: float, bed_y: float, scale: float):
    """Same placement as the STL slice: optional shrink, then centred on the bed, sitting on z = 0."""
    placed = mesh.copy()
    if scale < 1:
        placed.apply_scale(scale)
    lo, hi = placed.bounds
    placed.apply_translation([
        bed_x / 2 - (float(lo[0]) + float(hi[0])) / 2,
        bed_y / 2 - (float(lo[1]) + float(hi[1])) / 2,
        -float(lo[2]),
    ])
    return placed


def _header(rows: list[dict], materials: list[str]) -> str:
    lines = []
    for row in rows:
        name = " ".join(str(row.get("name") or "Part").split())
        lines.append(f"; ZEIM part {name}: slot {row['slot']} extruder {row['extruder']}")
    if len(set(materials)) > 1:
        lines.append("; ZEIM: bed temperature is this printer profile's bed temperature for every slot.")
    lines.append("; ZEIM: Not yet tested on a printer.")
    return "\n".join(lines) + "\n"


def _rows(matched, index: dict[int, int]) -> list[dict]:
    rows = []
    for part in matched:
        slot = part.get("slot")
        if type(slot) is not int or slot < 1:
            slot = 1
        rows.append({
            "id": part.get("id"),
            "name": part.get("name") or "Part",
            "slot": slot,
            "extruder": index[slot],
        })
    return rows


def build(model_id: str | None, prof, slot_plan: dict | None, work: Path, scaling: dict | None, *,
          unit_id=None, unit_count=None, painted: bool = False) -> dict | None:
    """None when this slice stays on today's one-slot path.

    Otherwise ``mode`` is ``multi`` (3MF + expanded profile) or ``fallback``
    (today's file, with a sentence).
    """
    if not model_id:
        return None
    meta = _meta(model_id)
    if meta is None:
        return None
    stored = [p for p in (meta.get("parts") or []) if isinstance(p, dict)]
    assigned = _assigned(stored)
    if len(assigned) < 2:
        return None
    if painted:
        return _fallback("paint", PAINT)
    slot_count, has_unit = _capability(prof.id, unit_id, unit_count)
    if not has_unit:
        return _fallback("no_unit", NO_UNIT)
    if any(slot > slot_count for slot in assigned):
        return _fallback("outside", OUTSIDE)
    used = sorted(slot for slot in assigned if slot <= slot_count)
    if len(used) < 2:
        return _fallback("outside", OUTSIDE)
    keys = _ini_map(prof.ini)
    count = _nozzle_count(keys)
    if count == 0 or (count >= 2 and count != len(used)):
        message = ONE_EXTRUDER if count < 2 else (
            f"This printer profile has {count} extruders and these parts use {len(used)} filament slots. "
            "ZEIM sliced this as one colour. The part slots stay on the model."
        )
        return _fallback("extruders", message)
    try:
        mesh = editproj.printable_at(model_id, meta)
    except Exception:
        return _fallback("mesh", MESH)
    matched = meshparts.validate(meta.get("parts"), len(getattr(mesh, "faces", [])))
    if not matched or len(matched) < 2:
        return _fallback("mesh", MESH)
    index = {slot: i + 1 for i, slot in enumerate(used)}
    mapped = []
    for part in matched:
        copy = dict(part)
        slot = part.get("slot")
        if type(slot) is not int or slot < 1:
            slot = 1
        if slot not in index:
            return _fallback("outside", OUTSIDE)
        copy["slot"] = index[slot]
        mapped.append(copy)
    scale = float((scaling or {}).get("scale") or 1)
    try:
        placed = _place(mesh, float(prof.bed_x), float(prof.bed_y), scale)
        baked = part3mf.build(placed, {**meta, "parts": mapped}, len(used))
    except Exception:
        return _fallback("mesh", MESH)
    if not baked:
        return _fallback("mesh", MESH)
    mat_of, col_of = _by_slot(slot_plan)
    primary = _bits(keys.get("filament_type", "PLA"), ";")
    primary_name = primary[0] if primary else "PLA"
    materials = [str(mat_of.get(slot) or primary_name) for slot in used]
    part_colour = {}
    for part in matched:
        slot = part.get("slot")
        if type(slot) is not int or slot < 1 or slot in part_colour:
            continue
        part_colour[slot] = _hex(part.get("color"))
    colours = [col_of.get(slot) or part_colour.get(slot) or "#FFFFFF" for slot in used]
    try:
        pub = printer_public(prof.id)
        max_noz = float(pub.get("max_nozzle_c") or 300)
    except Exception:
        max_noz = 300.0
    expanded = _expand(
        prof.ini, n=len(used), materials=materials, colours=colours,
        bed_x=float(prof.bed_x), bed_y=float(prof.bed_y), max_noz=max_noz,
    )
    if expanded is None:
        return _fallback("extruders", ONE_EXTRUDER)
    path = Path(work) / "model_parts.3mf"
    path.write_bytes(baked[0])
    plan = fslots.plan_heads(used, materials, colours)
    rows = _rows(matched, index)
    return {
        "mode": "multi",
        "reason": "",
        "message": "",
        "profile": replace(prof, ini=expanded),
        "plan": plan,
        "path": path,
        "parts": rows,
        "header_extra": _header(rows, materials),
        "label": PRINT_NOTE,
    }
