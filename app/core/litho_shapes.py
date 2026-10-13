"""Lithophane shapes: flat outlines (heart, circle, star, square) and curved shells (globe, night-light cover).

Same pipeline as the flat rectangle in geometry.lithophane: photo -> grayscale -> tone -> thickness map
(bright = thin, dark = thick, between min_thickness and max_thickness).

* Flat shapes: the thickness map is clipped to the outline (cell mask), an optional solid rim (border_mm, full
  max_thickness) runs round the inside of the outline, and the result is ONE watertight mesh lying on the bed.
* Curved shapes stand upright (axis = Z) on the bed: the map is wrapped all the way round, so there is no seam gap.
  The inner wall is smooth (fits the light), the outer wall carries the picture, solid rings close the top and bottom.
  - nightlight: a straight cylinder sleeve; diameter_mm is the INSIDE diameter of the light it slips over.
  - globe: a FULL sphere, photo wrapped equirectangularly (360 x 180), hollow, open at the bottom (edge at 45 deg S)
    over a flat foot ring so a light goes in and it prints without supports.
  - cup: "Cylinder / Cup" - the photo round a cylinder wall, solid 2 mm printed bottom, open top (pen holder / cup).
* Flat outlines are smooth vector curves (analytic circle/heart/star/square, 640 points), not pixel masks.

color_mode hook: only "mono" exists. thickness_map() is the single place a future colour mode would plug in
(e.g. return per-channel maps / extra bodies); everything downstream takes the map it returns.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from . import thumbnail

FLAT_SHAPES = ("heart", "circle", "star", "square")
CURVED_SHAPES = ("globe", "nightlight", "cup")
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


# ------------------------------------------------------------------ outlines: smooth vector curves
N_OUTLINE = 640                  # boundary samples (divisible by 8 and 10: square corners and star points are exact)


def _ray_hit(poly, ang):
    """Distance from the origin to a closed polygon along each ray angle (polygon must be star-shaped about 0)."""
    d = np.stack([np.cos(ang), np.sin(ang)], -1)                # (A,2)
    p0 = poly; p1 = np.roll(poly, -1, 0); e = p1 - p0           # (S,2)
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (p0[None, :, 0] * e[None, :, 1] - p0[None, :, 1] * e[None, :, 0]) / den
        u = (p0[None, :, 0] * d[:, None, 1] - p0[None, :, 1] * d[:, None, 0]) / den
    ok = (t > 0) & (u >= -1e-9) & (u <= 1 + 1e-9) & np.isfinite(t)
    return np.where(ok, t, np.inf).min(1)


def outline_radius(shape: str, ang: np.ndarray) -> np.ndarray:
    """Exact outline as r(angle) about the centre, in a -1..1 box (y up). Analytic for every shape."""
    if shape == "circle":
        return np.ones_like(ang)
    if shape == "square":
        return 1.0 / np.maximum(np.abs(np.cos(ang)), np.abs(np.sin(ang)))
    if shape == "star":                                         # 5 points, straight edges, one point up
        k, ro, ri = 5, 1.0, 0.45
        a = np.arange(2 * k) * np.pi / k + np.pi / 2
        rr = np.where(np.arange(2 * k) % 2 == 0, ro, ri)
        return _ray_hit(np.stack([rr * np.cos(a), rr * np.sin(a)], -1), ang)
    if shape == "heart":
        return _ray_hit(heart_curve(), ang)
    raise ValueError(f"unknown flat shape {shape!r}")


def heart_curve(n=4096):
    """Classic parametric heart (x=16 sin^3 t, y=13cos t-5cos2t-2cos3t-cos4t), centred and scaled into -1..1."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    x = x / 17.0; y = (y + 2.5) / 17.0 * 1.15
    s = 1.0 / max(np.abs(x).max(), np.abs(y).max())
    return np.stack([x * s, y * s], -1)


