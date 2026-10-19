"""QA N1: mirroring a body (copy or not, any axis / pivot) keeps it outside-out with +volume."""
import numpy as np
import pytest
import trimesh

from app.core import cadops


def _cube():
    return cadops._new(*(lambda b: (b.vertices, b.faces))(trimesh.creation.box((20, 20, 20))))


def _outward(b):
    return float((b.face_normals * (b.triangles_center - b.centroid)).sum(axis=1).min()) > 0


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("pivot", ["center", "origin", [-1, 0, 0], [35, -40, 12]])
def test_mirror_keeps_positive_volume(axis, pivot):
    m = _cube()
    out, _ = cadops.op_body_transform(m, {"body": 0, "mirror": axis, "pivot": pivot})
    assert out.is_watertight and out.volume == pytest.approx(8000, rel=1e-6)
    assert all(_outward(b) for b in cadops.bodies(out))


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_mirror_copy_two_positive_bodies(axis):
    m = _cube()
    piv = [0, 0, 0]; piv["xyz".index(axis)] = -11  # mirror plane 1 mm off the cube: no touching
    out, _ = cadops.op_body_transform(m, {"body": 0, "mirror": axis, "copy": True, "pivot": piv})
    bs = cadops.bodies(out)
    assert len(bs) == 2 and out.volume == pytest.approx(16000, rel=1e-6)
    assert [round(float(b.volume), 3) for b in bs] == [8000.0, 8000.0]
    assert all(b.is_watertight and _outward(b) for b in bs)


def test_qa_repro_mirror_copy_pivot_minus_one():
    """The exact QA steps: 20 mm cube from the CAD 'new' flow, mirror x copy, pivot (-1, 0, 0)."""
    m = cadops._new(*(lambda b: (b.vertices, b.faces))(trimesh.creation.box((20, 20, 20), transform=trimesh.transformations.translation_matrix([10, 10, 10]))))
    out, _ = cadops.op_body_transform(m, {"body": 0, "mirror": "x", "copy": True, "pivot": [-1, 0, 0]})
    assert sorted(round(float(b.volume), 3) for b in cadops.bodies(out)) == [8000.0, 8000.0]


@pytest.mark.parametrize("p", [{"move": [5, 0, 0]}, {"rotate": [30, 45, 10]}, {"scale": [2, 1, 0.5]},
                               {"rotate": [0, 0, 90], "scale": [1.5, 1.5, 1.5], "pivot": "origin"}])
def test_non_mirror_transforms_unchanged(p):
    m = _cube()
    out, _ = cadops.op_body_transform(m, dict(p, body=0))
    exp = 8000 * float(np.prod(p.get("scale", [1, 1, 1])))
    assert out.volume == pytest.approx(exp, rel=1e-6) and _outward(out)
