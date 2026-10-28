"""Stand-alone 'Repair my STL/3MF' (no account): parse → fix → same format back, with a before/after report.

Built on meshedit (trimesh / numpy, MIT; hole fill = meshedit's minimum-area patch, QA B7). No GPL code: nothing
here is taken from admesh, MeshLab or PrusaSlicer. Pure function of the bytes, so it can run in core/guard.py's
memory-capped child. Geometry is the same repair as before. Body ids already on the mesh are kept
for shells that remain (cadops.preserve_body_ids); a file with no ids is unchanged aside from the fix.
Duplicates are matched on sorted vertex ids, so a back-to-back (double-sided) copy counts as a duplicate."""
from __future__ import annotations

import io

import numpy as np
import trimesh

from . import cadops, exporters, meshedit
from .geometry import Body, Model
from .meshedit import OpError

DEBRIS_AREA_FRACTION = 0.001     # a separate shell with < 0.1 % of the surface area ...
DEBRIS_MAX_FACES = 200           # ... and at most this many triangles is debris; anything bigger is a real part


def _edges(m):
    _, cnt = np.unique(m.edges_sorted, axis=0, return_counts=True) if len(m.faces) else (None, np.zeros(0, int))
    return int((cnt == 1).sum()), int((cnt > 2).sum())


def _canon(f):
    """Each triangle rotated so its smallest vertex id comes first (keeps the winding)."""
    r = np.argmin(f, axis=1)
    return np.stack([f[np.arange(len(f)), (r + k) % 3] for k in range(3)], axis=1)


def _flipped(ref, out) -> int:
    """How many of the input triangles come back with the opposite winding (matched by vertex ids)."""
    a, b = _canon(ref), _canon(np.asarray(out))
    key = lambda x: x[:, 0] * 4_000_003 ** 2 + np.minimum(x[:, 1], x[:, 2]) * 4_000_003 + np.maximum(x[:, 1], x[:, 2])
    ka, kb = key(a), key(b)
    order = np.argsort(kb); pos = np.searchsorted(kb[order], ka).clip(0, len(kb) - 1); j = order[pos]
    hit = kb[j] == ka
    return int((hit & (a[:, 1] != b[j, 1])).sum())


def _health(m) -> dict:
    mm = m.copy(); mm.merge_vertices()
    bnd, nm = _edges(mm)
    wt = bool(mm.is_watertight)
    return {"triangles": int(len(m.faces)), "watertight": wt, "boundary_edges": bnd, "nonmanifold_edges": nm,
            "shells": int(len(mm.split(only_watertight=False))) if len(mm.faces) <= 2_000_000 else None,
            "inverted": bool(wt and mm.volume < 0), "volume_mm3": round(abs(float(mm.volume)), 3) if wt else None}


OVERLAP_NOTE = "Some parts overlap but aren't joined. That usually prints fine; join them if you see seams."
OVERLAP_MAX_SHELLS = 40                                   # cheap: skip the check on very fragmented meshes
OVERLAP_SAMPLES = 32


def overlapping_shells(m: trimesh.Trimesh) -> bool:
    """Cheap check: do two separate closed shells intersect/overlap? Bounding boxes first, then a few
    sampled vertices of one shell tested for containment in the other. Never raises."""
    try:
        if len(m.faces) > 2_000_000:
            return False
        shells = [s for s in m.split(only_watertight=False) if len(s.faces) >= 4]
        if not (1 < len(shells) <= OVERLAP_MAX_SHELLS):
            return False
        bb = [s.bounds for s in shells]
        for i in range(len(shells)):
            for j in range(i + 1, len(shells)):
                if np.any(bb[i][1] <= bb[j][0]) or np.any(bb[j][1] <= bb[i][0]):
                    continue
                for a, b in ((shells[i], shells[j]), (shells[j], shells[i])):
                    if not b.is_watertight:
                        continue
                    v = a.vertices
                    if len(v) > OVERLAP_SAMPLES:
                        v = v[np.linspace(0, len(v) - 1, OVERLAP_SAMPLES).astype(int)]
                    if b.contains(v).any():
                        return True
    except Exception:
        return False
    return False


