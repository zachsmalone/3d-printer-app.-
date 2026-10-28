"""CAD workspace solid operations, recorded as ordinary edit-project history steps.

Original ZEIM code. Geometry kernel: manifold3d (Apache-2.0) for extrude / revolve / booleans /
Minkowski; shapely (BSD) for sketch regions. Every op here is a pure function mesh -> mesh
registered in meshedit.OPS, so undo/redo, step editing with replay, exports, slicing and the
plate editor work unchanged.

"Bodies" are the connected pieces of the project mesh. The list order is still sorted by
centre (x, then y, then z) so the on-screen numbers stay predictable. That order is not
identity. Each body carries a stable id on its faces (`b1`, `b2`, …). A step stores that id.
Replay resolves the id. A stored id that is not on the mesh is an error — a different body
is not chosen by centre. An older step that stored a list index is rewritten to the id it
named at that point in the saved history, once, in order. If two bodies share a centre, that
index is ambiguous and the step fails instead of guessing.

Display colours are stored on that same id. The viewer still receives them under the current
list number, so the colour stays on that body when a boolean or a repair changes the list.
"""
from __future__ import annotations

import math
import re

import numpy as np
import trimesh
from trimesh.graph import connected_components

from . import sketch as sk
from .meshedit import OpError, _check, _new

MAX_PATTERN = 64
MAX_PATTERN_FACES = 600_000      # refuse BEFORE fusing: input faces x count (memory grows with it)
MAX_ROUND_FACES = 60_000         # Minkowski fillet/chamfer cost explodes on dense meshes
LIM = 5000.0
BODY_ATTR = "zeim_body"
_BODY_ID = re.compile(r"^b([1-9][0-9]*)$")
# Ops that store a body reference. Values are param keys. `bodies` is a list.
_BODY_REF_KEYS = {
    "body_transform": ("body",),
    "round_edges": ("body",),
    "pattern": ("body",),
    "align": ("body", "to_body"),
    "body_boolean": ("target", "tool"),
    "merge_bodies": ("bodies",),
}


def _num(p, k, d, lo, hi):
    v = p.get(k, d)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise OpError(f"{k} must be a number.")
    if not math.isfinite(v) or not lo <= v <= hi:
        raise OpError(f"{k} must be between {lo:g} and {hi:g}.")
    return v


def _vec(p, k, d=(0, 0, 0), lim=LIM):
    v = p.get(k, d)
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise OpError(f"{k} must be [x, y, z].")
    return np.array([_num({"v": x}, "v", 0, -lim, lim) for x in v])


# ------------------------------------------------------------------ kernel bridges
def _to_manifold(m: trimesh.Trimesh):
    import manifold3d as mf
    if len(m.faces) == 0:
        return mf.Manifold()
    mm = m.copy(); mm.merge_vertices()
    out = mf.Manifold(mf.Mesh(vert_properties=np.asarray(mm.vertices, np.float32), tri_verts=np.asarray(mm.faces, np.uint32)))
    if out.status() != mf.Error.NoError:
        raise OpError("This body isn't a closed solid, so solid tools can't use it. Run Fix / repair first.")
    if out.volume() < 0 or (mm.is_watertight and mm.volume < 0):
        raise OpError("This body is inside-out (negative volume). Run Fix mesh first so solid tools work correctly.")
    return out


def _solid_or_none(x, n_bodies: int):
    """Manifold -> trimesh that stays a closed 2-manifold after vertex merging (as every export does), else None."""
    t = _from_manifold(x)
    mm = trimesh.Trimesh(t.vertices.copy(), t.faces.copy(), process=False)
    mm.merge_vertices()
    if not mm.is_watertight:                  # sliver faces collapse to zero length when merged: drop + close the pin-holes
        mm.update_faces(mm.nondegenerate_faces())
        mm.update_faces(mm.unique_faces())
        mm.remove_unreferenced_vertices()
        trimesh.repair.fill_holes(mm)
        trimesh.repair.fix_normals(mm)
    if len(mm.faces) == 0 or not (mm.is_watertight and mm.is_winding_consistent):
        return None
    if len(bodies(mm)) != n_bodies:
        return None
    return mm


def _from_manifold(x) -> trimesh.Trimesh:
    mesh = x.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    f = np.asarray(mesh.tri_verts)
    return _new(v, f)


def _face_ids(mesh):
    if mesh is None or len(getattr(mesh, "faces", [])) == 0:
        return None
    raw = mesh.face_attributes.get(BODY_ATTR) if hasattr(mesh, "face_attributes") else None
    if raw is None or len(raw) != len(mesh.faces):
        return None
    return np.asarray(raw, np.int64)


def _stamp(mesh, body_id: int):
    if mesh is None or len(getattr(mesh, "faces", [])) == 0:
        return mesh
    mesh.face_attributes[BODY_ATTR] = np.full(len(mesh.faces), int(body_id), dtype=np.int64)
    return mesh


def body_id_of(mesh) -> int | None:
    """The single positive body id on every face, or None when the mesh is untagged or mixed."""
    ids = _face_ids(mesh)
    if ids is None or (ids <= 0).any():
        return None
    uniq = {int(x) for x in ids}
    return uniq.pop() if len(uniq) == 1 else None


def public_id(n: int) -> str:
    return f"b{int(n)}"


def max_body_id(mesh) -> int:
    ids = _face_ids(mesh) if mesh is not None else None
    if ids is None or len(ids) == 0:
        return 0
    return int(ids.max())


def _as_index(ref):
    """A legacy list index. Bool is rejected (it is a subclass of int). Strings are not indices."""
    if isinstance(ref, bool) or isinstance(ref, str):
        return None
    if isinstance(ref, (int, np.integer)):
        return int(ref)
    if isinstance(ref, float) and math.isfinite(ref) and ref.is_integer():
        return int(ref)
    return None


def _is_all(ref) -> bool:
    if ref is None:
        return True
    idx = _as_index(ref)
    return idx is not None and idx < 0


def _centre_key(mesh):
    return tuple(np.round(np.asarray(mesh.bounds.mean(axis=0), float), 3))


def _component_faces(m: trimesh.Trimesh):
    """(face indices into m, shell mesh) for each connected shell.

    Face indices line up with m only when vertex merging does not drop or reorder faces.
    None means they do not line up; callers must not invent ids from centres.
    """
    if m is None or len(m.faces) == 0:
        return []
    mm = m.copy()
    mm.merge_vertices()
    if len(mm.faces) != len(m.faces):
        return None
    comps = connected_components(edges=mm.face_adjacency, nodes=np.arange(len(mm.faces)), min_len=1)
    src = _face_ids(m)
    out = []
    for comp in comps:
        fi = np.asarray(sorted(int(i) for i in comp), np.int64)
        sub = mm.submesh([fi], only_watertight=False, repair=True, append=True)
        if isinstance(sub, (list, tuple)):
            sub = sub[0]
        if src is not None and len(fi) and not (src[fi] <= 0).any():
            uniq = {int(x) for x in src[fi]}
            if len(uniq) == 1:
                _stamp(sub, uniq.pop())
        out.append((fi, sub))
    return out


