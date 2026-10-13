"""Lithophane shapes: flat outlines (heart, circle, star, square) and curved shells (globe, night-light cover).

Same pipeline as the flat rectangle in geometry.lithophane: photo -> grayscale -> tone -> thickness map
(bright = thin, dark = thick, between min_thickness and max_thickness).

* Flat shapes: the thickness map is clipped to the outline (cell mask), an optional solid rim (border_mm, full
  max_thickness) runs round the inside of the outline, and the result is ONE watertight mesh lying on the bed.
* Curved shapes stand upright (axis = Z) on the bed: the map is wrapped all the way round, so there is no seam gap.
  The inner wall is smooth (fits the light), the outer wall carries the picture, solid rings close the top and bottom.
  - nightlight: a straight cylinder sleeve; diameter_mm is the INSIDE diameter of the light it slips over.
  - globe: a band of a sphere between +-lat (max 40 deg, so overhangs stay under 45 deg on a K1 without supports).

color_mode hook: only "mono" exists. thickness_map() is the single place a future colour mode would plug in
(e.g. return per-channel maps / extra bodies); everything downstream takes the map it returns.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from . import thumbnail

FLAT_SHAPES = ("heart", "circle", "star", "square")
CURVED_SHAPES = ("globe", "nightlight")
SHAPES = ("rect",) + FLAT_SHAPES + CURVED_SHAPES
COLOR_MODES = ("mono",)          # future: "cmyk" etc. - not built yet
CLEARANCE_MM = 1.0               # night-light: inside diameter = light diameter + clearance
RIM_RING_MM = 2.0                # curved shapes: solid band at the top and bottom edge
GLOBE_MAX_LAT = 40.0
TARGET_PITCH = 0.35              # mm per map pixel (matches a 0.4 mm nozzle)
MAX_SIDE = 600


def thickness_map(im: Image.Image, nx: int, ny: int, min_thickness, max_thickness, smooth=0.8, gamma=1.0,
                  auto_contrast=True, invert=False, color_mode="mono"):
    """(ny, nx) thickness in mm, bright = thin. The picture is centre-cropped to nx:ny first."""
    from .geometry import _luma, _tone
    if color_mode not in COLOR_MODES:
        raise ValueError(f"color_mode {color_mode!r} is not available yet")
    if max_thickness <= min_thickness:
        raise ValueError("max_thickness must be greater than min_thickness")
    small = ImageOps.fit(im, (int(nx), int(ny)), Image.LANCZOS)
    g = _tone(_luma(np.asarray(small, np.float64)), auto_contrast, gamma, smooth)
    if invert:
        g = 1 - g
    return max_thickness - (max_thickness - min_thickness) * g


# ------------------------------------------------------------------ outlines (unit square, y up, 0..1)
def outline_mask(shape: str, n: int) -> np.ndarray:
    """Boolean (n, n) cell mask, row 0 = top."""
    c = (np.arange(n) + 0.5) / n
    x, y = np.meshgrid(c * 2 - 1, 1 - c * 2)            # -1..1, y up
    if shape == "square":
        return np.ones((n, n), bool)
    if shape == "circle":
        return x * x + y * y <= 1.0
    if shape == "heart":
        X, Y = x * 1.25, y * 1.25 + 0.2                    # classic implicit heart, scaled to fill the square
        return (X * X + Y * Y - 1) ** 3 - X * X * Y ** 3 <= 0
    if shape == "star":
        r = np.hypot(x, y)
        a = np.arctan2(y, x) - np.pi / 2                  # one point straight up
        k = 5
        ro, ri = 1.0, 0.45
        seg = np.mod(a, 2 * np.pi / k) - np.pi / k        # -pi/k..pi/k from a point
        # straight edge between point (ro at 0) and inner vertex (ri at pi/k)
        th = np.abs(seg)
        p1 = np.array([ro, 0.0]); p2 = np.array([ri * np.cos(np.pi / k), ri * np.sin(np.pi / k)])
        # polar line through p1,p2: r(th) = d / cos(th - phi)
        nrm = np.array([p2[1] - p1[1], -(p2[0] - p1[0])]); nrm /= np.linalg.norm(nrm)
        d = abs(float(nrm @ p1)); phi = np.arctan2(nrm[1], nrm[0])
        if float(nrm @ p1) < 0:
            phi += np.pi
        return r <= d / np.cos(th - phi)
    raise ValueError(f"unknown flat shape {shape!r}")


def _fix(mask):
    from .geometry import fix_checkers
    from scipy import ndimage
    lab, n = ndimage.label(mask)
    if n > 1:                                           # keep the biggest piece: one mesh
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        mask = lab == (1 + int(np.argmax(sizes)))
    return fix_checkers(mask)


def masked_heightfield(mask: np.ndarray, ztop: np.ndarray, pitch: float):
    """Watertight solid over a cell mask (H,W): top surface at node heights ztop (H+1,W+1), flat bottom at z=0."""
    H, W = mask.shape
    stride = W + 1
    nv = (H + 1) * stride
    r, c = np.nonzero(mask)
    TL = r * stride + c; TR = TL + 1; BL = TL + stride; BR = BL + 1
    top = np.concatenate([np.stack([BL, BR, TR], -1), np.stack([BL, TR, TL], -1)])
    bot = (top + nv)[:, ::-1]
    p = np.pad(mask, 1); pr, pc = r + 1, c + 1
    walls = []
    for empty, u, v in ((~p[pr + 1, pc], BL, BR), (~p[pr, pc + 1], BR, TR),
                        (~p[pr - 1, pc], TR, TL), (~p[pr, pc - 1], TL, BL)):
        uu, vv = u[empty], v[empty]
        walls.append(np.stack([vv, uu, uu + nv], -1))
        walls.append(np.stack([vv, uu + nv, vv + nv], -1))
    faces = np.vstack([top, bot] + walls)
    used = np.unique(faces)
    remap = np.full(2 * nv, -1, np.int64); remap[used] = np.arange(len(used))
    gi = used % nv; gr, gc = gi // stride, gi % stride
    z = np.where(used < nv, ztop.reshape(-1)[gi], 0.0)
    verts = np.stack([gc * pitch, (H - gr) * pitch, z], -1).astype(np.float64)
    return verts, remap[faces]


def flat_shape(im, shape, width_mm=100.0, min_thickness=0.8, max_thickness=3.0, border_mm=3.0,
               resolution=200, smooth=0.8, gamma=1.0, auto_contrast=True, invert=False, color_mode="mono"):
    n = int(np.clip(resolution, 32, MAX_SIDE))
    pitch = width_mm / n
    thick = thickness_map(im, n + 1, n + 1, min_thickness, max_thickness, smooth, gamma, auto_contrast, invert, color_mode)
    mask = _fix(outline_mask(shape, n))
    rim_cells = 0
    if border_mm > 0:
        from scipy import ndimage
        rim_cells = max(1, int(round(border_mm / pitch)))
        dist = ndimage.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1]
        rim = mask & (dist <= rim_cells)
        # a node is solid-rim if any cell touching it is rim
        rn = np.zeros((n + 1, n + 1), bool)
        for dr in (0, 1):
            for dc in (0, 1):
                rn[dr:dr + n, dc:dc + n] |= rim
        thick = np.where(rn, max_thickness, thick)
    v, f = masked_heightfield(mask, thick, pitch)
    shown = np.where(np.pad(mask, ((0, 1), (0, 1))), thick, np.nan)
    return v, f, dict(pixels=[n, n], pitch_mm=round(pitch, 4), border_cells=rim_cells), shown


# ------------------------------------------------------------------ curved shells
def _shell(inner: np.ndarray, normal: np.ndarray, thick: np.ndarray):
    """Closed shell from a periodic (rows, cols) surface: inner points + outward normals, outer = inner + n*thick.
    Columns wrap round (no seam); row 0 and the last row are closed by rings joining inner and outer."""
    R, C = thick.shape
    outer = inner + normal * thick[..., None]
    n = R * C
    verts = np.vstack([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    idx = np.arange(n).reshape(R, C)
    a = idx[:-1]; b = np.roll(idx, -1, 1)[:-1]; d = idx[1:]; c = np.roll(idx, -1, 1)[1:]
    out_f = np.vstack([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    in_f = (out_f + n)[:, ::-1]
    t0, t1 = idx[0], np.roll(idx[0], -1)
    l0, l1 = idx[-1], np.roll(idx[-1], -1)
    caps = np.vstack([np.stack([t1, t0, t0 + n], -1), np.stack([t1, t0 + n, t1 + n], -1),
                      np.stack([l0, l1, l1 + n], -1), np.stack([l0, l1 + n, l0 + n], -1)])
    faces = np.vstack([out_f, in_f, caps]).astype(np.int64)
    # orient outward whatever the parametrisation handedness
    tri = verts[faces]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()
    if vol < 0:
        faces = faces[:, ::-1]
    return verts, faces


def curved_shape(im, shape, diameter_mm=40.0, height_mm=60.0, min_thickness=0.8, max_thickness=3.0,
                 border_mm=3.0, resolution=200, smooth=0.8, gamma=1.0, auto_contrast=True, invert=False,
                 color_mode="mono"):
    ring = max(RIM_RING_MM, border_mm) if border_mm > 0 else 0.0
    if shape == "nightlight":
        r_in = diameter_mm / 2 + CLEARANCE_MM / 2
        circ, length = 2 * np.pi * r_in, height_mm
    else:                                            # globe band
        r_in = diameter_mm / 2
        lat = np.radians(min(GLOBE_MAX_LAT, np.degrees(np.arcsin(min(1.0, height_mm / diameter_mm)))))
        circ, length = 2 * np.pi * r_in, 2 * lat * r_in
    scale = min(1.0, resolution / 200.0) if resolution else 1.0
    C = int(np.clip(circ / TARGET_PITCH * scale, 48, 1200))
    Rr = int(np.clip(length / TARGET_PITCH * scale, 8, MAX_SIDE)) + 1
    ring_rows = int(round(ring / (length / (Rr - 1)))) if ring > 0 else 0
    pic_rows = max(4, Rr - 2 * ring_rows)
    pic = thickness_map(im, C, pic_rows, min_thickness, max_thickness, smooth, gamma, auto_contrast, invert, color_mode)
    pic = pic[::-1]                                   # row 0 = bottom of the print
    thick = np.full((pic_rows + 2 * ring_rows, C), float(max_thickness))
    thick[ring_rows:ring_rows + pic_rows] = pic
    Rr = thick.shape[0]
    th = np.linspace(0, 2 * np.pi, C, endpoint=False)
    # image runs left->right going clockwise seen from outside-front: flip so it reads correctly from outside
    th = -th
    if shape == "nightlight":
        z = np.linspace(0, length, Rr)
        inner = np.stack([r_in * np.cos(th)[None].repeat(Rr, 0), r_in * np.sin(th)[None].repeat(Rr, 0),
                          z[:, None].repeat(C, 1)], -1)
        normal = np.stack([np.cos(th)[None].repeat(Rr, 0), np.sin(th)[None].repeat(Rr, 0), np.zeros((Rr, C))], -1)
    else:
        phi = np.linspace(-lat, lat, Rr)
        cp, sp = np.cos(phi)[:, None], np.sin(phi)[:, None]
        normal = np.stack([cp * np.cos(th)[None], cp * np.sin(th)[None], sp.repeat(C, 1)], -1)
        inner = normal * r_in
    v, f = _shell(inner, normal, thick)
    v[:, 2] -= v[:, 2].min()                           # stand it on the bed
    info = dict(pixels=[C, pic_rows], pitch_mm=round(circ / C, 4), inner_diameter_mm=round(2 * r_in, 2))
    if shape == "globe":
        info["band_deg"] = round(float(np.degrees(lat)), 1)
    return v, f, info, thick[::-1]


def build(im, shape, **params):
    """Returns (vertices, faces, info, thickness map for the preview thumb)."""
    if shape in FLAT_SHAPES:
        keys = ("width_mm", "min_thickness", "max_thickness", "border_mm", "resolution", "smooth", "gamma",
                "auto_contrast", "invert", "color_mode")
        return flat_shape(im, shape, **{k: params[k] for k in keys if k in params})
    if shape in CURVED_SHAPES:
        keys = ("diameter_mm", "height_mm", "min_thickness", "max_thickness", "border_mm", "resolution", "smooth",
                "gamma", "auto_contrast", "invert", "color_mode")
        return curved_shape(im, shape, **{k: params[k] for k in keys if k in params})
    raise ValueError(f"unknown shape {shape!r}")


def thumb(thick, tmin, tmax):
    img = thumbnail.lithophane_backlit(np.nan_to_num(thick, nan=tmax * 3), tmin, tmax)
    return img
