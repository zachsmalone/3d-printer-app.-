"""Paint-on supports: maker marks where supports must / must not grow.

Strokes are small cylinders in model millimetres. ZEIM turns them into PrusaSlicer
SupportEnforcer / SupportBlocker volumes inside a 3MF, then slices that file. The
CLI is still run unmodified (same as every other slice).

Honest labels: not K1-tested; painted volumes are approximate brushes, not a mesh
facet paint like the PrusaSlicer GUI.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

KINDS = ("enforce", "block")
MAX_STROKES = 200
R_MIN, R_MAX = 0.5, 25.0
Z_MIN, Z_MAX = 0.0, 500.0
XY_LIM = 500.0
H_DEFAULT = 8.0          # cylinder height mm (covers a band of overhangs)
H_MIN, H_MAX = 1.0, 80.0


class PaintError(ValueError):
    """Bad paint payload (user-facing message)."""


def parse_strokes(raw: Any) -> list[dict]:
    """Accept a JSON string or list. Empty list is fine (no paint)."""
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PaintError("Paint data isn't valid JSON.") from e
    if not isinstance(raw, list):
        raise PaintError("Paint data must be a list of brush strokes.")
    if len(raw) > MAX_STROKES:
        raise PaintError(f"That's too many brush strokes (max {MAX_STROKES}). Clear some and try again.")
    out = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise PaintError(f"Stroke {i + 1} isn't an object.")
        kind = str(s.get("kind", "")).strip().lower()
        if kind not in KINDS:
            raise PaintError("Each stroke needs kind 'enforce' (need support) or 'block' (never support).")
        try:
            x, y = float(s["x"]), float(s["y"])
            z = float(s.get("z", 0.0))
            r = float(s.get("r", 3.0))
            h = float(s.get("h", H_DEFAULT))
        except (KeyError, TypeError, ValueError) as e:
            raise PaintError(f"Stroke {i + 1} needs numeric x, y (and optional z, r, h).") from e
        if not all(abs(v) <= XY_LIM for v in (x, y)):
            raise PaintError(f"Stroke {i + 1} is outside the paint area.")
        if not (Z_MIN <= z <= Z_MAX):
            raise PaintError(f"Stroke {i + 1} has a height that isn't believable.")
        if not (R_MIN <= r <= R_MAX):
            raise PaintError(f"Brush size must be between {R_MIN} and {R_MAX} mm.")
        if not (H_MIN <= h <= H_MAX):
            raise PaintError(f"Brush height must be between {H_MIN} and {H_MAX} mm.")
        out.append({"kind": kind, "x": x, "y": y, "z": z, "r": r, "h": h})
    return out


def stroke_mesh(s: dict) -> trimesh.Trimesh:
    """One upright cylinder centred on (x, y), sitting on z (bottom)."""
    m = trimesh.creation.cylinder(radius=s["r"], height=s["h"], sections=16)
    m.apply_translation([s["x"], s["y"], s["z"] + s["h"] / 2.0])
    return m


def meshes_from_strokes(strokes: list[dict]) -> list[tuple[str, trimesh.Trimesh]]:
    return [(s["kind"], stroke_mesh(s)) for s in strokes]


def _mesh_to_vertices_triangles(mesh: trimesh.Trimesh) -> tuple[str, str]:
    v = np.asarray(mesh.vertices, dtype=float)
    f = np.asarray(mesh.faces, dtype=int)
    verts = "\n".join(f'      <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}" />' for x, y, z in v)
    tris = "\n".join(f'      <triangle v1="{a}" v2="{b}" v3="{c}" />' for a, b, c in f)
    return verts, tris


def write_paint_3mf(model: trimesh.Trimesh, strokes: list[dict], path: Path) -> dict:
    """Write a PrusaSlicer-friendly 3MF: object 1 = the model, then enforcer/blocker volumes.

    PrusaSlicer reads `slic3rpe:volume type` metadata (SupportEnforcer / SupportBlocker).
    Returns a small summary for the API / tests.
    """
    if not strokes:
        raise PaintError("No paint strokes to write.")
    parts = meshes_from_strokes(strokes)
    # Build one model XML with multiple objects (id 1 = printable model, rest = paint volumes)
    objects_xml = []
    types = []
    # model
    mv, mt = _mesh_to_vertices_triangles(model)
    objects_xml.append(
        f'  <object id="1" type="model">\n    <mesh>\n      <vertices>\n{mv}\n      </vertices>\n'
        f'      <triangles>\n{mt}\n      </triangles>\n    </mesh>\n  </object>'
    )
    types.append("model")
    for i, (kind, mesh) in enumerate(parts, start=2):
        vv, tt = _mesh_to_vertices_triangles(mesh)
        vol = "SupportEnforcer" if kind == "enforce" else "SupportBlocker"
        objects_xml.append(
            f'  <object id="{i}" type="model">\n'
            f'    <metadatagroup>\n'
            f'      <metadata name="slic3rpe:volume type" type="string">{vol}</metadata>\n'
            f'    </metadatagroup>\n'
            f'    <mesh>\n      <vertices>\n{vv}\n      </vertices>\n'
            f'      <triangles>\n{tt}\n      </triangles>\n    </mesh>\n  </object>'
        )
        types.append(vol)
    build_items = "\n".join(
        f'    <item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 0 0 0" />'
        for i in range(1, len(objects_xml) + 1)
    )
    model_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US"\n'
        '  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"\n'
        '  xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n'
        '  <metadata name="Application">ZEIM paint-on supports</metadata>\n'
        '  <resources>\n' + "\n".join(objects_xml) + "\n  </resources>\n"
        "  <build>\n" + build_items + "\n  </build>\n</model>\n"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        "</Relationships>\n"
    )
    ctype = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        "</Types>\n"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctype)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model_xml)
    n_enf = sum(1 for t in types if t == "SupportEnforcer")
    n_blk = sum(1 for t in types if t == "SupportBlocker")
    return {
        "path": str(path),
        "objects": len(types),
        "enforcers": n_enf,
        "blockers": n_blk,
        "note": "Painted supports use PrusaSlicer SupportEnforcer / SupportBlocker volumes. "
                "Not tested on a real K1. Brushes are cylinders, not a facet paint like the PrusaSlicer GUI.",
    }


def summary(strokes: list[dict]) -> dict:
    return {
        "strokes": len(strokes),
        "enforcers": sum(1 for s in strokes if s["kind"] == "enforce"),
        "blockers": sum(1 for s in strokes if s["kind"] == "block"),
        "tested": "not K1-tested",
    }
