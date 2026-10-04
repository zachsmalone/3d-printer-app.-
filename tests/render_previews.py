"""Render preview PNGs of generated meshes with matplotlib (python tests/render_previews.py)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgb
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image
from app.core import geometry

im = geometry.load_image(open("tests/sample.png", "rb").read())


def render(model, path, title, elev=48, azim=-62, zscale=1.0):
    fig = plt.figure(figsize=(8, 6.2), dpi=130)
    ax = fig.add_subplot(111, projection="3d")
    light = np.array([-0.4, -0.6, 0.7]); light /= np.linalg.norm(light)
    allv = np.vstack([b.vertices for b in model.bodies])
    for b in model.bodies:
        tri = b.vertices[b.faces]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        # only draw faces facing the camera side (cheap hidden-surface removal for convex-ish slabs)
        shade = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
        base = np.array(to_rgb(b.color or "#e8dfc8"))
        cols = np.clip(base[None] * shade[:, None], 0, 1)
        keep = tri[:, :, 2].mean(1) >= 0  # all
        pc = Poly3DCollection(tri[keep], facecolors=cols[keep], edgecolors="none", linewidths=0)
        ax.add_collection3d(pc)
    mn, mx = allv.min(0), allv.max(0)
    ax.set_xlim(mn[0], mx[0]); ax.set_ylim(mn[1], mx[1]); ax.set_zlim(0, (mx[0] - mn[0]) * 0.5 * zscale + 0)
    ax.set_box_aspect((mx[0] - mn[0], mx[1] - mn[1], (mx[2] - mn[2]) * 6 * zscale))
    ax.view_init(elev, azim); ax.set_axis_off(); ax.set_title(title)
    fig.savefig(path, bbox_inches="tight", facecolor="white"); plt.close(fig)


m = geometry.build(im, "popart", dict(width_mm=100, levels=4, resolution=70, base_mm=2, layer_mm=1.5, smooth=0.8))
render(m, "previews/popart_layers.png", "Pop-art: 4 stacked colour layers (z exaggerated)")
m = geometry.build(im, "lithophane", dict(width_mm=100, resolution=90, min_thickness=0.8, max_thickness=3.0, border_mm=3, smooth=0.8))
render(m, "previews/lithophane_relief.png", "Lithophane: brightness -> thickness (z exaggerated)", elev=55, azim=-70)
Image.fromarray(m.thumb).save("previews/lithophane_backlit.png")
print("ok")
