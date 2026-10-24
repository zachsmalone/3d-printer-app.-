"""Select mode: keep only the part of the photo the user traced (lasso) before it becomes a model.

The selection travels inside the build params as ``params["select"]`` (a small dict), so every rebuild
(history preview, re-open, Send-to, edit-from-build, resume of a parked upload) applies the same cut:

    {"v": 1, "mask": "<base64 PNG, grey, white = keep>", "soft": 0..20, "outside": "plain" | "flat",
     "paths": [{"op": "new" | "add" | "sub", "pts": [[x, y], ...]}], "invert": bool, "snap": bool}

``mask`` is what the user saw in the live preview (the browser snaps the outline to edges and sends the
result).  When only ``paths`` arrive (API callers, old clients) the server rasterises them and runs the
same edge-snap here (numpy/scipy only, no OpenCV).

Effect per mode (``apply``):
* relief / popart / bust: the photo is cropped to the selection and everything outside is REMOVED from the mesh.
* lithophane: the panel keeps its shape; outside the selection becomes plain (thin, glows evenly white)
  or flat (full thickness, dark, no picture) - the user's choice.
Warnings are returned, never raised: a tiny or empty selection still builds (empty = whole photo).
"""
from __future__ import annotations

import base64
import io
import json

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

MAX_MASK_B64 = 3 * 2**20          # base64 characters
MAX_MASK_SIDE = 2048
MAX_PATHS = 60
MAX_POINTS = 4000
OUTSIDE = ("plain", "flat")
WORK = 512                         # long side of the working raster for snapping


class SelectError(ValueError):
    pass


# ---------------------------------------------------------------- parsing
def parse(raw) -> dict | None:
    """Validate the 'select' form field / params entry. '' or None -> no selection (whole photo)."""
    if raw in (None, "", {}):
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise SelectError("The selection didn't come through. Please trace again, or use the whole photo.")
    if not isinstance(raw, dict):
        raise SelectError("The selection didn't come through. Please trace again, or use the whole photo.")
    if raw.get("whole"):
        return None
    out = {"v": 1}
    soft = raw.get("soft", 0)
    try:
        soft = float(soft)
    except (TypeError, ValueError):
        soft = 0.0
    out["soft"] = float(np.clip(soft, 0, 20))
    out["outside"] = raw.get("outside") if raw.get("outside") in OUTSIDE else "plain"
    out["invert"] = bool(raw.get("invert", False))
    out["snap"] = bool(raw.get("snap", True))
    paths = []
    for p in (raw.get("paths") or [])[:MAX_PATHS]:
        if not isinstance(p, dict):
            continue
        pts = p.get("pts") or []
        try:
            pts = [[float(np.clip(float(x), 0, 1)), float(np.clip(float(y), 0, 1))] for x, y in pts[:MAX_POINTS]]
        except (TypeError, ValueError):
            continue
        if len(pts) >= 3:
            paths.append({"op": p.get("op") if p.get("op") in ("sub", "new") else "add", "pts": [[round(x, 4), round(y, 4)] for x, y in pts]})
    out["paths"] = paths
    m = raw.get("mask")
    if m:
        if not isinstance(m, str) or len(m) > MAX_MASK_B64:
            raise SelectError("The selection is too big to send. Please trace again with fewer strokes.")
        if m.startswith("data:"):
            m = m.split(",", 1)[-1]
        decode_mask(m)                                    # refuse junk now, before a history slot is used
        out["mask"] = m
    if not paths and "mask" not in out:
        return None
    return out


def decode_mask(b64: str) -> np.ndarray:
    """base64 PNG -> float32 (h, w) in 0..1 (1 = keep)."""
    try:
        data = base64.b64decode(b64, validate=False)
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "PNG" or max(im.size) > MAX_MASK_SIDE or min(im.size) < 4:
                raise ValueError
            a = np.asarray(im.convert("L"), np.float32) / 255.0
    except Exception:
        raise SelectError("The selection didn't come through. Please trace again, or use the whole photo.")
    return a


