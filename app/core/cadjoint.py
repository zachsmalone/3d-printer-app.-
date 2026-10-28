"""CAD print-in-place joints and merge tools (original ZEIM code, manifold3d Apache-2.0 for the solids).

Ops (each is an ordinary history step):
  * cad_joint    - a hinge (print-in-place or snap-on), a ball joint, a pin joint or a short chain,
                   added as new separate bodies with a clearance gap between the moving parts.
  * merge_bodies - fuse picked bodies into one (optionally snap the 2nd.. against the 1st first).
  * smart_merge  - put Smart Split pieces back where they were cut from (recorded by smart_split) and fuse.
Clearance defaults to 0.3 mm (willprint.PIP_CLEARANCE_FDM). Fit is simulated: nothing here is test-printed.
"""
from __future__ import annotations

import numpy as np
import trimesh

KINDS = ("hinge", "snap_hinge", "ball", "pin", "chain")
NAMES = {"hinge": "print-in-place hinge", "snap_hinge": "snap-on hinge", "ball": "ball joint", "pin": "pin joint", "chain": "chain"}
KEYS = {"kind", "length", "width", "thickness", "knuckles", "clearance", "size", "links", "position", "mode", "replace"}
MERGE_KEYS = {"bodies", "snap", "overlap"}
SMART_KEYS = {"pieces", "tolerance"}
SEG = 48

from .meshedit import OpError   # noqa: E402  (after KEYS: meshedit -> cadops -> this module)


def _mf():
    import manifold3d as mf
    return mf


def _box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return _mf().Manifold.cube((hi - lo).tolist(), False).translate(lo.tolist())


def _cyl_x(r, x0, x1, y=0.0, z=0.0):
    """Cylinder along X from x0 to x1 with its axis at (y, z)."""
    return _mf().Manifold.cylinder(x1 - x0, r, r, SEG).rotate([0, 90, 0]).translate([x0, y, z])


def _cyl_z(r, z0, z1, x=0.0, y=0.0):
    return _mf().Manifold.cylinder(z1 - z0, r, r, SEG).translate([x, y, z0])


def _union(xs):
    out = xs[0]
    for x in xs[1:]:
        out = out + x
    return out


def hinge(L=40.0, W=15.0, t=2.0, n=5, c=0.3, snap=False):
    """Two leaves flat on the bed joined by alternating knuckles around a pin along X.
    Print-in-place: leaf B's knuckles ring the pin with a clearance gap. Snap: leaf B is printed beside A
    with C-shaped knuckles that clip onto A's pin."""
    if n < 3 or n % 2 == 0:
        raise OpError("Knuckles must be an odd number from 3 to 9.")
    R = max(t, 2.0) + 0.6                       # knuckle outer radius (leaves sit flush with the bottom)
    rp = max(1.0, R * 0.45)                     # pin radius
    if rp + c + 0.8 > R:
        raise OpError("The clearance is too big for this leaf thickness. Use a thicker leaf or a smaller clearance.")
    seg = (L - (n - 1) * c) / n
    if seg < 2 * c + 2:
        raise OpError("The hinge is too short for that many knuckles. Make it longer or use fewer knuckles.")
    xs = [(-L / 2 + i * (seg + c), -L / 2 + i * (seg + c) + seg) for i in range(n)]
    z = R
    a_parts = [_box([-L / 2, -W, 0], [L / 2, -(R + c), t]), _cyl_x(rp, -L / 2, L / 2, 0, z)]
    b_parts = [_box([-L / 2, R + c, 0], [L / 2, W, t])]
    for i, (x0, x1) in enumerate(xs):
        if i % 2 == 0:
            a_parts += [_cyl_x(R, x0, x1, 0, z), _box([x0, -(R + c) - 0.5, 0], [x1, 0, t])]
        else:
            k = _cyl_x(R, x0, x1, 0, z) + _box([x0, 0, 0], [x1, R + c + 0.5, t])
            b_parts.append(k - _cyl_x(rp + c, x0 - 1, x1 + 1, 0, z))
    A = _union(a_parts)
    B = _union(b_parts)
    if snap:
        # open the ring on top so it clips down over the pin (slot a little narrower than the pin)
        slot = _box([-L / 2 - 1, -rp * 0.8, z], [L / 2 + 1, rp * 0.8, z + R + 1])
        B = B - slot
        B = B.translate([0, 2 * R + 6, 0])     # printed beside A, not around the pin
    return [A, B], {"clearance_mm": c, "pin_mm": round(2 * rp, 2), "knuckles": n}


