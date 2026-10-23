"""Lithophane shapes: flat outlines (heart, circle, star, square, hexagon, diamond) and curved shells (globe, night-light cover).

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
* Flat outlines are smooth vector curves (analytic circle/heart/star/square/hexagon/diamond, 640 points), not pixel masks.

color_mode hook: only "mono" exists. thickness_map() is the single place a future colour mode would plug in
(e.g. return per-channel maps / extra bodies); everything downstream takes the map it returns.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from . import thumbnail

FLAT_SHAPES = ("heart", "circle", "star", "square", "hexagon", "diamond")
CURVED_SHAPES = ("globe", "nightlight", "cup")
PANEL_SHAPES = ("curve",)        # adjustable curved panel: flat (0 deg) .. half circle (180 deg), see curved_panel()
SHAPES = ("rect",) + FLAT_SHAPES + CURVED_SHAPES + PANEL_SHAPES
COLOR_MODES = ("mono",)          # future: "cmyk" etc. - not built yet
CLEARANCE_MM = 1.0               # night-light: inside diameter = light diameter + clearance
RIM_RING_MM = 2.0                # curved shapes: solid band at the top and bottom edge
GLOBE_MAX_LAT = 40.0
TARGET_PITCH = 0.35              # mm per map pixel (matches a 0.4 mm nozzle)
MAX_SIDE = 600


PLACE_LIMITS = dict(x=(-1.0, 1.0), y=(-1.0, 1.0), scale=(0.1, 8.0))


def check_place(place):
    """Validate an image placement {x, y, scale, rotation}. x/y: offset of the photo centre as a fraction of the
    shape box width/height (+x right, +y down); scale: 1 = fill (today's centre crop), rotation: degrees clockwise.
    Returns a clean dict, or None when it is the identity (so the default output stays byte-identical)."""
    if not place:
        return None
    import math
    out = {}
    for k, d in (("x", 0.0), ("y", 0.0), ("scale", 1.0), ("rotation", 0.0)):
        try:
            v = float(place.get(k, d))
        except (TypeError, ValueError):
            raise ValueError(f"placement {k} must be a number")
        if not math.isfinite(v):
            raise ValueError(f"placement {k} must be a finite number")
        if k in PLACE_LIMITS:
            lo, hi = PLACE_LIMITS[k]
            if not lo <= v <= hi:
                raise ValueError(f"placement {k} must be {lo:g}..{hi:g}")
        else:
            if abs(v) > 3600:
                raise ValueError("placement rotation must be -3600..3600 degrees")
            v = v % 360.0
        out[k] = v
    if out["x"] == 0 and out["y"] == 0 and out["scale"] == 1 and out["rotation"] == 0:
        return None
    return out


def place_image(im: Image.Image, nx: int, ny: int, place, wrap=False) -> Image.Image:
    """Render the photo into an nx x ny box with the user's move / zoom / rotate. Empty area = white (thinnest).
    wrap=True (globe / cup / night-light): the box goes all the way round, so x slides the photo round the wrap
    (no gap at the seam) instead of off the edge."""
    nx, ny = int(nx), int(ny)
    if wrap and place["x"]:
        a = np.asarray(place_image(im, nx, ny, {**place, "x": 0.0}))
        return Image.fromarray(np.roll(a, int(round(place["x"] * nx)), axis=1))
    base = max(nx / im.width, ny / im.height)                  # scale 1 == ImageOps.fit cover
    k = base * place["scale"]
    w, h = max(1, round(im.width * k)), max(1, round(im.height * k))
    small = im.convert("RGB").resize((w, h), Image.LANCZOS)
    if place["rotation"]:
        small = small.rotate(-place["rotation"], resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    canvas = Image.new("RGB", (nx, ny), (255, 255, 255))
    cx = nx / 2 + place["x"] * nx; cy = ny / 2 + place["y"] * ny
    canvas.paste(small, (int(round(cx - small.width / 2)), int(round(cy - small.height / 2))))
    return canvas


def thickness_map(im: Image.Image, nx: int, ny: int, min_thickness, max_thickness, smooth=0.8, gamma=1.0,
                  auto_contrast=True, invert=False, color_mode="mono", place=None, wrap=False):
    """(ny, nx) thickness in mm, bright = thin. The picture is centre-cropped to nx:ny first (or placed by `place`)."""
    from .geometry import _luma, _tone
    if color_mode not in COLOR_MODES:
        raise ValueError(f"color_mode {color_mode!r} is not available yet")
    if max_thickness <= min_thickness:
        raise ValueError("max_thickness must be greater than min_thickness")
    small = place_image(im, nx, ny, place, wrap) if place else ImageOps.fit(im, (int(nx), int(ny)), Image.LANCZOS)
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
    if shape == "hexagon":
        # regular hexagon, pointy top, vertices on the unit circle
        a = np.arange(6) * np.pi / 3 + np.pi / 6
        return _ray_hit(np.stack([np.cos(a), np.sin(a)], -1), ang)
    if shape == "diamond":
        # diamond (square rotated 45 deg), pointy top
        a = np.array([np.pi/2, np.pi, 3*np.pi/2, 0.0])
        return _ray_hit(np.stack([np.cos(a), np.sin(a)], -1), ang)
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
               resolution=200, smooth=0.8, gamma=1.0, auto_contrast=True, invert=False, color_mode="mono", place=None):
    """Polar mesh inside the vector outline: rings scaled from the centre to the exact (smooth) edge, so the
    outer wall and rim follow the curve with no pixel steps. One watertight solid on z=0."""
    from scipy.spatial import cKDTree
    n = int(np.clip(resolution, 32, MAX_SIDE))
    half = width_mm / 2
    pitch = width_mm / n
    thick_img = thickness_map(im, n + 1, n + 1, min_thickness, max_thickness, smooth, gamma, auto_contrast, invert, color_mode, place)
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
                 color_mode="mono", place=None, lip_mm=None, lip_taper="none", taper_deg=45.0):
    scale = min(1.0, resolution / 200.0) if resolution else 1.0
    tmap = lambda c, r: thickness_map(im, c, r, min_thickness, max_thickness, smooth, gamma, auto_contrast,
                                      invert, color_mode, place, wrap=True)
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
        if lip_mm is None:                                    # older builds: the band follows the border setting
            ring = max(RIM_RING_MM, border_mm) if border_mm > 0 else 0.0
        else:                                                 # lip_mm = how far the band reaches out past the wall
            ring = (max(RIM_RING_MM, border_mm) if border_mm > 0 else RIM_RING_MM) if float(lip_mm) > 0 else 0.0
        lip_w = float(lip_mm) if lip_mm is not None else 0.0
        band_t = max_thickness + lip_w                        # full thickness of the band
        lip_taper = check_lip(lip_w if lip_mm is not None else 0, lip_taper, taper_deg)[1] if (ring > 0 and lip_mm is not None) else "none"
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
        thick = np.full((pic_rows + 2 * ring_rows, C), float(band_t))
        thick[ring_rows:ring_rows + pic_rows] = pic
        Rr = thick.shape[0]
        th = -np.linspace(0, 2 * np.pi, C, endpoint=False)
        d = np.stack([np.cos(th), np.sin(th), np.zeros(C)], -1)[None]
        zs = np.linspace(z_lo, height_mm, Rr)
        inset = np.zeros(Rr)                                  # how far the band reaches inside the inner wall (mm)
        if ring > 0 and lip_taper != "none":
            # the band meets the picture on a slope, not a flat step: at most taper_deg from vertical, so the
            # printer builds each layer on the one below and no supports are needed
            delta = band_t - min_thickness
            ramp = delta / (0.8 * np.tan(np.radians(taper_deg)))   # 20% spare: the picture's own slope adds on top
            zr = zs - z_lo
            from_band = np.minimum(np.maximum(zr - ring_rows * length / (Rr - 1), 0),
                                   np.maximum((length - zr) - ring_rows * length / (Rr - 1), 0))
            b = np.clip(1.0 - from_band / max(ramp, 1e-6), 0.0, 1.0)   # 1 in the band, slope down to 0
            out_k, in_k = {"outward": (1.0, 0.0), "inward": (0.0, 1.0), "both": (0.5, 0.5)}[lip_taper]
            pic_part = thick.copy()                           # the band rows take the picture's edge row
            if ring_rows:
                pic_part[:ring_rows] = pic_part[ring_rows]
                pic_part[Rr - ring_rows:] = pic_part[Rr - ring_rows - 1]
            inset = b * delta * in_k
            thick = pic_part + b[:, None] * (band_t - pic_part) * out_k + inset[:, None]   # blend to full
            thick = np.maximum(thick, np.where(b[:, None] >= 1.0, band_t, 0.0))
        z = zs[:, None, None] * np.array([0, 0, 1.0])
        inner = d * (r_in - inset[:, None, None]) + z; outer = inner + d * thick[..., None]
        if cup:                                               # bottom: outer goes down to z=0 and fans to the centre
            outer = np.concatenate([outer[:1] * [1, 1, 0], outer])                      # straight down to the bed
            inner = np.concatenate([d * (r_in - inset[0] - 0.5) + [0, 0, z_lo], inner])     # tiny inner fillet ring
            v, f = _closed_cup(outer, inner, [0, 0, 0], [0, 0, z_lo])
        else:
            v, f = _shell(inner, d.repeat(Rr, 0), thick)
        info = dict(pixels=[C, pic_rows], pitch_mm=round(circ / C, 4), inner_diameter_mm=round(2 * r_in, 2),
                    lip_mm=round(lip_w, 2), band_mm=round(ring, 2), lip_taper=lip_taper)
        if lip_taper != "none":
            info["taper_deg"] = round(float(taper_deg), 1)
        if inset.max() > 0:
            info["lip_inner_diameter_mm"] = round(2 * (r_in - inset.max()), 2)   # the band narrows the opening
        if cup:
            info["bottom_mm"] = CUP_BOTTOM_MM
        shown = thick[::-1]
    v[:, 2] -= v[:, 2].min()                                  # stand it on the bed
    return v, f, info, shown


# ------------------------------------------------------------------ curved panel (bend 0..180 deg)
BEND_MAX_DEG = 180.0
PANEL_STAND_H_MM = 4.0           # built-in stand: an arc-shaped foot under the panel, part of the same solid
PANEL_STAND_LIP_MM = 8.0         # how far the foot reaches out on each side of the panel


def _slab(inner: np.ndarray, normal: np.ndarray, thick: np.ndarray):
    """Closed solid from an OPEN (rows, cols) surface grid (no wrap): outer = inner + normal*thick; the four edges are
    closed by strips joining outer and inner. Same idea as _shell, minus the seam wrap."""
    R, C = thick.shape
    outer = inner + normal * thick[..., None]
    n = R * C
    verts = np.vstack([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    idx = np.arange(n).reshape(R, C)
    a = idx[:-1, :-1]; b = idx[:-1, 1:]; c = idx[1:, 1:]; d = idx[1:, :-1]
    out_f = np.vstack([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    in_f = (out_f + n)[:, ::-1]
    loop = np.concatenate([idx[0, :-1], idx[:-1, -1], idx[-1, :0:-1], idx[:0:-1, 0]])   # boundary, one way round
    nxt = np.roll(loop, -1)
    side = np.vstack([np.stack([nxt, loop, loop + n], -1), np.stack([nxt, loop + n, nxt + n], -1)])
    faces = np.vstack([out_f, in_f, side]).astype(np.int64)
    tri = verts[faces]
    if np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() < 0:
        faces = faces[:, ::-1]
    return verts, faces


def arc_frame(s: np.ndarray, length: float, bend_deg: float):
    """Inner-surface points (x, y) and outward normals for arc positions s (mm, centred on 0) of a panel `length` mm
    long bent through bend_deg. Arc length is kept exactly, so the picture is not stretched along the bend.
    The convex (picture) side faces -Y, the viewer; image left is -X."""
    a = np.radians(bend_deg)
    if a < 1e-4:
        return np.stack([s, np.zeros_like(s)], -1), np.stack([np.zeros_like(s), -np.ones_like(s)], -1)
    R = length / a
    phi = s / R
    return (np.stack([R * np.sin(phi), R - R * np.cos(phi)], -1),
            np.stack([np.sin(phi), -np.cos(phi)], -1))


def curved_panel(im, width_mm=100.0, bend_deg=90.0, stand=False, min_thickness=0.8, max_thickness=3.0,
                 border_mm=3.0, resolution=200, smooth=0.8, gamma=1.0, auto_contrast=True, invert=False,
                 color_mode="mono", **_):
    """A rectangle lithophane bent round a vertical axis, printed standing up.
    width_mm = arc length of the panel (the picture's width along the bend); the height follows the photo's aspect.
    Thickness is laid along the surface normal, so bright = thin holds at every point of the arc.
    stand=True adds an arc-shaped foot under the panel, merged into ONE watertight solid."""
    if not (0.0 <= bend_deg <= BEND_MAX_DEG):
        raise ValueError(f"bend must be 0..{BEND_MAX_DEG:g} degrees")
    scale = min(1.0, resolution / 200.0) if resolution else 1.0
    iw, ih = im.size
    height = width_mm * ih / max(1, iw)
    border = max(0.0, float(border_mm))
    C = int(np.clip(width_mm / TARGET_PITCH * scale, 32, 1200)) + 1
    Rr = int(np.clip(height / TARGET_PITCH * scale, 16, MAX_SIDE)) + 1
    bc = int(round(border / (width_mm / (C - 1)))) if border > 0 else 0
    br = int(round(border / (height / (Rr - 1)))) if border > 0 else 0
    pc, pr = max(4, C - 2 * bc), max(4, Rr - 2 * br)
    pic = thickness_map(im, pc, pr, min_thickness, max_thickness, smooth, gamma, auto_contrast, invert,
                        color_mode)[::-1]                    # row 0 = bottom of the print
    thick = np.full((pr + 2 * br, pc + 2 * bc), float(max_thickness))
    thick[br:br + pr, bc:bc + pc] = pic
    Rr, C = thick.shape
    s = np.linspace(-width_mm / 2, width_mm / 2, C)
    xy, nrm = arc_frame(s, width_mm, bend_deg)
    z = np.linspace(0.0, height, Rr)
    inner = np.concatenate([np.broadcast_to(xy[None], (Rr, C, 2)), np.broadcast_to(z[:, None, None], (Rr, C, 1))], -1)
    normal = np.concatenate([np.broadcast_to(nrm[None], (Rr, C, 2)), np.zeros((Rr, C, 1))], -1)
    v, f = _slab(inner, normal, thick)
    info = dict(pixels=[pc, pr], pitch_mm=round(width_mm / (C - 1), 4), bend_deg=round(float(bend_deg), 1),
                arc_length_mm=round(width_mm, 2), panel_height_mm=round(height, 2))
    if bend_deg > 1e-4:
        info["radius_mm"] = round(width_mm / np.radians(bend_deg), 2)
    if stand:
        v, f, foot = _panel_foot(v, f, s, width_mm, bend_deg, max_thickness)
        info["stand"] = foot
    v = v.copy(); v[:, 2] -= v[:, 2].min()
    return v, f, info, thick[::-1]


def _panel_foot(v, f, s, width_mm, bend_deg, max_thickness):
    """Built-in stand: an arc-shaped foot (follows the bend, reaches PANEL_STAND_LIP_MM out on both sides and past
    both ends) unioned with the panel, which is raised to sit on it. One solid, so it prints in one go."""
    import trimesh
    lip, h = PANEL_STAND_LIP_MM, PANEL_STAND_H_MM
    ext = lip if bend_deg < 1e-4 else min(lip, width_mm * (360.0 - bend_deg) / 720.0 / 2)  # ends never meet at 180
    s2 = np.linspace(s[0] - ext, s[-1] + ext, len(s))
    a = np.radians(bend_deg)
    if a < 1e-4:
        xy = np.stack([s2, np.zeros_like(s2)], -1); nrm = np.stack([np.zeros_like(s2), -np.ones_like(s2)], -1)
    else:
        R = width_mm / a; phi = s2 / R
        xy = np.stack([R * np.sin(phi), R - R * np.cos(phi)], -1); nrm = np.stack([np.sin(phi), -np.cos(phi)], -1)
    base = xy - nrm * lip                                       # start lip mm behind the inner (concave) side
    inner = np.concatenate([np.broadcast_to(base[None], (2, len(s2), 2)),
                            np.array([0.0, h])[:, None, None].repeat(len(s2), 1)], -1)
    normal = np.concatenate([np.broadcast_to(nrm[None], (2, len(s2), 2)), np.zeros((2, len(s2), 1))], -1)
    fv, ff = _slab(inner, normal, np.full((2, len(s2)), 2 * lip + max_thickness))
    pv = v.copy(); pv[:, 2] += h - 0.5                         # 0.5 mm overlap so the union is solid, not touching
    m = trimesh.boolean.union([trimesh.Trimesh(pv, f, process=False), trimesh.Trimesh(fv, ff, process=False)],
                              engine="manifold")
    if not m.is_watertight:
        raise ValueError("curved panel stand did not come out watertight")
    return (np.asarray(m.vertices, float), np.asarray(m.faces, np.int64),
            dict(height_mm=h, lip_mm=lip, built_in=True))


LIP_MAX_MM = 10.0
LIP_TAPERS = ("none", "outward", "inward", "both")
TAPER_MIN_DEG, TAPER_MAX_DEG = 20.0, 45.0


def check_lip(lip_mm, lip_taper, taper_deg):
    """Sleeve / cup band: lip_mm = reach past the wall 0..10 (0 = no band), taper none|outward|inward|both, slope 20..45 deg from vertical."""
    lip_taper = (lip_taper or "none").strip().lower()
    if lip_taper not in LIP_TAPERS:
        raise ValueError("lip_taper must be one of " + " | ".join(LIP_TAPERS))
    if not (0 <= float(lip_mm) <= LIP_MAX_MM):
        raise ValueError(f"lip_mm must be 0..{LIP_MAX_MM:g}")
    if not (TAPER_MIN_DEG <= float(taper_deg) <= TAPER_MAX_DEG):
        raise ValueError(f"taper_deg must be {TAPER_MIN_DEG:g}..{TAPER_MAX_DEG:g}")
    return float(lip_mm), lip_taper, float(taper_deg)


def build(im, shape, **params):
    """Returns (vertices, faces, info, thickness map for the preview thumb)."""
    if shape in FLAT_SHAPES:
        keys = ("width_mm", "min_thickness", "max_thickness", "border_mm", "resolution", "smooth", "gamma",
                "auto_contrast", "invert", "color_mode", "place")
        return flat_shape(im, shape, **{k: params[k] for k in keys if k in params})
    if shape in CURVED_SHAPES:
        keys = ("diameter_mm", "height_mm", "min_thickness", "max_thickness", "border_mm", "resolution", "smooth",
                "gamma", "auto_contrast", "invert", "color_mode", "place", "lip_mm", "lip_taper", "taper_deg")
        return curved_shape(im, shape, **{k: params[k] for k in keys if k in params})
    if shape in PANEL_SHAPES:
        keys = ("width_mm", "bend_deg", "stand", "min_thickness", "max_thickness", "border_mm", "resolution",
                "smooth", "gamma", "auto_contrast", "invert", "color_mode")
        return curved_panel(im, **{k: params[k] for k in keys if k in params})
    raise ValueError(f"unknown shape {shape!r}")


def thumb(thick, min_thickness, max_thickness):
    """Back-lit preview thumbnail for the lithophane thickness map."""
    return thumbnail.lithophane_backlit(thick, min_thickness, max_thickness)