def _group_components(recs):
    """Solids, with an inside-out shell kept on the solid that contains its centre (a cavity)."""
    solid = [r for r in recs if not (r[1].is_watertight and float(r[1].volume) < 0)]
    voids = [r for r in recs if r[1].is_watertight and float(r[1].volume) < 0]
    groups = [[r] for r in solid]
    for v in voids:
        c = v[1].bounds.mean(axis=0)
        host = [i for i, r in enumerate(solid) if (r[1].bounds[0] <= c).all() and (c <= r[1].bounds[1]).all()]
        if host:
            groups[min(host, key=lambda i: float(np.prod(solid[i][1].extents)))].append(v)
        else:
            groups.append([v])
    return groups


def _host_id(ids, group) -> int | None:
    """The single positive id on this body.

    Faces added by a repair (0 or negative) do not count, so a filled hole keeps the body's id.
    Two different positive ids on one body are left unset: that body is not guessed.
    """
    if ids is None:
        return None
    vals = np.asarray(ids[group[0][0]], np.int64)
    pos = vals[vals > 0]
    if len(pos) == 0:
        return None
    uniq = np.unique(pos)
    if len(uniq) != 1:
        return None
    return int(uniq[0])


def ensure_body_ids(m: trimesh.Trimesh, start: int = 0):
    """Give every untagged body a new id. Ids already on a body stay, including on faces a repair just added.

    `start` is the highest id already used on an earlier mesh, so a rebuilt result does not reuse it.
    New ids follow face order, not centre.
    """
    if m is None or len(getattr(m, "faces", [])) == 0:
        return m
    recs = _component_faces(m)
    if not recs:
        return m
    ids = _face_ids(m)
    ids = np.zeros(len(m.faces), np.int64) if ids is None else ids.copy()
    groups = _group_components(recs)
    for g in groups:
        hid = _host_id(ids, g)
        if hid:
            for fi, _sub in g:
                ids[fi] = hid
    # One id names one shell. A copied shell (same id, separate body) is a new body and gets its own id.
    # The earliest faces keep the id. This is face order, not which centre is nearer.
    seen = {}
    for g in groups:
        hid = _host_id(ids, g)
        if not hid:
            continue
        seen.setdefault(hid, []).append(g)
    for copies in seen.values():
        if len(copies) < 2:
            continue
        copies.sort(key=lambda g: int(g[0][0].min()))
        for extra in copies[1:]:
            for fi, _sub in extra:
                ids[fi] = 0
    untagged = [g for g in groups if _host_id(ids, g) is None]
    nxt = max(int(start), int(ids.max()) if len(ids) else 0)
    for g in sorted(untagged, key=lambda g: int(g[0][0].min())):
        nxt += 1
        for fi, _sub in g:
            ids[fi] = nxt
    m.face_attributes[BODY_ATTR] = ids
    return m


