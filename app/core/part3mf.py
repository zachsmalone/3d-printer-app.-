"""3MF export of each part's filament slot.

A printer with one slot keeps today's single-object 3MF. A printer with more than
one slot writes one object per part, or several volumes of one object when the
parts overlap or still sit in their file positions (the same cases the slicer
keeps as one mesh).

The slot number is 1-based. PrusaSlicer and OrcaSlicer read it from
``Metadata/Slic3r_PE_model.config`` (object or volume ``extruder``). Bambu Studio,
OrcaSlicer and Creality Print read it from ``Metadata/model_settings.config``.
A missing slot is slot 1. A slot past this printer is clamped to the last slot.

Nothing here changes slicing. No printer has run these files.
"""
from __future__ import annotations

import io
import json
import zipfile
from xml.sax.saxutils import quoteattr

import numpy as np

from . import meshparts

# Same tolerance the slice path uses when it decides two parts collide.
_OVERLAP_TOL_MM = 0.05
_MATRIX = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"
_TRANSFORM = "1 0 0 0 1 0 0 0 1 0 0 0"

_CT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    '<Default Extension="config" ContentType="text/xml"/>'
    '<Default Extension="json" ContentType="application/json"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
)


def export_slot(part: dict, slot_count: int) -> int:
    """1-based slot written for this part. Missing, or not a whole number, is slot 1."""
    try:
        count = int(slot_count)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    count = min(count, 16)
    slot = part.get("slot")
    if type(slot) is not int or slot < 1:
        return 1
    if slot > count:
        return count
    return slot


def stored_slot_count(parts) -> int:
    """Slot count for a file written without a printer.

    A saved slot above 1 means the editor had more than one slot, so the file
    carries those numbers (clamped only to 16). Otherwise the file stays the
    single-object 3MF a one-slot printer already downloads.
    """
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        slot = part.get("slot")
        if type(slot) is int and slot > 1:
            return 16
    return 1


def _arranged(meta: dict | None) -> bool:
    """True when the parts were placed on the bed on purpose.

    Matches ``app.api.slice.arranged_on_bed``. Imported parts that keep the
    positions from the file are not arranged.
    """
    if not isinstance(meta, dict):
        return False
    try:
        head = int(meta.get("head") or 0)
    except (TypeError, ValueError):
        head = 0
    ops = meta.get("ops") or []
    if any(isinstance(op, dict) and op.get("op") == "plate" for op in ops[:head]):
        return True
    base = meta.get("base") if isinstance(meta.get("base"), dict) else {}
    if base.get("type") == "plate":
        return True
    return base.get("from_mode") == "memorybox"


def _bounds_intersect(meshes, tol: float = _OVERLAP_TOL_MM) -> bool:
    """True when two meshes overlap on every axis by more than ``tol`` mm."""
    boxes = []
    for mesh in meshes:
        try:
            lo, hi = mesh.bounds
        except Exception:
            return True
        boxes.append((lo, hi))
    for i in range(len(boxes)):
        lo_a, hi_a = boxes[i]
        for j in range(i + 1, len(boxes)):
            lo_b, hi_b = boxes[j]
            if all(float(hi_a[k]) > float(lo_b[k]) + tol and float(hi_b[k]) > float(lo_a[k]) + tol for k in range(3)):
                return True
    return False


def stays_together(mesh, parts: list[dict], meta: dict | None) -> bool:
    """One slicer object when the parts overlap, or were not arranged on the bed."""
    if len(parts) < 2:
        return False
    pieces = [meshparts.submesh(mesh, part) for part in parts]
    if _bounds_intersect(pieces):
        return True
    return not _arranged(meta)


def _color_index(parts: list[dict]) -> tuple[list[str], list[int | None]]:
    """basematerials rows, and each part's pindex. A part with no colour is omitted."""
    rows: list[str] = []
    index: dict[str, int] = {}
    used: list[int | None] = []
    for part in parts:
        color = part.get("color")
        if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
            used.append(None)
            continue
        if color not in index:
            index[color] = len(rows)
            rows.append(color)
        used.append(index[color])
    return rows, used


def _mesh_body(mesh) -> str:
    out = io.StringIO()
    out.write("<vertices>")
    np.savetxt(out, np.asarray(mesh.vertices, float), fmt='<vertex x="%.5f" y="%.5f" z="%.5f"/>', newline="")
    out.write("</vertices><triangles>")
    np.savetxt(out, np.asarray(mesh.faces, np.int64), fmt='<triangle v1="%d" v2="%d" v3="%d"/>', newline="")
    out.write("</triangles>")
    return out.getvalue()


def _object_xml(oid: int, name: str, mesh, pindex: int | None) -> str:
    paint = f' pid="1" pindex="{pindex}"' if pindex is not None else ""
    body = _mesh_body(mesh)
    return (
        f'<object id="{oid}" type="model" name={quoteattr(name)}{paint}>'
        f"<mesh>{body}</mesh></object>"
    )


def _meta(kind: str, key: str, value: str, typed: bool) -> str:
    if typed:
        return f'<metadata type={quoteattr(kind)} key={quoteattr(key)} value={quoteattr(value)}/>'
    return f'<metadata key={quoteattr(key)} value={quoteattr(value)}/>'


