"""Universal export service: 'Export for my printer'.

Outputs 3MF (with STL fallback) sized and named for the chosen printer,
with 'Open in' hints for Creality Print, Bambu Studio, OrcaSlicer, PrusaSlicer, and Cura.
Uses sourced printer configurations from app/data/printers/.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import trimesh

from app.community.identity import Actor
from app.services import print_setup as ps
from app.services.history import store

# The 5 universal slicers with user-friendly step-by-step instructions.
# Sourced without undocumented URL schemes or unofficial account linking.
OPEN_IN_HINTS = [
    {
        "id": "creality",
        "name": "Creality Print",
        "format": "3mf",
        "steps": "Open Creality Print, choose File > Import (or drag the file onto the plate), select your printer and click Slice.",
        "url": "https://www.creality.com/pages/download-software",
    },
    {
        "id": "bambustudio",
        "name": "Bambu Studio",
        "format": "3mf",
        "steps": "Open Bambu Studio, choose File > Import > Import 3MF/STL (or drag the file in), then click Slice plate.",
        "url": "https://bambulab.com/en/download/studio",
    },
    {
        "id": "orcaslicer",
        "name": "OrcaSlicer",
        "format": "3mf",
        "steps": "Open OrcaSlicer, choose File > Import > Import 3MF/STL (or drag the file in), verify your printer preset and click Slice plate.",
        "url": "https://github.com/SoftFever/OrcaSlicer/releases",
    },
    {
        "id": "prusaslicer",
        "name": "PrusaSlicer",
        "format": "3mf",
        "steps": "Open PrusaSlicer, choose File > Import > Import STL/3MF (Ctrl+I), check the printer profile at top right, and click Slice now.",
        "url": "https://www.prusa3d.com/page/prusaslicer_424/",
    },
    {
        "id": "cura",
        "name": "Cura",
        "format": "3mf",
        "steps": "Open UltiMaker Cura, choose File > Open File(s)... (or drag the file in), select your printer and click Slice.",
        "url": "https://ultimaker.com/software/ultimaker-cura/",
    },
]

SLICER_MAP = {
    "creality": "creality",
    "creality print": "creality",
    "bambu": "bambustudio",
    "bambu studio": "bambustudio",
    "bambustudio": "bambustudio",
    "orcaslicer": "orcaslicer",
    "orca": "orcaslicer",
    "prusa": "prusaslicer",
    "prusaslicer": "prusaslicer",
    "cura": "cura",
}


def get_open_in_hints(printer_id: Optional[str] = None) -> list[dict]:
    """Return the 5 slicer hints, marking the printer's official slicer if recognized."""
    hints = [dict(h) for h in OPEN_IN_HINTS]
    if not printer_id:
        return hints
    try:
        p = ps.printer_public(printer_id)
        official = (p.get("official_slicer") or "").strip().lower()
        official_key = SLICER_MAP.get(official)
        for h in hints:
            h["recommended"] = bool(official_key and h["id"] == official_key)
            if h["recommended"] and p.get("official_slicer_url"):
                h["url"] = p["official_slicer_url"]
    except Exception:
        pass
    return hints


def sanitize_filename(title: Optional[str], default: str = "model") -> str:
    """Sanitize title for use in filenames; never empty or unsafe."""
    if not title or title.lower() in ("untitled", "model"):
        return default
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")
    return slug[:48] or default


def format_export_filename(bid: str, title: Optional[str], printer_id: str, ext: str = "3mf") -> str:
    """Filename sized and named for the chosen printer, e.g. 'vase_bambu_x1c.3mf'."""
    clean_title = sanitize_filename(title, default=f"photo3d_{bid}")
    clean_printer = re.sub(r"[^A-Za-z0-9_-]+", "_", printer_id)
    return f"{clean_title}_{clean_printer}.{ext}"


def prepare_mesh_for_printer(mesh: trimesh.Trimesh, printer_id: str) -> tuple[trimesh.Trimesh, dict]:
    """Size and position a mesh on the chosen printer bed: sitting at z=0, centered in X and Y, scaled if exceeding limits."""
    m = mesh.copy()
    p = ps.printer_public(printer_id)
    bed_x, bed_y, bed_z = p["bed_mm"]
    limits = (float(bed_x), float(bed_y), float(bed_z))
    lo, hi = m.bounds
    extents = hi - lo

    # Scale down with a small margin (98%) if exceeding any bed dimension
    scaled_pct = None
    if any(e > l for e, l in zip(extents, limits)):
        f = min(l / d for d, l in zip(limits, extents) if d > 0)
        f = f * 0.98
        m.apply_scale(f)
        scaled_pct = round(f * 100, 1)

    # Position on bed: z=0, centered on bed plate
    lo, hi = m.bounds
    center_x = limits[0] / 2.0
    center_y = limits[1] / 2.0
    m.apply_translation([center_x - (lo[0] + hi[0]) / 2.0, center_y - (lo[1] + hi[1]) / 2.0, -lo[2]])

    info = {
        "printer_id": printer_id,
        "printer_name": p["name"],
        "bed_mm": [limits[0], limits[1], limits[2]],
        "scaled_pct": scaled_pct,
        "official_slicer": p.get("official_slicer"),
        "official_slicer_url": p.get("official_slicer_url"),
    }
    return m, info