def bodies(m: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    if m is None or len(getattr(m, "faces", [])) == 0:
        return []
    recs = _component_faces(m)
    if recs is None:
        mm = m.copy(); mm.merge_vertices()
        shells = list(mm.split(only_watertight=False))
        solid = [b for b in shells if not (b.is_watertight and b.volume < 0)]
        voids = [b for b in shells if b.is_watertight and b.volume < 0]
        groups = [[b] for b in solid]
        for v in voids:
            c = v.bounds.mean(axis=0)
            host = [i for i, b in enumerate(solid) if (b.bounds[0] <= c).all() and (c <= b.bounds[1]).all()]
            if host:
                groups[min(host, key=lambda i: np.prod(solid[i].extents))].append(v)
            else:
                groups.append([v])
        parts = [g[0] if len(g) == 1 else _join_all(g) for g in groups]
        return sorted(parts, key=lambda b: tuple(np.round(b.bounds.mean(axis=0), 3)))
    parts = []
    for g in _group_components(recs):
        if len(g) == 1:
            part = g[0][1]
        else:
            part = _join_all([r[1] for r in g])
            hid = body_id_of(g[0][1])
            if hid:
                _stamp(part, hid)
        parts.append(part)
    # Display order only. Stored steps do not use this index as identity.
    return sorted(parts, key=lambda b: tuple(np.round(b.bounds.mean(axis=0), 3)))


def _join_all(ms):
    out = None
    for x in ms:
        out = _join(out, x)
    return out


def body_info(m: trimesh.Trimesh) -> list[dict]:
    out = []
    for i, b in enumerate(bodies(m)):
        pid = body_id_of(b)
        out.append({"index": i, "id": public_id(pid) if pid else None, "name": f"Body {i + 1}",
                    "triangles": int(len(b.faces)),
                    "center": np.round(b.bounds.mean(axis=0), 3).tolist(), "size": np.round(b.extents, 3).tolist(),
                    "volume_mm3": round(float(abs(b.volume)), 3) if b.is_watertight else None})
    return out


def _appearance_style(v) -> dict | None:
    if not isinstance(v, dict):
        return None
    color = v.get("color")
    finish = v.get("finish", "satin")
    if not isinstance(color, str) or not isinstance(finish, str):
        return None
    return {"color": color, "finish": finish}


def bind_appearance(stored, mesh, *, strict: bool = False) -> dict:
    """Store colours by body id.

    A list number is the body at that position on `mesh` now. An id that is already stored stays,
    including when that body is absent, so undo can bring its colour back. With `strict`, a number
    or id that is not on `mesh` is an error (saving a colour from the viewer).
    """
    if not isinstance(stored, dict) or not stored:
        return {}
    if mesh is not None and len(getattr(mesh, "faces", [])):
        ensure_body_ids(mesh)
    info = body_info(mesh) if mesh is not None else []
    index_to_id = {str(b["index"]): b["id"] for b in info if b.get("id")}
    known = {b["id"] for b in info if b.get("id")}
    if strict:
        for k in stored:
            key = str(k)
            if _BODY_ID.match(key):
                if key not in known:
                    raise OpError(f"Body {key} is not in this model.")
            elif key.isdigit():
                if str(int(key)) not in index_to_id:
                    raise OpError(f"There is no Body {int(key) + 1}.")
            else:
                raise OpError("Use a body id or a body number.")
    out = {}
    for k, v in stored.items():
        key = str(k)
        if not _BODY_ID.match(key):
            continue
        style = _appearance_style(v)
        if style:
            out[key] = style
    for k, v in stored.items():
        key = str(k)
        if not key.isdigit():
            continue
        pid = index_to_id.get(str(int(key)))
        if not pid or pid in out:
            continue
        style = _appearance_style(v)
        if style:
            out[pid] = style
    return out


def appearance_for_viewer(stored, mesh) -> dict:
    """Colours keyed by the current list number, for the workspace viewer.

    Stored ids are looked up on `mesh`. A project that still has list-number keys is returned
    as stored; the next boolean, repair, or save rewrites those keys to ids first.
    """
    if not isinstance(stored, dict) or not stored:
        return {}
    if not any(_BODY_ID.match(str(k)) for k in stored):
        return {str(k): v for k, v in stored.items() if isinstance(v, dict)}
    if mesh is not None and len(getattr(mesh, "faces", [])):
        ensure_body_ids(mesh)
    out = {}
    for b in body_info(mesh) if mesh is not None else []:
        style = stored.get(b["id"]) if b.get("id") else None
        if isinstance(style, dict):
            out[str(b["index"])] = style
    return out


def _broken_ref(ref) -> OpError:
    return OpError(
        f"Body reference {ref} does not match any body. The step was not applied to a different body."
    )


def _select_body(bs, ref, key="body"):
    """One body from the current list. An id must match exactly. An index must be in range and unique by centre."""
    if isinstance(ref, str):
        matched = _BODY_ID.match(ref)
        if not matched:
            raise _broken_ref(ref)
        want = int(matched.group(1))
        hits = [b for b in bs if body_id_of(b) == want]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise _broken_ref(ref)
        raise OpError(
            f"Body reference {ref} is ambiguous: {len(hits)} bodies have that id. The step was not applied."
        )
    idx = _as_index(ref)
    if idx is None:
        raise OpError(f"{key} must be a body id or a body number.")
    if idx < 0:
        raise OpError(f"{key} does not name one body.")
    if idx >= len(bs):
        raise OpError(f"There is no Body {idx + 1} (the model has {len(bs)}).")
    ck = _centre_key(bs[idx])
    tied = [b for b in bs if _centre_key(b) == ck]
    if len(tied) > 1:
        raise OpError(
            f"Saved body number {idx + 1} is ambiguous: {len(tied)} bodies share the same centre, "
            "so this index cannot be matched to one body."
        )
    chosen = bs[idx]
    if body_id_of(chosen) is None:
        raise OpError(f"Saved body number {idx + 1} cannot be given a stable id. The step was not applied.")
    return chosen


def resolve_body(mesh, ref, key="body"):
    """The shell named by a stored id or a legacy index. Tags untagged shells first."""
    ensure_body_ids(mesh)
    return _select_body(bodies(mesh), ref, key)


def _pick(m, p, key="body"):
    """(selected mesh, the rest). A missing reference or -1 is every body. An unknown id is an error."""
    ref = p.get(key, -1)
    if _is_all(ref):
        return m, None
    chosen = resolve_body(m, ref, key)
    cid = body_id_of(chosen)
    bs = bodies(m)
    rest = [b for b in bs if body_id_of(b) != cid]
    return chosen, (_join_all(rest) if rest else None)


def _faces_aligned(before, after) -> bool:
    """True when after's faces are the same triangles in the same order (winding may be flipped)."""
    if before is None or after is None:
        return False
    if len(getattr(before, "faces", [])) == 0 or len(before.faces) != len(after.faces):
        return False
    fa = np.asarray(before.faces)
    fb = np.asarray(after.faces)
    if fa.shape != fb.shape:
        return False
    return bool(np.array_equal(fa, fb) or np.array_equal(fa, fb[:, ::-1]))


def tag_result(mesh, kept_id, start: int = 0):
    """Keep `kept_id` when the result is still one body. Otherwise give each shell a fresh id past `start`."""
    if mesh is None or len(getattr(mesh, "faces", [])) == 0:
        return mesh
    if kept_id and len(bodies(mesh)) == 1:
        return _stamp(mesh, int(kept_id))
    return ensure_body_ids(mesh, start=max(int(start), int(kept_id or 0)))


def preserve_body_ids(before, after):
    """Carry body ids across an operation that built a new mesh.

    A fully tagged result is kept. The same faces in the same order keep their ids (a move of the
    whole mesh). One body in and one body out keeps that id. A body that already has one id keeps
    it on faces a repair added. Anything still untagged gets a new id above every id on the input,
    so a missing id cannot land on a different body.
    """
    if after is None or len(getattr(after, "faces", [])) == 0:
        return after
    if _fully_tagged(after):
        return after
    if _faces_aligned(before, after):
        src = _face_ids(before)
        if src is not None and (src > 0).any():
            after.face_attributes[BODY_ATTR] = src.copy()
            if _fully_tagged(after):
                return after
    if before is not None and len(getattr(before, "faces", [])) and len(bodies(before)) == 1 and len(bodies(after)) == 1:
        hid = body_id_of(bodies(before)[0])
        if hid:
            return _stamp(after, hid)
    return ensure_body_ids(after, start=max_body_id(before))


def _fully_tagged(mesh) -> bool:
    if mesh is None or len(getattr(mesh, "faces", [])) == 0:
        return True
    ids = _face_ids(mesh)
    if ids is None or (ids <= 0).any():
        return False
    seen = []
    parts = bodies(mesh)
    if not parts:
        return False
    for part in parts:
        pid = body_id_of(part)
        if pid is None or pid in seen:
            return False
        seen.append(pid)
    return True


def _bind_scalar(bs, ref, key):
    if _is_all(ref):
        return ref, False
    if isinstance(ref, str) and _BODY_ID.match(ref):
        return ref, False
    idx = _as_index(ref)
    if idx is None or idx < 0:
        return ref, False
    chosen = _select_body(bs, idx, key)
    return public_id(body_id_of(chosen)), True


def _bind_value(bs, ref, key):
    if isinstance(ref, list):
        bound = []
        changed = False
        for item in ref:
            nxt, did = _bind_scalar(bs, item, key)
            bound.append(nxt)
            changed = changed or did
        return bound, changed
    return _bind_scalar(bs, ref, key)


def history_needs_body_migration(ops) -> bool:
    for o in ops or []:
        keys = _BODY_REF_KEYS.get(o.get("op") or "")
        if not keys:
            continue
        params = o.get("params") or {}
        if o.get("op") == "body_boolean" and ("target" not in params or "tool" not in params):
            return True
        for k in keys:
            if k not in params:
                continue
            v = params[k]
            if isinstance(v, list):
                if any(_as_index(x) is not None and _as_index(x) >= 0 for x in v):
                    return True
            elif _as_index(v) is not None and _as_index(v) >= 0:
                return True
    return False


def bind_legacy_body_refs(mesh, op: str, params: dict) -> tuple[dict, bool]:
    """Rewrite index references to stable ids against `mesh` as it is now. Ids already stored stay.

    Does not look for a nearby body. An index whose centre is shared, or an id that is not on the
    mesh, raises OpError.
    """
    params = dict(params or {})
    keys = _BODY_REF_KEYS.get(op)
    if not keys:
        return params, False
    changed = False
    if op == "body_boolean":
        if "target" not in params:
            params["target"] = 0
            changed = True
        if "tool" not in params:
            params["tool"] = 1
            changed = True
    ensure_body_ids(mesh)
    bs = bodies(mesh)
    for k in keys:
        if k not in params:
            continue
        nxt, did = _bind_value(bs, params[k], k)
        if did:
            params[k] = nxt
            changed = True
        elif isinstance(nxt, str) and _BODY_ID.match(nxt):
            _select_body(bs, nxt, k)  # a stored id that is already gone fails here, before the op runs
    return params, changed


def combine_keeping_ids(cur, tool, mode, replace=False):
    """_combine, with a fresh id on a new body and the previous ids kept on bodies that remain."""
    mode = mode or "new"
    if cur is not None and len(getattr(cur, "faces", [])):
        ensure_body_ids(cur)
    fresh = bool(replace or cur is None or len(getattr(cur, "faces", [])) == 0 or mode == "new")
    if fresh:
        ensure_body_ids(tool, start=max_body_id(cur))
    out = _combine(cur if cur is not None else trimesh.Trimesh(), tool, mode, replace)
    return preserve_body_ids(cur if cur is not None else trimesh.Trimesh(), out)


def _with_ids(mesh):
    if mesh is None or len(mesh.faces) == 0:
        return mesh
    if _face_ids(mesh) is None:
        mesh = mesh.copy()
        mesh.face_attributes[BODY_ATTR] = np.zeros(len(mesh.faces), np.int64)
    return mesh


def _join(a, b):
    if a is None or len(getattr(a, "faces", [])) == 0:
        return b
    if b is None or len(getattr(b, "faces", [])) == 0:
        return a
    a, b = _with_ids(a), _with_ids(b)
    out = _new(np.vstack([a.vertices, b.vertices]), np.vstack([a.faces, b.faces + len(a.vertices)]))
    out.face_attributes[BODY_ATTR] = np.concatenate([_face_ids(a), _face_ids(b)])
    return out


def _touching(m) -> bool:
    """True if separate bodies share a face/edge exactly (after vertex merge some edges get >2 faces)."""
    mm = trimesh.Trimesh(m.vertices, m.faces, process=False); mm.merge_vertices()
    if len(mm.faces) == 0:
        return False
    _, cnt = np.unique(mm.edges_sorted, axis=0, return_counts=True)
    return bool((cnt > 2).any())


def _join_sep(a, b, hint="Use Union (Join) instead, or leave a small gap."):
    """Keep b as separate bodies next to a, but refuse a result that would not be a clean solid
    (bodies touching face-to-face become non-manifold when the file is saved). QA B2."""
    out = _join(a, b)
    if a is not None and b is not None and len(a.faces) and len(b.faces) and _touching(out):
        raise OpError("The new body would touch another body face-to-face, which can't be kept as two separate "
                      "solids in a print file. " + hint)
    return out


def _combine(cur, tool, mode, replace=False):
    """Apply a new solid to the model: new (separate body) / join / cut / intersect."""
    if replace or len(cur.faces) == 0:
        if mode in ("cut", "intersect"):
            raise OpError("There is nothing to cut yet - make a solid first.")
        return tool
    if mode == "new":
        return _join_sep(cur, tool)
    a, b = _to_manifold(cur), _to_manifold(tool)
    r = {"join": a + b, "cut": a - b, "intersect": a ^ b}.get(mode)
    if r is None:
        raise OpError("mode must be new | join | cut | intersect")
    if r.is_empty():
        raise OpError("The result is empty (do the shapes overlap?).")
    return _from_manifold(r)


def _frame(o, xd, yd, n):
    T = np.eye(4)
    T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = xd, yd, n, o
    return T


def _cross_section(params):
    import manifold3d as mf
    try:
        sketch = sk.check(params.get("sketch") or {})
        if params.get("solve", True) and sketch["constraints"]:
            sketch = sk.solve(sketch)["sketch"]
        g = sk.regions(sketch, params.get("picks") or None)
    except sk.SketchError as e:
        raise OpError(str(e))
    if g is None:
        raise OpError("The sketch has no closed shape to use. Close the outline (end where you started) or draw a rectangle/circle.")
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    rings = []
    for pg in polys:
        rings.append(np.asarray(pg.exterior.coords)[:-1])
        rings += [np.asarray(h.coords)[:-1] for h in pg.interiors]
    return mf.CrossSection([r.astype(np.float64) for r in rings], mf.FillRule.EvenOdd), sketch


# ------------------------------------------------------------------ ops
def op_sketch_extrude(m, p):
    """Extrude closed sketch regions. direction: up | down | both (symmetric); mode: new | join | cut | intersect."""
    import manifold3d as mf
    d = _num(p, "distance", 10, 0.001, LIM)
    direction = p.get("direction", "up")
    if direction not in ("up", "down", "both"):
        raise OpError("direction must be up | down | both")
    try:
        o, xd, yd, n = sk.plane(p.get("plane", "XY"))
    except sk.SketchError as e:
        raise OpError(str(e))
    cs, _ = _cross_section(p)
    taper = _num(p, "taper", 0, -60, 60)
    top = 1.0
    if taper:
        b = cs.bounds(); half = max(b[2] - b[0], b[3] - b[1]) / 2 or 1
        top = max(0.0, 1 - d * math.tan(math.radians(taper)) / half)
    solid = mf.Manifold.extrude(cs, d, 0, 0.0, (top, top))
    z0 = {"up": 0.0, "down": -d, "both": -d / 2}[direction]
    solid = solid.translate((0, 0, z0))
    T = _frame(o, xd, yd, n)
    tool = _from_manifold(solid.transform(T[:3, :]))
    out = combine_keeping_ids(m, tool, p.get("mode", "new"), bool(p.get("replace")))
    return out, {"message": f"Extruded {d:g} mm ({direction}, {p.get('mode', 'new')})."}


def op_revolve(m, p):
    """Revolve sketch regions about an axis line in the sketch plane: axis = {p:[x,y], d:[dx,dy]}."""
    import manifold3d as mf
    ang = _num(p, "angle", 360, 0.1, 360)
    try:
        o, xd, yd, n = sk.plane(p.get("plane", "XY"))
    except sk.SketchError as e:
        raise OpError(str(e))
    ax = p.get("axis") or {"p": [0, 0], "d": [0, 1]}
    try:
        ap = np.array(sk._pt(ax.get("p", [0, 0]), "axis point")); ad = np.array(sk._pt(ax.get("d", [0, 1]), "axis direction"))
    except (sk.SketchError, AttributeError) as e:
        raise OpError(str(e))
    if np.linalg.norm(ad) < 1e-9:
        raise OpError("axis direction can't be zero.")
    ad = ad / np.linalg.norm(ad)
    cs, _ = _cross_section(p)
    # move the profile into "axis = +Y through origin" coordinates; profile must be on one side
    perp = np.array([ad[1], -ad[0]])
    R2 = np.array([[perp[0], perp[1]], [ad[0], ad[1]]])          # rows: new x = perp, new y = axis
    rings = [(np.asarray(r) - ap) @ R2.T for r in cs.to_polygons()]
    xs = np.concatenate([r[:, 0] for r in rings])
    if xs.min() < -1e-6 and xs.max() > 1e-6:
        raise OpError("The profile crosses the axis. Keep the whole shape on one side of the axis line.")
    flip = xs.max() <= 1e-6
    if flip:
        rings = [r * np.array([-1, 1]) for r in rings]
        perp = -perp
    solid = mf.Manifold.revolve(mf.CrossSection(rings, mf.FillRule.EvenOdd), 0, ang)
    # revolve: profile X -> radial, profile Y -> world Z of the result. Map back: Z -> axis, X -> perp
    ax3 = xd * ad[0] + yd * ad[1]; perp3 = xd * perp[0] + yd * perp[1]
    third = np.cross(ax3, perp3)
    origin = o + xd * ap[0] + yd * ap[1]
    T = np.eye(4); T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = perp3, -third, ax3, origin
    tool = _from_manifold(solid.transform(T[:3, :]))
    out = combine_keeping_ids(m, tool, p.get("mode", "new"), bool(p.get("replace")))
    return out, {"message": f"Revolved {ang:g}°."}


def _cover(shell, solid) -> float:
    """Share of `shell` that still sits inside `solid` (1 when the shell is that body)."""
    if shell is None or solid is None or len(getattr(shell, "vertices", [])) == 0:
        return 0.0
    if not getattr(solid, "is_watertight", False):
        return 0.0
    pts = np.asarray(shell.vertices, float)
    if len(pts) > 800:
        pts = pts[np.linspace(0, len(pts) - 1, 800).astype(int)]
    centre = np.asarray(shell.bounds.mean(axis=0), float)
    inward = pts + (centre - pts) * 0.02
    inward = np.vstack([inward, centre])
    try:
        hit = np.asarray(solid.contains(inward), bool)
    except Exception:
        return 0.0
    if len(hit) == 0:
        return 0.0
    return float(hit.mean())


def _shell_rank(groups, target, tool, tid, uid):
    """(group index -> id or None). One id is used once; the stronger shell keeps it."""
    scored = []
    for n, g in enumerate(groups):
        shell = g[0][1]
        ft, fu = _cover(shell, target), _cover(shell, tool)
        vol = abs(float(shell.volume)) if shell.is_watertight else float(shell.area)
        order = int(np.min(g[0][0])) if len(g[0][0]) else n
        if ft >= 0.75 and ft >= fu:
            scored.append((int(tid), ft, vol, order))
        elif fu >= 0.75 and fu > ft:
            scored.append((int(uid), fu, vol, order))
        else:
            scored.append((None, 0.0, vol, order))
    chosen = {}
    used = set()
    rank = sorted(
        range(len(scored)),
        key=lambda i: (scored[i][0] is None, -scored[i][1], -scored[i][2], scored[i][3]),
    )
    for i in rank:
        hid = scored[i][0]
        if hid is None or hid in used:
            chosen[i] = None
            continue
        used.add(hid)
        chosen[i] = hid
    return chosen


def keep_boolean_ids(res, target, tool, tid, uid, start: int = 0):
    """Ids on a boolean result.

    One resulting body keeps the target id. When the bodies stay separate, a shell that is still
    the target or the tool keeps that id. Anything else receives a new id past `start`.
    """
    if res is None or len(getattr(res, "faces", [])) == 0:
        return res
    recs = _component_faces(res)
    if not recs:
        return tag_result(res, tid, start)
    groups = _group_components(recs)
    if len(groups) == 1:
        return _stamp(res, int(tid))
    chosen = _shell_rank(groups, target, tool, tid, uid)
    ids = np.zeros(len(res.faces), np.int64)
    for i, g in enumerate(groups):
        hid = chosen.get(i)
        if not hid:
            continue
        for fi, _sub in g:
            ids[fi] = hid
    res.face_attributes[BODY_ATTR] = ids
    return ensure_body_ids(res, start=max(int(start), int(tid or 0), int(uid or 0)))


def op_body_boolean(m, p):
    """Union / subtract / intersect two bodies.

    One resulting solid keeps the target id. Shells that are still the target or the tool keep
    those ids, so a later step finds the same body. Other bodies are left as they are.
    """
    kind = p.get("kind", "union")
    if kind not in ("union", "subtract", "intersect"):
        raise OpError("kind must be union | subtract | intersect")
    ensure_body_ids(m)
    bs = bodies(m)
    target = resolve_body(m, p.get("target", 0), "target")
    tool = resolve_body(m, p.get("tool", 1), "tool")
    tid, uid = body_id_of(target), body_id_of(tool)
    if tid is None or uid is None or tid == uid:
        raise OpError(f"Pick two different bodies (the model has {len(bs)}).")
    A, B = _to_manifold(target), _to_manifold(tool)
    r = {"union": A + B, "subtract": A - B, "intersect": A ^ B}[kind]
    rest = [x for x in bs if body_id_of(x) not in (tid, uid)]
    res = _from_manifold(r) if not r.is_empty() else None
    if res is not None:
        res = keep_boolean_ids(res, target, tool, tid, uid, max_body_id(m))
    out = None
    for x in rest + ([res] if res is not None else []):
        out = _join(out, x)
    if out is None:
        raise OpError("The result is empty.")
    return out, {"message": f"Boolean {kind}."}


_SHARP_DEG = 25.0          # same cutoff as the edges drawn in the workspace
_CHAIN_TURN_DEG = 20.0     # follow a straight run or a gentle curve; stop at a corner
_SNAP_MM = 0.75            # a slightly off pick still means the edge under it
_MAX_ROUND_SEGS = 400


def _convex_flags(mm: trimesh.Trimesh) -> np.ndarray:
    """True on a convex (outside) adjacency. Coplanar pairs are filtered by angle later."""
    n = len(mm.face_adjacency)
    try:
        flags = np.asarray(mm.face_adjacency_convex, bool)
        if len(flags) == n:
            return flags
    except (AttributeError, TypeError, ValueError):
        pass
    if n == 0:
        return np.zeros(0, bool)
    pairs = mm.face_adjacency
    free = mm.vertices[mm.face_adjacency_unshared[:, 0]]
    origin = mm.vertices[mm.faces[pairs[:, 1], 0]]
    normal = mm.face_normals[pairs[:, 1]]
    return np.einsum("ij,ij->i", free - origin, normal) < -1e-6


def _feature_chains(mesh: trimesh.Trimesh) -> list[dict]:
    """Sharp edges chained along a straight run or a gentle curve. A corner starts a new chain.

    Each chain is {pts, convex, closed}. Closed means the last point joins the first (a hole rim).
    """
    mm = mesh.copy()
    mm.merge_vertices()
    if len(mm.faces) == 0 or len(mm.face_adjacency) == 0:
        return []
    ang = mm.face_adjacency_angles
    keep = np.nonzero(ang > np.radians(_SHARP_DEG))[0]
    if len(keep) == 0:
        return []
    edges = mm.face_adjacency_edges[keep]
    convex = _convex_flags(mm)[keep]
    v = mm.vertices
    recs = []
    buckets: dict[int, list[int]] = {}
    for i, (a, b) in enumerate(edges):
        a, b = int(a), int(b)
        d = v[b] - v[a]
        length = float(np.linalg.norm(d))
        if length < 1e-8:
            continue
        recs.append({"a": a, "b": b, "dir": d / length, "convex": bool(convex[i])})
        buckets.setdefault(a, []).append(len(recs) - 1)
        buckets.setdefault(b, []).append(len(recs) - 1)
    cos_turn = math.cos(math.radians(_CHAIN_TURN_DEG))
    used: set[int] = set()

    def other(rec, vid):
        return rec["b"] if rec["a"] == vid else rec["a"]

    def outgoing(rec, vid):
        return rec["dir"] if rec["a"] == vid else -rec["dir"]

    chains = []
    for i, rec in enumerate(recs):
        if i in used:
            continue
        used.add(i)
        poly = [rec["a"], rec["b"]]
        conv = rec["convex"]
        closed = False
        for side in (1, 0):
            if closed:
                break
            while True:
                vid = poly[-1] if side == 1 else poly[0]
                prev = poly[-2] if side == 1 else poly[1]
                inbound = v[vid] - v[prev]
                il = float(np.linalg.norm(inbound))
                if il < 1e-8:
                    break
                inbound = inbound / il
                cands = []
                for j in buckets.get(vid, []):
                    if j in used or recs[j]["convex"] != conv:
                        continue
                    if float(np.dot(inbound, outgoing(recs[j], vid))) < cos_turn:
                        continue
                    cands.append(j)
                    if len(cands) > 1:
                        break
                if len(cands) != 1:
                    break
                j = cands[0]
                nxt = other(recs[j], vid)
                far = poly[0] if side == 1 else poly[-1]
                if nxt == far and len(poly) > 2:
                    used.add(j)
                    closed = True
                    break
                if nxt in poly:
                    break
                used.add(j)
                if side == 1:
                    poly.append(nxt)
                else:
                    poly.insert(0, nxt)
        pts = [np.asarray(v[k], float).copy() for k in poly]
        if len(pts) >= 2:
            chains.append({"pts": pts, "convex": conv, "closed": closed})
    return chains


def _segment_distance(p, a, b) -> float:
    ab = b - a
    L2 = float(np.dot(ab, ab))
    if L2 < 1e-18:
        return float(np.linalg.norm(p - a))
    t = float(np.clip(np.dot(p - a, ab) / L2, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + ab * t)))


