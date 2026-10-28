"""Photo preparation before TripoSR.

Centre the subject, steady a dark, bright, or flat photo, and put plain grey behind
the subject when it can be told from the edges. Each step can be turned off.
Nothing here invents detail. The same file is what the ZEIM app imports.
"""
from __future__ import annotations

import io
from typing import Callable

import numpy as np
from PIL import Image

MAX_SIDE = 1024
GREY = 128.0
# TripoSR's published examples sit the subject in about 85% of a square grey frame.
FILL = 0.85


def prepare_image(
    data: bytes,
    mode: str,
    *,
    crop: bool = True,
    tone: bool = True,
    grey: bool = True,
    alpha_fn: Callable | None = None,
) -> tuple[bytes, list[str]]:
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGBA")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    rgba = np.asarray(im).astype(np.float32)
    rgb = rgba[..., :3]
    notes: list[str] = []

    mask, how = _mask(rgba, im.convert("RGB"), alpha_fn)
    if tone:
        rgb, tone_note = _tone(rgb, mask)
        if tone_note:
            notes.append(tone_note)

    canvas, placed = _place(rgb, mask, how, crop=crop, grey=grey, bust=(mode == "bust"))
    notes.extend(placed)
    out = Image.fromarray(np.clip(np.rint(canvas), 0, 255).astype(np.uint8), "RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue(), notes


def _mask(rgba: np.ndarray, rgb_im: Image.Image, alpha_fn: Callable | None):
    rgb = rgba[..., :3]
    if alpha_fn is not None:
        try:
            got = alpha_fn(rgb_im)
        except Exception:
            got = None
        if got is not None:
            a = np.asarray(got, dtype=np.float32)
            if a.shape[:2] == rgb.shape[:2]:
                m = a > (127.0 if float(np.nanmax(a)) > 1.5 else 0.5)
                if 50 <= int(m.sum()) <= 0.92 * m.size:
                    return m, "cutout"
    alpha = rgba[..., 3]
    if float(alpha.min()) < 250 and float(alpha.max()) > 10:
        m = alpha > 128
        if 50 <= int(m.sum()) <= 0.92 * m.size:
            return m, "alpha"
    h, w = rgb.shape[:2]
    band = max(2, min(h, w) // 32)
    edges = np.concatenate([
        rgb[:band].reshape(-1, 3), rgb[-band:].reshape(-1, 3),
        rgb[:, :band].reshape(-1, 3), rgb[:, -band:].reshape(-1, 3),
    ], axis=0)
    bg = np.median(edges, axis=0)
    dist = np.linalg.norm(rgb - bg, axis=2)
    m = _close(dist > 28.0)
    count = int(m.sum())
    if count < 50 or count > 0.92 * m.size:
        return None, "none"
    return m, "edges"


def _close(m: np.ndarray) -> np.ndarray:
    """One-pixel close, so a thin gap in the subject does not become a hole. No scipy."""
    pad = np.pad(m, 1, constant_values=False)
    grown = np.zeros_like(m, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            grown |= pad[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    pad = np.pad(grown, 1, constant_values=False)
    keep = np.ones_like(m, dtype=bool)
    for dy in range(3):
        for dx in range(3):
            keep &= pad[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return keep


def _apply(rgb: np.ndarray, mask: np.ndarray | None, changed: np.ndarray) -> np.ndarray:
    """Keep the adjustment on the subject when we have one, so a light background is not blown out."""
    if mask is None:
        return changed
    out = rgb.copy()
    out[mask] = changed[mask]
    return out


def _tone(rgb: np.ndarray, mask: np.ndarray | None) -> tuple[np.ndarray, str | None]:
    sel = rgb[mask] if mask is not None and int(mask.sum()) >= 20 else rgb.reshape(-1, 3)
    luma = 0.2126 * sel[:, 0] + 0.7152 * sel[:, 1] + 0.0722 * sel[:, 2]
    lo = float(np.percentile(luma, 2))
    hi = float(np.percentile(luma, 98))
    span = hi - lo
    mean = float(np.mean(luma))
    subject = mask is not None and int(mask.sum()) >= 20
    if hi < 90 and hi > 1:
        gain = min(2.5, 150.0 / hi)
        note = "Brightened the dark subject. No detail was added." if subject else "Brightened a dark photo. No detail was added."
        return _apply(rgb, mask if subject else None, np.clip(rgb * gain, 0, 255)), note
    if lo > 175:
        scale = min(1.0, 165.0 / max(mean, 1.0))
        note = "Eased a very bright subject. No detail was added." if subject else "Eased a very bright photo. No detail was added."
        return _apply(rgb, mask if subject else None, np.clip(rgb * scale, 0, 255)), note
    if span < 22 and 25 < mean < 230:
        note = "Spread a flat subject a little so light and shadow separate. No detail was added." if subject else "Spread a flat photo a little so light and shadow separate. No detail was added."
        return _apply(rgb, mask if subject else None, np.clip((rgb - mean) * 1.35 + mean, 0, 255)), note
    return rgb, None


def _bbox(mask: np.ndarray):
    ys, xs = np.where(mask)
    if len(xs) < 50:
        return None
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def _place(rgb, mask, how: str, *, crop: bool, grey: bool, bust: bool):
    notes: list[str] = []
    h, w = rgb.shape[:2]
    use = mask
    if bust and crop and mask is not None:
        box = _bbox(mask)
        if box:
            y0, y1, x0, x1 = box
            cut = y0 + max(1, int(round((y1 - y0) * 0.55)))
            trimmed = mask.copy()
            trimmed[cut + 1:, :] = False
            if int(trimmed.sum()) >= 50:
                use = trimmed
                notes.append("Bust keeps the top of the subject, about the head and shoulders.")
    box = _bbox(use) if crop and use is not None else None
    if crop and box is None:
        notes.append("No clear subject to centre, so the whole photo is kept.")
    if box is not None:
        y0, y1, x0, x1 = box
        pad_y = int(0.06 * (y1 - y0 + 1))
        pad_x = int(0.06 * (x1 - x0 + 1))
        y0, y1 = max(0, y0 - pad_y), min(h - 1, y1 + pad_y)
        x0, x1 = max(0, x0 - pad_x), min(w - 1, x1 + pad_x)
        crop_rgb = rgb[y0:y1 + 1, x0:x1 + 1]
        crop_m = use[y0:y1 + 1, x0:x1 + 1]
        notes.append("Centred the subject in the frame.")
    else:
        crop_rgb = rgb
        crop_m = use
    ch, cw = crop_rgb.shape[:2]
    side = max(ch, cw, int(round(max(ch, cw) / FILL)))
    if grey:
        canvas = np.full((side, side, 3), GREY, np.float32)
    else:
        edge = np.median(np.concatenate([
            crop_rgb[0].reshape(-1, 3), crop_rgb[-1].reshape(-1, 3),
            crop_rgb[:, 0].reshape(-1, 3), crop_rgb[:, -1].reshape(-1, 3),
        ], axis=0), axis=0)
        canvas = np.full((side, side, 3), edge, np.float32)
    oy, ox = (side - ch) // 2, (side - cw) // 2
    if grey and crop_m is not None:
        a = crop_m.astype(np.float32)[..., None]
        canvas[oy:oy + ch, ox:ox + cw] = crop_rgb * a + GREY * (1.0 - a)
        if how == "cutout":
            notes.append("Cut the subject out of the background and placed it on plain grey.")
        else:
            notes.append("Plain grey behind the subject, where it could be separated from the edges.")
    else:
        canvas[oy:oy + ch, ox:ox + cw] = crop_rgb
        if grey and crop_m is None:
            notes.append("Background kept. The subject was not clear enough to separate.")
        elif not grey:
            notes.append("Background left as in the photo.")
    if not notes:
        notes.append("Photo prep left this photo as it is.")
    return canvas, notes
