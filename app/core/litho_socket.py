"""Print-friendly mechanical sockets for the lithophane stand system.

End-cap plugs: two friction-fit caps that push into the open ends of the U-channel
stand, so the panel cannot slide out. Separate bodies in the same download (named
stand_cap_a / stand_cap_b). Not an electrical socket — plastic mechanical stops only.

Also exposes sizes so the UI can say honestly what they are.
"""
from __future__ import annotations

import numpy as np
import trimesh

from . import litho_stand

# Plug sits slightly under groove width / depth for a push fit (PLA shrinks a little).
FIT_UNDER_MM = 0.25
CAP_LIP_MM = 2.0          # outer flange that stops the plug going all the way in
CAP_INSERT_MM = 6.0       # how deep the plug goes into the channel
MIN_PANEL_W = litho_stand.MIN_PANEL_WIDTH


def check(on) -> bool:
    if isinstance(on, str):
        return on.strip().lower() in ("1", "true", "yes", "on")
    return bool(on)


def end_caps(panel_width_mm: float, panel_thickness_mm: float):
    """Two watertight end-cap plugs sized to the stand groove. Returns [(v,f,name,info), ...]."""
    if not (litho_stand.MIN_PANEL_WIDTH <= panel_width_mm <= litho_stand.MAX_PANEL_WIDTH):
        raise ValueError("stand caps need a panel in the stand's width range")
    if not (litho_stand.MIN_PANEL_THICKNESS <= panel_thickness_mm <= litho_stand.MAX_PANEL_THICKNESS):
        raise ValueError("stand caps need a panel in the stand's thickness range")

    _, _, sinfo = litho_stand.stand(panel_width_mm, panel_thickness_mm)
    gw = sinfo["groove_width_mm"] - FIT_UNDER_MM
    gd = sinfo["groove_depth_mm"] - FIT_UNDER_MM
    depth = sinfo["depth_mm"]          # stand front-to-back; flange matches this
    if gw < 0.8 or gd < 1.0:
        raise ValueError("stand caps need a deeper / wider groove — thicken the panel a little")

    # Insert block (into groove) + outer flange plate
    insert = trimesh.creation.box(extents=[CAP_INSERT_MM, gw, gd])
    insert.apply_translation([CAP_INSERT_MM / 2.0, 0.0, gd / 2.0])
    flange = trimesh.creation.box(extents=[CAP_LIP_MM, depth, gd + 2.0])
    flange.apply_translation([-CAP_LIP_MM / 2.0, 0.0, (gd + 2.0) / 2.0 - 1.0])
    m = trimesh.boolean.union([insert, flange], engine="manifold")
    if not m.is_watertight:
        raise ValueError("stand cap geometry is not watertight")
    v = np.asarray(m.vertices, float)
    f = np.asarray(m.faces, np.int64)
    # sit on bed
    v[:, 2] -= v[:, 2].min()
    info = dict(kind="stand_end_cap", groove_width_mm=round(gw, 3), groove_depth_mm=round(gd, 3),
                insert_mm=CAP_INSERT_MM, lip_mm=CAP_LIP_MM,
                note="Friction-fit plastic end stops for the display stand — not an electrical socket.")
    # two copies; caller parks them beside the stand
    return [(v.copy(), f.copy(), "stand_cap_a", info),
            (v.copy(), f.copy(), "stand_cap_b", dict(info))]
