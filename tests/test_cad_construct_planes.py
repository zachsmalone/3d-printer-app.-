import numpy as np
import pytest
from app.core import sketch as sk
from app.core import cadops


def test_offset_named_plane():
    o, xd, yd, n = sk.plane({"offset": {"base": "XY", "distance": 12.5}})
    assert np.allclose(o, [0, 0, 12.5]) and np.allclose(n, [0, 0, 1]) and np.allclose(xd, [1, 0, 0])


def test_offset_face_plane_negative():
    o, _, _, n = sk.offset_plane({"origin": [1, 2, 3], "normal": [0, 2, 0]}, -4)
    assert np.allclose(o, [1, -2, 3]) and np.allclose(n, [0, 1, 0])


def test_midplane_between_parallel_faces_any_order():
    a = {"origin": [0, 0, 2], "normal": [0, 0, 1]}
    b = {"origin": [5, 5, 10], "normal": [0, 0, -1]}
    o, _, _, n = sk.plane({"mid": [a, b]})
    assert np.isclose(o[2], 6) and np.allclose(n, [0, 0, 1])
    o2, _, _, _ = sk.mid_plane("XY", {"offset": {"base": "XY", "distance": 30}})
    assert np.allclose(o2, [0, 0, 15])


def test_midplane_rejects_non_parallel():
    with pytest.raises(sk.SketchError):
        sk.plane({"mid": ["XY", "XZ"]})


@pytest.mark.parametrize("bad", [{"offset": "XY"}, {"offset": {"base": "XY", "distance": "x"}},
                                 {"offset": {"base": "XY", "distance": float("nan")}}, {"mid": ["XY"]},
                                 {"offset": {"base": {"offset": {"base": {"offset": {"base": {"offset": {"base": "XY", "distance": 1}}, "distance": 1}}, "distance": 1}}, "distance": 1}}])
def test_bad_construction_planes(bad):
    with pytest.raises(sk.SketchError):
        sk.plane(bad)


def test_clean_params_flattens_and_labels():
    sketch = {"entities": [{"id": "e1", "type": "circle", "c": [0, 0], "r": 5}], "constraints": []}
    out = cadops.clean_params("sketch_extrude", {"sketch": sketch, "plane": {"offset": {"base": "XY", "distance": 7}}, "distance": 3})
    assert out["plane"]["origin"] == [0, 0, 7] and out["plane"]["construct"] == "offset"
    with pytest.raises(cadops.OpError):
        cadops.clean_params("sketch_extrude", {"sketch": sketch, "plane": {"mid": ["XY", "YZ"]}, "distance": 3})
    # re-saved flattened plane keeps its label but a bogus label is dropped
    again = cadops.clean_params("sketch_extrude", {"sketch": sketch, "plane": out["plane"], "distance": 3})
    assert again["plane"]["construct"] == "offset"
    bogus = cadops.clean_params("sketch_extrude", {"sketch": sketch, "plane": {"origin": [0, 0, 0], "normal": [0, 0, 1], "construct": "<b>"}, "distance": 3})
    assert "construct" not in bogus["plane"]


def test_extrude_on_offset_plane_builds_at_height():
    sketch = {"entities": [{"id": "e1", "type": "circle", "c": [0, 0], "r": 5}], "constraints": []}
    p = cadops.clean_params("sketch_extrude", {"sketch": sketch, "plane": {"offset": {"base": "XY", "distance": 20}}, "distance": 4, "mode": "new"})
    assert p["plane"]["origin"][2] == 20
