"""Memory box: four photo lithophane walls round a light (cube), in three print styles.

  snap      4 panels with solid edge posts; each post carries pins on one side and matching
            sockets on the other so neighbours click together (butt joint, pinwheel layout),
            plus a separate base with the light hole and an optional lid.
  frame     a base and a top ring, each with a square groove track; the 4 flat panels slide in.
  enclosed  base + 4 walls fused into ONE piece; a lid slides along grooved rails on two
            opposite walls (inserted from the open side, stopped by the far wall).

Everything scales with panel_mm (outer side of the cube). Walls reuse geometry.lithophane
(flat rect panels); solids are trimesh boxes/cylinders combined with manifold booleans, so
every part is watertight. Returns (print_model, preview_model): the print model lays every
part flat and apart for export, the preview model is the assembled cube.
Values are starting points; tolerances depend on the printer.
"""
from __future__ import annotations

import numpy as np
import trimesh
from PIL import Image, ImageOps

from . import geometry
from .geometry import Body, Model

STYLES = ("snap", "frame", "enclosed")
MIN_PANEL, MAX_PANEL = 40.0, 200.0
HOLE_PRESETS = {"tealight": 40.0, "puck": 60.0}
CLEARANCE = {"filament": 0.2, "resin": 0.1}
THICK = {"filament": (0.8, 3.0), "resin": (0.5, 2.8)}
PITCH = {"filament": 0.4, "resin": 0.25}
BED_MM = (220.0, 220.0)


def _box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return trimesh.creation.box(extents=hi - lo, transform=trimesh.transformations.translation_matrix((lo + hi) / 2))


def _cyl(r, z0, z1, x=0.0, y=0.0, axis="z"):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=48)
    c.apply_translation([0, 0, (z0 + z1) / 2])
    if axis == "x":
        c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    c.apply_translation([x, y, 0])
    return c


def _xcyl(r, x0, x1, y, z):
    """cylinder along x from x0 to x1, axis through (y, z)"""
    c = trimesh.creation.cylinder(radius=r, height=x1 - x0, sections=32)
    c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    c.apply_translation([(x0 + x1) / 2, y, z])
    return c


def _ycyl(r, y0, y1, x, z):
    c = trimesh.creation.cylinder(radius=r, height=y1 - y0, sections=32)
    c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    c.apply_translation([x, (y0 + y1) / 2, z])
    return c


def _diff(a, *cut):
    return trimesh.boolean.difference([a, *cut], engine="manifold")


def _union(*parts):
    return trimesh.boolean.union(list(parts), engine="manifold")


def _check(m, name):
    if not m.is_watertight or m.volume <= 0:
        raise ValueError(f"memory box: the {name} did not come out watertight")
    return m


def check_params(p: dict) -> dict:
    """Validate + normalise the options (raises ValueError with a plain message)."""
    q = dict(p)
    q["style"] = q.get("style") or "frame"
    if q["style"] not in STYLES:
        raise ValueError("style must be snap, frame or enclosed")
    q["material"] = q.get("material") or "filament"
    if q["material"] not in CLEARANCE:
        raise ValueError("material must be filament or resin")
    P = float(q.get("panel_mm", 80))
    if not (MIN_PANEL <= P <= MAX_PANEL):
        raise ValueError(f"panel size must be {MIN_PANEL:g}-{MAX_PANEL:g} mm")
    q["panel_mm"] = P
    c = q.get("clearance_mm")
    c = CLEARANCE[q["material"]] if c in (None, "") else float(c)
    if not (0.0 <= c <= 1.0):
        raise ValueError("fit clearance must be 0-1 mm")
    q["clearance_mm"] = c
    q["hole_shape"] = q.get("hole_shape") or "round"
    if q["hole_shape"] not in ("round", "square"):
        raise ValueError("light hole must be round or square")
    preset = q.get("hole_preset") or "tealight"
    if preset != "custom" and preset not in HOLE_PRESETS:
        raise ValueError("light hole preset must be tealight, puck or custom")
    d = HOLE_PRESETS.get(preset)
    q["hole_w"] = float(q.get("hole_w") or d or 40) if preset == "custom" else d
    q["hole_d"] = float(q.get("hole_d") or q["hole_w"]) if (preset == "custom" and q["hole_shape"] == "square") else q["hole_w"]
    inner = P - 2 * 10.0
    if not (5 <= q["hole_w"] <= inner and 5 <= q["hole_d"] <= inner):
        raise ValueError(f"light hole must be 5-{inner:g} mm for a {P:g} mm box (leave a 10 mm rim)")
    n = q.get("notch_mm")
    q["notch_mm"] = 0.0 if n in (None, "", 0, "0") else float(n)
    if not (0 <= q["notch_mm"] <= min(20.0, P / 3)):
        raise ValueError("cable notch must be 0-20 mm wide (0 = none)")
    q["lid"] = bool(q.get("lid", True))
    return q


def _square_image(im: Image.Image, w: float, h: float) -> Image.Image:
    return ImageOps.fit(im.convert("RGB"), (max(16, int(400 * w / h)), 400), Image.LANCZOS)


