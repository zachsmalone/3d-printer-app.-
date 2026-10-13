"""Optional slicer integration (PrusaSlicer CLI, falls back to CuraEngine detection)."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh

from ..core.geometry import Model

CANDIDATES = ["prusa-slicer", "PrusaSlicer", "prusa-slicer-console", "superslicer", "orca-slicer"]


def find_slicer():
    for c in CANDIDATES:
        p = shutil.which(c)
        if p:
            return p
    return None


def status():
    p = find_slicer()
    if not p:
        return {"available": False,
                "message": "No slicer CLI found. Install one (e.g. `sudo apt install prusa-slicer`) "
                           "and restart the server. STL/OBJ/3MF exports still work and can be "
                           "opened in any slicer."}
    try:
        v = subprocess.run([p, "--help"], capture_output=True, text=True, timeout=30)
        first = (v.stdout or v.stderr).strip().splitlines()[:1]
    except Exception:
        first = []
    return {"available": True, "path": p, "version": first[0] if first else ""}


PLA_DENSITY = 1.24      # g/cm3 - PrusaSlicer's default profile has density 0, which made every weight "0.00 g"
_STAT_PATTERNS = {
    "print_time": r"^; estimated printing time \(normal mode\) = (.+)$",
    "filament_mm": r"^; filament used \[mm\] = ([\d.]+)",
    "filament_cm3": r"^; filament used \[cm3\] = ([\d.]+)",
    "filament_g": r"^; total filament used \[g\] = ([\d.]+)",
}


def parse_stats(text: str) -> dict:
    """Print time / filament from the G-code comments. PrusaSlicer 2.9 writes them BEFORE its big config block, so the
    WHOLE file is searched (the old version only looked at the last 8 KB and found nothing)."""
    stats = {}
    for key, pat in _STAT_PATTERNS.items():
        m = re.search(pat, text, re.M)
        if m:
            stats[key] = m.group(1).strip()
    return stats


BED_MARGIN_MM = 2.0      # keep a little room for the skirt / brim edge


def _max_height(profile_ini) -> float | None:
    try:
        m = re.search(r"^max_print_height\s*=\s*([\d.]+)", Path(profile_ini).read_text(errors="ignore"), re.M)
        return float(m.group(1)) if m and float(m.group(1)) > 0 else None
    except (OSError, TypeError, ValueError):
        return None


def bed_fit(extents, bed, profile_ini=None) -> dict | None:
    """None if the model fits the printer's bed (either way round), else a friendly refusal BEFORE the slicer runs."""
    x, y, z = (float(v) for v in extents)
    bx, by = (float(bed[0]) - BED_MARGIN_MM, float(bed[1]) - BED_MARGIN_MM)
    flat_ok = (x <= bx and y <= by) or (y <= bx and x <= by)
    hmax = _max_height(profile_ini) if profile_ini else None
    tall_ok = hmax is None or z <= hmax
    if flat_ok and tall_ok:
        return None
    size = f"{x:.0f} × {y:.0f} × {z:.0f} mm"
    room = f"{bed[0]:.0f} × {bed[1]:.0f} mm" + (f", {hmax:.0f} mm tall" if hmax else "")
    return {"available": True, "ok": False, "code": "too_big",
            "message": f"This model is too big for your printer's bed. It is {size}; your printer has room for {room}. "
                       "Make it smaller (lower the width, or Edit → Scale), or cut it into pieces with Edit → Split and print them one at a time.",
            "size_mm": [round(x, 1), round(y, 1), round(z, 1)], "bed_mm": [float(bed[0]), float(bed[1])]}


def slice_model(model: Model, outdir: Path, layer_height=0.2, fill_density=15,
                upright=False, supports=False, brim=0.0, bed=(250, 210), profile_ini=None,
                printer_id=None, nozzle=None, opts=None) -> dict:
    """Slice a ZEIM build. Merged path: config comes from slice_engine.profile_for (the same builder POST /api/slice
    uses) and the engine runs through slice_engine.run_engine. A network-printer preset .ini (e.g. the K1 Moonraker
    preset) is the base config; the chosen catalog printer + nozzle + panel settings override it."""
    from . import slice_engine as eng
    st = status()
    if not st["available"]:
        return st
    v, f = model.solid()
    mesh = trimesh.Trimesh(v, f, process=False)
    if upright:  # stand the model on its long edge (typical for lithophanes)
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    fit = bed_fit(mesh.extents, bed, profile_ini)
    if fit:
        return fit
    outdir.mkdir(parents=True, exist_ok=True)
    stl = outdir / "slice_input.stl"
    mesh.export(stl)
    gcode = outdir / "model.gcode"
    o = {"layer_height": layer_height, "infill": int(fill_density), "brim": brim,
         "supports": "everywhere" if supports else "off", **(opts or {})}
    base = Path(profile_ini).read_text() if profile_ini else None
    try:
        prof, s = eng.profile_for(printer_id, nozzle, o, base)
    except eng.SliceError:            # legacy callers send a layer height outside the nozzle range: keep their value, skip the clamp
        prof, s = eng.profile_for(printer_id, nozzle, {k: v for k, v in o.items() if k != "layer_height"}, base)
        s["layer_height"] = float(layer_height)
    ov = {"layer_height": f"{float(layer_height):g}" if "layer_height" not in (opts or {}) else f"{s['layer_height']:g}",
          "filament_density": str(PLA_DENSITY)}
    if not printer_id:                 # no catalog printer chosen: the bed of the network printer (or the generic bed)
        ov["bed_shape"] = f"0x0,{bed[0]:g}x0,{bed[0]:g}x{bed[1]:g},0x{bed[1]:g}"
        center = (bed[0] / 2, bed[1] / 2)
    else:
        center = (prof.bed_x / 2, prof.bed_y / 2)
    ini = outdir / "slice_profile.ini"
    ini.write_text(eng.merge_ini(prof.ini, ov))
    try:
        eng.run_engine(st["path"], ini, stl, gcode, timeout=600, center=center)
    except eng.SliceError as e:
        return {"available": True, "ok": False, "message": e.message, "log": e.message}
    text = gcode.read_text(errors="ignore")
    stats = parse_stats(text)
    layers = len(re.findall(r"^;LAYER_CHANGE", text, re.M))
    return {"available": True, "ok": True, "gcode": "model.gcode", "layers": layers,
            "size_kb": round(gcode.stat().st_size / 1024), "stats": stats, "settings": s,
            "stats_note": f"Estimates from the slicer using {s['material']}. Your filament, printer and settings will change them.",
            "slicer": st.get("version", ""), "log": ""}