# One export picker: every mesh format we can write, with a one-line description shown next to it.
# STEP is deliberately absent: it needs a true B-rep solid and ZEIM models are triangle meshes (no B-rep kernel here).
FORMATS = {
    "stl": {"label": "STL", "mime": "model/stl", "desc": "Works in every slicer. Shape only, no colour or units."},
    "3mf": {"label": "3MF", "mime": "model/3mf", "desc": "Modern slicer format: keeps millimetres and placement. Best for Bambu, Orca, Prusa, Cura."},
    "obj": {"label": "OBJ", "mime": "model/obj", "desc": "Common 3D format for Blender and other 3D apps."},
    "ply": {"label": "PLY", "mime": "application/ply", "desc": "Mesh format used by 3D scanning and mesh tools like MeshLab."},
    "glb": {"label": "GLB (glTF)", "mime": "model/gltf-binary", "desc": "One-file glTF for the web, AR and game engines."},
    "amf": {"label": "AMF", "mime": "application/x-amf", "desc": "Older XML print format, still read by PrusaSlicer and Cura."},
}
STEP_NOTE = "STEP is not offered: it needs a true solid (B-rep), and ZEIM models are triangle meshes."


def formats_public() -> dict:
    return {"formats": [{"id": k, **{x: v[x] for x in ("label", "desc")}} for k, v in FORMATS.items()],
            "step": False, "step_note": STEP_NOTE}


def amf_bytes(mesh: trimesh.Trimesh) -> bytes:
    """Plain AMF 1.1 (millimetres): one object, one volume. Written here; trimesh has no AMF writer."""
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n<amf unit="millimeter" version="1.1">\n'
              '<metadata type="producer">ZEIM</metadata>\n<object id="0"><mesh><vertices>\n')
    for x, y, z in mesh.vertices:
        out.write(f"<vertex><coordinates><x>{x:.6g}</x><y>{y:.6g}</y><z>{z:.6g}</z></coordinates></vertex>\n")
    out.write("</vertices><volume>\n")
    for a, b, c in mesh.faces:
        out.write(f"<triangle><v1>{a}</v1><v2>{b}</v2><v3>{c}</v3></triangle>\n")
    out.write("</volume></mesh></object>\n</amf>\n")
    return out.getvalue().encode()


def export_mesh_data(mesh: trimesh.Trimesh, force_format: Optional[str] = None) -> tuple[bytes, str, str]:
    """Export a mesh. Default is 3MF with automatic STL fallback; any FORMATS key can be forced.

    Returns (bytes, extension, mime_type).
    """
    f = (force_format or "3mf").lower()
    if f not in FORMATS:
        raise ValueError(f"Unknown format {f!r}")
    if f == "stl":
        return mesh.export(file_type="stl"), "stl", FORMATS["stl"]["mime"]
    if f == "amf":
        return amf_bytes(mesh), "amf", FORMATS["amf"]["mime"]
    if f in ("obj", "ply", "glb"):
        data = mesh.export(file_type=f)
        if isinstance(data, str):
            data = data.encode()
        return data, f, FORMATS[f]["mime"]
    try:
        data = mesh.export(file_type="3mf")
        if not data or not data.startswith(b"PK"):
            raise ValueError("3MF generation did not produce a valid package")
        return data, "3mf", "model/3mf"
    except Exception:
        # Graceful fallback to binary STL
        data = mesh.export(file_type="stl")
        return data, "stl", "model/stl"


def name_parts(meta: dict, printer_id: str, nozzle: Optional[float] = None) -> tuple[str, str, Optional[float]]:
    """(title, printer name, layer height) for the default file name. Layer height: the Standard preset for the nozzle
    (half the nozzle, so 0.2 mm on a 0.4 mm nozzle); resin printers use 0.05 mm."""
    p = ps.printer_public(printer_id)
    if p.get("technology") == "Resin":
        lay = 0.05
    else:
        lay = round((nozzle or p.get("stock_nozzle_mm") or 0.4) * 0.5, 3)
    return meta.get("title") or "", p["name"], lay


