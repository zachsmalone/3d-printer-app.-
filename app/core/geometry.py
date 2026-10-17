"""Image -> watertight mesh generation (lithophane, relief, pop-art).

All meshes are built from shared-vertex grids so they are watertight and
consistently wound by construction. Units are millimetres. Coordinates:
X = image right, Y = image up, Z = thickness / height (back plane at Z=0).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from scipy.cluster.vq import kmeans2

from . import thumbnail

MAX_RES = 600
MAX_CELLS = MAX_RES * MAX_RES        # total grid cells (~2 triangles each, x2 for the base): a 10x1000 px strip used to make 4 million triangles
MAX_ASPECT = 20.0                    # longer/shorter side: beyond this the picture is refused with a plain message
WARN_ASPECT = 6.0
MIN_BASE_MM = 0.2                    # a base thinner than this is not a printable layer


@dataclass
class Body:
    name: str
    vertices: np.ndarray  # (N,3) float64
    faces: np.ndarray  # (M,3) int64
    color: str | None = None  # "#rrggbb"


@dataclass
class Model:
    bodies: list[Body] = field(default_factory=list)
    mode: str = ""
    info: dict = field(default_factory=dict)
    thumb: np.ndarray | None = None  # small RGB preview of the result
    single: tuple | None = None  # (verts, faces) one watertight mesh for formats/slicers without multi-body

    def solid(self):
        """Single watertight mesh: STL export + slicing use this (falls back to merged bodies)."""
        return self.single if self.single is not None else self.merged()

    def merged(self):
        verts, faces, off = [], [], 0
        for b in self.bodies:
            verts.append(b.vertices)
            faces.append(b.faces + off)
            off += len(b.vertices)
        return np.vstack(verts), np.vstack(faces)


# ----------------------------------------------------------------- images
def load_image(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return im.convert("RGB")


def _resize(im: Image.Image, nx: int) -> Image.Image:
    nx = int(np.clip(nx, 16, MAX_RES))
    ny = max(2, int(round(nx * im.height / im.width)))
    if nx * ny > MAX_CELLS:                      # keep the proportions, lose detail instead of making a gigantic file
        k = (MAX_CELLS / (nx * ny)) ** 0.5
        nx, ny = max(16, int(nx * k)), max(2, int(ny * k))
    return im.resize((nx, ny), Image.LANCZOS)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]) / 255.0


def _tone(g: np.ndarray, contrast: bool, gamma: float, smooth: float) -> np.ndarray:
    if smooth > 0:
        g = ndimage.gaussian_filter(g, smooth)
    if contrast:
        lo, hi = np.percentile(g, [1, 99])
        if hi - lo > 1e-6:
            g = np.clip((g - lo) / (hi - lo), 0, 1)
    if gamma and gamma != 1:
        g = np.power(np.clip(g, 0, 1), 1.0 / gamma)
    return np.clip(g, 0, 1)


# ------------------------------------------------- heightfield solid mesh
def heightfield_solid(top: np.ndarray, pitch: float, bottom: float = 0.0):
    """Watertight solid: node-grid top surface `top` (ny,nx) in mm, flat bottom."""
    ny, nx = top.shape
    n = ny * nx
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    x = jj * pitch
    y = (ny - 1 - ii) * pitch
    vt = np.stack([x, y, top], -1).reshape(-1, 3)
    vb = np.stack([x, y, np.full_like(top, bottom)], -1).reshape(-1, 3)
    verts = np.vstack([vt, vb]).astype(np.float64)

    idx = np.arange(n).reshape(ny, nx)
    a, b = idx[:-1, :-1], idx[:-1, 1:]  # a=(i,j) b=(i,j+1)
    d, c = idx[1:, :-1], idx[1:, 1:]  # d=(i+1,j) c=(i+1,j+1)
    # CCW seen from +Z (row index grows downwards in y)
    t1 = np.stack([d, c, b], -1).reshape(-1, 3)
    t2 = np.stack([d, b, a], -1).reshape(-1, 3)
    top_f = np.vstack([t1, t2])
    bot_f = (top_f + n)[:, ::-1]

    # boundary edges of the top surface, directed as in the faces
    e = np.vstack([top_f[:, [0, 1]], top_f[:, [1, 2]], top_f[:, [2, 0]]])
    key = e[:, 0].astype(np.int64) * n + e[:, 1]
    rkey = e[:, 1].astype(np.int64) * n + e[:, 0]
    bnd = e[~np.isin(key, rkey)]
    u, v = bnd[:, 0], bnd[:, 1]
    w1 = np.stack([v, u, u + n], -1)
    w2 = np.stack([v, u + n, v + n], -1)
    faces = np.vstack([top_f, bot_f, w1, w2]).astype(np.int64)
    return verts, faces


def fix_checkers(mask: np.ndarray) -> np.ndarray:
    """Fill diagonal-only contacts so the extruded mask is 2-manifold.

    A 2x2 block with only one diagonal set (`a&d` or `b&c`) makes the extruded prisms touch along a single edge that
    four faces share (non-manifold). We add one cell from the empty diagonal: the top-right cell `b` for the a/d case, the
    top-left cell `a` for the b/c case (the old code filled `b` for both, which is already set in the b/c case, so that
    contact was never repaired). Filling can create new contacts next door, so repeat until stable."""
    m = mask.copy()
    for _ in range(max(64, mask.shape[0] + mask.shape[1])):
        a, b = m[:-1, :-1], m[:-1, 1:]
        c, d = m[1:, :-1], m[1:, 1:]
        diag1 = a & d & ~b & ~c
        diag2 = b & c & ~a & ~d
        if not (diag1.any() or diag2.any()):
            break
        fill = np.zeros_like(m)
        fill[:-1, 1:] |= diag1          # b
        fill[:-1, :-1] |= diag2         # a
        m |= fill
    return m


def prism_mask_solid(mask: np.ndarray, pitch: float, z0: float, z1: float):
    """Extrude a boolean cell mask (H,W) between z0 and z1 (watertight)."""
    H, W = mask.shape
    stride = W + 1
    nv = (H + 1) * stride
    r, c = np.nonzero(mask)
    TL = r * stride + c
    TR = TL + 1
    BL = TL + stride
    BR = BL + 1
    top = np.concatenate([np.stack([BL, BR, TR], -1), np.stack([BL, TR, TL], -1)])
    bot = (top + nv)[:, ::-1]
    p = np.pad(mask, 1)
    pr, pc = r + 1, c + 1
    walls = []
    # (neighbour empty, u, v) with u->v the directed top-face edge
    for empty, u, v in (
        (~p[pr + 1, pc], BL, BR),  # south
        (~p[pr, pc + 1], BR, TR),  # east
        (~p[pr - 1, pc], TR, TL),  # north
        (~p[pr, pc - 1], TL, BL),  # west
    ):
        uu, vv = u[empty], v[empty]
        walls.append(np.stack([vv, uu, uu + nv], -1))
        walls.append(np.stack([vv, uu + nv, vv + nv], -1))
    faces = np.vstack([top, bot] + walls)
    used = np.unique(faces)
    remap = np.full(2 * nv, -1, np.int64)
    remap[used] = np.arange(len(used))
    gi = used % nv
    gr, gc = gi // stride, gi % stride
    z = np.where(used < nv, z1, z0)
    verts = np.stack([gc * pitch, (H - gr) * pitch, z], -1).astype(np.float64)
    return verts, remap[faces]


# ------------------------------------------------------------------ modes
def lithophane(im: Image.Image, width_mm=100.0, min_thickness=0.8, max_thickness=3.0,
               border_mm=3.0, resolution=200, smooth=0.8, gamma=1.0,
               auto_contrast=True, invert=False, shape="rect", diameter_mm=40.0, height_mm=60.0,
               color_mode="mono", place=None, hang="", hole_d=4.0, inset_mm=6.0,
               spacing_mm=40.0, stand=False, **_) -> Model:
    if max_thickness <= min_thickness:
        raise ValueError("max_thickness must be greater than min_thickness")
    if color_mode != "mono":                       # hook for a future colour lithophane; only mono exists today
        raise ValueError(f"color_mode {color_mode!r} is not available yet")
    shape = shape or "rect"
    from . import litho_hang, litho_shapes
    if hang:                                    # validate + widen the rim before any mesh is built
        hang_opts = litho_hang.check_hang(hang, hole_d, inset_mm, spacing_mm)
        if shape in litho_shapes.CURVED_SHAPES:
            raise ValueError("hanging holes are only available for flat lithophane shapes")
        border_mm = max(border_mm, litho_hang.border_needed(hole_d, inset_mm))
    if stand and shape in litho_shapes.CURVED_SHAPES:
        raise ValueError("the display stand is only available for flat lithophane shapes")
    if shape != "rect":
        if shape not in litho_shapes.SHAPES:
            raise ValueError(f"unknown lithophane shape {shape!r}")
        v, f, info, thick = litho_shapes.build(
            im, shape, width_mm=width_mm, min_thickness=min_thickness, max_thickness=max_thickness,
            border_mm=border_mm, resolution=resolution, smooth=smooth, gamma=gamma, auto_contrast=auto_contrast,
            invert=invert, diameter_mm=diameter_mm, height_mm=height_mm, color_mode=color_mode,
            place=litho_shapes.check_place(place))
        if hang or stand:                       # attachments for flat shapes: hang holes, display stand
            half = width_mm / 2.0
            poly = (litho_shapes.outline(shape, 8192) * half) + half   # plate mm coords, y up
            v, f, info = _flat_attachments(v, f, info, width_mm, max_thickness,
                                           poly, hang, hang_opts if hang else None, stand)
        m = Model([Body("lithophane", v, f)], "lithophane")
        if stand:
            y0 = v[:, 1].max() + 5.0 + info["stand"]["depth_mm"] / 2.0   # park it beside the plate: parts must not overlap in a combined print
            m.bodies.append(litho_stand_body(width_mm, max_thickness, y0))
        m.info = {**info, "shape": shape}
        m.thumb = litho_shapes.thumb(thick, min_thickness, max_thickness)
        return m
    small = _resize(im, resolution)
    g = _tone(_luma(np.asarray(small, np.float64)), auto_contrast, gamma, smooth)
    if invert:
        g = 1 - g
    thick = max_thickness - (max_thickness - min_thickness) * g  # bright -> thin
    ny, nx = thick.shape
    pad = 0
    if border_mm > 0:
        pad = max(1, int(round(border_mm / (width_mm / (nx - 1)))))
        if hang:
            # The final pitch shrinks as pad grows, and the LAST padded row is a transition
            # cell, so the guaranteed full-thickness band is (pad - 1) * final pitch, not
            # pad * pitch. Grow pad until that band covers the requested rim.
            if border_mm >= width_mm * 0.45:
                raise ValueError("hanging holes need a narrower rim: reduce hole_d and inset_mm or widen the plate")
            while (pad - 1) * (width_mm / (nx - 1 + 2 * pad)) < border_mm:
                pad += 1
        thick = np.pad(thick, pad, constant_values=max_thickness)
    pitch = width_mm / (nx - 1 + 2 * pad)          # width_mm is the OUTSIDE width: picture + border together (it used to be picture only)
    v, f = heightfield_solid(thick, pitch)
    info = dict(pixels=[nx, ny], pitch_mm=round(pitch, 4), border_cells=pad)
    if hang or stand:
        H = v[:, 1].max()
        poly = np.array([[0.0, 0.0], [width_mm, 0.0], [width_mm, H], [0.0, H]])
        v, f, info = _flat_attachments(v, f, info, width_mm, max_thickness,
                                       poly, hang, hang_opts if hang else None, stand)
    m = Model([Body("lithophane", v, f)], "lithophane")
    if stand:
        y0 = v[:, 1].max() + 5.0 + info["stand"]["depth_mm"] / 2.0   # park it beside the plate: parts must not overlap in a combined print
        m.bodies.append(litho_stand_body(width_mm, max_thickness, y0))
    m.info = info
    m.thumb = thumbnail.lithophane_backlit(thick, min_thickness, max_thickness)
    return m


def _flat_attachments(v, f, info, width_mm, max_thickness, poly, hang, hang_opts, want_stand):
    """Apply the Phase-2 flat-plate attachments to a built flat lithophane mesh.

    Hanging holes are cut through the rim (litho_hang); the display stand is sized here
    (litho_stand) and added as a second body by the caller. Returns (v, f, info).
    """
    from . import litho_hang, litho_stand
    if hang:
        centres = litho_hang.positions(hang, v[:, 0].max(), v[:, 1].max(),
                                       hang_opts["hole_d"], hang_opts["inset_mm"], hang_opts["spacing_mm"])
        litho_hang.fit_check(centres, hang_opts["hole_d"], poly)
        v, f = litho_hang.punch(v, f, centres, hang_opts["hole_d"], max_thickness)
        info = {**info, "hang": hang, "hole_d": hang_opts["hole_d"],
                "inset_mm": hang_opts["inset_mm"], "spacing_mm": hang_opts["spacing_mm"]}
    if want_stand:
        info = {**info, "stand": litho_stand.stand(width_mm, max_thickness)[2]}
    return v, f, info


def litho_stand_body(width_mm: float, max_thickness: float, y_offset: float = 0.0):
    """Second model body: the display stand matching a flat lithophane (see litho_stand).

    `y_offset` parks the stand beside the plate so the two parts never overlap in the
    combined export (both print flat on the bed, side by side).
    """
    from . import litho_stand
    v, f, _ = litho_stand.stand(width_mm, max_thickness)
    if y_offset:
        v = v.copy()
        v[:, 1] += y_offset
    return Body("stand", v, f)


def relief(im: Image.Image, width_mm=100.0, base_mm=2.0, relief_mm=6.0, resolution=200,
           smooth=1.0, gamma=1.0, auto_contrast=True, invert=False, **_) -> Model:
    small = _resize(im, resolution)
    g = _tone(_luma(np.asarray(small, np.float64)), auto_contrast, gamma, smooth)
    if invert:
        g = 1 - g
    h = max(base_mm, 0.2) + relief_mm * g  # bright -> high
    ny, nx = h.shape
    pitch = width_mm / (nx - 1)
    v, f = heightfield_solid(h, pitch)
    m = Model([Body("relief", v, f)], "relief")
    m.info = dict(pixels=[nx, ny], pitch_mm=round(pitch, 4))
    m.thumb = thumbnail.relief_shaded(h, pitch)
    return m


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(x)) for x in c)


def parse_palette(s: str | None):
    if not s:
        return None
    out = []
    for tok in s.replace(";", ",").split(","):
        tok = tok.strip().lstrip("#")
        if len(tok) == 6:
            out.append([int(tok[i:i + 2], 16) for i in (0, 2, 4)])
    return np.array(out, float) if out else None


def pop_labels(im: Image.Image, levels=4, resolution=160, style="posterize",
               halftone_cell=6.0, smooth=0.8, gamma=1.0, auto_contrast=True,
               invert=False, palette=None):
    small = _resize(im, resolution)
    rgb = np.asarray(small, np.float64)
    if smooth > 0:
        rgb = ndimage.gaussian_filter(rgb, (smooth, smooth, 0))
    levels = int(np.clip(levels, 2, 8))
    g = _tone(_luma(rgb), auto_contrast, gamma, 0)
    if invert:
        g = 1 - g
    H, W = g.shape
    pal = parse_palette(palette)
    if pal is None:
        px = rgb.reshape(-1, 3)
        rng = np.random.default_rng(0)
        sample = px[rng.choice(len(px), min(len(px), 20000), replace=False)]
        init = sample[np.argsort(_luma(sample))[np.linspace(0, len(sample) - 1, levels).astype(int)]]
        cent, _ = kmeans2(sample, init, minit="matrix", iter=15)
        cent = np.nan_to_num(cent, nan=128.0)
        pal = cent[np.argsort(_luma(cent))]
    if len(pal) < levels:  # pad custom palette
        pal = np.vstack([pal, np.tile(pal[-1], (levels - len(pal), 1))])
    pal = pal[:levels]
    pal = pal[np.argsort(_luma(pal))] if palette is None else pal
    if style == "halftone":
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
        th = np.deg2rad(45)
        u = (xx * np.cos(th) + yy * np.sin(th)) / halftone_cell
        v = (-xx * np.sin(th) + yy * np.cos(th)) / halftone_cell
        s = (np.cos(2 * np.pi * u) + np.cos(2 * np.pi * v)) / 4 + 0.5  # 0..1
        lab = np.floor(g * (levels - 1) + s * 0.999)
    else:
        lab = np.round(g * (levels - 1))
    lab = np.clip(lab, 0, levels - 1).astype(int)
    return lab, pal


def popart(im: Image.Image, width_mm=100.0, levels=4, base_mm=2.0, layer_mm=1.0,
           resolution=160, style="posterize", halftone_cell=6.0, multi_body=True,
           smooth=0.8, gamma=1.0, auto_contrast=True, invert=False, palette=None, **_) -> Model:
    lab, pal = pop_labels(im, levels, resolution, style, halftone_cell, smooth, gamma,
                          auto_contrast, invert, palette)
    levels = len(pal)
    H, W = lab.shape
    info = dict(pixels=[W, H], levels=levels, palette=[_hex(c) for c in pal],
                total_height_mm=round(base_mm + (levels - 1) * layer_mm, 3))
    if not multi_body:
        pitch = width_mm / (W - 1)
        h = base_mm + lab * layer_mm
        v, f = heightfield_solid(h.astype(np.float64), pitch)
        m = Model([Body("popart", v, f, _hex(pal[0]))], "popart")
        info["note"] = "single mesh: risers are one pixel wide (sloped)"
        m.info = info
        m.thumb = thumbnail.popart_shaded(lab, pal, layer_mm, pitch)
        return m
    pitch = width_mm / W
    masks = [lab >= k for k in range(levels)]
    for k in range(levels - 2, -1, -1):  # keep nested, then de-checker
        masks[k] = masks[k] | masks[k + 1]
    for k in range(levels - 1, 0, -1):
        masks[k] = fix_checkers(masks[k])
        masks[k - 1] = masks[k - 1] | masks[k]
    bodies = []
    for k in range(levels):
        if not masks[k].any():
            continue
        if k == 0:
            z0, z1 = 0.0, base_mm
        else:
            z0, z1 = base_mm + (k - 1) * layer_mm, base_mm + k * layer_mm
        v, f = prism_mask_solid(masks[k], pitch, z0, z1)
        bodies.append(Body(f"layer{k}", v, f, _hex(pal[k])))
    m = Model(bodies, "popart")
    m.info = info
    # STL/slicer variant: one merged watertight mesh (risers are 1 px sloped) - touching coplanar
    # bodies would not survive vertex-welding STL readers as a clean manifold.
    m.single = heightfield_solid((base_mm + lab * layer_mm).astype(np.float64), width_mm / (W - 1))
    m.thumb = thumbnail.popart_shaded(lab, pal, layer_mm, pitch)
    return m


def build(im: Image.Image, mode: str, params: dict) -> Model:
    fn = {"lithophane": lithophane, "relief": relief, "popart": popart}.get(mode)
    if fn is None:
        raise ValueError(f"unknown mode {mode!r}")
    params, warnings = check_params(im, mode, params)
    m = fn(im, **params)
    if warnings:
        m.info = {**(m.info or {}), "warnings": warnings}
    return m


def check_params(im: Image.Image, mode: str, params: dict) -> tuple[dict, list]:
    """Refuse or warn about settings that silently produce something unprintable (mesh audit, Ren Ishikawa, 2026-10-04)."""
    params = dict(params); warnings = []
    long_, short = max(im.width, im.height), max(1, min(im.width, im.height))
    ratio = long_ / short
    if ratio > MAX_ASPECT:
        raise ValueError(f"This picture is very long and thin ({im.width} × {im.height} pixels). Crop it to a shape that is less than "
                         f"{MAX_ASPECT:g} times longer than wide, then try again.")
    w = float(params.get("width_mm", 100.0))
    if ratio > WARN_ASPECT:
        shortmm = w * min(im.width, im.height) / max(im.width, im.height) if im.width >= im.height else w * im.width / im.height
        warnings.append(f"This picture is long and thin, so the model is {w:g} × {w * im.height / im.width:.0f} mm "
                        f"(or the other way round). Check that is the shape you want." + (f" The short side is only {shortmm:.1f} mm: fine details won't print." if shortmm < 10 else ""))
    if mode in ("relief", "popart") and float(params.get("base_mm", 2.0)) < MIN_BASE_MM:
        warnings.append(f"A base of {float(params.get('base_mm', 0)):g} mm can't be printed, so {MIN_BASE_MM:g} mm was used.")
        params["base_mm"] = MIN_BASE_MM
    nx = int(np.clip(params.get("resolution", 200), 16, MAX_RES)); ny = int(round(nx * im.height / im.width))
    if nx * ny > MAX_CELLS:
        warnings.append("Detail was reduced so the file stays a sensible size.")
    return params, warnings
