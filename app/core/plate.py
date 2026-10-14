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
           "lay_flat", "hide", "show", "cut"}
CUT_JOINS = ("none", "glue", "magnet", "dovetail", "pin")
CUT_MATERIALS = ("PLA", "PETG")


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


# ---------------------------------------------------------------- cut one object with a plane (+ Smart Split connectors)
def _cyl_vol(r, h, sections=48):
    """Volume of the 48-sided cylinders Smart Split cuts / adds (a polygon prism, a hair under pi r^2 h)."""
    return 0.5 * sections * r * r * np.sin(2 * np.pi / sections) * h


def _clearance_default(join: str, material: str) -> float:
    """Starting clearances from data/split/split-specs.json (magnet glue fit: +0.25 mm PLA / +0.30 mm PETG)."""
    from . import smartsplit
    sp = smartsplit.specs()
    if join == "dovetail":
        return float(sp["dovetails"]["starting_geometry"]["per_side_clearance_mm"][material])
    if join == "pin":
        return float(sp["alignment_pins"]["starting_geometry"]["hole_clearance_mm"][material])
    if join == "magnet":
        return 0.25 if material == "PLA" else 0.30
    return 0.0


WALL_MM = 1.2      # split specs: keep at least 1.2 mm (about 3 perimeters) of plastic around a pocket


def _section_2d(o, origin, normal, u, v):
    """The object's cross-section on the cut plane as a shapely shape in (u, v) mm (even-odd, so holes stay holes)."""
    from shapely.geometry import Polygon
    sec = o.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        return None
    geom = None
    for loop in sec.discrete:
        if len(loop) < 3:
            continue
        pg = Polygon(np.c_[loop @ u, loop @ v]).buffer(0)
        if pg.is_empty:
            continue
        geom = pg if geom is None else geom.symmetric_difference(pg)
    return geom


def _connector_inside(o, origin, normal, join, detail) -> bool:
    """True when every pocket / pin hole / dovetail slot sits inside the cut face with WALL_MM of plastic around it."""
    from shapely.geometry import Point, box as sbox
    from . import smartsplit
    u, v = smartsplit._inplane_axes(normal)
    face = _section_2d(o, origin, normal, u, v)
    if face is None or face.is_empty:
        return False
    inner = face.buffer(-WALL_MM)
    pts = [np.asarray(a, float) for a in detail.get("at") or []]
    if join == "magnet":
        r = (detail["magnet_mm"][0] + detail["clearance_mm"]) / 2
        shapes = [Point(float(pt @ u), float(pt @ v)).buffer(r, 48) for pt in pts]
    elif join == "pin":
        r = (detail["pin_diameter_mm"] + detail["clearance_mm"]) / 2
        shapes = [Point(float(pt @ u), float(pt @ v)).buffer(r, 48) for pt in pts]
    else:
        c, w, L = pts[0], detail["mouth_mm"] + 2 * detail["clearance_mm"], detail["length_mm"] + 0.2
        cu, cv = float(c @ u), float(c @ v)
        shapes = [sbox(cu - w / 2, cv - L / 2, cu + w / 2, cv + L / 2)]
    return bool(shapes) and all(inner.contains(sh) for sh in shapes)


