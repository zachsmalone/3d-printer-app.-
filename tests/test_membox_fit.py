"""Memory box B: light base, lid over the light, fits, scaling, sample fill, export picker (multi-part 3MF, naming)."""
import io
import zipfile

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import memorybox as mb

IMS = [Image.fromarray((np.random.default_rng(10 + i).random((50, 70, 3)) * 255).astype("uint8")) for i in range(4)]
C = 0.25


def _tm(b):
    return trimesh.Trimesh(b.vertices, b.faces, process=False)


@pytest.fixture(scope="module")
def built():
    return {(st, P): mb.build(IMS, dict(style=st, panel_mm=P, clearance_mm=C)) for st in mb.STYLES for P in (60, 100)}


def test_every_style_every_part_watertight_with_base(built):
    for (st, P), (pm, view) in built.items():
        names = [b.name for b in pm.bodies]
        assert names[-1] == "light_base", st
        for b in pm.bodies:
            m = _tm(b)
            assert m.is_watertight and m.volume > 0, (st, P, b.name)
        assert pm.info["lid"] is True and not pm.info["warnings"]


def test_parts_do_not_collide_when_assembled(built):
    for (st, P), (_, view) in built.items():
        ms = {b.name: _tm(b) for b in view.bodies}
        names = list(ms)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                v = ms[a].intersection(ms[b], engine="manifold").volume
                assert v < 0.5, (st, P, a, b, v)


def test_base_ring_fits_box_hole_with_clearance(built):
    for (st, P), (pm, view) in built.items():
        info = pm.info["base"]
        assert info["ring_mm"][0] == pytest.approx(40 - 2 * C)
        assert info["light_room_mm"] == [40, 40, 24] and info["opening_mm"][0] == pytest.approx(40 - 2 * C - 3.2)
        H = info["height_mm"]
        box = [_tm(b) for b in view.bodies if b.name != "light_base"]
        assert min(m.bounds[0][2] for m in box) == pytest.approx(H, abs=1e-6)      # box sits on the base
        lb = _tm(view.bodies[0])
        assert np.ptp(lb.vertices[:, :2], 0) == pytest.approx([P, P])          # same footprint as the box
        # ring top is inside the box floor hole: a ray across at ring height crosses ring, then gap c, then box
        z = H + 1.0
        hit = [m.ray.intersects_location([[P / 2, P / 2, z]], [[1, 0, 0]])[0] for m in box]
        xs = sorted(p[0] for h in hit for p in h)
        ring = lb.ray.intersects_location([[P / 2, P / 2, z]], [[1, 0, 0]])[0][:, 0]
        assert min(xs) - ring.max() == pytest.approx(C, abs=0.05), (st, P)


def test_light_is_hidden_by_lid_and_open_below(built):
    for (st, P), (_, view) in built.items():
        allm = trimesh.util.concatenate([_tm(b) for b in view.bodies])
        assert allm.ray.intersects_any([[P / 2, P / 2, 500]], [[0, 0, -1]])[0], st    # something covers the light from above
        lb = _tm(view.bodies[0])
        assert not lb.ray.intersects_any([[P / 2, P / 2, -5]], [[0, 0, 1]])[0]        # base is open underneath
        back = lambda x: [p for p in lb.ray.intersects_location([[x, P + 5, 3]], [[0, -1, 0]])[0] if p[1] > P / 2 + 20.5]
        assert not back(P / 2) and back(P / 2 + 15)                                 # cable notch through the back wall only


def test_everything_scales_with_panel_size(built):
    for st in mb.STYLES:
        a = np.vstack([b.vertices for b in built[(st, 60)][1].bodies])
        b = np.vstack([b.vertices for b in built[(st, 100)][1].bodies])
        H = built[(st, 60)][0].info["base"]["height_mm"]
        assert np.ptp(a, 0) == pytest.approx([60, 60, 60 + H], abs=0.6), st
        assert np.ptp(b, 0) == pytest.approx([100, 100, 100 + H], abs=0.6), st
        pa = {x.name: np.ptp(x.vertices, 0) for x in built[(st, 60)][0].bodies}
        pb = {x.name: np.ptp(x.vertices, 0) for x in built[(st, 100)][0].bodies}
        for n in pa:
            assert pb[n].max() > pa[n].max() + 30, (st, n)