def _chain_segments(chain) -> list[tuple[np.ndarray, np.ndarray]]:
    pts = chain["pts"]
    if len(pts) < 2:
        return []
    if not chain["closed"] and len(pts) >= 2:
        straight = True
        for i in range(1, len(pts) - 1):
            d0 = pts[i] - pts[i - 1]
            d1 = pts[i + 1] - pts[i]
            n0, n1 = float(np.linalg.norm(d0)), float(np.linalg.norm(d1))
            if n0 < 1e-8 or n1 < 1e-8 or abs(float(np.dot(d0, d1)) / (n0 * n1)) < 0.999:
                straight = False
                break
        if straight:
            return [(pts[0], pts[-1])]
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if chain["closed"]:
        segs.append((pts[-1], pts[0]))
    return segs


def _chain_polyline(chain):
    pts = chain["pts"]
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if chain["closed"] and len(pts) > 2:
        segs.append((pts[-1], pts[0]))
    return segs


def _nearest_dir(p, segs, tol):
    best = None
    best_d = tol + 1e-9
    for pa, pb in segs:
        d = _segment_distance(p, pa, pb)
        if d <= tol and d < best_d:
            best_d = d
            best = pb - pa
    return best


def _chain_matches(chain, a, b, tol) -> bool:
    """Both picks lie on this edge, and the pick runs along it. A corner is a different chain."""
    segs = _chain_polyline(chain)
    if not segs:
        return False
    da, db = _nearest_dir(a, segs, tol), _nearest_dir(b, segs, tol)
    if da is None or db is None:
        return False
    req = b - a
    rl = float(np.linalg.norm(req))
    if rl < 1e-8:
        return False
    req = req / rl
    cos = math.cos(math.radians(_CHAIN_TURN_DEG))
    for direc in (da, db):
        el = float(np.linalg.norm(direc))
        if el >= 1e-8 and abs(float(np.dot(req, direc / el))) >= cos:
            return True
    return False


