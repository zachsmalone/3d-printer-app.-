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


def slice_model(model: Model, outdir: Path, layer_height=0.2, fill_density=15,
                upright=False, supports=False, brim=0.0, bed=(250, 210)) -> dict:
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
           "--fill-density", f"{int(fill_density)}%", "--center", f"{bed[0] / 2},{bed[1] / 2}",
           "--bed-shape", f"0x0,{bed[0]}x0,{bed[0]}x{bed[1]},0x{bed[1]}",
           "--brim-width", str(brim), "-o", str(gcode), str(stl)]
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
    tail = text[-8000:]
    stats = {}
    for key, pat in {
        "print_time": r"estimated printing time \(normal mode\) = (.+)",
        "filament_mm": r"filament used \[mm\] = ([\d.]+)",
        "filament_g": r"total filament used \[g\] = ([\d.]+)",
        "filament_cm3": r"filament used \[cm3\] = ([\d.]+)",
    }.items():
        m = re.search(pat, tail)
        if m:
            stats[key] = m.group(1).strip()
    layers = len(re.findall(r"^;LAYER_CHANGE", text, re.M))
    return {"available": True, "ok": True, "gcode": "model.gcode", "layers": layers,
            "size_kb": round(gcode.stat().st_size / 1024), "stats": stats,
            "slicer": st.get("version", ""), "log": log[-500:]}