def _panel(im, w, h, q):
    """Flat lithophane w x h mm: x along the wall, y up the wall, z = thickness (flat back at z=0)."""
    tmin, tmax = THICK[q["material"]]
    res = int(np.clip(round(w / PITCH[q["material"]]), 60, 400))
    m = geometry.lithophane(_square_image(im, w, h), width_mm=w, min_thickness=tmin, max_thickness=tmax,
                            border_mm=2.0, resolution=res, shape="rect")
    v, f = m.solid()
    v = np.array(v, float)
    v -= v.min(0)
    sx, sy = w / max(v[:, 0].max(), 1e-9), h / max(v[:, 1].max(), 1e-9)
    v[:, 0] *= sx; v[:, 1] *= sy
    v[:, 1] = h - v[:, 1]                       # image top at the top of the wall
    f = f[:, ::-1]                              # the flip above mirrors; restore outward normals
    return _check(trimesh.Trimesh(v, f, process=True), "lithophane panel"), tmax


def _stand_up(panel, x0, y0, z0):
    """Lay the flat panel into the front wall: flat back facing outward (-y), image upright."""
    t = panel.copy()
    t.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))   # (x,y,z) -> (x,-z,y)
    t.apply_translation([x0, y0 - t.bounds[0][1], z0])
    return t


def _about_centre(m, k, P):
    r = trimesh.transformations.rotation_matrix(k * np.pi / 2, [0, 0, 1], point=[P / 2, P / 2, 0])
    t = m.copy(); t.apply_transform(r); return t


def _hole_and_notch(base, q, z0, z1):
    P = q["panel_mm"]
    if q["hole_shape"] == "round":
        cut = [_cyl(q["hole_w"] / 2, z0 - 1, z1 + 1, P / 2, P / 2)]
    else:
        cut = [_box([P / 2 - q["hole_w"] / 2, P / 2 - q["hole_d"] / 2, z0 - 1], [P / 2 + q["hole_w"] / 2, P / 2 + q["hole_d"] / 2, z1 + 1])]
    if q["notch_mm"]:                           # channel under the base from the hole out through the back edge
        n = q["notch_mm"]
        cut.append(_box([P / 2 - n / 2, P / 2, z0 - 1], [P / 2 + n / 2, P + 1, z0 + min(4.0, (z1 - z0) * 0.6)]))
    return _diff(base, *cut)


