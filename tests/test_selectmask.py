"""Select mode backend: the traced selection is parsed, snapped to edges and applied, so only the selected part
becomes the model (relief / pop-art: outside removed; lithophane: outside plain or flat), and it is kept in the build."""
import base64, io, json, os
import numpy as np, pytest, trimesh
from PIL import Image
from fastapi.testclient import TestClient
from app.core import geometry, selectmask
from app.main import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "static", "sample.png")         # built-in sample: sky, hills, a face and a sun at (360, 85) r~48
IM = Image.open(SAMPLE).convert("RGB")
W, H = IM.size
SUN_C, SUN_R = (360 / W, 85 / H), 48


def ring(cx, cy, rx, ry, n=40, wobble=0.0):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = 1 + wobble * np.sin(5 * a)
    return [[float(cx + rx * r[i] * np.cos(a[i])), float(cy + ry * r[i] * np.sin(a[i]))] for i in range(n)]


def sun_trace():                                              # a sloppy lasso ~1.35x the sun's radius
    return [{"op": "new", "pts": ring(SUN_C[0], SUN_C[1], 65 / W, 65 / H, wobble=0.06)}]


def sun_disk(w=W, h=H):
    yy, xx = np.mgrid[0:h, 0:w]
    return (xx - 360 * w / W) ** 2 + (yy - 85 * h / H) ** 2 <= (SUN_R * w / W) ** 2


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def test_parse_whole_photo_and_junk():
    assert selectmask.parse("") is None and selectmask.parse({"whole": True}) is None
    assert selectmask.parse({"paths": []}) is None
    with pytest.raises(selectmask.SelectError):
        selectmask.parse("{not json")
    with pytest.raises(selectmask.SelectError):
        selectmask.parse({"mask": base64.b64encode(b"not a png").decode()})
    s = selectmask.parse({"paths": [{"op": "weird", "pts": [[-1, 0], [2, 0], [0.5, 9]]}], "soft": 99, "outside": "x"})
    assert s["paths"][0]["op"] == "add" and s["soft"] == 20 and s["outside"] == "plain"
    assert all(0 <= v <= 1 for p in s["paths"][0]["pts"] for v in p)


def test_rasterize_add_subtract_new():
    sq = lambda x0, x1: [[x0, .1], [x1, .1], [x1, .9], [x0, .9]]
    m = selectmask.rasterize([{"op": "add", "pts": sq(.1, .9)}, {"op": "sub", "pts": sq(.4, .6)}], 100, 100)
    assert m[50, 20] and not m[50, 50] and m[50, 80]
    m = selectmask.rasterize([{"op": "add", "pts": sq(.1, .3)}, {"op": "new", "pts": sq(.6, .9)}], 100, 100)
    assert not m[50, 20] and m[50, 75]


def test_snap_hugs_the_subject_edge_better_than_the_rough_trace():
    sel = selectmask.parse({"paths": sun_trace(), "snap": True})
    rough = selectmask.rasterize(sel["paths"], W, H)
    snapped = selectmask.mask_for(IM, sel) >= 0.5
    truth = sun_disk()
    assert iou(rough, truth) < 0.7
    assert iou(snapped, truth) > 0.9, iou(snapped, truth)


def test_invert_and_soft_edge():
    sel = selectmask.parse({"paths": sun_trace(), "invert": True, "soft": 10})
    a = selectmask.mask_for(IM, sel)
    assert a[85, 360] < 0.05 and a[300, 50] > 0.95
    assert ((a > 0.1) & (a < 0.9)).sum() > 200                # a real ramp, not a hard step


def test_relief_keeps_only_the_selected_region_and_stays_watertight():
    sel = selectmask.parse({"paths": sun_trace()})
    full = geometry.build(IM, "relief", {"width_mm": 100, "resolution": 120})
    m = geometry.build(IM, "relief", {"width_mm": 100, "resolution": 120, "select": sel})
    v, f = m.solid(); t = trimesh.Trimesh(v, f)
    assert t.is_watertight and t.is_winding_consistent
    fv, ff = full.solid()
    assert len(f) < len(ff) * 0.6
    # footprint is a disc: its area is close to pi/4 of its bounding square (a rectangle would be ~1.0)
    ext = t.extents
    top_area = t.area_faces[t.face_normals[:, 2] < -0.99].sum()
    assert 0.65 < top_area / (ext[0] * ext[1]) < 0.9
    assert m.info["select"]["paths"] == 1


