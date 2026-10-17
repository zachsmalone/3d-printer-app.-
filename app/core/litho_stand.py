"""One-piece display stand for flat lithophane panels (docs/specs/lithophane-upgrade-spec.md, Phase 2).

A U-channel base: the panel stands on edge, slotted into the groove; the channel runs the
whole length so the panel drops in from the end. Printed opening-up it needs no supports
and no brim (flat base, generous walls). Generated as a second body of the lithophane
model, so one download contains both parts and the exports (STL/OBJ/3MF) carry both.

Geometry is a box with a lengthwise groove cut through both ends (a manifold boolean), so
the result is watertight and slicer-friendly.
"""
from __future__ import annotations

import numpy as np
import trimesh

GROOVE_CLEARANCE_MM = 0.4     # slip fit: groove = panel max thickness + this
MARGIN_MM = 5.0                # the channel extends this far past the panel on each side
MIN_WALL_MM = 2.0              # printable wall: sides and under the groove
DEFAULT_BASE_DEPTH = 14.0      # front-to-back
DEFAULT_GROOVE_DEPTH = 5.0     # how deep the panel sits in the channel
MIN_PANEL_WIDTH, MAX_PANEL_WIDTH = 20.0, 400.0
MIN_PANEL_THICKNESS, MAX_PANEL_THICKNESS = 0.5, 12.0


def stand(panel_width_mm: float, panel_thickness_mm: float):
    """Build the channel stand for a flat panel. Returns (verts, faces, info).

    Raises ValueError for out-of-range panels.
    """
    if not (MIN_PANEL_WIDTH <= panel_width_mm <= MAX_PANEL_WIDTH):
        raise ValueError(f"stand needs a panel {MIN_PANEL_WIDTH:g}..{MAX_PANEL_WIDTH:g} mm wide")
    if not (MIN_PANEL_THICKNESS <= panel_thickness_mm <= MAX_PANEL_THICKNESS):
        raise ValueError(f"stand needs a panel {MIN_PANEL_THICKNESS:g}..{MAX_PANEL_THICKNESS:g} mm thick")

    groove_w = panel_thickness_mm + GROOVE_CLEARANCE_MM
    depth = max(DEFAULT_BASE_DEPTH, groove_w + 2 * MIN_WALL_MM)     # side walls >= MIN_WALL
    height = max(8.0, DEFAULT_GROOVE_DEPTH + MIN_WALL_MM)          # base under the groove >= MIN_WALL
    groove_d = min(DEFAULT_GROOVE_DEPTH, height - MIN_WALL_MM)
    length = panel_width_mm + 2 * MARGIN_MM

    base = trimesh.creation.box(
        extents=[length, depth, height],
        transform=trimesh.transformations.translation_matrix([length / 2.0, 0.0, height / 2.0]))
    # groove: floor exactly at height - groove_d, through the top face and past BOTH ends
    # -> an open channel, panel slides in
    groove = trimesh.creation.box(
        extents=[length + 4.0, groove_w, groove_d + 1.0],
        transform=trimesh.transformations.translation_matrix(
            [length / 2.0, 0.0, height - groove_d / 2.0 + 0.5]))
    m = trimesh.boolean.difference([base, groove], engine="manifold")
    if not m.is_watertight:
        raise ValueError("stand geometry is not watertight")
    v = np.asarray(m.vertices, float)
    f = np.asarray(m.faces, np.int64)
    if v.min(0)[2] < -1e-9 or abs(v.max(0)[2] - height) > 1e-6:
        raise ValueError("stand geometry did not come out as expected")
    info = dict(length_mm=round(length, 3), depth_mm=round(depth, 3), height_mm=round(height, 3),
                groove_width_mm=round(groove_w, 3), groove_depth_mm=round(groove_d, 3),
                panel_width_mm=round(panel_width_mm, 3), panel_thickness_mm=round(panel_thickness_mm, 3))
    return v, f, info


def fits(groove_width_mm: float, panel_thickness_mm: float) -> bool:
    """True when the panel (its thickest, dark section) drops into the groove."""
    return groove_width_mm - GROOVE_CLEARANCE_MM >= panel_thickness_mm - 1e-9
