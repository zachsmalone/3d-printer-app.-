"""CAD beginner shapes (original ZEIM code): drop a simple solid (cube, cylinder, sphere, cone, torus,
tube, wedge) on the bed as a new body, join it to the model, or cut it out as a hole. Geometry reuses the
parts builder's primitives (app/core/parts.py); booleans go through cadops._combine (manifold3d)."""
from __future__ import annotations

import numpy as np
import trimesh

from . import cadops as C
from . import parts
from .meshedit import OpError

KINDS = ("box", "cylinder", "sphere", "cone", "torus", "tube", "wedge")
MODES = ("new", "join", "cut")
KEYS = {"kind", "dims", "position", "rotation", "mode", "replace"}
NAMES = {"box": "Cube", "cylinder": "Cylinder", "sphere": "Sphere", "cone": "Cone", "torus": "Ring",
         "tube": "Tube", "wedge": "Wedge"}


def _wedge(size):
    x, y, z = (s / 2 for s in size)
    # right-angled ramp: full height at -x, zero at +x (a triangular prism along y)
    v = np.array([[-x, -y, -z], [x, -y, -z], [-x, -y, z], [-x, y, -z], [x, y, -z], [-x, y, z]], float)
    f = np.array([[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2], [1, 2, 5], [1, 5, 4]])
    m = trimesh.Trimesh(v, f, process=True)
    m.fix_normals()
    return m


def shape_mesh(p: dict) -> trimesh.Trimesh:
    kind = p.get("kind", "box")
    if kind not in KINDS:
        raise OpError(f"kind must be one of {' | '.join(KINDS)}.")
    try:
        pos = parts._vec3(p.get("position") or [0, 0, 0], "position", -parts.MAX_POS, parts.MAX_POS)
        rot = parts._vec3(p.get("rotation") or [0, 0, 0], "rotation", -360.0, 360.0)
        if kind == "wedge":
            d = parts._dims("box", p.get("dims") or {}, "Wedge")
            m = _wedge(d["size"])
            T = np.eye(4); T[:3, :3] = trimesh.transformations.euler_matrix(*np.radians(rot), axes="sxyz")[:3, :3]
            m.apply_transform(T)
        else:
            d = parts._dims(kind, p.get("dims") or {}, NAMES[kind])
            m = parts._part_mesh({"kind": kind, "dims": d, "position": [0, 0, 0], "rotation": rot})
    except parts.RecipeError as e:
        raise OpError(str(e))
    # position = centre of the shape's footprint, resting on its bottom (easy to drop on the bed)
    lo, hi = m.bounds
    m.apply_translation([pos[0] - (lo[0] + hi[0]) / 2, pos[1] - (lo[1] + hi[1]) / 2, pos[2] - lo[2]])
    return C._new(m.vertices, m.faces)


def op_cad_shape(m, p):
    mode = p.get("mode", "new")
    if mode not in MODES:
        raise OpError("mode must be new | join | cut")
    tool = shape_mesh(p)
    out = C.combine_keeping_ids(m, tool, mode, bool(p.get("replace")))
    word = {"new": "Added", "join": "Joined", "cut": "Cut a hole with"}[mode]
    return out, {"message": f"{word} a {NAMES[p.get('kind', 'box')].lower()}."}


def label(p: dict) -> str:
    mode = {"new": "", "join": " (joined)", "cut": " hole"}.get(p.get("mode", "new"), "")
    return f"{NAMES.get(p.get('kind'), 'Shape')}{mode}"