def build_file_name(meta: dict, printer_id: str, ext: str, nozzle: Optional[float] = None, name: Optional[str] = None) -> str:
    """A chosen name (sanitised) wins; then the name saved on the project; else 'Title - Printer - 0.2mm'."""
    from app.services import filenames as fn
    chosen = name or meta.get("file_name")
    if chosen:
        return fn.file_name(chosen, ext)
    return fn.file_name(fn.default_stem(*name_parts(meta, printer_id, nozzle)), ext)


def load_build_mesh(bid: str, actor: Actor) -> tuple[trimesh.Trimesh, dict]:
    """Load model mesh for a build owned by actor."""
    from app.api.builds import meta_for
    from app.services import editproj

    meta = meta_for(bid, actor, owner_only=True)
    if meta.get("kind") == "edit":
        editproj.ensure_exports(bid)
        m = editproj.mesh_at(bid, meta)
        return m.copy(), meta

    stl_path = store.dir(bid) / "model.stl"
    if stl_path.is_file():
        m = trimesh.load(str(stl_path), force="mesh")
        return m, meta

    from app.api.builds import load_model
    model = load_model(bid)
    v, f = model.solid()
    m = trimesh.Trimesh(v, f, process=False)
    return m, meta


def export_build_for_printer(
    bid: str,
    actor: Actor,
    printer_id: Optional[str] = None,
    force_format: Optional[str] = None,
    name: Optional[str] = None,
    nozzle: Optional[float] = None,
    slots=None,
) -> tuple[bytes, str, str, str, dict]:
    """Export a build for the chosen printer.

    Returns: (data_bytes, filename, format, mime_type, export_info)
    """
    pid = printer_id
    if not pid and actor.user and actor.user.get("printer", {}).get("printer_id"):
        pid = actor.user["printer"]["printer_id"]
    try:
        pid, _ = ps.resolve(pid)
    except ps.SetupError:
        pid, _ = ps.resolve()

    pref = ((actor.user or {}).get("printer") or {}) if actor.user else {}
    if nozzle is None and pref.get("printer_id") == pid:
        nozzle = pref.get("nozzle")
    from app.api.builds import meta_for
    if meta_for(bid, actor, owner_only=True).get("mode") == "memorybox":
        return _memorybox_export(bid, actor, pid, force_format, name, nozzle, slots)
    from app.services import filament_slots as fs
    mesh, meta = load_build_mesh(bid, actor)
    prepared, info = prepare_mesh_for_printer(mesh, pid)
    data, ext, mime = export_mesh_data(prepared, force_format=force_format)
    plan = fs.plan([], fs.parse_slots(slots))           # one merged mesh = one material = one slot (the first picked)
    if ext == "3mf":
        data = fs.annotate_3mf(data, plan)
    info.update({"slots": plan["slots"], "slot_notes": plan["notes"]})
    filename = build_file_name(meta, pid, ext, nozzle=nozzle, name=name)
    return data, filename, ext, mime, info


def _memorybox_export(bid, actor, pid, force_format, name, nozzle, slots=None):
    """Memory box: never scaled (that would break the fits). 3MF = one object per part; other formats hold every
    part laid out apart in one file. A part larger than the bed is only a note (warnings never block)."""
    from app.api.builds import load_model, meta_for
    from app.core import exporters
    from app.services import filament_slots as fs
    meta = meta_for(bid, actor, owner_only=True)
    model = load_model(bid)
    plan = fs.plan(fs.model_colours(model), fs.parse_slots(slots))
    p = ps.printer_public(pid)
    bed = [float(v) for v in p["bed_mm"]]
    f = (force_format or "3mf").lower()
    if f not in FORMATS:
        raise ValueError(f"Unknown format {f!r}")
    big = []
    for b in model.bodies:
        e = np.ptp(np.asarray(b.vertices), 0)
        if e[0] > bed[0] or e[1] > bed[1] or e[2] > bed[2]:
            big.append(b.name)
    if f == "3mf":
        data, ext, mime = exporters.to_3mf(model, meta.get("title") or "Memory box", slots=fs.parse_slots(slots)), "3mf", "model/3mf"
    else:
        v, fc = model.solid()
        data, ext, mime = export_mesh_data(trimesh.Trimesh(v, fc, process=False), force_format=f)
    info = {"printer_id": pid, "printer_name": p["name"], "bed_mm": bed, "scaled_pct": None,
            "official_slicer": p.get("official_slicer"), "official_slicer_url": p.get("official_slicer_url"),
            "parts": [b.name for b in model.bodies], "larger_than_bed": big,
            "slots": plan["slots"], "slot_notes": plan["notes"]}
    return data, build_file_name(meta, pid, ext, nozzle=nozzle, name=name), ext, mime, info