def test_clearance_is_adjustable_and_base_options():
    pm = mb.build(IMS, dict(style="frame", panel_mm=60, clearance_mm=0.3))[0]
    assert pm.info["groove_mm"] == pytest.approx(3.0 + 0.6) and pm.info["base"]["ring_mm"][0] == pytest.approx(39.4)
    nb = mb.build(IMS, dict(style="enclosed", panel_mm=60, base=False))[0]
    assert "light_base" not in [b.name for b in nb.bodies] and "base" not in nb.info
    sq = mb.build(IMS, dict(style="enclosed", panel_mm=80, hole_preset="custom", hole_shape="square", hole_w=30, hole_d=25,
                            light_h=40, base_notch_mm=0))[0]
    b = sq.info["base"]
    assert b["outer_mm"] == [80, 80, 43] and b["notch_mm"] == [0, 0] and _tm(sq.bodies[-1]).is_watertight
    for bad in (dict(light_h=3), dict(light_h=200), dict(base_notch_mm=30)):
        with pytest.raises(ValueError):
            mb.check_params(bad)


def test_sample_photo_fills_empty_sides():
    ims, sides = mb.fill_slots(IMS[:1])
    assert len(ims) == 4 and sides == [False, True, True, True]
    assert mb.fill_slots([])[1] == [True] * 4
    with pytest.raises(ValueError):
        mb.fill_slots(IMS[:2], fill_sample=False)


def test_print_layout_fits_rows_and_parts_flat(built):
    pm, _ = built[("frame", 60)]
    v = np.vstack([b.vertices for b in pm.bodies])
    assert v[:, 0].max() <= 230 and v[:, 2].min() == pytest.approx(0, abs=1e-6)
    boxes = [(_tm(b).bounds) for b in pm.bodies]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            assert (a[1][0] < b[0][0] or b[1][0] < a[0][0] or a[1][1] < b[0][1] or b[1][1] < a[0][1])   # apart on the bed


def test_api_saves_build_and_export_picker_names_and_multipart():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    def png(i):
        b = io.BytesIO(); IMS[i].save(b, "PNG"); return ("p%d.png" % i, b.getvalue(), "image/png")
    r = c.post("/api/memorybox", files=[("files", png(0)), ("files", png(1))],
               data={"style": "frame", "panel_mm": "60", "photo_ack": "true", "clearance_mm": "0.25"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["saved"] and j["id"] and j["info"]["sample_sides"] == [3, 4]
    assert [b["name"] for b in j["preview"]["bodies"]][0] == "light_base" and j["info"]["base"]["notch_mm"][0] == 8
    bid = j["id"]
    e = c.get(f"/api/export/{bid}", params={"printer_id": "creality_k1"}).json()
    assert e["default_name"].startswith("Memory box - ") and e["default_name"].endswith(" - 0.2mm"), e["default_name"]
    d = c.get(f"/api/export/{bid}/download", params={"format": "3mf", "printer_id": "creality_k1"})
    assert d.status_code == 200 and d.headers["x-export-format"] == "3mf"
    assert "Memory box - " in d.headers["content-disposition"]
    xml = zipfile.ZipFile(io.BytesIO(d.content)).read("3D/3dmodel.model").decode()
    assert xml.count("<object ") == 7 and 'name="light_base"' in xml
    s = c.get(f"/api/export/{bid}/download", params={"format": "stl", "printer_id": "creality_k1"})
    m = trimesh.load(io.BytesIO(s.content), file_type="stl")
    assert len(m.split(only_watertight=False)) >= 7
    for f in ("obj", "ply", "glb", "amf"):
        assert c.get(f"/api/export/{bid}/download", params={"format": f}).status_code == 200, f
    # big box: never scaled to fit, bed size only noted
    r = c.post("/api/memorybox", data={"style": "enclosed", "panel_mm": "200", "fill_sample": "true"})
    assert r.status_code == 200, r.text
    z = c.get(f"/api/export/{r.json()['id']}/download", params={"format": "3mf", "printer_id": "creality_k1"})
    assert z.status_code == 200
    # refusals: too many photos, no sample fill
    assert c.post("/api/memorybox", files=[("files", png(i % 4)) for i in range(5)], data={"photo_ack": "true"}).status_code == 400
    assert c.post("/api/memorybox", files=[("files", png(0))], data={"photo_ack": "true", "fill_sample": "false"}).status_code == 400
