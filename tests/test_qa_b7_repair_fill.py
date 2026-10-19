"""QA B7: Fix mesh on a non-flat hole must follow the hole (not cut a wedge out) and still say the patch is a guess."""
import numpy as np
import pytest
import trimesh

from app.core import meshedit


# samples/open_flipped.stl from the QA run: a 20 mm cube with the two triangles on x=0 / y=0 next to the edge x=y=0
# removed (one 4-edge hole bent 90°) and some faces flipped. Before the fix: watertight, but 6 666.67 mm³.
OPEN_V = [[0, 20, 0], [0, 20, 20], [0, 0, 0], [20, 0, 0], [20, 20, 20], [0, 0, 20], [20, 0, 20], [20, 20, 0]]
OPEN_F = [[0, 1, 2], [2, 3, 0], [1, 4, 5], [3, 5, 6], [6, 4, 5], [1, 4, 0], [7, 3, 0], [0, 4, 7], [7, 6, 3], [4, 6, 7]]


def _open_cube_bent_hole():
    return trimesh.Trimesh(np.array(OPEN_V, float), np.array(OPEN_F), process=False)


def test_bent_hole_keeps_cube_volume_and_warns():
    m = _open_cube_bent_hole()
    assert not m.is_watertight
    out, rep = meshedit.op_repair(m, {})
    assert out.is_watertight and rep["after"]["watertight"]
    assert out.volume == pytest.approx(8000, rel=0.01)      # was 6 666.67 (corner cut off)
    assert len(out.faces) == 12
    assert "weren't flat" in rep["warning"] and "check filled areas" in rep["message"]


def test_bent_hole_on_finer_mesh():
    """A bigger bent hole (many-edge loop) across a box edge on a subdivided box."""
    b = trimesh.creation.box((20, 20, 20), transform=trimesh.transformations.translation_matrix([10, 10, 10])).subdivide().subdivide()
    c = b.triangles_center
    near = (np.linalg.norm(c[:, :2], axis=1) < 6) & (np.abs(c[:, 2] - 10) < 6) & ((c[:, 0] < 1e-6) | (c[:, 1] < 1e-6))
    m = trimesh.Trimesh(b.vertices, b.faces[~near], process=False)
    out, rep = meshedit.op_repair(m, {})
    assert out.is_watertight and out.volume == pytest.approx(8000, rel=0.01)


def test_flat_hole_unchanged_and_no_warning():
    b = trimesh.creation.box((20, 20, 20))
    m = trimesh.Trimesh(b.vertices, b.faces[1:], process=False)   # one triangle missing on one face: flat hole
    out, rep = meshedit.op_repair(m, {})
    assert out.is_watertight and out.volume == pytest.approx(8000, rel=1e-6)
    assert "warning" not in rep and rep["message"] == "Mesh is watertight ✔"


def test_closed_mesh_untouched():
    s = trimesh.creation.icosphere(2, 10)
    out, rep = meshedit.op_repair(trimesh.Trimesh(s.vertices, s.faces, process=False), {})
    assert out.volume == pytest.approx(s.volume, rel=1e-9) and len(out.faces) == len(s.faces) and "warning" not in rep