def outline(shape: str, n: int = N_OUTLINE) -> np.ndarray:
    """(n,2) smooth outline polygon in the -1..1 box, counter-clockwise."""
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = outline_radius(shape, ang)
    return np.stack([r * np.cos(ang), r * np.sin(ang)], -1)


def outline_mask(shape: str, n: int) -> np.ndarray:
    """Boolean (n, n) cell mask, row 0 = top (kept for previews; the mesh uses the vector outline)."""
    from matplotlib.path import Path
    c = (np.arange(n) + 0.5) / n
    x, y = np.meshgrid(c * 2 - 1, 1 - c * 2)
    return Path(outline(shape)).contains_points(np.stack([x.ravel(), y.ravel()], -1), radius=1e-9).reshape(n, n)


def _bilinear(img, u, v):
    """Sample a (H,W) map at fractional pixel coords u (col) v (row)."""
    H, W = img.shape
    u = np.clip(u, 0, W - 1); v = np.clip(v, 0, H - 1)
    u0 = np.minimum(np.floor(u).astype(int), W - 2); v0 = np.minimum(np.floor(v).astype(int), H - 2)
    fu, fv = u - u0, v - v0
    return (img[v0, u0] * (1 - fu) * (1 - fv) + img[v0, u0 + 1] * fu * (1 - fv)
            + img[v0 + 1, u0] * (1 - fu) * fv + img[v0 + 1, u0 + 1] * fu * fv)


def flat_shape(im, shape, width_mm=100.0, min_thickness=0.8, max_thickness=3.0, border_mm=3.0,
               resolution=200, smooth=0.8, gamma=1.0, auto_contrast=True, invert=False, color_mode="mono"):
    """Polar mesh inside the vector outline: rings scaled from the centre to the exact (smooth) edge, so the
    outer wall and rim follow the curve with no pixel steps. One watertight solid on z=0."""
    from scipy.spatial import cKDTree
    n = int(np.clip(resolution, 32, MAX_SIDE))
    half = width_mm / 2
    pitch = width_mm / n
    thick_img = thickness_map(im, n + 1, n + 1, min_thickness, max_thickness, smooth, gamma, auto_contrast, invert, color_mode)
    A = N_OUTLINE
    ang = np.linspace(0, 2 * np.pi, A, endpoint=False)
    edge = np.stack([np.cos(ang), np.sin(ang)], -1) * outline_radius(shape, ang)[:, None] * half   # (A,2) mm
    M = max(8, int(np.ceil(half / pitch)))                     # rings
    s = np.linspace(0, 1, M + 1)[1:]
    if border_mm > 0:                                          # a ring exactly at the inner edge of the rim
        s = np.unique(np.concatenate([s, np.clip(1 - border_mm / np.linalg.norm(edge, axis=1).min(), 0.02, 0.98)[None]]))
    ring = s[:, None, None] * edge[None]                       # (M,A,2)
    xy = np.vstack([[[0.0, 0.0]], ring.reshape(-1, 2)])
    # thickness: bilinear from the map (image covers the -half..half box), rim = full thickness
    u = (xy[:, 0] + half) / width_mm * n; v = (half - xy[:, 1]) / width_mm * n
    z = _bilinear(thick_img, u, v)
    rim_cells = 0
    if border_mm > 0:
        dense = outline(shape, 8192) * half
        dist = cKDTree(dense).query(xy)[0]
        w = np.clip((dist - border_mm) / max(pitch, 0.5), 0, 1)        # smooth ramp, no stepped rim line
        z = max_thickness + (z - max_thickness) * w
        z[1 + (len(s) - 1) * A:] = max_thickness
        rim_cells = max(1, int(round(border_mm / pitch)))
    nv = len(xy)
    idx = 1 + np.arange(len(s) * A).reshape(len(s), A)
    nxt = np.roll(idx, -1, 1)
    fan = np.stack([np.zeros(A, int), idx[0], nxt[0]], -1)
    q = [np.stack([idx[:-1], idx[1:], nxt[1:]], -1).reshape(-1, 3), np.stack([idx[:-1], nxt[1:], nxt[:-1]], -1).reshape(-1, 3)]
    top = np.vstack([fan] + q)
    bot = (top + nv)[:, ::-1]
    o, on = idx[-1], nxt[-1]
    wall = np.vstack([np.stack([o, o + nv, on + nv], -1), np.stack([o, on + nv, on], -1)])
    faces = np.vstack([top, bot, wall]).astype(np.int64)
    verts = np.vstack([np.column_stack([xy + half, z]), np.column_stack([xy + half, np.zeros(nv)])])
    mask = outline_mask(shape, n)
    shown = np.where(np.pad(mask, ((0, 1), (0, 1)), mode="edge"), thick_img, np.nan)
    return verts, faces, dict(pixels=[n, n], pitch_mm=round(pitch, 4), border_cells=rim_cells,
                              outline_points=A), shown


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


