"""Shared helpers for the batch-1 test files (tests/test_b1_*.py)."""
import io, json, os, tempfile, time
_tmp = tempfile.mkdtemp()
os.environ.setdefault("PHOTO3D_OUT", _tmp + "/out"); os.environ.setdefault("PHOTO3D_DATA", _tmp + "/data")
os.environ.setdefault("PHOTO3D_ADMIN_TOKEN", "t0k")
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest, trimesh
from fastapi.testclient import TestClient
from PIL import Image
from app import config
from app.main import app
from app.community import classrooms, moderation
from app.core import ratelimit  # noqa
from tests.make_sample import make

SAMPLE = make(_tmp + "/s3.png")
ADMIN = {"X-Admin-Token": "t0k"}
ADULT = {"display_name": "Ada Adult", "dob": "1985-05-05"}
TEEN = {"display_name": "Tess Teen", "dob": "2011-01-01"}


def client(user=None):
    c = TestClient(app)
    if user:
        r = c.post("/api/me/signup", json=user); assert r.status_code == 200, r.text
    return c



def gen(c, ack=True, name="s.png", data=None, ctype="image/png", mode="relief", **extra):
    form = {"mode": mode, "width_mm": "50", "resolution": "40", **extra}
    if ack: form["photo_ack"] = "true"
    return c.post("/api/generate", files={"file": (name, data if data is not None else open(SAMPLE, "rb").read(), ctype)}, data=form)


def photo_build(c): r = gen(c); assert r.status_code == 200, r.text; return r.json()["id"]


def make_class(teacher=None, pw="pass-123", name="Period 1"):
    t = teacher or client(ADULT)
    room = t.post("/api/classrooms", json={"name": name, "password": pw}).json()
    return t, room["code"], pw


def join(s, code, pw, nick, **kw):
    return s.post("/api/classrooms/join", json={"code": code, "nickname": nick, "password": pw, **kw})


def student(code, pw, nick):
    s = client(); assert join(s, code, pw, nick).status_code == 200; return s


def jpeg_with_gps():
    im = Image.open(SAMPLE).convert("RGB")
    ex = Image.Exif()
    ex[0x010F] = "SecretCam"                       # Make
    ex[0x8825] = {1: "N", 2: (41.0, 52.0, 0.0), 3: "W", 4: (87.0, 38.0, 0.0)}   # GPS IFD
    b = io.BytesIO(); im.save(b, "JPEG", exif=ex); return b.getvalue()




def box_stl():
    return trimesh.creation.box([10, 10, 10]).export(file_type="stl")