def _model_settings(entries: list[dict], together: bool, parent_id: int | None) -> str:
    """Bambu Studio / OrcaSlicer / Creality Print extruder metadata."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    if together and parent_id is not None:
        lines.append(f'  <object id="{parent_id}">')
        lines.append("    " + _meta("", "name", "model", False))
        lines.append(f'    <metadata key="extruder" value="{entries[0]["slot"]}"/>')
        for entry in entries:
            lines.append(f'    <part id="{entry["id"]}" subtype="normal_part">')
            lines.append("      " + _meta("", "name", entry["name"], False))
            lines.append(f'      <metadata key="extruder" value="{entry["slot"]}"/>')
            lines.append(f'      <metadata key="matrix" value="{_MATRIX}"/>')
            lines.append("    </part>")
        lines.append("  </object>")
    else:
        for entry in entries:
            lines.append(f'  <object id="{entry["id"]}">')
            lines.append("    " + _meta("", "name", entry["name"], False))
            lines.append(f'    <metadata key="extruder" value="{entry["slot"]}"/>')
            lines.append("  </object>")
    lines.append("</config>")
    return "\n".join(lines) + "\n"


def _slic3r_config(entries: list[dict], together: bool, parent_id: int | None) -> str:
    """PrusaSlicer / OrcaSlicer extruder metadata. ``extruder`` is the 1-based slot."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]

    def volume(entry: dict) -> list[str]:
        last = max(0, int(entry["triangles"]) - 1)
        return [
            f'    <volume firstid="0" lastid="{last}">',
            "      " + _meta("volume", "name", entry["name"], True),
            "      " + _meta("volume", "volume_type", "ModelPart", True),
            "      " + _meta("volume", "extruder", str(entry["slot"]), True),
            "      " + _meta("volume", "matrix", _MATRIX, True),
            "      " + _meta("volume", "source_object_id", "0", True),
            "      " + _meta("volume", "source_volume_id", "0", True),
            "      " + _meta("volume", "source_offset_x", "0", True),
            "      " + _meta("volume", "source_offset_y", "0", True),
            "      " + _meta("volume", "source_offset_z", "0", True),
            "    </volume>",
        ]

    if together and parent_id is not None:
        lines.append(f'  <object id="{parent_id}" instances_count="1">')
        lines.append("    " + _meta("object", "name", "model", True))
        lines.append("    " + _meta("object", "extruder", str(entries[0]["slot"]), True))
        for entry in entries:
            lines.extend(volume(entry))
        lines.append("  </object>")
    else:
        for entry in entries:
            lines.append(f'  <object id="{entry["id"]}" instances_count="1">')
            lines.append("    " + _meta("object", "name", entry["name"], True))
            lines.append("    " + _meta("object", "extruder", str(entry["slot"]), True))
            lines.extend(volume(entry))
            lines.append("  </object>")
    lines.append("</config>")
    return "\n".join(lines) + "\n"


def build(mesh, meta: dict | None, slot_count: int) -> tuple[bytes, list[int]] | None:
    """Parts 3MF, or None when this printer should keep today's single-object file.

    The returned slot list is the 1-based slots written, in part order.
    """
    try:
        count = int(slot_count)
    except (TypeError, ValueError):
        return None
    if count <= 1 or mesh is None or len(getattr(mesh, "faces", [])) == 0:
        return None
    meta = meta or {}
    parts = meshparts.resolve(meta.get("parts"), len(mesh.faces), "Model")
    if len(parts) < 2:
        return None
    slots = [export_slot(part, count) for part in parts]
    together = stays_together(mesh, parts, meta)
    pieces = [meshparts.submesh(mesh, part) for part in parts]
    colors, paint = _color_index(parts)
    entries = []
    objects = []
    first = 2
    for i, (part, piece, slot, pindex) in enumerate(zip(parts, pieces, slots, paint)):
        oid = first + i
        name = part.get("name") or f"Part {i + 1}"
        objects.append(_object_xml(oid, name, piece, pindex))
        entries.append({
            "id": oid,
            "name": name,
            "slot": slot,
            "triangles": int(len(piece.faces)),
            "color": part.get("color"),
            "part_id": part.get("id"),
        })
    parent_id = None
    if together:
        parent_id = first + len(entries)
        comps = "".join(
            f'<component objectid="{entry["id"]}" transform="{_TRANSFORM}"/>' for entry in entries
        )
        objects.append(f'<object id="{parent_id}" type="model" name="model"><components>{comps}</components></object>')
        build_items = f'<item objectid="{parent_id}" transform="{_TRANSFORM}"/>'
    else:
        build_items = "".join(
            f'<item objectid="{entry["id"]}" transform="{_TRANSFORM}"/>' for entry in entries
        )
    model = io.StringIO()
    model.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    model.write(
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
    )
    model.write('<metadata name="Title">photo3d</metadata><metadata name="Application">photo3d</metadata><resources>')
    if colors:
        model.write('<basematerials id="1">')
        for i, color in enumerate(colors):
            model.write(f'<base name="color{i + 1}" displaycolor="{color}FF"/>')
        model.write("</basematerials>")
    model.write("".join(objects))
    model.write("</resources><build>")
    model.write(build_items)
    model.write("</build></model>")
    info = {
        "slots": sorted({entry["slot"] for entry in entries}),
        "filament_to_slot": {str(slot): slot for slot in sorted({entry["slot"] for entry in entries})},
        "parts": [
            {"id": entry["part_id"], "name": entry["name"], "slot": entry["slot"], "color": entry["color"]}
            for entry in entries
        ],
        "together": together,
        "notes": [
            "Extruder numbers are the filament slots (1-based).",
            "Not confirmed on a printer.",
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("[Content_Types].xml", _CT)
        zipped.writestr("_rels/.rels", _RELS)
        zipped.writestr("3D/3dmodel.model", model.getvalue())
        zipped.writestr("Metadata/model_settings.config", _model_settings(entries, together, parent_id))
        zipped.writestr("Metadata/Slic3r_PE_model.config", _slic3r_config(entries, together, parent_id))
        zipped.writestr("Metadata/zeim_slots.json", json.dumps(info, indent=1))
    return buf.getvalue(), [entry["slot"] for entry in entries]