def encode_mask(a: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L").save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- raster + snap
def rasterize(paths, w: int, h: int) -> np.ndarray:
    """Paths in normalised 0..1 photo coords, applied in order (add = union, sub = cut) -> bool (h, w)."""
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    for p in paths:
        if p["op"] == "new":                    # 'Trace' starts a fresh selection; Add / Subtract change it
            d.rectangle((0, 0, w, h), fill=0)
        pts = [(x * (w - 1), y * (h - 1)) for x, y in p["pts"]]
        d.polygon(pts, fill=0 if p["op"] == "sub" else 255)
    return np.asarray(m) > 127


def snap(rgb: np.ndarray, rough: np.ndarray, band: int | None = None) -> np.ndarray:
    """Edge-aware refinement of a rough lasso (GrabCut-style, simplified, permissive: numpy + scipy).

    Pixels well inside the trace are 'sure keep', well outside 'sure remove'.  In the band between,
    each pixel goes to whichever side it resembles more (distance to a few colour clusters sampled from
    each side, plus a pull towards the drawn line); the answer is then smoothed so it hugs strong edges
    and has no speckles.  rgb: (h, w, 3) float 0..255, rough: bool (h, w)."""
    h, w = rough.shape
    if not rough.any() or rough.all():
        return rough.copy()
    band = band or max(4, int(round(0.06 * max(h, w))))
    inner = ndimage.binary_erosion(rough, iterations=band)
    outer = ~ndimage.binary_dilation(rough, iterations=band)
    unsure = ~(inner | outer)
    if inner.sum() < 20 or outer.sum() < 20:
        return rough.copy()
    ring_in = inner & ~ndimage.binary_erosion(inner, iterations=band * 2)
    ring_out = outer & ~ndimage.binary_erosion(outer, iterations=band * 2)
    lab = rgb.astype(np.float32)

    def clusters(sel, k=4):
        px = lab[sel]
        if len(px) > 4000:
            px = px[np.linspace(0, len(px) - 1, 4000).astype(int)]
        c = px[np.linspace(0, len(px) - 1, k).astype(int)].copy()
        for _ in range(8):                          # tiny k-means
            d = ((px[:, None, :] - c[None]) ** 2).sum(-1)
            a = d.argmin(1)
            for j in range(k):
                if (a == j).any():
                    c[j] = px[a == j].mean(0)
        return c

    cf, cb = clusters(ring_in if ring_in.sum() > 20 else inner), clusters(ring_out if ring_out.sum() > 20 else outer)
    q = lab[unsure]
    df = np.sqrt(((q[:, None, :] - cf[None]) ** 2).sum(-1).min(1))
    db = np.sqrt(((q[:, None, :] - cb[None]) ** 2).sum(-1).min(1))
    # signed distance to the drawn line: inside positive (the user's intent breaks ties)
    sd = ndimage.distance_transform_edt(rough) - ndimage.distance_transform_edt(~rough)
    prior = sd[unsure] / band                       # -1..1 across the band
    score = (db - df) / (db + df + 1e-3) + 0.35 * prior
    out = inner.copy()
    out[unsure] = score > 0
    out = ndimage.binary_opening(out, iterations=1)
    out = ndimage.binary_closing(out, iterations=2)
    lbl, n = ndimage.label(out)                     # drop crumbs that are not attached to what was traced
    if n > 1:
        keep = np.unique(lbl[inner & out])
        out = np.isin(lbl, keep[keep > 0]) if len(keep) else out
    return out


def mask_for(im: Image.Image, sel: dict) -> np.ndarray:
    """Float (H, W) 0..1 keep-mask at the photo's own size (soft edge applied)."""
    W, H = im.size
    if sel.get("mask"):
        a = decode_mask(sel["mask"])
        hard = a
    else:
        s = WORK / max(W, H)
        w, h = max(4, int(round(W * min(1, s)))), max(4, int(round(H * min(1, s))))
        rough = rasterize(sel["paths"], w, h)
        if sel.get("snap", True):
            rgb = np.asarray(im.convert("RGB").resize((w, h), Image.BILINEAR), np.float32)
            rough = snap(rgb, rough)
        if sel.get("invert"):
            rough = ~rough
        hard = rough.astype(np.float32)
    m = np.asarray(Image.fromarray((hard * 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR), np.float32) / 255
    soft = float(sel.get("soft", 0))
    if soft > 0:
        m = ndimage.gaussian_filter(m, sigma=soft / 1000.0 * max(W, H))
        # keep the edge where the user put it: re-centre the blur on 0.5
    return np.clip(m, 0, 1)


# ---------------------------------------------------------------- apply
def apply(im: Image.Image, mode: str, sel: dict | None):
    """-> (image to build from, keep-alpha float (H, W) or None, warnings).
    relief / popart / bust: image cropped to the selection, alpha used to cut the mesh.
    lithophane: same frame, outside composited to plain white (thin) or flat black (thick); alpha None."""
    if not sel:
        return im, None, []
    warn = []
    a = mask_for(im, sel)
    keep = a >= 0.5
    frac = float(keep.mean())
    if frac < 0.002:
        return im, None, ["Nothing was selected, so the whole photo was used. Trace around what you want, or press Use whole photo."]
    if frac < 0.02:
        warn.append("The selected part is very small, so fine detail may not print. You can trace a bigger area or make the model wider.")
    rgb = im.convert("RGB")
    if mode == "lithophane":
        fill = 255.0 if sel.get("outside", "plain") == "plain" else 0.0
        if sel.get("_invert_tone"):
            fill = 255.0 - fill
        arr = np.asarray(rgb, np.float32)
        arr = arr * a[..., None] + fill * (1 - a[..., None])
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), None, warn
    rows, cols = np.nonzero(keep)
    pad = max(2, int(0.02 * max(im.size)))
    r0, r1 = max(0, rows.min() - pad), min(im.height, rows.max() + pad + 1)
    c0, c1 = max(0, cols.min() - pad), min(im.width, cols.max() + pad + 1)
    crop = rgb.crop((c0, r0, c1, r1))
    if max(crop.size) / max(1, min(crop.size)) > 20:
        warn.append("The selected part is very long and thin; the model may be hard to print.")
    return crop, a[r0:r1, c0:c1], warn


def node_alpha(alpha: np.ndarray, nx: int, ny: int) -> np.ndarray:
    """Resample a keep-alpha to a (ny, nx) grid."""
    return np.asarray(Image.fromarray((alpha * 255).astype(np.uint8), "L").resize((nx, ny), Image.BILINEAR), np.float64) / 255


def summary(sel: dict | None) -> dict | None:
    """What history / the client needs to know without the heavy mask."""
    if not sel:
        return None
    return {"outside": sel.get("outside"), "soft": sel.get("soft"), "paths": len(sel.get("paths", [])), "invert": sel.get("invert")}
