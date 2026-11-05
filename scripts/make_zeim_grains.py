#!/usr/bin/env python3
"""Original procedural wood grains for the ZEIM B2 theme.

Each tile is a small self-contained SVG (no photos, no external URLs).
The pigment is faint on purpose: panels stay readable, and the grain is a
wash, not a picture. Run from the repo root:

    python3 scripts/make_zeim_grains.py
"""
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "zt")
W, H = 180, 260

# Highlight colour is what shows on the dark panel. Alpha stays low.
WOODS = (
    # name, file, rgb, noise (fx, fy, octaves, seed, alpha), lines
    ("cherry", "grain-cherry.svg", (0.93, 0.58, 0.52), (0.055, 0.011, 3, 7, 0.06), "wave"),
    ("cypress", "grain-cypress.svg", (0.86, 0.74, 0.46), (0.022, 0.003, 1, 2, 0.04), "straight"),
    ("maple", "grain-maple.svg", (0.86, 0.36, 0.26), (0.09, 0.012, 2, 11, 0.055), "fine"),
    ("wenge", "grain-wenge.svg", (0.70, 0.50, 0.30), (0.28, 0.004, 2, 19, 0.07), "tight"),
    ("beech", "grain-beech.svg", (0.95, 0.89, 0.78), (0.012, 0.01, 1, 5, 0.045), "smooth"),
    ("walnut", "grain-walnut.svg", (0.58, 0.40, 0.24), (0.04, 0.008, 2, 13, 0.05), "quiet"),
)


def matrix(rgb, alpha):
    r, g, b = rgb
    return (
        f"0 0 0 0 {r:.3f} 0 0 0 0 {g:.3f} 0 0 0 0 {b:.3f} 0 0 0 {alpha:.3f} 0"
    )


def line_group(kind, rgb):
    """A few vector fibers so the species reads even when the noise is quiet."""
    r, g, b = rgb
    stroke = "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))
    if kind == "straight":
        # Bald cypress: few calm, almost ruler-straight bands.
        xs = (18, 52, 96, 138, 168)
        amp, op, width = 0.35, 0.05, 0.9
    elif kind == "tight":
        # Wenge: dark ground, thin close lines.
        xs = tuple(range(4, W, 5))
        amp, op, width = 0.2, 0.065, 0.45
    elif kind == "wave":
        xs = (12, 28, 46, 70, 96, 118, 142, 164)
        amp, op, width = 3.2, 0.05, 0.85
    elif kind == "fine":
        xs = tuple(range(8, W, 11))
        amp, op, width = 1.3, 0.05, 0.6
    elif kind == "quiet":
        xs = (16, 40, 74, 112, 150)
        amp, op, width = 0.8, 0.045, 1.05
    else:
        # Beech: no stripes. Tiny ray flecks only.
        dots = []
        for i, (x, y) in enumerate(
            ((24, 30), (70, 48), (120, 36), (156, 70), (40, 100), (96, 118),
             (150, 140), (22, 168), (78, 190), (132, 176), (168, 210), (54, 230))
        ):
            dots.append(
                f'<circle cx="{x}" cy="{y}" r="0.7" fill="{stroke}" fill-opacity="0.05"/>'
            )
        veil = f'<rect width="{W}" height="{H}" fill="{stroke}" fill-opacity="0.03"/>'
        return veil + "".join(dots)
    paths = []
    cycles = 1 if kind != "wave" else 1
    steps = 4 if amp < 1 else 8
    for n, x in enumerate(xs):
        phase = (n * 1.7) % (2 * math.pi)
        pts = []
        for i in range(steps + 1):
            t = i / steps
            y = round(H * t, 1)
            xx = round(x + amp * math.sin(phase + cycles * 2 * math.pi * t), 1)
            pts.append(f"{xx} {y}")
        paths.append(f'<path d="M{pts[0]}' + "".join(f"L{p}" for p in pts[1:]) + '"/>')
    return (
        f'<g fill="none" stroke="{stroke}" stroke-opacity="{op}" stroke-width="{width}" '
        f'stroke-linecap="butt">{"".join(paths)}</g>'
    )


def svg(name, rgb, noise, kind):
    fx, fy, octaves, seed, alpha = noise
    # Cap is part of the file so the theme test can reject a louder texture.
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" data-wood="{name}" data-max-opacity="0.16">'
        f'<filter id="g" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{fx} {fy}" numOctaves="{octaves}" '
        f'seed="{seed}" stitchTiles="stitch"/>'
        f'<feColorMatrix values="{matrix(rgb, alpha)}"/>'
        f'</filter>'
        f'<rect width="{W}" height="{H}" filter="url(#g)"/>'
        f'{line_group(kind, rgb)}'
        f'</svg>'
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn, rgb, noise, kind in WOODS:
        text = svg(name, rgb, noise, kind)
        path = os.path.join(OUT, fn)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{fn} {len(text)} bytes")


if __name__ == "__main__":
    main()
