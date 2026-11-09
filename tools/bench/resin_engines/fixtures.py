"""Meshes for the resin-engine bench. Binary STL only. Nothing here is a printer file.

Coordinates are millimetres. Z is up and the bed is z = 0. XY is centred on the
plate: DragonFruit's raster origin is the plate centre. The harness translates a
copy by half the plate for mslicer's ``--placed`` mode, whose origin is the
minimum corner.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

BOX = {
    "name": "box",
    "size_mm": (20.0, 16.0, 12.0),
    "note": "Axis-aligned 20 x 16 x 12 mm box, centred on the plate, sitting on the bed.",
}
ASYM = {
    "name": "asymmetric",
    "size_mm": (30.0, 20.0, 12.0),
    "note": (
        "30 x 20 x 4 mm slab with a 10 x 8 mm tower on the +X +Y corner, from z = 4 to z = 12. "
        "A mirror or a Y flip moves the tower to another corner."
    ),
}
SCULPT = {
    "name": "sculpt",
    "size_mm": (48.0, 40.0, 20.0),
    "grid": 476,
    "note": (
        "Height-field solid, 48 x 40 mm in XY and exactly 20 mm tall, with two smooth bumps. "
        "Generated here; the repository had no mesh over 900k triangles."
    ),
}


def box_tris(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> np.ndarray:
    """Closed box. Each quad is wound so the first triangle's normal points outward."""
    p = [
        np.array([x0, y0, z0], np.float32),
        np.array([x1, y0, z0], np.float32),
        np.array([x1, y1, z0], np.float32),
        np.array([x0, y1, z0], np.float32),
        np.array([x0, y0, z1], np.float32),
        np.array([x1, y0, z1], np.float32),
        np.array([x1, y1, z1], np.float32),
        np.array([x0, y1, z1], np.float32),
    ]
    # Indices follow the usual 0..7 box. Each pair is wound outward.
    tris = np.array(
        [
            [p[0], p[2], p[1]],
            [p[0], p[3], p[2]],  # -Z
            [p[4], p[5], p[6]],
            [p[4], p[6], p[7]],  # +Z
            [p[0], p[1], p[5]],
            [p[0], p[5], p[4]],  # -Y
            [p[1], p[2], p[6]],
            [p[1], p[6], p[5]],  # +X
            [p[2], p[3], p[7]],
            [p[2], p[7], p[6]],  # +Y
            [p[3], p[0], p[4]],
            [p[3], p[4], p[7]],  # -X
        ],
        dtype=np.float32,
    )
    return tris


def mesh_box() -> np.ndarray:
    return box_tris(-10.0, -8.0, 0.0, 10.0, 8.0, 12.0)


def mesh_asymmetric() -> np.ndarray:
    """Slab plus a corner tower.

    The shared rectangle at z = 4 is present on both solids, with opposite
    normals, so a nonzero-winding rasterizer cancels it. The outside shape is
    the L in Z: full slab below 4 mm, tower only above.
    """
    slab = box_tris(-15.0, -10.0, 0.0, 15.0, 10.0, 4.0)
    tower = box_tris(5.0, 2.0, 4.0, 15.0, 10.0, 12.0)
    return np.concatenate((slab, tower), axis=0)