def ball(size=20.0, c=0.3):
    """Captive ball in an open-top socket; the stem leaves through the top opening (narrower than the ball)."""
    rb = size / 2 * 0.55
    w = max(1.6, rb * 0.25)
    ro = rb + c + w
    zc = ro - 0.25 * ro                        # flatten the socket bottom so it sits on the bed
    mf = _mf()
    sock = mf.Manifold.sphere(ro, SEG).translate([0, 0, zc]) - mf.Manifold.sphere(rb + c, SEG).translate([0, 0, zc])
    cut_z = zc + rb * 0.5
    sock = sock - _box([-ro - 1, -ro - 1, cut_z], [ro + 1, ro + 1, zc + ro + 1]) - _box([-ro - 1, -ro - 1, -ro * 3], [ro + 1, ro + 1, 0])
    rs = rb * 0.35
    top = zc + ro + 4
    knob = mf.Manifold.sphere(rb, SEG).translate([0, 0, zc]) + _cyl_z(rs, zc, top) + _cyl_z(rb * 0.9, top, top + 2.4)
    opening = float(np.sqrt(max(0.0, (rb + c) ** 2 - (rb * 0.5) ** 2)))
    return [sock, knob], {"clearance_mm": c, "ball_mm": round(2 * rb, 2), "opening_mm": round(2 * opening, 2)}


def pin(L=40.0, w=10.0, t=3.0, c=0.3):
    """Two arms turning on a capped pin. Arm A on the bed carries the pin; arm B's pad sits over A with a
    clearance gap and its arm steps down to the bed so it does not need supports."""
    rp = max(1.5, w * 0.2)
    cap = 1.2
    A = _box([-L, -w / 2, 0], [0, w / 2, t]) + _cyl_z(w / 2, 0, t) + _cyl_z(rp, 0, 2 * t + 2 * c + cap) \
        + _cyl_z(rp + 1.4, 2 * t + 2 * c, 2 * t + 2 * c + cap)
    B = _cyl_z(w / 2, t + c, 2 * t + c) + _box([0, -w / 2, t + c], [w / 2 + c, w / 2, 2 * t + c]) \
        + _box([w / 2 + c, -w / 2, 0], [L, w / 2, 2 * t + c])
    B = B - _cyl_z(rp + c, -1, 3 * t + 5)
    return [A, B], {"clearance_mm": c, "pin_mm": round(2 * rp, 2)}


def chain(links=5, size=16.0, c=0.3):
    """Alternating flat / standing rectangular links that interlock as printed."""
    if not 2 <= links <= 30:
        raise OpError("A chain needs 2 to 30 links.")
    Lo = size
    b = max(1.6, size * 0.14)
    Wo = max(3 * b + 4 * c + 2, size * 0.6)
    p = Lo - 2 * b - 2 * c - 0.2
    if p <= b:
        raise OpError("Links are too small for that clearance. Make them bigger.")
    zf = b + c
    Hv = 3 * b + 2 * c + 0.4
    out = []
    for k in range(links):
        x = k * p
        if k % 2 == 0:
            frame = _box([x - Lo / 2, -Wo / 2, zf], [x + Lo / 2, Wo / 2, zf + b]) - _box([x - Lo / 2 + b, -Wo / 2 + b, zf - 1], [x + Lo / 2 - b, Wo / 2 - b, zf + b + 1])
        else:
            frame = _box([x - Lo / 2, -b / 2, 0], [x + Lo / 2, b / 2, Hv]) - _box([x - Lo / 2 + b, -b, b], [x + Lo / 2 - b, b, Hv - b])
        out.append(frame)
    return out, {"clearance_mm": c, "pitch_mm": round(p, 2), "links": links}


def build(p: dict):
    kind = p.get("kind", "hinge")
    if kind not in KINDS:
        raise OpError(f"kind must be one of {' | '.join(KINDS)}.")
    c = C._num(p, "clearance", 0.3, 0.15, 1.0)
    if kind in ("hinge", "snap_hinge"):
        n = int(C._num(p, "knuckles", 5, 3, 9))
        parts, info = hinge(C._num(p, "length", 40, 10, 300), C._num(p, "width", 15, 5, 200),
                            C._num(p, "thickness", 2, 1, 10), n, c, snap=kind == "snap_hinge")
    elif kind == "ball":
        parts, info = ball(C._num(p, "size", 20, 8, 120), c)
    elif kind == "pin":
        parts, info = pin(C._num(p, "length", 40, 10, 300), C._num(p, "width", 10, 5, 100), C._num(p, "thickness", 3, 1.2, 20), c)
    else:
        parts, info = chain(int(C._num(p, "links", 5, 2, 30)), C._num(p, "size", 16, 8, 80), c)
    meshes = [C._from_manifold(x) for x in parts]
    # the moving parts must not touch: check the actual gap between them
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            if (parts[i] ^ parts[j]).volume() > 1e-6:
                raise OpError("The parts would overlap at this size. Try a bigger size or a larger clearance.")
    tool = C._join_all(meshes)
    lo, hi = tool.bounds
    pos = C._vec(p, "position", (0, 0, 0))
    tool.apply_translation([pos[0] - (lo[0] + hi[0]) / 2, pos[1] - (lo[1] + hi[1]) / 2, pos[2] - lo[2]])
    return tool, info


def op_cad_joint(m, p):
    tool, info = build(p)
    out = C._combine(m, tool, "new", replace=bool(p.get("replace")))
    kind = p.get("kind", "hinge")
    msg = f"Added a {NAMES[kind]} ({info['clearance_mm']:g} mm gap)."
    warns = ["Moving-part fit is simulated, not test-printed. Print a small one first and adjust the clearance for your printer."]
    if kind in ("chain", "pin"):
        warns.append("Some link or arm faces print over a small gap; turn on supports if your printer sags there.")
    return out, {"message": msg, "joint": info, "warnings": warns}


