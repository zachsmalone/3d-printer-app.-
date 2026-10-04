"""Small shaded thumbnail of a mesh (history cards). matplotlib/Agg, flat shading, painter's algorithm."""
from __future__ import annotations

import numpy as np


def render(vertices: np.ndarray, faces: np.ndarray, size=(320, 240)) -> np.ndarray:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    if len(faces) > 30000:
        faces = faces[np.random.default_rng(0).choice(len(faces), 30000, replace=False)]
    v = vertices - (vertices.min(0) + vertices.max(0)) / 2
    az, el = np.radians(35), np.radians(28)       # camera: azimuth around Z, elevation
    Rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(el), -np.sin(el)], [0, np.sin(el), np.cos(el)]])
    w = v @ Rz.T @ Rx.T                             # x right, y = depth (away), z up
    tri = w[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True); n = n / np.where(ln == 0, 1, ln)
    light = np.array([-0.4, -0.7, 0.6]); light /= np.linalg.norm(light)
    shade = 0.25 + 0.75 * np.abs(n @ light)
    depth = tri[:, :, 1].mean(1)
    order = np.argsort(-depth)
    pts = tri[order][:, :, [0, 2]]
    col = np.c_[0.55 * shade, 0.68 * shade, 0.92 * shade][order]
    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100, facecolor="#10141c")
    ax = fig.add_axes([0.04, 0.04, 0.92, 0.92]); ax.set_facecolor("#10141c"); ax.axis("off")
    ax.add_collection(PolyCollection(pts, facecolors=col, edgecolors=col, linewidths=0.2))
    lo, hi = pts.reshape(-1, 2).min(0), pts.reshape(-1, 2).max(0)
    c, r = (lo + hi) / 2, max(hi - lo) / 2 * 1.05 or 1
    ax.set_xlim(c[0] - r * size[0] / size[1], c[0] + r * size[0] / size[1]); ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_aspect("equal")
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
    plt.close(fig)
    return img
