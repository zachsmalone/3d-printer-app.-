"""Memory box lithophane: 4 photo walls round a light, snap / frame / enclosed styles."""
import io
import zipfile

import numpy as np
import pytest
import trimesh
from PIL import Image

from app.core import exporters, memorybox as mb

IMS = [Image.fromarray((np.random.default_rng(i).random((60, 80, 3)) * 255).astype("uint8")) for i in range(4)]


def _tm(b):
    return trimesh.Trimesh(b.vertices, b.faces, process=False)


@pytest.fixture(scope="module")
def built():
    return {st: mb.build(IMS, dict(style=st, panel_mm=60, notch_mm=8)) for st in mb.STYLES}


def test_part_counts_and_every_part_watertight(built):
    names = {st: [b.name for b in pm.bodies] for st, (pm, _) in built.items()}
    assert names["frame"] == ["base", "frame_top", "panel_1", "panel_2", "panel_3", "panel_4"]
    assert names["enclosed"] == ["box", "lid"]
    assert names["snap"] == ["base", "panel_1", "panel_2", "panel_3", "panel_4", "lid"]
    assert [b.name for b in mb.build(IMS, dict(style="snap", panel_mm=60, lid=False))[0].bodies][-1] == "panel_4"
    for pm, view in built.values():
        assert all(_tm(b).is_watertight for b in pm.bodies) and len(view.bodies) == len(pm.bodies)
        assert not pm.info["warnings"]


def test_assembled_cube_matches_panel_size_and_scales(built):
    for st, (_, view) in built.items():
        v = np.vstack([b.vertices for b in view.bodies])
        assert np.ptp(v, 0) == pytest.approx([60, 60, 60], abs=0.6), st
    big = mb.build(IMS, dict(style="frame", panel_mm=120))[1]
    v = np.vstack([b.vertices for b in big.bodies])
    assert np.ptp(v, 0) == pytest.approx([120, 120, 120], abs=0.6)


def test_light_hole_size_is_honoured():
    for preset, w in (("tealight", 40), ("puck", 60)):
        base = mb.build(IMS, dict(style="frame", panel_mm=100, hole_preset=preset))[0].bodies[0]
        m = _tm(base)
        hit = m.ray.intersects_any([[50, 50, -5], [50 + w / 2 - 1, 50, -5], [50 + w / 2 + 1, 50, -5]], [[0, 0, 1]] * 3)
        assert list(hit) == [False, False, True], preset
    sq = _tm(mb.build(IMS, dict(style="frame", panel_mm=100, hole_shape="square", hole_preset="custom", hole_w=30, hole_d=20))[0].bodies[0])
    assert list(sq.ray.intersects_any([[64, 50, -5], [50, 59, -5], [50, 61.5, -5]], [[0, 0, 1]] * 3)) == [False, False, True]


def test_lid_groove_clearance_and_material_defaults(built):
    pm, view = built["enclosed"]
    info = pm.info
    assert info["clearance_mm"] == 0.2 and info["groove_mm"] == pytest.approx(2.0 + 0.4)
    lid = _tm(view.bodies[1]); box = _tm(view.bodies[0])
    assert box.intersection(lid, engine="manifold").volume < 1e-3                  # lid sits in the track without touching
    assert mb.build(IMS, dict(style="enclosed", panel_mm=60, material="resin"))[0].info["clearance_mm"] == 0.1
    assert built["frame"][0].info["groove_mm"] == pytest.approx(3.0 + 0.4)


def test_snap_neighbours_do_not_collide(built):
    _, view = built["snap"]
    p = [_tm(b) for b in view.bodies if b.name.startswith("panel")]
    assert p[0].intersection(p[1], engine="manifold").volume < 0.5


def test_3mf_has_one_object_per_part_and_zip_has_stls(built):
    pm, _ = built["frame"]
    data = exporters.to_3mf(pm, "memory-box")
    xml = zipfile.ZipFile(io.BytesIO(data)).read("3D/3dmodel.model").decode()
    assert xml.count("<object ") == 6
    assert sorted(zipfile.ZipFile(io.BytesIO(mb.stl_zip(pm))).namelist()) == sorted(f"{b.name}.stl" for b in pm.bodies)


def test_bed_warning_and_input_validation():
    pm, _ = mb.build(IMS, dict(style="frame", panel_mm=200), )
    assert pm.info["warnings"] == [] or all("bed" in w for w in pm.info["warnings"])
    with pytest.raises(ValueError, match="exactly 4"):
        mb.build(IMS[:3], {})
    for bad in (dict(panel_mm=30), dict(panel_mm=250), dict(style="tube"), dict(material="wood"), dict(clearance_mm=2),
                dict(hole_preset="custom", hole_w=90, panel_mm=80), dict(notch_mm=40), dict(hole_shape="oval")):
        with pytest.raises(ValueError):
            mb.check_params(bad)


def test_api_memorybox_preview_3mf_and_refusals():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    def png(i):
        b = io.BytesIO(); IMS[i].save(b, "PNG"); return ("p%d.png" % i, b.getvalue(), "image/png")
    files = [("files", png(i)) for i in range(4)]
    r = c.post("/api/memorybox", files=files, data={"style": "enclosed", "panel_mm": "60", "photo_ack": "true"})
    assert r.status_code == 200, r.text
    assert [b["name"] for b in r.json()["preview"]["bodies"]] == ["box", "lid"] and r.json()["stats"]["watertight"]
    r = c.post("/api/memorybox", files=files, data={"style": "frame", "panel_mm": "60", "photo_ack": "true", "fmt": "3mf"})
    assert r.status_code == 200 and r.headers["content-type"] == "model/3mf"
    assert c.post("/api/memorybox", files=files, data={"photo_ack": "true", "panel_mm": "500"}).status_code == 400
    assert c.post("/api/memorybox", files=files[:3], data={"photo_ack": "true"}).status_code == 400


def test_backlit_thickness_for_box_walls_and_ui_wiring():
    import json, shutil, subprocess
    from pathlib import Path
    from app.core import litho_light as ll
    root = Path(__file__).resolve().parent.parent
    pts = np.array([[0, 30, 30], [1.5, 30, 30], [30, 0.8, 10], [60, 30, 5], [30, 30, 0], [0, 0, 60], [60, 60, 60]], float)
    t = ll.wall_thickness(pts, "memorybox")
    assert list(t) == pytest.approx([0, 1.5, 0.8, 0, 30, 0, 0])
    if shutil.which("node"):
        js = (root / "static" / "lithlight.js").as_uri()
        code = (f"import {{ wallThickness }} from '{js}';"
                f"console.log(JSON.stringify(Array.from(wallThickness(new Float32Array({pts.ravel().tolist()}), 'memorybox',"
                " {lo: [0, 0, 0], hi: [60, 60, 60]}))))")
        out = json.loads(subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True).stdout)
        assert out == pytest.approx(list(t), abs=1e-6)
    html = (root / "static" / "index.html").read_text()
    for i in ("mbFiles", "mbStyle", "mbSize", "mbHole", "mbNotch", "mbClear", "mbAck", "mbPreview", "mb3mf", "mbZip"):
        assert f'id="{i}"' in html
    for v in ("frame", "snap", "enclosed", "tealight", "puck", "custom"):
        assert f'value="{v}"' in html
    app = (root / "static" / "app.js").read_text()
    assert 'fetch("/api/memorybox"' in app and 'shape: "memorybox"' in app and "syncLight()" in app
    css = (root / "static" / "style.css").read_text()
    assert "#mboxBox .btn, #mboxBox select" in css and "min-height: 44px" in css
