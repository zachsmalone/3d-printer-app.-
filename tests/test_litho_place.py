"""Lithophane image placement (move / zoom / rotate inside the shape)."""
import io
import numpy as np
import pytest
from PIL import Image

from app.core import geometry, litho_shapes

SHAPES = litho_shapes.FLAT_SHAPES + litho_shapes.CURVED_SHAPES


def img():
    a = np.zeros((160, 240, 3), np.uint8)
    a[:, :80] = 255; a[40:90, 150:200] = 128
    return Image.fromarray(a)


def build(shape, place=None):
    p = dict(shape=shape, width_mm=60, min_thickness=0.8, max_thickness=3.0, border_mm=2, resolution=60,
             diameter_mm=30, height_mm=30, auto_contrast=False, smooth=0)
    if place is not None:
        p["place"] = place
    return geometry.build(img(), "lithophane", p).solid()[0]


@pytest.mark.parametrize("shape", SHAPES)
def test_default_unchanged(shape):
    a = build(shape)
    for ident in ({}, {"x": 0, "y": 0, "scale": 1, "rotation": 0}, {"rotation": 360}):
        assert np.array_equal(a, build(shape, ident))


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("place", [{"x": 0.3}, {"y": -0.2}, {"scale": 0.5}, {"scale": 2}, {"rotation": 90}])
def test_transform_changes_output(shape, place):
    a, b = build(shape), build(shape, place)
    assert a.shape == b.shape and not np.allclose(a, b)


def test_wrap_shift_is_a_roll():
    from app.core.litho_shapes import thickness_map
    im = img()
    a = thickness_map(im, 100, 50, 0.8, 3, 0, 1, False, place={"x": 0, "y": 0, "scale": 1, "rotation": 0}, wrap=True)
    b = thickness_map(im, 100, 50, 0.8, 3, 0, 1, False, place={"x": 0.25, "y": 0, "scale": 1, "rotation": 0}, wrap=True)
    assert np.allclose(np.roll(a, 25, 1), b, atol=1e-9)          # moved round the cylinder, no white gap


@pytest.mark.parametrize("bad", [{"x": 2}, {"y": -1.5}, {"scale": 0}, {"scale": 50}, {"x": "nan"}, {"scale": "inf"},
                                 {"rotation": "abc"}, {"rotation": 1e9}])
def test_bad_values_rejected(bad):
    with pytest.raises(ValueError):
        litho_shapes.check_place(bad)


def test_api_rejects_and_accepts():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    buf = io.BytesIO(); img().save(buf, "PNG")
    def post(**extra):
        data = dict(mode="lithophane", shape="heart", width_mm="60", resolution="40", **extra)
        return client.post("/api/generate", data=data, files={"file": ("p.png", buf.getvalue(), "image/png")})
    assert post(place_scale="99").status_code == 400
    assert post(place_x="nan").status_code == 400
    r = post(place_x="0.2", place_scale="1.5", place_rotation="-90")
    assert r.status_code == 200, r.text
    assert r.json()["params"]["place"] == {"x": 0.2, "y": 0.0, "scale": 1.5, "rotation": 270.0}
    r = post()
    assert r.status_code == 200 and "place" not in r.json()["params"]
    for b in client.get("/api/builds").json()["builds"]:
        client.delete("/api/builds/" + b["id"])