def _closed_cup(outer, inner, pole_o, pole_i):
    """Watertight solid from two (R,C,3) grids ordered pole -> open rim. Columns wrap (no seam); row 0 of each grid
    is fanned to its pole vertex; the last rows are joined by a flat ring (the rim / the base ring)."""
    R, C = outer.shape[:2]
    n = R * C + 1
    verts = np.vstack([outer.reshape(-1, 3), [pole_o], inner.reshape(-1, 3), [pole_i]])
    idx = np.arange(R * C).reshape(R, C); nx = np.roll(idx, -1, 1)
    q = np.vstack([np.stack([idx[:-1], idx[1:], nx[1:]], -1).reshape(-1, 3),
                   np.stack([idx[:-1], nx[1:], nx[:-1]], -1).reshape(-1, 3)])
    fan = np.stack([np.full(C, R * C), idx[0], nx[0]], -1)
    o_f = np.vstack([q, fan])
    i_f = (o_f + n)[:, ::-1]
    l0, l1 = idx[-1], nx[-1]
    ring = np.vstack([np.stack([l0, l0 + n, l1 + n], -1), np.stack([l0, l1 + n, l1], -1)])
    faces = np.vstack([o_f, i_f, ring]).astype(np.int64)
    tri = verts[faces]
    if np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() < 0:
        faces = faces[:, ::-1]
    return verts, faces


GLOBE_OPENING_DEG = 45.0         # bottom opening edge at 45 deg south: light goes in, overhang stays <= 45 deg
GLOBE_BASE_MM = 3.0              # flat foot ring under the opening
CUP_BOTTOM_MM = 2.0


