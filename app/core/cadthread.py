"""Threaded connectors for Edit (upgrade 9).

Approximate ISO-metric external / internal threads as stacked frustum rings
(trapezoidal profile). Good enough for FDM fit after a test print — not a
machine-shop thread mill. Clearance widens the female / shrinks the male.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

from .meshedit import OpError, _boolean, _new


# Common metric pitches (mm) when user leaves pitch auto
_METRIC_PITCH = {
    2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0, 8: 1.25,
    10: 1.5, 12: 1.75, 16: 2.0, 20: 2.5,
}


def _pitch_for(d: float) -> float:
    keys = sorted(_METRIC_PITCH)
    best = min(keys, key=lambda k: abs(k - d))
    return _METRIC_PITCH[best]


def _helix_mesh(major_d: float, pitch: float, length: float, *,
                internal: bool, clearance: float, sections: int = 24) -> trimesh.Trimesh:
    """Build a threaded cylinder (external male or internal cutter)."""
    # Thread depth ~ 0.54 * pitch for metric 60° V
    depth = 0.54 * pitch
    # Clearance: male shrinks, female (cutter) grows
    adj = clearance if internal else -clearance
    r_major = major_d / 2 + adj
    r_minor = r_major - depth
    if r_minor < 0.2:
        raise OpError("Thread diameter too small for this pitch/clearance.")
    n_turns = max(1, int(math.ceil(length / pitch)))
    # Approximate with stacked truncated cones (crest→root→crest) per half-pitch
    parts = []
    z = 0.0
    half = pitch / 2
    for i in range(n_turns * 2):
        r_bot = r_major if (i % 2 == 0) else r_minor
        r_top = r_minor if (i % 2 == 0) else r_major
        h = min(half, length - z)
        if h <= 1e-4:
            break
        fr = trimesh.creation.cone(radius=r_bot, height=h, sections=sections)
        # cone tip at origin pointing +Z; we want a frustum — use cylinder of mean radius as approximation
        # Better: annulus extruded via cylinder then we accept truncated cone via creation.cone scaled
        cyl = trimesh.creation.cylinder(radius=(r_bot + r_top) / 2, height=h, sections=sections)
        # Taper vertices toward axis based on z within segment
        v = cyl.vertices.copy()
        z0 = v[:, 2].min()
        t = (v[:, 2] - z0) / max(h, 1e-9)
        r_at = r_bot + (r_top - r_bot) * t
        xy = v[:, :2]
        rad = np.linalg.norm(xy, axis=1)
        rad = np.where(rad < 1e-9, 1.0, rad)
        scale = r_at / rad
        v[:, 0] *= scale
        v[:, 1] *= scale
        v[:, 2] += z - z0
        parts.append(_new(v, cyl.faces))
        z += h
        if z >= length - 1e-6:
            break
    if not parts:
        raise OpError("Could not build thread geometry.")
    body = trimesh.util.concatenate(parts)
    # Core shaft so boolean is solid (male) / solid cutter (female)
    core_r = r_minor * 0.95 if not internal else r_major + 0.05
    core = trimesh.creation.cylinder(radius=max(core_r, 0.15), height=length, sections=sections)
    core.apply_translation([0, 0, length / 2])
    body = _boolean(body, core, "union") if not internal else body
    # Center at origin bottom on z=0
    body.apply_translation([0, 0, -body.bounds[0][2]])
    return body


def make_thread(params: dict[str, Any]) -> trimesh.Trimesh:
    """Standalone threaded connector mesh (for export / boolean)."""
    kind = (params.get("kind") or "external").lower()  # external | internal
    d = float(params.get("diameter") or 6)
    length = float(params.get("length") or max(d * 1.5, 8))
    pitch = float(params.get("pitch") or 0) or _pitch_for(d)
    clearance = float(params.get("clearance") or 0.2)
    if d < 1.5 or d > 40:
        raise OpError("Thread diameter must be between 1.5 and 40 mm.")
    if length < pitch * 2 or length > 120:
        raise OpError("Thread length must be at least 2 pitches and under 120 mm.")
    if pitch < 0.2 or pitch > 4:
        raise OpError("Pitch must be between 0.2 and 4 mm.")
    internal = kind in ("internal", "female", "nut")
    return _helix_mesh(d, pitch, length, internal=internal, clearance=clearance)


def op_thread(mesh: trimesh.Trimesh, p: dict) -> tuple[trimesh.Trimesh, dict]:
    """Boolean a threaded feature onto/into the model.

    mode: add|external|male (union stud) | cut|internal|female|nut (difference hole)
    position: [x,y,z] tip/base of thread axis
    axis: x|y|z direction of the thread axis (default z)
    """
    mode_raw = (p.get("mode") or "add").lower().strip()
    if mode_raw in ("add", "external", "male", "stud", "bolt"):
        add = True
        kind = "external"
        mode = "external"
    elif mode_raw in ("cut", "internal", "female", "nut", "hole"):
        add = False
        kind = "internal"
        mode = "internal"
    else:
        raise OpError("Thread mode must be external (add) or internal (cut).")
    thr = make_thread({**p, "kind": kind})
    axis = (p.get("axis") or "z").lower()
    pos = p.get("position") or [0, 0, 0]
    if len(pos) != 3:
        raise OpError("position must be [x, y, z] in mm.")
    # Orient from +Z to requested axis
    if axis == "x":
        thr.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    elif axis == "y":
        thr.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    thr.apply_translation(pos)
    if add:
        out = _boolean(mesh, thr, "union")
        msg = f"Added M{float(p.get('diameter') or 6):g} external thread ({float(p.get('length') or 0):g} mm)."
    else:
        out = _boolean(mesh, thr, "difference")
        msg = f"Cut M{float(p.get('diameter') or 6):g} internal thread ({float(p.get('length') or 0):g} mm)."
    return out, {
        "message": msg + " Fit is Simulated until you test-print.",
        "connector_fit": "simulated",
        "diameter": float(p.get("diameter") or 6),
        "pitch": float(p.get("pitch") or 0) or _pitch_for(float(p.get("diameter") or 6)),
        "clearance": float(p.get("clearance") or 0.2),
        "mode": mode,
    }
