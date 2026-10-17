"""Hanging holes for flat lithophanes (docs/specs/lithophane-upgrade-spec.md, Phase 2).

A hole is cut through the rim band at the top of the plate so the print can hang from
twine on a window (suction cups) or a hook. Holes live entirely in rim material (max
thickness) so they are strong; the caller widens the border first if needed
(border_needed). The cut is a manifold boolean, so the result stays watertight and the
plate gains one handle (genus) per hole.

Only flat shapes are supported: curved shells (globe/nightlight/cup) hang differently
and are refused with a clear error.
"""
from __future__ import annotations

import numpy as np
import trimesh

HANG_STYLES = ("top", "two")
MIN_HOLE_D, MAX_HOLE_D = 2.0, 8.0
MIN_INSET, MAX_INSET = 3.0, 15.0
MIN_SPACING, MAX_SPACING = 20.0, 120.0
WALL_MM = 1.6            # 4 perimeters at a 0.4 mm nozzle: the smallest reliable wall around a hole
SECTIONS = 48            # cylinder facets (holes are round to the eye, cheap to slice)


def check_hang(hang, hole_d=4.0, inset_mm=6.0, spacing_mm=40.0) -> dict:
    """Validate the hang options and return them normalised. Raises ValueError."""
    if hang not in HANG_STYLES:
        raise ValueError(f"hang must be one of {' | '.join(HANG_STYLES)} (got {hang!r})")
    if not (MIN_HOLE_D <= hole_d <= MAX_HOLE_D):
        raise ValueError(f"hole_d must be {MIN_HOLE_D:g}..{MAX_HOLE_D:g} mm")
    if not (MIN_INSET <= inset_mm <= MAX_INSET):
        raise ValueError(f"inset_mm must be {MIN_INSET:g}..{MAX_INSET:g} mm")
    if not (MIN_SPACING <= spacing_mm <= MAX_SPACING):
        raise ValueError(f"spacing_mm must be {MIN_SPACING:g}..{MAX_SPACING:g} mm")
    return dict(hang=hang, hole_d=float(hole_d), inset_mm=float(inset_mm), spacing_mm=float(spacing_mm))


def border_needed(hole_d: float, inset_mm: float) -> float:
    """Rim width that keeps the whole hole inside solid rim material (max thickness)."""
    return inset_mm + hole_d / 2.0


def positions(hang: str, width_mm: float, height_mm: float,
              hole_d: float, inset_mm: float, spacing_mm: float) -> list[tuple[float, float]]:
    """Hole centres in plate mm coordinates (x: 0..width, y: 0..height, top edge at y = height).

    Raises ValueError when a hole would come closer than WALL_MM to a plate edge.
    """
    cx = width_mm / 2.0
    y = height_mm - inset_mm
    if hang == "top":
        pts = [(cx, y)]
    else:                                            # "two": symmetric pair, spacing between centres
        half_s = spacing_mm / 2.0
        pts = [(cx - half_s, y), (cx + half_s, y)]
    r = hole_d / 2.0
    for (x, yy) in pts:
        if x - r < WALL_MM or x + r > width_mm - WALL_MM:
            raise ValueError("hanging hole is too close to the side edge: reduce hole_d or spacing_mm, "
                             "or use a wider plate")
        if yy + r > height_mm - WALL_MM or yy - r < WALL_MM:
            raise ValueError("hanging hole is too close to the top or bottom edge: adjust inset_mm")
    return pts


def points_in_poly(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Even-odd ray casting: True for points strictly inside the polygon (poly = (N,2), open loop)."""
    pts = np.asarray(pts, float)
    poly = np.asarray(poly, float)
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        straddle = (y1 > y) != (y2 > y)                # edge crosses the horizontal ray
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
        inside ^= straddle & (x < xint)
    return inside


def fit_check(centres, hole_d: float, poly: np.ndarray) -> None:
    """Every point of the hole circle (plus the wall margin) must be inside the outline.

    Raises ValueError with guidance when a hole would fall outside the shape (e.g. the
    notch of a heart, the round edge of a circle with the "two" style).
    """
    for (cx, cy) in centres:
        ang = np.linspace(0, 2 * np.pi, 33)[:-1]
        for rr, what in ((hole_d / 2.0, "hole"), (hole_d / 2.0 + WALL_MM, "wall around the hole")):
            pts = np.stack([cx + rr * np.cos(ang), cy + rr * np.sin(ang)], -1)
            if not points_in_poly(pts, poly).all():
                raise ValueError(
                    f"hanging hole at ({cx:.1f}, {cy:.1f}) mm does not fit inside the shape: the {what} "
                    "would leave the plate. Try the 'top' style, a smaller hole_d, a smaller inset_mm, "
                    "or a wider plate")


def punch(v, f, centres, hole_d: float, z_top: float):
    """Cut the holes through the plate (z: 0..z_top) with manifold booleans; returns (verts, faces)."""
    mesh = trimesh.Trimesh(vertices=np.asarray(v, float), faces=np.asarray(f, np.int64), process=False)
    if not mesh.is_watertight:
        raise ValueError("cannot cut hanging holes: the lithophane mesh is not watertight")
    for (cx, cy) in centres:
        h = z_top + 2.0                               # cylinder pokes out both faces: a clean through cut
        cyl = trimesh.creation.cylinder(
            radius=hole_d / 2.0, height=h, sections=SECTIONS,
            transform=trimesh.transformations.translation_matrix([cx, cy, h / 2.0 - 1.0]))
        mesh = trimesh.boolean.difference([mesh, cyl], engine="manifold")
    if not mesh.is_watertight:
        raise ValueError("cutting the hanging holes produced a non-watertight mesh")
    return np.asarray(mesh.vertices, float), np.asarray(mesh.faces, np.int64)