def test_popart_cut_both_bodies_and_single_mesh():
    sel = selectmask.parse({"paths": sun_trace()})
    m = geometry.build(IM, "popart", {"width_mm": 80, "resolution": 100, "select": sel})
    v, f = m.solid(); assert trimesh.Trimesh(v, f).is_watertight
    for b in m.bodies:
        assert trimesh.Trimesh(b.vertices, b.faces).is_watertight


@pytest.mark.parametrize("outside,thin", [("plain", True), ("flat", False)])
def test_lithophane_outside_is_plain_or_flat(outside, thin):
    sel = selectmask.parse({"paths": sun_trace(), "outside": outside})
    m = geometry.build(IM, "lithophane", {"width_mm": 100, "resolution": 120, "border_mm": 0, "auto_contrast": False, "select": sel})
    v, f = m.solid(); assert trimesh.Trimesh(v, f).is_watertight
    top = v[v[:, 2] > 0.01]
    corner = top[(top[:, 0] < 15) & (top[:, 1] < 15)][:, 2]       # bottom-left: far outside the sun
    assert np.ptp(corner) < 0.05                                  # no picture there: one even thickness
    assert (corner.mean() < 1.0) if thin else (corner.mean() > 2.9)


def test_lithophane_curved_shape_accepts_selection():
    sel = selectmask.parse({"paths": sun_trace()})
    m = geometry.build(IM, "lithophane", {"width_mm": 60, "resolution": 80, "shape": "cup", "select": sel})
    assert len(m.bodies[0].faces)


def test_tiny_or_empty_selection_warns_but_builds():
    tiny = selectmask.parse({"paths": [{"op": "new", "pts": ring(.5, .5, .04, .04)}], "snap": False})
    m = geometry.build(IM, "relief", {"width_mm": 60, "resolution": 80, "select": tiny})
    assert any("very small" in w for w in m.info["warnings"])
    none = selectmask.parse({"paths": [{"op": "new", "pts": ring(.5, .5, .2, .2)}], "invert": True, "snap": False})
    none["paths"].append({"op": "add", "pts": [[0, 0], [1, 0], [1, 1], [0, 1]]})   # invert of everything = nothing
    m = geometry.build(IM, "relief", {"width_mm": 60, "resolution": 80, "select": none})
    assert any("whole photo" in w for w in m.info["warnings"])


def _mask_b64():
    a = sun_disk(240, 180).astype(np.float32)
    return "data:image/png;base64," + selectmask.encode_mask(a)


def test_api_generate_with_client_mask_is_saved_and_reapplied_on_reopen():
    c = TestClient(app)
    sel = {"v": 1, "mask": _mask_b64(), "soft": 0, "outside": "plain", "paths": sun_trace()}
    with open(SAMPLE, "rb") as fh:
        r = c.post("/api/generate", files={"file": ("sample.png", fh, "image/png")},
                   data={"mode": "relief", "width_mm": "80", "select": json.dumps(sel)})
    assert r.status_code == 200, r.text
    j = r.json(); assert j["stats"]["watertight"]
    assert j["params"]["select"]["paths"] and j["params"]["select"]["mask"]
    stl = c.get(j["downloads"]["stl"]).content
    t = trimesh.load(io.BytesIO(stl), file_type="stl")
    # cropped to the sun (+ a small margin): about 80 mm wide disc, height ~= width (sun is round)
    assert abs(t.extents[0] - t.extents[1]) < 0.15 * t.extents[0]
    g = c.get("/api/builds/" + j["id"]).json()                       # re-open: selection still there
    assert g["params"]["select"]["mask"] == j["params"]["select"]["mask"]
    with open(SAMPLE, "rb") as fh:
        bad = c.post("/api/generate", files={"file": ("sample.png", fh, "image/png")},
                     data={"mode": "relief", "select": "{oops"})
    assert bad.status_code == 400 and "selection" in bad.json()["detail"]