def _match_feature_chains(chains, requested, tol):
    """(chosen convex chains, inside-corner misses, not-on-this-body misses)."""
    chosen = []
    seen = set()
    inside = missed = 0
    for edge in requested:
        a = np.asarray(edge[0], float)
        b = np.asarray(edge[1], float)
        hits = [i for i, c in enumerate(chains) if c["convex"] and _chain_matches(c, a, b, tol)]
        if hits:
            i = min(hits, key=lambda k: _chain_gap(chains[k], a, b))
            if i not in seen:
                seen.add(i)
                chosen.append(chains[i])
            continue
        if any((not c["convex"]) and _chain_matches(c, a, b, tol) for c in chains):
            inside += 1
        else:
            missed += 1
    return chosen, inside, missed


def _chain_gap(chain, a, b) -> float:
    segs = _chain_polyline(chain)
    if not segs:
        return 1e9
    nearest = lambda p: min(_segment_distance(p, pa, pb) for pa, pb in segs)
    return nearest(a) + nearest(b)


def _round_miss(inside: int, missed: int) -> OpError:
    if inside and not missed:
        return OpError("Those are inside corners. Fillet and chamfer only change outside edges, and only approximately.")
    if missed and not inside:
        return OpError("Those edges are not on this body. Pick an outside edge of the body you chose.")
    return OpError("None of those edges could be rounded. Inside corners stay sharp, and an edge that is not on this body is left alone.")