def curved_shape(im, shape, diameter_mm=40.0, height_mm=60.0, min_thickness=0.8, max_thickness=3.0,
                 border_mm=3.0, resolution=200, smooth=0.8, gamma=1.0, auto_contrast=True, invert=False,
                 color_mode="mono"):
    scale = min(1.0, resolution / 200.0) if resolution else 1.0
    tmap = lambda c, r: thickness_map(im, c, r, min_thickness, max_thickness, smooth, gamma, auto_contrast,
                                      invert, color_mode)
    if shape == "globe":
        # full sphere, equirectangular: image columns = longitude (360), rows = latitude (+90 top .. -90 bottom)
        r_in = diameter_mm / 2
        C = int(np.clip(2 * np.pi * r_in / TARGET_PITCH * scale, 64, 1200))
        Rf = max(16, C // 2)
        eq = tmap(C, Rf)                                      # (Rf, C), 2:1 crop
        lat_lo = -np.radians(GLOBE_OPENING_DEG)
        nrow = int(np.clip(round(Rf * (np.pi / 2 - lat_lo) / np.pi), 8, MAX_SIDE))
        lat = np.linspace(np.pi / 2, lat_lo, nrow + 1)[1:]   # rows below the pole down to the opening
        th = -np.linspace(0, 2 * np.pi, C, endpoint=False)   # reads correctly from outside
        cols = np.arange(C)
        vrow = (np.pi / 2 - lat) / np.pi * (Rf - 1)
        t = _bilinear(eq, cols[None].repeat(nrow, 0).astype(float), vrow[:, None].repeat(C, 1))
        nrm = np.stack([np.cos(lat)[:, None] * np.cos(th)[None], np.cos(lat)[:, None] * np.sin(th)[None],
                        np.sin(lat)[:, None].repeat(C, 1)], -1)
        inner = nrm * r_in; outer = nrm * (r_in + t[..., None])
        # flat foot: vertical skirt from the opening edge straight down, solid max_thickness, ending flat
        z0 = inner[-1, 0, 2] - GLOBE_BASE_MM
        rc = r_in * np.cos(lat_lo)
        ring_dir = np.stack([np.cos(th), np.sin(th), np.zeros(C)], -1)
        sk_i = np.stack([ring_dir * rc + [0, 0, z0]])
        sk_o = np.stack([ring_dir * (rc + max_thickness) + [0, 0, z0]])
        inner = np.concatenate([inner, sk_i]); outer = np.concatenate([outer, sk_o])
        pole_t = float(eq[0].mean())
        v, f = _closed_cup(outer, inner, [0, 0, r_in + pole_t], [0, 0, r_in])
        info = dict(pixels=[C, Rf], pitch_mm=round(2 * np.pi * r_in / C, 4), inner_diameter_mm=round(2 * r_in, 2),
                    opening_diameter_mm=round(2 * rc, 1), mapping="equirectangular")
        shown = eq
    else:                                                     # nightlight sleeve / cup with a solid bottom
        ring = max(RIM_RING_MM, border_mm) if border_mm > 0 else 0.0
        cup = shape == "cup"
        r_in = diameter_mm / 2 + (0 if cup else CLEARANCE_MM / 2)
        circ = 2 * np.pi * r_in
        z_lo = CUP_BOTTOM_MM if cup else 0.0
        length = height_mm - z_lo
        C = int(np.clip(circ / TARGET_PITCH * scale, 48, 1200))
        Rr = int(np.clip(length / TARGET_PITCH * scale, 8, MAX_SIDE)) + 1
        ring_rows = int(round(ring / (length / (Rr - 1)))) if ring > 0 else 0
        pic_rows = max(4, Rr - 2 * ring_rows)
        pic = tmap(C, pic_rows)[::-1]                         # row 0 = bottom of the print
        thick = np.full((pic_rows + 2 * ring_rows, C), float(max_thickness))
        thick[ring_rows:ring_rows + pic_rows] = pic
        Rr = thick.shape[0]
        th = -np.linspace(0, 2 * np.pi, C, endpoint=False)
        d = np.stack([np.cos(th), np.sin(th), np.zeros(C)], -1)[None]
        z = np.linspace(z_lo, height_mm, Rr)[:, None, None] * np.array([0, 0, 1.0])
        inner = d * r_in + z; outer = d * (r_in + thick[..., None]) + z
        if cup:                                               # bottom: outer goes down to z=0 and fans to the centre
            outer = np.concatenate([d * (r_in + max_thickness), outer])
            inner = np.concatenate([d * (r_in - 0.5) + [0, 0, z_lo], inner])     # tiny inner fillet ring
            v, f = _closed_cup(outer, inner, [0, 0, 0], [0, 0, z_lo])
        else:
            v, f = _shell(inner, d.repeat(Rr, 0), thick)
        info = dict(pixels=[C, pic_rows], pitch_mm=round(circ / C, 4), inner_diameter_mm=round(2 * r_in, 2))
        if cup:
            info["bottom_mm"] = CUP_BOTTOM_MM
        shown = thick[::-1]
    v[:, 2] -= v[:, 2].min()                                  # stand it on the bed
    return v, f, info, shown


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