def cut_object(o: trimesh.Trimesh, p: dict, bed=None, others=None) -> tuple[list, dict]:
    """Cut ONE object with a flat plane across X, Y or Z, optionally adding a Smart Split connector on the two cut faces.
    `offset` is mm from the object's low side along that axis. `bed` (x, y, z) and `others` (bounds of the other visible
    objects) only steer where the second piece is put. Returns ([piece_a, piece_b], info). Fit is Simulated."""
    from . import meshedit, smartsplit
    axis = str(p.get("axis") or "z").lower()
    if axis not in ("x", "y", "z"):
        raise PlateError("Cut across X, Y or Z.")
    ai = "xyz".index(axis)
    join = str(p.get("join") or "none").lower()
    if join not in CUT_JOINS:
        raise PlateError("Join must be none, glue, magnet, dovetail or pin.")
    material = str(p.get("material") or "PLA").upper()
    if material not in CUT_MATERIALS:
        raise PlateError("Material must be PLA or PETG (it sets the starting gap).")
    lo, hi = o.bounds
    ext = float(hi[ai] - lo[ai])
    if ext < 2.0:
        raise PlateError(f"This object is only {ext:.1f} mm along {axis.upper()}, too thin to cut there.")
    off = _num(p, "offset", ext / 2, -1e5, 1e5)
    if not 0.5 <= off <= ext - 0.5:
        raise PlateError(f"Put the cut inside the object: between 0.5 and {ext - 0.5:.1f} mm from its {('left', 'front', 'bottom')[ai]} side.")
    pos = float(lo[ai] + off)
    if join != "none" and not meshedit.have_boolean():
        raise PlateError("Magnet, dovetail, pin and glue joins need manifold3d on the server. Choose None for a plain cut.")
    try:
        below, above, normal = smartsplit._slice_one(o, axis, pos)
    except meshedit.OpError as e:
        raise PlateError(str(e))
    closed = bool(below.is_watertight and above.is_watertight)
    detail, origin = {}, normal * pos
    if join != "none":
        if not closed:
            raise PlateError("This object isn't watertight, so the cut faces can't take a connector. Run Fix first, or choose None.")
        q = {} if join == "glue" else {"clearance": _num(p, "clearance", _clearance_default(join, material), 0.05, 1.0)}
        for k in ("magnet_diameter", "magnet_thickness", "pin_diameter", "count"):
            if p.get(k) not in (None, ""):
                q[k] = p[k]
        v0b, v0a = float(below.volume), float(above.volume)
        try:
            below, above, detail = smartsplit.apply_join(below, above, origin, normal, join, q)
        except meshedit.OpError as e:
            raise PlateError(f"The {join} join didn't work on this cut ({e}). Try another spot, a smaller connector, or None.")
        db, da = float(below.volume) - v0b, float(above.volume) - v0a       # + added, - removed
        exp_b = exp_a = None
        if join == "magnet":
            r = (detail["magnet_mm"][0] + detail["clearance_mm"]) / 2
            exp_b = exp_a = -detail["pockets"] * _cyl_vol(r, detail["magnet_mm"][1] + 0.15)
        elif join == "pin":
            d, half, c = detail["pin_diameter_mm"], detail["engagement_mm"] / 2, detail["clearance_mm"]
            exp_b = detail["pins"] * _cyl_vol(d / 2, half)
            exp_a = -detail["pins"] * _cyl_vol((d + c) / 2, half + 0.4)
        elif join == "dovetail":
            d, m_, r_, c, L = (detail[k] for k in ("depth_mm", "mouth_mm", "root_mm", "clearance_mm", "length_mm"))
            exp_b = (m_ + r_) / 2 * d * L
            exp_a = -((m_ + 2 * c) + (r_ + 2 * c)) / 2 * (d + c) * (L + 0.2)
        if join in ("magnet", "pin", "dovetail") and not _connector_inside(o, origin, normal, join, detail):
            need = {"magnet": "magnet pockets", "pin": "pins and holes", "dovetail": "dovetail tab"}[join]
            raise PlateError(f"The {need} {'does' if join == 'dovetail' else 'do'} not fit inside this cut face with a {WALL_MM:g} mm wall around them. "
                             "Move the cut to a wider spot, use a smaller size or fewer, or choose Glue or None.")
        if exp_b is not None:
            tol = lambda got, exp: abs(got - exp) <= 0.03 * abs(exp) + 0.05
            bodies_ok = len(below.split(only_watertight=False)) == 1 and len(above.split(only_watertight=False)) == 1
            if not (tol(db, exp_b) and tol(da, exp_a) and bodies_ok and below.is_watertight and above.is_watertight):
                need = {"magnet": "magnet pockets", "pin": "pins and holes", "dovetail": "dovetail tab"}[join]
                raise PlateError(f"The {need} {'does' if join == 'dovetail' else 'do'} not fit inside this cut face (it would break through the side or the far face). "
                                 "Move the cut to a thicker spot, use a smaller size or fewer, or choose Glue or None.")
        detail = {**detail, "material": material}
    # Place the two pieces side by side on the bed. Z cuts: both already stand on a flat face.
    pieces = [(below, normal, join in ("pin", "dovetail", "glue")), (above, -normal, False)]   # (mesh, cut-face outward normal, raised connector?)
    lay = bool(p.get("lay_flat")) and axis != "z"
    out, laid = [], []
    for k, (m, n, raised) in enumerate(pieces):
        q = m.copy()
        if lay and not raised:
            q.apply_transform(trimesh.geometry.align_vectors(n, [0, 0, -1])); laid.append(k)
        out.append(q)
    gap = _num(p, "gap", 5.0, 0, 100)
    c0 = (lo + hi) / 2
    b_lo, b_hi = out[0].bounds
    out[0] = _move(out[0], [c0[0] - (b_lo[0] + b_hi[0]) / 2, c0[1] - (b_lo[1] + b_hi[1]) / 2, -b_lo[2]])
    b_lo, b_hi = out[0].bounds
    a_lo, a_hi = out[1].bounds
    j = 1 if axis == "y" else 0                                    # Y cuts open along Y, the rest along X
    # Second piece next to the first: try the cut's opening side first, then the other sides; keep it on the bed and off
    # the other objects when it can (Auto-arrange is there for anything harder).
    bx, by = (bed or DEFAULT_BED)[:2]
    others = others or []
    best = None
    for k, (jj, sgn) in enumerate([(j, 1), (j, -1), (1 - j, 1), (1 - j, -1)]):
        d = np.zeros(3)
        d[jj] = (b_hi[jj] + gap - a_lo[jj]) if sgn > 0 else (b_lo[jj] - gap - a_hi[jj])
        d[1 - jj] = (b_lo[1 - jj] + b_hi[1 - jj]) / 2 - (a_lo[1 - jj] + a_hi[1 - jj]) / 2
        d[2] = -a_lo[2]
        lo2, hi2 = a_lo + d, a_hi + d
        off_bed = lo2[0] < -bx / 2 or hi2[0] > bx / 2 or lo2[1] < -by / 2 or hi2[1] > by / 2
        hits = sum(1 for olo, ohi in others if lo2[0] < ohi[0] and olo[0] < hi2[0] and lo2[1] < ohi[1] and olo[1] < hi2[1])
        score = (int(off_bed), hits, k)
        if best is None or score < best[0]:
            best = (score, d)
    out[1] = _move(out[1], best[1])
    note = ("Connector fit is Simulated: starting sizes come from ZEIM's split specs for " + material +
            ". Print a small test piece first. Not tested on a real printer." if join != "none" else
            "Plain flat cut faces. Fit is Simulated until you test-print.")
    if lay and join in ("pin", "dovetail", "glue"):
        note += " The piece with the raised connector stays standing so the connector points up."
    if not closed:
        note += " The object wasn't watertight, so the cut faces may be open. Run Fix on the model for capped faces."
    info = {"axis": axis, "offset_mm": round(off, 2), "position_mm": round(pos, 2), "join": join, "verification": "Simulated",
            "note": note, "watertight": [bool(x.is_watertight) for x in out], "laid_on_cut_face": laid, **({"connector": detail} if detail else {})}
    return out, info


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
    msg, extra_rep = "", {}
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
    elif act == "cut":
        if len(sel) != 1:
            raise PlateError("Select one object to cut.")
        if n + 1 > MAX_OBJECTS:
            raise PlateError(f"Up to {MAX_OBJECTS} objects on one plate.")
        i = sel[0]
        others = [tuple(objs[k].bounds) for k in range(n) if k != i and not hidden[k]]
        pieces, cut = cut_object(objs[i], p, _bed(p), others)
        top = max(groups) + 1
        objs = objs[:i] + pieces + objs[i + 1:]
        groups = groups[:i] + [top, top + 1] + groups[i + 1:]
        hidden = hidden[:i] + [hidden[i], hidden[i]] + hidden[i + 1:]
        jn = {"none": "plain cut", "glue": "glue marks", "magnet": "magnet pockets", "dovetail": "dovetail tab", "pin": "pins + holes"}[cut["join"]]
        msg = (f"Cut Object {i + 1} across {cut['axis'].upper()} at {cut['offset_mm']:g} mm into 2 pieces ({jn}). "
               f"Fit is Simulated. Undo puts it back.")
        extra_rep["cut"] = cut
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
    return out, {"message": msg, "layout": layout, "action": act, **extra_rep}


def label(p: dict) -> str:
    names = {"transform": "Move / rotate / resize", "duplicate": "Duplicate", "delete": "Delete", "center": "Auto-centre",
             "arrange": "Auto-arrange", "group": "Group", "ungroup": "Ungroup", "merge": "Merge", "separate": "Separate",
             "lay_flat": "Lay flat", "hide": "Hide", "show": "Show", "cut": "Cut"}
    n = len(p.get("sel") or [])
    if p.get("action") == "cut":
        j = str(p.get("join") or "none")
        return f"Plate: Cut {str(p.get('axis') or 'z').upper()} at {p.get('offset', 'middle')} mm" + ("" if j == "none" else f" ({j})")
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