def _edge_capsules(edges, r):
    import manifold3d as mf
    caps = None
    for e in edges:
        a, b = np.array(e[0], float), np.array(e[1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1e-6:
            continue
        cyl = mf.Manifold.cylinder(L, 1.5 * r, 1.5 * r, 32)   # neighbouring edges blend within 1.5 r of the ends
        z = (b - a) / L
        ref = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
        x = np.cross(ref, z); x /= np.linalg.norm(x); y = np.cross(z, x)
        T = np.eye(4); T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = x, y, z, a
        c = cyl.transform(T[:3, :])
        caps = c if caps is None else caps + c
    return caps


def op_round_edges(m, p):
    """Fillet (round) or chamfer convex edges by morphological opening (Minkowski with a ball or
    an octahedron). APPROXIMATE: concave (inside) corners are not filleted; the ball is faceted.
    edges = [[[x,y,z],[x,y,z]], ...] limits it to the picked edges; empty = every convex edge."""
    import manifold3d as mf
    r = _num(p, "radius", 1, 0.05, 50)
    style = p.get("style", "fillet")
    if style not in ("fillet", "chamfer"):
        raise OpError("style must be fillet | chamfer")
    sel, rest = _pick(m, p)
    if len(sel.faces) > MAX_ROUND_FACES:
        raise OpError(f"Fillet/chamfer works on bodies up to {MAX_ROUND_FACES:,} triangles (this one has {len(sel.faces):,}). Simplify first.")
    if max(sel.extents) / r > 400:
        raise OpError("The radius is tiny compared with the body; use at least 1/400 of its size.")
    if 2 * r >= min(sel.extents):
        raise OpError(f"Radius {r:g} mm is too big for this body (thinnest side {min(sel.extents):.1f} mm).")
    edges = p.get("edges") or []
    caps_edges = None
    n_features = 0
    warns = []
    if edges:
        if not isinstance(edges, list) or len(edges) > 64:
            raise OpError("edges must be a list of up to 64 [[x,y,z],[x,y,z]] pairs.")
        try:
            parsed = [[list(map(float, e[0]))[:3], list(map(float, e[1]))[:3]] for e in edges]
        except (TypeError, ValueError, IndexError):
            raise OpError("edges must be [[x,y,z],[x,y,z]] pairs.")
        chosen, inside, missed = _match_feature_chains(_feature_chains(sel), parsed, _SNAP_MM)
        if not chosen:
            raise _round_miss(inside, missed)
        caps_edges = []
        for chain in chosen:
            caps_edges.extend(_chain_segments(chain))
        if not caps_edges:
            raise _round_miss(inside, missed)
        if len(caps_edges) > _MAX_ROUND_SEGS:
            raise OpError("That outside edge is too detailed to round in one step. Simplify the body, or pick a shorter edge.")
        n_features = len(chosen)
        if inside:
            warns.append(f"{inside} inside corner(s) stayed sharp. This only rounds outside edges.")
        if missed:
            warns.append(f"{missed} edge(s) were not on this body, so they were left alone.")
    A = _to_manifold(sel)
    if style == "fillet":
        tool = mf.Manifold.sphere(r, 24)
    else:
        v = np.array([[r, 0, 0], [-r, 0, 0], [0, r, 0], [0, -r, 0], [0, 0, r], [0, 0, -r]], np.float32)
        tool = mf.Manifold.hull_points(v)
    try:
        opened = A.minkowski_difference(tool).minkowski_sum(tool)
    except Exception as e:
        raise OpError(f"Rounding failed on this shape: {e}")
    if opened.is_empty():
        raise OpError("The radius removes the whole body.")
    opened_raw = opened
    opened = opened ^ A                       # never grow past the original faces
    if caps_edges:
        caps = _edge_capsules([[a.tolist(), b.tolist()] for a, b in caps_edges], r)
        if caps is not None:
            opened = A - ((A - opened) ^ caps)
    out = None
    nb = len(bodies(sel))
    cands = [opened] + ([opened_raw] if not edges else [])   # the ^A clip can leave coplanar slivers; the raw opening is already inside A up to facets
    for cand in cands:
        for tol in (1e-3, 5e-3, 2e-2, 5e-2, 0):       # merge the near-coincident sliver vertices Minkowski leaves behind
            out = _solid_or_none(cand.simplify(tol), nb)
            if out is not None:
                break
        if out is not None:
            break
    if out is None:                           # QA B3: never hand back a non-manifold mesh
        if caps_edges and len(caps_edges) > 1:
            raise OpError("That curved outside edge could not be rounded cleanly. Try a smaller size, or a straight edge. "
                          "Inside corners stay sharp.")
        raise OpError("The rounded result wouldn't be a clean closed solid on this shape, so it was not applied. "
                      "Try a smaller radius or pick fewer edges.")
    if caps_edges and sel.is_watertight and out.is_watertight and abs(float(sel.volume) - float(out.volume)) < 1e-3 * r * r:
        raise OpError("Those edges were not rounded. Pick an outside edge on this body. Inside corners stay sharp.")
    out = tag_result(out, body_id_of(sel), max_body_id(m))
    if n_features:
        noun = "edge" if n_features == 1 else "edges"
        msg = f"{style.title()} {r:g} mm on {n_features} outside {noun}. Approximate mesh: inside corners stay sharp."
    else:
        msg = f"{style.title()} {r:g} mm (approximate, convex edges)."
    rep = {"message": msg}
    if warns:
        rep["warnings"] = warns
    return _join(out, rest), rep


def op_face_offset(m, p):
    """Push/pull one flat face along its normal by `distance` (the face's connected coplanar region)."""
    d = _num(p, "distance", 1, -LIM, LIM)
    pt, nrm = _vec(p, "point"), _vec(p, "normal", (0, 0, 1), 10)
    if np.linalg.norm(nrm) < 1e-9:
        raise OpError("normal can't be zero.")
    nrm = nrm / np.linalg.norm(nrm)
    mm = m.copy(); mm.merge_vertices()
    fn = mm.face_normals
    cent = mm.triangles_center
    ok = (fn @ nrm > 0.999) & (np.abs((cent - pt) @ nrm) < 1e-3 * max(1.0, float(mm.scale)))
    if not ok.any():
        raise OpError("No flat face found there. Tap a flat face.")
    cand = np.nonzero(ok)[0]
    seed = cand[np.argmin(np.linalg.norm(cent[cand] - pt, axis=1))]
    # grow the connected coplanar region from the seed face
    adj = mm.face_adjacency
    nb = {}
    for a, b in adj:
        if ok[a] and ok[b]:
            nb.setdefault(a, []).append(b); nb.setdefault(b, []).append(a)
    region, stack = {seed}, [seed]
    while stack:
        f = stack.pop()
        for g in nb.get(f, []):
            if g not in region:
                region.add(g); stack.append(g)
    verts = np.unique(mm.faces[list(region)])
    v = mm.vertices.copy()
    v[verts] += nrm * d
    out = _new(v, mm.faces)
    if mm.is_watertight and out.volume <= 0:
        raise OpError("That offset turns the body inside out.")
    side = "inward" if d < 0 else "outward"
    return out, {"message": f"Face moved {abs(d):g} mm {side} ({len(region)} triangles). "
                            "Mesh push of one flat region, not a precise solid offset."}


def _xform_matrix(p, center):
    T = trimesh.transformations.translation_matrix(-center)
    s = _vec(p, "scale", (1, 1, 1), 1000)
    if (s <= 0).any():
        raise OpError("scale values must be positive.")
    T = np.diag([*s, 1]) @ T
    r = _vec(p, "rotate", (0, 0, 0), 3600)
    R = trimesh.transformations.euler_matrix(*np.radians(r), axes="sxyz")
    T = R @ T
    mir = p.get("mirror")
    if mir:
        if mir not in ("x", "y", "z"):
            raise OpError("mirror must be x | y | z")
        M = np.eye(4); M["xyz".index(mir), "xyz".index(mir)] = -1
        T = M @ T
    T = trimesh.transformations.translation_matrix(center + _vec(p, "move")) @ T
    return T


def op_body_transform(m, p):
    """Move / rotate / scale (uniform or per axis) / mirror one body (or all with body = -1), about
    its centre or a given pivot. copy=true keeps the original too (mirror copy)."""
    sel, rest = _pick(m, p)
    piv = p.get("pivot", "center")
    center = sel.bounds.mean(axis=0) if piv == "center" else np.zeros(3) if piv == "origin" else _vec(p, "pivot")
    T = _xform_matrix(p, center)
    # trimesh's apply_transform already flips the winding for a mirror (det < 0); inverting again
    # made mirrored bodies inside-out (-volume). QA N1.
    moved = sel.copy(); moved.apply_transform(T)
    if p.get("copy"):
        # The copy is a new body. The original keeps its id. A shared id would make the next replay ambiguous.
        _stamp(moved, max_body_id(m) + 1)
    out = _join_sep(_join(rest, sel) if p.get("copy") else rest, moved, "Move it slightly, or Union the bodies.")
    return out, {"message": "Transformed."}


def op_pattern(m, p):
    """Linear (step [dx,dy,dz]) or circular (axis + total angle about centre) copies of a body."""
    kind = p.get("kind", "linear")
    count = int(_num(p, "count", 3, 2, MAX_PATTERN))
    sel, rest = _pick(m, p)
    est = len(sel.faces) * count
    if est > MAX_PATTERN_FACES:
        raise OpError(f"That pattern would make about {est:,} triangles (limit {MAX_PATTERN_FACES:,}). "
                      "Use fewer copies or simplify / remesh coarser first.")
    copies = []
    kept = body_id_of(sel)
    nxt = max_body_id(m)
    if kind == "linear":
        step = _vec(p, "step", (20, 0, 0))
        for k in range(count):
            c = sel.copy(); c.apply_translation(step * k)
            if k > 0:
                nxt += 1
                _stamp(c, nxt)
            elif kept:
                _stamp(c, kept)
            copies.append(c)
    elif kind == "circular":
        axis = _vec(p, "axis", (0, 0, 1), 10)
        if np.linalg.norm(axis) < 1e-9:
            raise OpError("axis can't be zero.")
        tot = _num(p, "angle", 360, 1, 360)
        cen = _vec(p, "center")
        n = count if tot < 360 - 1e-6 else count
        stepa = tot / (count - 1 if tot < 360 - 1e-6 else count)
        for k in range(n):
            c = sel.copy()
            c.apply_transform(trimesh.transformations.rotation_matrix(math.radians(stepa * k), axis, cen))
            if k > 0:
                nxt += 1
                _stamp(c, nxt)
            elif kept:
                _stamp(c, kept)
            copies.append(c)
    else:
        raise OpError("kind must be linear | circular")
    if p.get("fuse", True):
        try:
            import manifold3d as mf
            acc = mf.Manifold.batch_boolean([_to_manifold(c) for c in copies], mf.OpType.Add)
            pat = tag_result(_from_manifold(acc), kept, max_body_id(m))
        except OpError:
            pat = _join_all(copies)
    else:
        pat = _join_all(copies)
        if _touching(pat):
            raise OpError("The copies would touch face-to-face, which can't be kept as separate solids. Turn on Fuse, or use a slightly larger spacing.")
    return _join_sep(rest, pat, "Turn on Fuse, or use a slightly larger spacing."), {"message": f"{kind.title()} pattern ×{count}."}


def op_align(m, p):
    """Align a body's min / centre / max on an axis to a value, or to another body's same side."""
    sel, rest = _pick(m, p)
    axis = p.get("axis", "z")
    side = p.get("side", "min")
    if axis not in ("x", "y", "z") or side not in ("min", "center", "max"):
        raise OpError("axis must be x|y|z and side min|center|max")
    k = "xyz".index(axis)
    def at(b):
        lo, hi = b.bounds
        return {"min": lo[k], "max": hi[k], "center": (lo[k] + hi[k]) / 2}[side]
    to_body = p.get("to_body")
    if to_body is not None and not _is_all(to_body):
        target = at(resolve_body(m, to_body, "to_body"))
    else:
        target = _num(p, "value", 0, -LIM, LIM)
    mv = np.zeros(3); mv[k] = target - at(sel)
    out = sel.copy(); out.apply_translation(mv)
    return _join(rest, out), {"message": f"Aligned {side} {axis.upper()}."}


OPS = {"sketch_extrude": op_sketch_extrude, "revolve": op_revolve, "body_boolean": op_body_boolean,
       "round_edges": op_round_edges, "face_offset": op_face_offset, "body_transform": op_body_transform,
       "pattern": op_pattern, "align": op_align}

# Keys each CAD op reads. Anything else in a step's params is dropped before it is stored
# (stored params are shown in History and shared with public projects).
PARAM_KEYS = {
    "sketch_extrude": {"sketch", "plane", "picks", "distance", "direction", "mode", "taper", "replace", "solve"},
    "revolve": {"sketch", "plane", "picks", "axis", "angle", "mode", "replace", "solve"},
    "body_boolean": {"kind", "target", "tool"},
    "round_edges": {"radius", "style", "body", "edges"},
    "face_offset": {"point", "normal", "distance"},
    "body_transform": {"body", "move", "rotate", "scale", "mirror", "pivot", "copy"},
    "pattern": {"kind", "count", "step", "axis", "angle", "center", "body", "fuse"},
    "align": {"body", "axis", "side", "to_body", "value"},
    "sculpt_stroke": {"brush", "radius", "strength", "points", "normal", "delta", "symmetry_x"},
    "remesh": {"edge"},
}


def clean_params(op: str, p: dict) -> dict:
    """Drop unknown keys and validate the plane (named plane or a numeric frame only)."""
    keys = PARAM_KEYS.get(op)
    if keys is None:
        return p
    out = {k: v for k, v in p.items() if k in keys}
    if "plane" in out:
        try:
            o, xd, yd, n = sk.plane(out["plane"])
        except (sk.SketchError, TypeError, ValueError, AttributeError) as e:
            raise OpError(str(e) or "Bad plane.")
        if not isinstance(out["plane"], str):
            r = lambda v: [round(float(x), 6) for x in v]
            kind = "offset" if "offset" in out["plane"] else "midplane" if "mid" in out["plane"] else None
            if kind is None and out["plane"].get("construct") in ("offset", "midplane"):
                kind = out["plane"]["construct"]
            out["plane"] = {"origin": r(o), "normal": r(n), "xdir": r(xd)}
            if kind:
                out["plane"]["construct"] = kind   # label only (fixed strings), shown in History
    if "sketch" in out:
        try:
            out["sketch"] = sk.check(out["sketch"])
        except sk.SketchError as e:
            raise OpError(str(e))
    return out

from . import sculptws as _sculptws   # noqa: E402  (workspace sculpt strokes + remesh)
if hasattr(_sculptws, "OPS"):           # sculptws imported first: it registers itself at its end (QA B15)
    OPS.update(_sculptws.OPS)
from . import cadtext as _cadtext   # noqa: E402  (Text & Emboss)
OPS["cad_text"] = _cadtext.op_cad_text
PARAM_KEYS["cad_text"] = _cadtext.KEYS
from . import cadshape as _cadshape   # noqa: E402  (beginner shapes)
OPS["cad_shape"] = _cadshape.op_cad_shape
PARAM_KEYS["cad_shape"] = _cadshape.KEYS
from . import cadjoint as _cadjoint   # noqa: E402  (print-in-place joints + merge)
OPS.update({"cad_joint": lambda m, p: _cadjoint.op_cad_joint(m, p), "merge_bodies": lambda m, p: _cadjoint.op_merge_bodies(m, p),
            "smart_merge": lambda m, p: _cadjoint.op_smart_merge(m, p)})
PARAM_KEYS.update({"cad_joint": _cadjoint.KEYS, "merge_bodies": _cadjoint.MERGE_KEYS, "smart_merge": _cadjoint.SMART_KEYS})
from . import meshedit as _meshedit   # noqa: E402  (register even when this module is imported first)
_meshedit.OPS.update(OPS)


def label(op: str, p: dict) -> str | None:
    if op in getattr(_sculptws, "OPS", ()):
        return _sculptws.label(op, p)
    if op == "cad_text":
        return _cadtext.label(p)
    if op == "cad_shape":
        return _cadshape.label(p)
    if op in ("cad_joint", "merge_bodies", "smart_merge"):
        return _cadjoint.label(op, p)
    g = lambda k, d="": p.get(k, d)

    def _shown(v, default=None):
        if v is None:
            v = default
        if isinstance(v, str) and _BODY_ID.match(v):
            return f"Body {v}"
        idx = _as_index(v)
        if idx is None or idx < 0:
            return ""
        return f"Body {idx + 1}"

    def b():
        shown = _shown(p.get("body", -1))
        return f" · {shown}" if shown else ""

    try:
        return {
            "sketch_extrude": lambda: f"Extrude {float(g('distance', 10)):g} mm {g('direction', 'up')} ({g('mode', 'new')})",
            "revolve": lambda: f"Revolve {float(g('angle', 360)):g}° ({g('mode', 'new')})",
            "body_boolean": lambda: f"Boolean {g('kind', 'union')} {_shown(g('target', 0), 0)} / {_shown(g('tool', 1), 1)}",
            "round_edges": lambda: f"{str(g('style', 'fillet')).title()} {float(g('radius', 1)):g} mm" + (f" ({len(g('edges'))} edges)" if g("edges") else " (all convex edges)") + b() + " · approximate mesh",
            "face_offset": lambda: f"Face offset {float(g('distance', 1)):g} mm · mesh push, not a solid offset",
            "body_transform": lambda: ("Mirror copy" if g("copy") and g("mirror") else "Mirror" if g("mirror") else "Move/Rotate/Scale") + b(),
            "pattern": lambda: f"{str(g('kind', 'linear')).title()} pattern ×{int(float(g('count', 3)))}" + b(),
            "align": lambda: f"Align {g('side', 'min')} {str(g('axis', 'z')).upper()}" + b(),
        }[op]()
    except Exception:
        return None
