"""The user-facing sample is the cat photo: web-sized, no EXIF/GPS, and its model was made with ZEIM's own pipeline."""
import io, os
import trimesh
from PIL import Image
from tests.b1 import client, gen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JPG = os.path.join(ROOT, "static", "sample.jpg")


def test_sample_photo_is_web_sized_and_has_no_metadata():
    assert not os.path.exists(os.path.join(ROOT, "static", "sample.png"))      # the old smiley test image is gone from the app
    assert os.path.getsize(JPG) < 150_000
    im = Image.open(JPG)
    assert im.format == "JPEG" and im.size == (600, 800)
    assert not dict(im.getexif()) and "exif" not in im.info and "icc_profile" not in im.info


def test_sample_model_is_a_watertight_relief_of_the_sample_photo():
    m = trimesh.load(os.path.join(ROOT, "static", "sample_model.stl"))
    assert m.is_watertight and m.body_count == 1
    x, y, z = m.extents
    assert abs(x - 80) < 0.5 and abs(y / x - 800 / 600) < 0.02 and 7 < z < 9
    assert os.path.getsize(os.path.join(ROOT, "static", "sample_model.stl")) < 2_000_000


def test_sample_builds_and_gets_the_friendly_titles():
    c = client()
    r = gen(c, data=open(JPG, "rb").read(), name="IMG_0001.jpg", ctype="image/jpeg"); assert r.status_code == 200, r.text
    assert r.json()["title"] == "Sample photo"
    stl = open(os.path.join(ROOT, "static", "sample_model.stl"), "rb").read()
    assert c.post("/api/edit/new", files={"file": ("x.stl", stl, "application/octet-stream")}).json()["title"] == "Sample model"


def test_ui_loads_the_jpeg_sample():
    for f in ("app.js", "edit.js"):
        s = open(os.path.join(ROOT, "static", f), encoding="utf-8").read()
        assert "/static/sample.jpg" in s and "/static/sample.png" not in s