def build(images: list, params: dict):
    if len(images) != 4:
        raise ValueError("a memory box needs exactly 4 photos, one per side")
    q = check_params(params)
    P, c, st = q["panel_mm"], q["clearance_mm"], q["style"]
    parts, view = {}, {}                        # name -> mesh (print pose), name -> mesh (assembled pose)
    info = dict(style=st, panel_mm=P, clearance_mm=c, hole=[q["hole_shape"], q["hole_w"], q["hole_d"]], notch_mm=q["notch_mm"])

    if st == "frame":
        Bh, Rh, d, o = max(4.0, P * 0.05), max(4.0, P * 0.05), 2.5, 3.0
        T = THICK[q["material"]][1]
        g = T + 2 * c                           # groove width
        Lp = (P - 2 * (o + c)) - T - c          # pinwheel panels butt against their neighbour
        Hp = P - Bh - Rh + 2 * d - c
        groove = lambda z0, z1: _diff(_box([o, o, z0], [P - o, P - o, z1]), _box([o + g, o + g, z0 - 1], [P - o - g, P - o - g, z1 + 1]))
        base = _diff(_box([0, 0, 0], [P, P, Bh]), groove(Bh - d, Bh + 1))
        base = _check(_hole_and_notch(base, q, 0, Bh), "base")
        ring = _diff(_box([0, 0, 0], [P, P, Rh]), _box([o + g, o + g, -1], [P - o - g, P - o - g, Rh + 1]), groove(-1, d))
        ring = _check(ring, "top ring")
        parts["base"], parts["frame_top"] = base, ring
        view["base"] = base
        r = ring.copy(); r.apply_translation([0, 0, P - Rh]); view["frame_top"] = r
        info["groove_mm"] = round(g, 3)
        for k in range(4):
            pan, _ = _panel(images[k], Lp, Hp, q)
            parts[f"panel_{k + 1}"] = pan
            view[f"panel_{k + 1}"] = _about_centre(_stand_up(pan, o + c, o + c, Bh - d), k, P)
        info["panel_size_mm"] = [round(Lp, 2), round(Hp, 2)]

    elif st == "enclosed":
        Bh, lt, rw, gd, lip = max(3.0, P * 0.04), 2.0, 4.0, 2.5, 1.5
        T = THICK[q["material"]][1]
        Rh = lt + 2 * c + 2 * lip
        Ht = P - Rh                             # front/back lithophane wall top; rails above
        gz = Ht + lip                           # groove floor
        Lp = P - T
        base = _box([0, 0, 0], [P, P, Bh])
        walls = []
        tops = {0: Ht, 1: P, 2: Ht, 3: gz}      # front, right (stop), back, left (lid slides in over it)
        for k in range(4):
            h = tops[k] - (Bh - 0.4)
            pan, _ = _panel(images[k], Lp, h, q)
            walls.append(_about_centre(_stand_up(pan, 0, 0, Bh - 0.4), k, P))
        rails = []
        for k in (0, 2):
            rail = _diff(_box([0, 0, Ht - 0.4], [P, T + rw, P]), _box([-1, T + rw - gd, gz], [P + 1, T + rw + 1, gz + lt + 2 * c]))
            rails.append(_about_centre(rail, k, P))
        body = _union(base, *walls, *rails)
        body = _check(_hole_and_notch(body, q, 0, Bh), "box")
        span = P - 2 * (T + rw - gd)            # groove floor to groove floor
        lid = _check(_box([0, 0, 0], [P - T - c, span - 2 * c, lt]), "lid")
        parts["box"], parts["lid"] = body, lid
        view["box"] = body
        lv = lid.copy(); lv.apply_translation([0, T + rw - gd + c, gz + c]); view["lid"] = lv
        info.update(groove_mm=round(lt + 2 * c, 3), lid_mm=[round(P - T - c, 2), round(span - 2 * c, 2), lt])

    else:  # snap
        Bh, d, o, post = max(4.0, P * 0.05), 2.5, 3.0, 5.0
        T = THICK[q["material"]][1]
        Lp = (P - 2 * o) - 2 * post - c         # wall from its own corner post to the next panel's post (pinwheel)
        Hp = P - Bh + d - ((Bh - d) if q["lid"] else 0)   # lid rebate sits d over the panel tops
        pin_r, pin_l = 1.2, 2.0
        zs = [Hp * 0.25, Hp * 0.75]
        g = post + 2 * c
        base = _diff(_box([0, 0, 0], [P, P, Bh]),
                     _diff(_box([o - c, o - c, Bh - d], [P - o + c, P - o + c, Bh + 1]), _box([o + g, o + g, Bh - d - 1], [P - o - g, P - o - g, Bh + 2])))
        base = _check(_hole_and_notch(base, q, 0, Bh), "base")
        parts["base"] = base; view["base"] = base
        end = Lp + post
        for k in range(4):
            pan, _ = _panel(images[k], Lp, Hp, q)
            # local frame: x along the side, y inward, z up. Corner post at x,y 0..post; the wall runs to x=end.
            # Pins stick inward (+y) out of the post and enter the end of the previous panel (rotational symmetry).
            postm = _box([0, 0, 0], [post, post, Hp])
            wall = _stand_up(pan, post, 0, 0)
            strip = _box([end - pin_l - 1.5, 0, 0], [end, post, Hp])        # solid end that takes the neighbour's pins
            pins = [_ycyl(pin_r, post - 0.01, post + pin_l, post / 2, z) for z in zs]
            sock = [_xcyl(pin_r + c, end - pin_l - 0.4, end + 0.01, post / 2, z) for z in zs]
            piece = _diff(_union(postm, wall, strip, *pins), *sock)
            piece = _check(piece, f"snap panel {k + 1}")
            parts[f"panel_{k + 1}"] = piece
            v = piece.copy(); v.apply_translation([o, o, Bh - d]); view[f"panel_{k + 1}"] = _about_centre(v, k, P)
        if q["lid"]:
            lid = _diff(_box([0, 0, 0], [P, P, Bh]), _diff(_box([o - c, o - c, -1], [P - o + c, P - o + c, d]), _box([o + g, o + g, -2], [P - o - g, P - o - g, d + 1])))
            lid = _check(lid, "lid"); parts["lid"] = lid
            lv = lid.copy(); lv.apply_translation([0, 0, Bh - d + Hp - d]); view["lid"] = lv
        info.update(panel_size_mm=[round(Lp + post, 2), round(Hp, 2)], pins_per_joint=len(zs))

    # print layout: each part flat on the bed (largest face down), laid out in a row with 10 mm gaps
    pm, x, warn = Model(mode="memorybox"), 0.0, []
    for name, m in parts.items():
        t = m.copy()
        if name.startswith("panel") and st == "frame":
            pass                                # frame panels are already flat
        elif name.startswith("panel"):
            t.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
        t.apply_translation(-t.bounds[0] + [x, 0, 0])
        ext = t.extents
        if ext[0] > BED_MM[0] or ext[1] > BED_MM[1]:
            warn.append(f"{name} is {ext[0]:.0f} x {ext[1]:.0f} mm, larger than a {BED_MM[0]:.0f} x {BED_MM[1]:.0f} mm bed")
        pm.bodies.append(Body(name, np.asarray(t.vertices, float), np.asarray(t.faces, np.int64)))
        x += ext[0] + 10
    view_m = Model([Body(n, np.asarray(m.vertices, float), np.asarray(m.faces, np.int64)) for n, m in view.items()], "memorybox")
    info["parts"] = list(parts)
    info["warnings"] = warn
    pm.info = view_m.info = info
    return pm, view_m


def stl_zip(model: Model) -> bytes:
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for b in model.bodies:
            z.writestr(f"{b.name}.stl", trimesh.Trimesh(b.vertices, b.faces, process=False).export(file_type="stl"))
    return buf.getvalue()