def repair_mesh(m: trimesh.Trimesh) -> tuple[trimesh.Trimesh, dict]:
    if len(m.faces) == 0:
        raise OpError("The file has no triangles.")
    source = m
    before = _health(m)
    src_ids = cadops._face_ids(m)
    m = trimesh.Trimesh(np.asarray(m.vertices, float), np.asarray(m.faces, np.int64), process=False)
    if src_ids is not None and len(src_ids) == len(m.faces):
        m.face_attributes[cadops.BODY_ATTR] = np.array(src_ids, np.int64, copy=True)
    m.merge_vertices()
    n0 = len(m.faces)
    m.update_faces(m.unique_faces()); dup = n0 - len(m.faces)
    n1 = len(m.faces)
    m.update_faces(m.nondegenerate_faces()); degen = n1 - len(m.faces)
    m.remove_unreferenced_vertices()
    if len(m.faces) == 0:
        raise OpError("Every triangle in the file is degenerate (zero area); there is no shape to repair.")
    # loose debris: tiny separate shells; real multi-body parts are kept
    debris = 0
    lab = trimesh.graph.connected_component_labels(m.face_adjacency, node_count=len(m.faces))
    if lab.max() > 0:                                     # face labels, not m.split(): split may re-wind pieces
        area = np.bincount(lab, weights=m.area_faces); cnt = np.bincount(lab)
        junk = (area < DEBRIS_AREA_FRACTION * area.sum()) & (cnt <= DEBRIS_MAX_FACES)
        if junk.any() and not junk.all():
            debris = int(junk.sum())
            m.update_faces(~junk[lab]); m.remove_unreferenced_vertices()
    nm_before = _edges(m)[1]
    ref = m.faces.copy(); n_ref = len(ref)
    out, rep = meshedit.op_repair(m, {"remove_duplicates": False})
    if out.is_watertight and out.volume < 0:
        out.invert()
    flipped = _flipped(ref, out.faces) if np.array_equal(out.vertices[:len(m.vertices)], m.vertices) else None
    after = _health(out)
    holes_found = before["boundary_edges"]
    report = {
        "before": before, "after": after,
        "fixed": {
            "duplicate_triangles": int(dup), "degenerate_triangles": int(degen), "debris_shells_removed": int(debris),
"flipped_triangles_reoriented": flipped,
            "hole_edges_closed": max(0, holes_found - after["boundary_edges"]),
            "nonmanifold_edges_fixed": max(0, before["nonmanifold_edges"] - after["nonmanifold_edges"])},
        "remaining": {"boundary_edges": after["boundary_edges"], "nonmanifold_edges": after["nonmanifold_edges"]},
        "message": rep.get("message", ""), "warnings": [w for w in [rep.get("warning")] if w]}
    if nm_before and after["nonmanifold_edges"]:
        report["warnings"].append(f"{after['nonmanifold_edges']} non-manifold edge(s) could not be fixed automatically "
                                  "(e.g. bodies touching along an edge). Most slicers still cope; Union them in the editor if not.")
    report["notes"] = []                                  # informational, dismissible, never block
    if overlapping_shells(out):
        report["notes"].append({"code": "overlapping_bodies", "text": OVERLAP_NOTE, "dismissible": True})
    # Face ids ride through the filters above. New patch faces pick up the id of the body they closed.
    out = cadops.preserve_body_ids(source, out)
    return out, report


def repair_bytes(data: bytes, ext: str) -> tuple[bytes, dict]:
    """Bytes in, (fixed bytes in the same format, report) out. Raises OpError with a friendly message."""
    m, warn = meshedit.load_mesh(data, ext)
    out, report = repair_mesh(m)
    report["warnings"] = [w for w in warn if not w.startswith("Fix the model")] + report["warnings"]
    mdl = Model(bodies=[Body("model", out.vertices.copy(), out.faces.copy())], mode="edit")
    if ext == "3mf":
        blob = exporters.to_3mf(mdl, "repaired")
    elif ext == "obj":
        blob = exporters.to_obj(mdl)
    else:
        buf = io.BytesIO(); out.export(buf, file_type="stl"); blob = buf.getvalue()
    report["format"] = ext
    return blob, report
