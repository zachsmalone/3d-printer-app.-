"""Plate editor: several independent objects on one printer bed, kept as ONE edit-project mesh.

The mesh is always the objects concatenated in order, so an object is a run of faces. The layout
({"counts": faces per object, "groups": group id per object, "hidden": bool per object}) travels inside
each "plate" op's params, so replaying the op history (undo / redo / jump) is deterministic.
Hidden objects stay in the project but are left out of exports, slicing and the bed checks.
"""
from __future__ import annotations

import numpy as np
import trimesh

MAX_OBJECTS = 60
DEFAULT_BED = (220.0, 220.0, 250.0)
ACTIONS = {"transform", "duplicate", "delete", "center", "arrange", "group", "ungroup", "merge", "separate",
           "lay_flat", "hide", "show"}


class PlateError(ValueError):
    pass


def _sub(m: trimesh.Trimesh, a: int, b: int) -> trimesh.Trimesh:
    f = m.faces[a:b]
    used, inv = np.unique(f.ravel(), return_inverse=True)
    return trimesh.Trimesh(m.vertices[used].copy(), inv.reshape(-1, 3), process=False)


def _components(m: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    try:
        parts = list(m.split(only_watertight=False))
    except Exception:
        parts = [m]
    if not parts or len(parts) > MAX_OBJECTS:           # dust / lithophane islands: treat as one object
        return [m.copy()]
    parts.sort(key=lambda p: (round(float(p.bounds[0][0]), 3), round(float(p.bounds[0][1]), 3)))
    return parts


def default_layout(m) -> dict:
    parts = _components(m)
    return {"counts": [len(p.faces) for p in parts], "groups": list(range(len(parts))), "hidden": [False] * len(parts)}


def valid(layout, m) -> bool:
    try:
        c = [int(x) for x in layout["counts"]]
        return (len(c) >= 1 and all(x > 0 for x in c) and sum(c) == len(m.faces)
                and len(layout.get("groups", c)) == len(c) and len(layout.get("hidden", c)) == len(c))
    except Exception:
        return False


def objects(m, layout) -> list[trimesh.Trimesh]:
    """Split the mesh into its objects. A missing/stale layout -> connected components (in a stable order)."""
    if not valid(layout, m):
        return _components(m)
    out, a = [], 0
    for c in layout["counts"]:
        out.append(_sub(m, a, a + int(c))); a += int(c)
    return out


def normalise(m, layout) -> tuple[list, dict]:
    objs = objects(m, layout)
    if not valid(layout, m):
        layout = {"counts": [len(o.faces) for o in objs], "groups": list(range(len(objs))), "hidden": [False] * len(objs)}
    return objs, {"counts": [int(c) for c in layout["counts"]], "groups": [int(g) for g in layout["groups"]],
                  "hidden": [bool(h) for h in layout["hidden"]]}


def combine(objs, groups, hidden) -> tuple[trimesh.Trimesh, dict]:
    if not objs:
        raise PlateError("The plate needs at least one object.")
    # renumber groups 0..n in first-seen order so layouts stay tidy
    ren: dict = {}
    g2 = [ren.setdefault(g, len(ren)) for g in groups]
    m = trimesh.util.concatenate(objs) if len(objs) > 1 else objs[0].copy()
    m = trimesh.Trimesh(np.asarray(m.vertices, float), np.asarray(m.faces, np.int64), process=False)
    return m, {"counts": [len(o.faces) for o in objs], "groups": g2, "hidden": [bool(h) for h in hidden]}


def printable(m, layout) -> trimesh.Trimesh:
    """The mesh that gets exported and sliced: hidden objects removed."""
    if not valid(layout, m) or not any(layout["hidden"]):
        return m
    objs = objects(m, layout)
    keep = [o for o, h in zip(objs, layout["hidden"]) if not h]
    if not keep:
        return m          # nothing visible: export everything rather than an empty file (the UI warns)
    return combine(keep, list(range(len(keep))), [False] * len(keep))[0]


# ---------------------------------------------------------------- geometry helpers
def _box(meshes):
    lo = np.min([o.bounds[0] for o in meshes], axis=0)
    hi = np.max([o.bounds[1] for o in meshes], axis=0)
    return lo, hi


def _T(m, M):
    o = m.copy(); o.apply_transform(M); return o


def _move(m, d):
    o = m.copy(); o.apply_translation(d); return o


def rot_z(deg, about):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    M = np.eye(4); M[:2, :2] = [[c, -s], [s, c]]
    p = np.array([about[0], about[1], 0.0])
    M[:3, 3] = p - M[:3, :3] @ p
    return M


def _num(p, k, d=None, lo=-1e5, hi=1e5):
    v = p.get(k, d)
    if v is None or v == "":
        return d
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise PlateError(f"{k} must be a number")
    if not np.isfinite(v) or not lo <= v <= hi:
        raise PlateError(f"{k} must be between {lo:g} and {hi:g}")
    return v


def transform_set(meshes, p):
    """Scale (uniform % then optional per-axis target size in mm), rotate about Z, then move. Pivot = the
    selection's footprint centre; the result sits on the bed (z=0)."""
    lo, hi = _box(meshes)
    c = (lo + hi) / 2
    pct = _num(p, "scale_pct", 100.0, 1, 10000)
    S = np.ones(3) * pct / 100.0
    size = p.get("size_mm") or {}
    ext = hi - lo
    for i, k in enumerate("xyz"):
        t = _num(size, k, None, 0.1, 5000) if isinstance(size, dict) else None
        if t:
            if ext[i] <= 1e-9:
                raise PlateError(f"Can't resize a flat object along {k.upper()}.")
            S[i] = t / ext[i]
    M = np.eye(4); M[:3, :3] = np.diag(S); M[:3, 3] = np.array([c[0], c[1], lo[2]]) * (1 - S)
    out = [_T(o, M) for o in meshes]
    rz = _num(p, "rz", 0.0, -3600, 3600)
    if rz:
        out = [_T(o, rot_z(rz, c)) for o in out]
    lo2, hi2 = _box(out)
    c2 = (lo2 + hi2) / 2
    tx = _num(p, "x", None); ty = _num(p, "y", None)
    d = np.array([_num(p, "dx", 0.0), _num(p, "dy", 0.0), -lo2[2]])
    if tx is not None:
        d[0] = tx - c2[0]
    if ty is not None:
        d[1] = ty - c2[1]
    return [_move(o, d) for o in out]


def arrange_units(units, bed, gap=5.0):
    """units: list of lists of meshes that move together (a group). Shelf-pack, centred on (0,0)."""
    from . import orient
    blocks = [trimesh.util.concatenate(u) if len(u) > 1 else u[0] for u in units]
    _, rep = orient.arrange(blocks, bed[:2], gap, bed[2] if len(bed) > 2 else None)
    out = []
    for u, b, pos in zip(units, blocks, rep["positions"]):
        lo = b.bounds[0]
        d = np.array([pos[0] - lo[0], pos[1] - lo[1], -lo[2]])
        out.append([_move(o, d) for o in u])
    return out, rep


def merge(meshes) -> tuple[trimesh.Trimesh, str]:
    """Combine into one body. Watertight parts are unioned (manifold3d) so touching parts fuse; otherwise joined as one mesh."""
    joined = trimesh.util.concatenate(meshes)
    try:
        from . import meshedit
        if meshedit.have_boolean() and all(o.is_watertight for o in meshes):
            u = trimesh.boolean.union(meshes, engine="manifold")
            if u is not None and len(u.faces):
                return trimesh.Trimesh(u.vertices, u.faces, process=False), "union"
    except Exception:
        pass
    return trimesh.Trimesh(joined.vertices, joined.faces, process=False), "joined"


# ---------------------------------------------------------------- the op
def _bed(p):
    b = p.get("bed") or DEFAULT_BED
    try:
        b = [float(x) for x in b][:3]
        if len(b) == 2:
            b.append(DEFAULT_BED[2])
        if all(20 <= x <= 2000 for x in b):
            return tuple(b)
    except (TypeError, ValueError):
        pass
    raise PlateError("Bed size must be 20..2000 mm.")


def apply(m, p) -> tuple[trimesh.Trimesh, dict]:
    act = p.get("action")
    if act not in ACTIONS:
        raise PlateError(f"Unknown plate action; choose from {sorted(ACTIONS)}")
    objs, L = normalise(m, p.get("layout"))
    n = len(objs)
    groups, hidden = list(L["groups"]), list(L["hidden"])
    sel = p.get("sel")
    if sel is None or sel == []:
        sel = list(range(n)) if act in ("center", "arrange", "show") else []
    try:
        sel = sorted({int(i) for i in sel})
    except (TypeError, ValueError):
        raise PlateError("sel must be a list of object numbers")
    if any(not 0 <= i < n for i in sel):
        raise PlateError("That object isn't on the plate any more.")
    if not sel and act not in ("arrange",):
        raise PlateError("Select an object first.")
    msg = ""
    if act == "transform":
        new = transform_set([objs[i] for i in sel], p)
        for i, o in zip(sel, new):
            objs[i] = o
        msg = f"Moved / turned / resized {len(sel)} object{'s' * (len(sel) > 1)}."
    elif act == "center":
        lo, hi = _box([objs[i] for i in sel])
        d = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
        for i in sel:
            objs[i] = _move(objs[i], d)
        msg = "Centred on the bed."
    elif act == "arrange":
        bed = _bed(p)
        gap = _num(p, "gap", 5.0, 0, 50)
        idx = [i for i in range(n) if not hidden[i]] or list(range(n))
        order = []
        for i in idx:
            if groups[i] not in order:
                order.append(groups[i])
        units = [[i for i in idx if groups[i] == g] for g in order]
        placed, rep = arrange_units([[objs[i] for i in u] for u in units], bed, gap)
        for u, ms in zip(units, placed):
            for i, o in zip(u, ms):
                objs[i] = o
        msg = (f"Arranged {len(units)} item{'s' * (len(units) > 1)} {gap:g} mm apart." if rep["fits"]
               else f"Arranged, but they need {rep['footprint_mm'][0]:g} × {rep['footprint_mm'][1]:g} mm, more than the bed.")
    elif act == "duplicate":
        if n + len(sel) > MAX_OBJECTS:
            raise PlateError(f"Up to {MAX_OBJECTS} objects on one plate.")
        lo, hi = _box([objs[i] for i in sel])
        d = np.array([hi[0] - lo[0] + 5.0, 0, 0])
        newg = {}
        top = max(groups) + 1
        for i in sel:
            objs.append(_move(objs[i], d))
            newg.setdefault(groups[i], top + len(newg))
            groups.append(newg[groups[i]]); hidden.append(hidden[i])
        msg = f"Duplicated {len(sel)} object{'s' * (len(sel) > 1)}."
    elif act == "delete":
        if len(sel) >= n:
            raise PlateError("You can't delete every object. Keep at least one, or open another model.")
        keep = [i for i in range(n) if i not in sel]
        objs, groups, hidden = [objs[i] for i in keep], [groups[i] for i in keep], [hidden[i] for i in keep]
        msg = f"Deleted {len(sel)} object{'s' * (len(sel) > 1)}. Undo brings them back."
    elif act in ("hide", "show"):
        for i in sel:
            hidden[i] = act == "hide"
        msg = (f"Hidden: {len(sel)} object{'s' * (len(sel) > 1)} won't print." if act == "hide"
               else f"Showing {len(sel)} object{'s' * (len(sel) > 1)}.")
    elif act == "group":
        if len(sel) < 2:
            raise PlateError("Select two or more objects to group.")
        g = groups[sel[0]]
        for i in sel:
            groups[i] = g
        msg = f"Grouped {len(sel)} objects. They move together but stay separate."
    elif act == "ungroup":
        top = max(groups) + 1
        for k, i in enumerate(sel):
            groups[i] = top + k
        msg = "Ungrouped."
    elif act == "merge":
        if len(sel) < 2:
            raise PlateError("Select two or more objects to merge.")
        body, how = merge([objs[i] for i in sel])
        first = sel[0]
        keep = [i for i in range(n) if i == first or i not in sel]
        objs[first] = body
        hid = all(hidden[i] for i in sel)
        objs, groups, hidden = [objs[i] for i in keep], [groups[i] for i in keep], [hidden[i] if i != first else hid for i in keep]
        msg = f"Merged {len(sel)} objects into one " + ("solid body." if how == "union" else "mesh (joined, not fused).")
    elif act == "separate":
        out_o, out_g, out_h, made = [], [], [], 0
        top = max(groups) + 1
        for i in range(n):
            if i in sel:
                parts = _components(objs[i])
                if len(parts) == 1 and len(objs[i].faces) > 0:
                    parts = [objs[i]]
                made += len(parts) - 1
                for k, part in enumerate(parts):
                    out_o.append(part); out_g.append(top); out_h.append(hidden[i]); top += 1
            else:
                out_o.append(objs[i]); out_g.append(groups[i]); out_h.append(hidden[i])
        if len(out_o) > MAX_OBJECTS:
            raise PlateError(f"That makes more than {MAX_OBJECTS} objects.")
        objs, groups, hidden = out_o, out_g, out_h
        msg = f"Split into {made + len(sel)} separate parts." if made else "Already one piece: nothing to separate."
    elif act == "lay_flat":
        from . import orient
        for i in sel:
            lo, hi = objs[i].bounds
            c = (lo + hi) / 2
            o, _ = orient.lay_flat(objs[i])
            lo2, hi2 = o.bounds
            c2 = (lo2 + hi2) / 2
            objs[i] = _move(o, [c[0] - c2[0], c[1] - c2[1], -lo2[2]])
        msg = f"Laid {len(sel)} object{'s' * (len(sel) > 1)} flat."
    out, layout = combine(objs, groups, hidden)
    return out, {"message": msg, "layout": layout, "action": act}


def label(p: dict) -> str:
    names = {"transform": "Move / rotate / resize", "duplicate": "Duplicate", "delete": "Delete", "center": "Auto-centre",
             "arrange": "Auto-arrange", "group": "Group", "ungroup": "Ungroup", "merge": "Merge", "separate": "Separate",
             "lay_flat": "Lay flat", "hide": "Hide", "show": "Show"}
    n = len(p.get("sel") or [])
    return "Plate: " + names.get(p.get("action"), "edit") + (f" ({n} selected)" if n else "")


# ---------------------------------------------------------------- report for the UI
def describe(m, layout, bed=DEFAULT_BED) -> dict:
    objs, L = normalise(m, layout)
    bx, by, bz = bed
    info = []
    for i, o in enumerate(objs):
        lo, hi = o.bounds
        info.append({"i": i, "name": f"Object {i + 1}", "group": L["groups"][i], "hidden": L["hidden"][i],
                     "faces": len(o.faces), "min": [round(float(v), 2) for v in lo], "max": [round(float(v), 2) for v in hi],
                     "size": [round(float(v), 2) for v in hi - lo], "center": [round(float(v), 2) for v in (lo + hi) / 2],
                     "warnings": []})
    vis = [x for x in info if not x["hidden"]]
    for x in vis:
        lo, hi = x["min"], x["max"]
        if x["size"][0] > bx or x["size"][1] > by or x["size"][2] > bz:
            x["warnings"].append("Too big for the bed.")
        elif lo[0] < -bx / 2 - 0.01 or hi[0] > bx / 2 + 0.01 or lo[1] < -by / 2 - 0.01 or hi[1] > by / 2 + 0.01:
            x["warnings"].append("Hangs off the bed edge.")
    for a in range(len(vis)):
        for b in range(a + 1, len(vis)):
            A, B = vis[a], vis[b]
            if A["group"] == B["group"]:
                continue
            if A["min"][0] < B["max"][0] and B["min"][0] < A["max"][0] and A["min"][1] < B["max"][1] and B["min"][1] < A["max"][1]:
                A["warnings"].append(f"Overlaps {B['name']}.")
                B["warnings"].append(f"Overlaps {A['name']}.")
    for x in info:
        if x["hidden"]:
            x["warnings"] = ["Hidden, won't print."]
    return {"objects": info, "layout": L, "bed_mm": [bx, by, bz], "visible": len(vis),
            "all_hidden": not vis}

