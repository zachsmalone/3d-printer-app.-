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


def export_mesh_data(mesh: trimesh.Trimesh, force_format: Optional[str] = None) -> tuple[bytes, str, str]:
    """Export mesh to 3MF with automatic STL fallback if 3MF fails or format is 'stl'.

    Returns (bytes, extension, mime_type).
    """
    if force_format == "stl":
        data = mesh.export(file_type="stl")
        return data, "stl", "model/stl"

    # Default to 3MF with fallback
    try:
        data = mesh.export(file_type="3mf")
        if not data or not data.startswith(b"PK"):
            raise ValueError("3MF generation did not produce a valid package")
        return data, "3mf", "model/3mf"
    except Exception:
        # Graceful fallback to binary STL
        data = mesh.export(file_type="stl")
        return data, "stl", "model/stl"


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

    mesh, meta = load_build_mesh(bid, actor)
    prepared, info = prepare_mesh_for_printer(mesh, pid)
    data, ext, mime = export_mesh_data(prepared, force_format=force_format)
    filename = format_export_filename(bid, meta.get("title"), pid, ext=ext)
    return data, filename, ext, mime, info