def mesh_sculpt(grid: int = 476) -> np.ndarray:
    """Closed height field. ``grid`` is the vertex count along each side of a cap."""
    xs = np.linspace(-24.0, 24.0, grid, dtype=np.float64)
    ys = np.linspace(-20.0, 20.0, grid, dtype=np.float64)
    # ij: axis 0 is X, axis 1 is Y. The cap and wall slices below depend on that.
    x, y = np.meshgrid(xs, ys, indexing="ij")
    z = (
        3.0
        + 6.0 * np.sin(x / 6.5) ** 2 * np.cos(y / 5.5)
        + 5.0 * np.exp(-((x - 8.0) ** 2 + (y + 5.0) ** 2) / 70.0)
        + 3.5 * np.exp(-((x + 10.0) ** 2 + (y - 6.0) ** 2) / 40.0)
        + 1.2 * np.sin(x / 2.2) * np.cos(y / 2.7)
    )
    z -= z.min()
    peak = float(z.max())
    if peak <= 0:
        raise RuntimeError("sculpt height collapsed")
    z *= 20.0 / peak
    # The highest sample must be exactly 20 mm so the layer count is 400 at 0.05 mm.
    z[np.unravel_index(int(np.argmax(z)), z.shape)] = 20.0
    z = z.astype(np.float32)
    x = x.astype(np.float32)
    y = y.astype(np.float32)

    n = grid - 1
    x00, x10 = x[:-1, :-1], x[1:, :-1]
    x11, x01 = x[1:, 1:], x[:-1, 1:]
    y00, y10 = y[:-1, :-1], y[1:, :-1]
    y11, y01 = y[1:, 1:], y[:-1, 1:]
    z00, z10 = z[:-1, :-1], z[1:, :-1]
    z11, z01 = z[1:, 1:], z[:-1, 1:]
    zero = np.zeros_like(z00)

    def pack(a, b, c) -> np.ndarray:
        return np.stack((a, b, c), axis=-1)

    top = np.concatenate(
        (
            np.stack((pack(x00, y00, z00), pack(x10, y10, z10), pack(x11, y11, z11)), axis=-2),
            np.stack((pack(x00, y00, z00), pack(x11, y11, z11), pack(x01, y01, z01)), axis=-2),
        ),
        axis=0,
    ).reshape(-1, 3, 3)
    bot = np.concatenate(
        (
            np.stack((pack(x00, y00, zero), pack(x01, y01, zero), pack(x11, y11, zero)), axis=-2),
            np.stack((pack(x00, y00, zero), pack(x11, y11, zero), pack(x10, y10, zero)), axis=-2),
        ),
        axis=0,
    ).reshape(-1, 3, 3)

    def wall(xa, ya, za, xb, yb, zb) -> np.ndarray:
        z0 = np.zeros_like(za)
        # Opposite of the cap-following order: that one pointed into the solid.
        return np.concatenate(
            (
                np.stack((pack(xa, ya, za), pack(xb, yb, z0), pack(xb, yb, zb)), axis=-2),
                np.stack((pack(xa, ya, za), pack(xa, ya, z0), pack(xb, yb, z0)), axis=-2),
            ),
            axis=0,
        ).reshape(-1, 3, 3)

    # Outward walls. Indexing is xy, so axis 0 is X and axis 1 is Y.
    south = wall(x[:, 0][:-1], y[:, 0][:-1], z[:, 0][:-1], x[:, 0][1:], y[:, 0][1:], z[:, 0][1:])
    north = wall(x[:, -1][1:], y[:, -1][1:], z[:, -1][1:], x[:, -1][:-1], y[:, -1][:-1], z[:, -1][:-1])
    west = wall(x[0, :][1:], y[0, :][1:], z[0, :][1:], x[0, :][:-1], y[0, :][:-1], z[0, :][:-1])
    east = wall(x[-1, :][:-1], y[-1, :][:-1], z[-1, :][:-1], x[-1, :][1:], y[-1, :][1:], z[-1, :][1:])
    return np.concatenate((top, bot, south, north, west, east), axis=0)


def write_stl(path: Path, tris: np.ndarray) -> int:
    tris = np.ascontiguousarray(tris, dtype=np.float32)
    count = int(tris.shape[0])
    rec = np.zeros(count, dtype=[("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
    a = tris[:, 1] - tris[:, 0]
    b = tris[:, 2] - tris[:, 0]
    normal = np.cross(a, b)
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    np.divide(normal, length, out=normal, where=length > 0)
    rec["n"] = normal
    rec["v"] = tris
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"zeim resin bench".ljust(80, b"\0"))
        handle.write(struct.pack("<I", count))
        handle.write(rec.tobytes())
    return count


def translate_corner(tris: np.ndarray, build_width_mm: float, build_depth_mm: float) -> np.ndarray:
    out = np.array(tris, copy=True)
    out[:, :, 0] += np.float32(build_width_mm * 0.5)
    out[:, :, 1] += np.float32(build_depth_mm * 0.5)
    return out


def ensure_meshes(cache: Path) -> dict[str, dict]:
    cache.mkdir(parents=True, exist_ok=True)
    made = {
        "box": mesh_box(),
        "asymmetric": mesh_asymmetric(),
        "sculpt": mesh_sculpt(int(SCULPT["grid"])),
    }
    out: dict[str, dict] = {}
    for name, tris in made.items():
        path = cache / f"{name}.stl"
        count = write_stl(path, tris)
        lo = tris.reshape(-1, 3).min(axis=0)
        hi = tris.reshape(-1, 3).max(axis=0)
        out[name] = {
            "path": path,
            "triangles": count,
            "min_mm": [float(v) for v in lo],
            "max_mm": [float(v) for v in hi],
            "tris": tris,
        }
    if out["sculpt"]["triangles"] < 900_000:
        raise RuntimeError(f"sculpt has {out['sculpt']['triangles']} triangles, need at least 900000")
    return out
