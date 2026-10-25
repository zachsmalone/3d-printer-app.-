"""Four orthographic drawings of a Showcase model (front, right, back, left).

These are drawings of the mesh, not photos of a finished print. Results are
cached under the data directory and never written next to original files.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from app import config

VIEWS = (
    ("front", "Front", np.array([0.0, 1.0, 0.0])),
    ("right", "Right", np.array([-1.0, 0.0, 0.0])),
    ("back", "Back", np.array([0.0, -1.0, 0.0])),
    ("left", "Left", np.array([1.0, 0.0, 0.0])),
)
VIEW_IDS = {v[0] for v in VIEWS}
_MAX_FACES = 6000
_SIZE = 420


def _axes(look: np.ndarray):
    look = look / np.linalg.norm(look)
    up = np.array([0.0, 0.0, 1.0])
    if abs(float(look @ up)) > 0.9:
        up = np.array([0.0, 1.0, 0.0])
    right = np.cross(look, up)
    right = right / np.linalg.norm(right)
    cam_up = np.cross(right, look)
    cam_up = cam_up / np.linalg.norm(cam_up)
    return right, cam_up


def render_png(mesh: trimesh.Trimesh, look: np.ndarray, size: int = _SIZE) -> bytes:
    """Orthographic shaded PNG. Faces beyond the cap are subsampled."""
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    if len(v) == 0 or len(f) == 0:
        raise ValueError("empty mesh")
    if len(f) > _MAX_FACES:
        step = int(np.ceil(len(f) / _MAX_FACES))
        f = f[::step]
    center = (v.min(0) + v.max(0)) / 2.0
    right, cam_up = _axes(np.asarray(look, dtype=np.float64))
    p = v - center
    u = p @ right
    w = p @ cam_up
    z = p @ (look / np.linalg.norm(look))
    span = max(float(u.max() - u.min()), float(w.max() - w.min()), 1e-6)
    scale = (size * 0.82) / span
    u = (u - float(u.mean())) * scale + size / 2.0
    w = (float(w.mean()) - w) * scale + size / 2.0
    e1 = v[f[:, 1]] - v[f[:, 0]]
    e2 = v[f[:, 2]] - v[f[:, 0]]
    n = np.cross(e1, e2)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.where(ln == 0, 1.0, ln)
    shade = np.clip(n @ np.array([0.25, -0.35, 0.85]), 0.22, 1.0)
    img = np.full((size, size, 3), 244, np.uint8)
    zb = np.full((size, size), -1e9, np.float32)
    for i, tri in enumerate(f):
        pts = np.stack([u[tri], w[tri]], axis=1)
        zs = z[tri]
        minx = max(0, int(np.floor(pts[:, 0].min())))
        maxx = min(size - 1, int(np.ceil(pts[:, 0].max())))
        miny = max(0, int(np.floor(pts[:, 1].min())))
        maxy = min(size - 1, int(np.ceil(pts[:, 1].max())))
        if maxx < minx or maxy < miny:
            continue
        step = 2 if (maxx - minx) * (maxy - miny) > 12000 else 1
        xs = np.arange(minx, maxx + 1, step)
        ys = np.arange(miny, maxy + 1, step)
        if len(xs) == 0 or len(ys) == 0:
            continue
        gx, gy = np.meshgrid(xs, ys)
        x0, y0 = pts[0]
        x1, y1 = pts[1]
        x2, y2 = pts[2]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(float(den)) < 1e-8:
            continue
        a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
        b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
        c = 1.0 - a - b
        inside = (a >= -0.001) & (b >= -0.001) & (c >= -0.001)
        if not inside.any():
            continue
        depth = a * zs[0] + b * zs[1] + c * zs[2]
        yy, xx = gy[inside], gx[inside]
        dd = depth[inside]
        better = dd > zb[yy, xx]
        if not better.any():
            continue
        yy, xx, dd = yy[better], xx[better], dd[better]
        zb[yy, xx] = dd
        col = shade[i]
        rgb = (np.array([0, 70, 220]) * col + np.array([210, 214, 220]) * (1.0 - col)).astype(np.uint8)
        img[yy, xx] = rgb
        if step == 2:
            img[np.clip(yy + 1, 0, size - 1), xx] = rgb
            img[yy, np.clip(xx + 1, 0, size - 1)] = rgb
    buf = io.BytesIO()
    Image.fromarray(img, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def cache_dir(item_id: str) -> Path:
    safe = "".join(ch for ch in item_id if ch.isalnum())
    return config.DATA / "showoff" / (safe or "item")


def ensure(item_id: str, stl: Path) -> list[tuple[str, str, Path]]:
    """Draw any missing side and return (id, label, png path) for each view."""
    folder = cache_dir(item_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = stl.stat().st_mtime
    mesh = None
    out = []
    for vid, label, look in VIEWS:
        png = folder / f"{vid}.png"
        if not png.is_file() or png.stat().st_mtime < stamp:
            if mesh is None:
                mesh = trimesh.load(str(stl), force="mesh")
            png.write_bytes(render_png(mesh, look))
        out.append((vid, label, png))
    return out