# ---------------------------------------------------------------- merge
_SNAP = {"x+": (0, 1), "x-": (0, -1), "y+": (1, 1), "y-": (1, -1), "z+": (2, 1)}


def _fuse(ms):
    out = C._to_manifold(ms[0])
    for x in ms[1:]:
        out = out + C._to_manifold(x)
    return C._from_manifold(out)


def op_merge_bodies(m, p):
    C.ensure_body_ids(m)
    bs = C.bodies(m)
    refs = p.get("bodies") or []
    if not isinstance(refs, (list, tuple)):
        raise OpError("bodies must be a list of body references.")
    pick = []
    seen = []
    for ref in refs:
        part = C.resolve_body(m, ref, "bodies")
        pid = C.body_id_of(part)
        if pid in seen:
            continue
        seen.append(pid)
        pick.append(part.copy())
    if len(pick) < 2:
        raise OpError("Pick at least two bodies to merge.")
    snap = p.get("snap") or "none"
    if snap != "none":
        if snap not in _SNAP:
            raise OpError("snap must be none | x+ | x- | y+ | y- | z+")
        ov = C._num(p, "overlap", 0.2, 0, 5)
        ax, sgn = _SNAP[snap]
        lo0, hi0 = pick[0].bounds
        for q in pick[1:]:
            lo, hi = q.bounds
            d = np.zeros(3)
            for k in range(3):
                if k != ax:
                    d[k] = (lo0[k] + hi0[k]) / 2 - (lo[k] + hi[k]) / 2 if k != 2 else lo0[2] - lo[2]
            d[ax] = (hi0[ax] - ov - lo[ax]) if sgn > 0 else (lo0[ax] + ov - hi[ax])
            q.apply_translation(d)
    fused = C.tag_result(_fuse(pick), C.body_id_of(pick[0]), C.max_body_id(m))
    rest = [b for b in bs if C.body_id_of(b) not in seen]
    n_out = len(C.bodies(fused))
    warns = []
    if n_out > 1:
        warns.append(f"{n_out} pieces still don't touch, so they stay separate. Move them so they overlap a little, then merge again.")
    out = C._join_sep(C._join_all(rest) if rest else None, fused, "Move it away from the other bodies a little first.")
    return out, {"message": f"Merged {len(pick)} bodies." if n_out == 1 else f"Merged where they touch; {n_out} pieces remain.", "warnings": warns}


def op_smart_merge(m, p):
    pieces = p.get("pieces") or []
    if not isinstance(pieces, list) or not pieces:
        raise OpError("No Smart Split cuts are recorded in this design's History.")
    tol = C._num(p, "tolerance", 1.0, 0.05, 20)
    bs = C.bodies(m)
    centers = [b.bounds.mean(axis=0) for b in bs]
    used, moved = set(), []
    for pc in pieces[:64]:
        try:
            at = np.array([float(v) for v in pc["at"]][:3]); mv = np.array([float(v) for v in pc["move"]][:3])
        except (KeyError, TypeError, ValueError):
            raise OpError("The recorded Smart Split pieces are not readable.")
        best = min((k for k in range(len(bs)) if k not in used), key=lambda k: np.linalg.norm(centers[k] - at), default=None)
        if best is None or np.linalg.norm(centers[best] - at) > tol:
            continue
        used.add(best)
        q = bs[best].copy(); q.apply_translation(-mv); moved.append(q)
    if len(moved) < 2:
        raise OpError("The split pieces have moved since the cut, so they can't be matched. Use Merge with snapping instead.")
    # Keep the first matched piece's id when the pieces become one solid. A new id would
    # orphan a later step that still names that body.
    fused = C.tag_result(_fuse(moved), C.body_id_of(moved[0]), C.max_body_id(m))
    rest = [b for k, b in enumerate(bs) if k not in used]
    warns = []
    if len(moved) < len(pieces):
        warns.append(f"{len(pieces) - len(moved)} piece(s) had moved and were left as they are.")
    n_out = len(C.bodies(fused))
    if n_out > 1:
        warns.append(f"The rejoined model has {n_out} separate pieces (connector pins or gaps). Check it before printing.")
    out = C._join_sep(C._join_all(rest) if rest else None, fused, "Move the leftover pieces away a little first.")
    return out, {"message": f"Rejoined {len(moved)} pieces along the Smart Split cuts.", "warnings": warns}


def label(op: str, p: dict) -> str:
    if op == "cad_joint":
        return "Add " + NAMES.get(p.get("kind", "hinge"), "joint")
    if op == "merge_bodies":
        return f"Merge {len(p.get('bodies') or [])} bodies" + ("" if (p.get("snap") or "none") == "none" else f" (snap {p['snap']})")
    return f"Smart merge ({len(p.get('pieces') or [])} pieces)"


from . import cadops as C   # noqa: E402  (bottom: cadops imports this module while it registers ops)
