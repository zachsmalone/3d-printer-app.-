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


def slice_model(model: Model, outdir: Path, layer_height=0.2, fill_density=15,
                upright=False, supports=False, brim=0.0, bed=(250, 210), profile_ini=None) -> dict:
    st = status()
    if not st["available"]:
        return st
    v, f = model.solid()
    mesh = trimesh.Trimesh(v, f, process=False)
    if upright:  # stand the model on its long edge (typical for lithophanes)
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    outdir.mkdir(parents=True, exist_ok=True)
    stl = outdir / "slice_input.stl"
    mesh.export(stl)
    gcode = outdir / "model.gcode"
    cmd = [st["path"], "--export-gcode", "--layer-height", str(layer_height),
           "--first-layer-height", str(max(layer_height, 0.2)),
           "--fill-density", f"{int(fill_density)}%", "--filament-density", str(PLA_DENSITY), "--center", f"{bed[0] / 2},{bed[1] / 2}",
           "--bed-shape", f"0x0,{bed[0]}x0,{bed[0]}x{bed[1]},0x{bed[1]}",
           "--brim-width", str(brim), "-o", str(gcode), str(stl)]
    if profile_ini:                                   # printer preset (e.g. Creality K1, experimental): its .ini first, our options override
        cmd[1:1] = ["--load", str(profile_ini)]
    if supports:
        cmd.insert(2, "--support-material")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"available": True, "ok": False, "message": "slicer timed out"}
    log = (r.stdout + "\n" + r.stderr).strip()
    if r.returncode != 0 or not gcode.exists():
        return {"available": True, "ok": False, "message": "slicer failed", "log": log[-2000:]}
    text = gcode.read_text(errors="ignore")
    stats = parse_stats(text)
    layers = len(re.findall(r"^;LAYER_CHANGE", text, re.M))
    return {"available": True, "ok": True, "gcode": "model.gcode", "layers": layers,
            "size_kb": round(gcode.stat().st_size / 1024), "stats": stats,
            "stats_note": f"Estimates from the slicer using PLA ({PLA_DENSITY} g/cm³). Your filament, printer and settings will change them.",
            "slicer": st.get("version", ""), "log": log[-500:]}
