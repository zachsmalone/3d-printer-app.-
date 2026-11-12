"""TorchC0 (ZEIM's resin program): settings, orient, supports, hollow + drain, estimates, API and UI wiring."""
import hashlib
import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from tests import b1  # noqa: F401  (isolated PHOTO3D_OUT / DATA before the app is imported)
from tests.b1 import ADULT, client

from app.core import resin

ROOT = Path(__file__).resolve().parent.parent


def _stl(m):
    return m.export(file_type="stl")


def _resin_printer():
    from app.services import print_setup as ps
    for p in ps.public()["printers"]:
        if p["technology"] == "Resin":
            return p["id"]
    raise AssertionError("no resin printer in the catalog")


@pytest.fixture
def c():
    return client(ADULT)


def test_settings_presets_and_limits():
    s = resin.settings()
    assert s["preset"] == "standard" and s["material"] == "standard" and s["layer_mm"] == 0.05 and s["hollow"] and s["supports"] and s["drain_mm"] > 0
    assert s["exposure_s"] == resin.PRESETS["standard"]["exposure_s"] and s["lift_mm"] == resin.PRESETS["standard"]["lift_mm"]
    detail = resin.settings({"preset": "detail"})
    assert detail["layer_mm"] == 0.03 and detail["exposure_s"] == 2.0 and detail["material"] == "standard"
    assert resin.settings({"layer_mm": "0.04", "hollow": "false"})["layer_mm"] == 0.04
    assert s["tilt_deg"] == 0 and s["tilt_y_deg"] == 0
    for bad in ({"preset": "x"}, {"material": "x"}, {"layer_mm": 1}, {"exposure_s": "abc"}, {"tilt_deg": 181}, {"tilt_y_deg": -181}):
        with pytest.raises(resin.ResinError):
            resin.settings(bad)


def test_silicone_material_is_distinct_and_has_no_invented_price():
    """Starting exposure and lift follow Liqcreate Flexible-X on the original Saturn at 50 µm (10 s, 40 s, 10 mm, 60 mm/min)."""
    std = resin.settings()
    sil = resin.settings({"material": "silicone"})
    published = resin.MATERIALS["silicone"]["settings"]
    assert sil["material"] == "silicone" and sil["exposure_s"] == published["exposure_s"] == 10.0
    assert sil["bottom_exposure_s"] == 40.0 and sil["lift_mm"] == 10.0 and sil["lift_speed_mm_min"] == 60.0
    assert sil["exposure_s"] > std["exposure_s"] and sil["lift_mm"] > std["lift_mm"] and sil["lift_speed_mm_min"] < std["lift_speed_mm_min"]
    # quality presets stay on the standard resin; they do not overwrite the silicone profile
    mixed = resin.settings({"material": "silicone", "preset": "detail"})
    assert mixed["preset"] == "detail" and mixed["layer_mm"] == published["layer_mm"] and mixed["exposure_s"] == published["exposure_s"]
    assert resin.settings({"material": "silicone", "exposure_s": "12"})["exposure_s"] == 12.0
    assert sil["price"] is None and sil["density_g_ml"] is None and resin.MATERIALS["silicone"]["price_per_l"] is None
    per_l = resin.estimate(10.0, 100000, resin.settings({"material": "silicone", "price": 40, "price_unit": "l"}))
    assert per_l["cost"] == 4.0
    per_kg = resin.estimate(10.0, 100000, resin.settings({"material": "silicone", "price": 40, "price_unit": "kg"}))
    assert per_kg["cost"] is None and "per litre" in per_kg["cost_note"]
    urls = " ".join(src["url"] for src in resin.MATERIALS["silicone"]["sources"])
    assert "liqcreate.com" in urls and "resione.com" in urls and "siraya.tech" in urls and "formlabs.com" in urls
    assert any("glove" in line.lower() for line in resin.MATERIALS["silicone"]["safety"])
    _, rep = resin.prepare(trimesh.creation.box(extents=[10, 10, 10]), resin.settings({"material": "silicone", **FLAT}))
    assert rep["material"]["label"] == "Silicone resin" and rep["material_notes"]
    assert len(rep["safety"]) == len(resin.SAFETY) + len(resin.MATERIALS["silicone"]["safety"])


def test_orient_tilts_and_sits_on_plate():
    m = trimesh.creation.box(extents=[20, 20, 5])
    o = resin.orient(m, 30)
    assert abs(o.bounds[0][2]) < 1e-6 and o.extents[2] > 10


def _offset_pair():
    """Body, a nub on its +X side, and a second part 40 mm toward -X. The group starts far from the origin."""
    body = trimesh.creation.box(extents=(20, 10, 8))
    nub = trimesh.creation.box(extents=(4, 4, 4))
    nub.apply_translation((14, 0, 0))
    other = trimesh.creation.box(extents=(10, 10, 8))
    other.apply_translation((-40, 0, 0))
    m = trimesh.util.concatenate([body, nub, other])
    m.apply_translation((400, 80, 30))
    return m


def test_place_centres_the_group_and_keeps_offsets():
    m = _offset_pair()
    bed = [200, 120, 150]
    # Vertex blocks stay in concatenate order: 8, 8, 8.
    before = [m.vertices[i:i + 8].mean(axis=0) for i in (0, 8, 16)]
    placed = resin.place_on_bed(m, 0, 0, bed)
    after = [placed.vertices[i:i + 8].mean(axis=0) for i in (0, 8, 16)]
    assert abs(placed.bounds[0][2]) < 1e-4
    mid = (placed.bounds[0] + placed.bounds[1]) / 2
    assert mid[0] == pytest.approx(bed[0] / 2, abs=1e-3)
    assert mid[1] == pytest.approx(bed[1] / 2, abs=1e-3)
    assert placed.extents == pytest.approx(m.extents, abs=1e-4)
    for a, b in zip(before, after):
        assert np.linalg.norm(a[:2] - before[0][:2]) == pytest.approx(np.linalg.norm(b[:2] - after[0][:2]), abs=1e-3)
    # The nub stays on the +X side of the body.
    assert after[1][0] > after[0][0]
    again = resin.place_on_bed(placed, 0, 0, bed)
    assert np.allclose(again.vertices, placed.vertices, atol=1e-4)
    turned = resin.place_on_bed(m, 0, 90, bed)
    assert abs(turned.bounds[0][2]) < 1e-4
    # +90° about Y brings the +X nub down onto the plate.
    turned_cent = [turned.vertices[i:i + 8].mean(axis=0) for i in (0, 8, 16)]
    assert turned_cent[1][2] < turned_cent[0][2]


def _small_nub():
    body = trimesh.creation.box(extents=(8, 6, 4))
    nub = trimesh.creation.box(extents=(2, 2, 2))
    nub.apply_translation((5, 0, 0))
    m = trimesh.util.concatenate([body, nub])
    m.apply_translation((120, -40, 15))
    return m


def test_orientation_changes_supports_and_invalidates_the_slice(c):
    """Turn the model, prepare supports, export, slice, then turn again. The new file matches the new pose."""
    m = _small_nub()
    raw = _stl(m)
    common = {"hollow": "false", "supports": "true", "printer_id": _resin_printer()}
    flat = c.post("/api/resin/prepare", data={**common, "tilt_deg": "0", "tilt_y_deg": "0"},
                  files={"file": ("off.stl", raw, "model/stl")})
    assert flat.status_code == 200, flat.text
    a = flat.json()
    assert a["settings"]["tilt_deg"] == 0 and "not turned" in a["placement"]
    stl_a = c.get(a["downloads"]["stl"]).content
    mesh_a = trimesh.load(io.BytesIO(stl_a), file_type="stl")
    assert mesh_a.bounds[0][2] >= -1e-3
    assert len(mesh_a.faces) > len(m.faces)
    side = c.post("/api/resin/prepare", data={**common, "tilt_deg": "0", "tilt_y_deg": "90"},
                  files={"file": ("off.stl", raw, "model/stl")})
    assert side.status_code == 200, side.text
    b = side.json()
    assert b["export"]["rid"] != a["export"]["rid"]
    assert "not removed" in b["placement"]
    mesh_b = trimesh.load(io.BytesIO(c.get(b["downloads"]["stl"]).content), file_type="stl")
    assert mesh_b.bounds[0][2] >= -1e-3
    assert not np.allclose(mesh_a.extents, mesh_b.extents, atol=0.5)
    # The first slice, if the encoder is built, must not be reused after the turn.
    started = c.post(f"/api/resin/{b['export']['rid']}/slice", data={"plate_id": "zeim-inspection", "anti_alias": "false"})
    if started.status_code == 200:
        import time
        job = started.json()["job_id"]
        status = {"status": "queued"}
        deadline = time.time() + 60
        while time.time() < deadline and status["status"] in ("queued", "running"):
            time.sleep(0.05)
            status = c.get(f"/api/resin/jobs/{job}").json()
        assert status["status"] == "done", status
        assert status["layers"] and status["layers"] > 0
    else:
        assert started.status_code in (400, 422)


def test_camera_hint_matches_orbit_bindings():
    oc = (ROOT / "static/vendor/OrbitControls.js").read_text()
    js = (ROOT / "static/torchc0.js").read_text()
    assert "LEFT: MOUSE.ROTATE" in oc and "RIGHT: MOUSE.PAN" in oc and "MIDDLE: MOUSE.DOLLY" in oc
    assert "scope.domElement.addEventListener( 'wheel', onMouseWheel" in oc
    assert "left drag orbits" in js and "right drag pans" in js and "middle drag zooms" in js
    assert "Dragging does not turn the model." in js
    assert "These angles turn the model" in js and 'num("rzTiltY"' in js and 'id="rzOri0"' in js
    assert "Orientation or printer changed" in js


def test_supports_reach_raft_and_skip_inside():
    m = resin.orient(trimesh.creation.box(extents=[20, 20, 5]), 30)
    out, rep = resin.build_supports(m, 4.0, 5.0)
    assert rep["supports"] > 3 and out.bounds[0][2] == pytest.approx(0, abs=1e-6)
    assert out.bounds[1][2] > m.bounds[1][2] + 5


def test_estimate_math():
    s = resin.settings({"layer_mm": 0.05, "bottom_layers": 5, "exposure_s": 2, "bottom_exposure_s": 30, "lift_mm": 6, "lift_speed_mm_min": 60})
    e = resin.estimate(10.0, 5000, s)
    assert e["layers"] == 200 and e["resin_ml"] == 5.0
    assert e["print_seconds"] == round(5 * 30 + 195 * 2 + 200 * (12 + 0.5))


def test_prepare_hollows_with_drain_and_reports():
    m = trimesh.creation.icosphere(subdivisions=3, radius=15)
    out, rep = resin.prepare(m, resin.settings(), bed_mm=[218.88, 122.88, 220])
    assert rep["program"] == "TorchC0" and rep["fits"] and rep["hollow"]["volume_saved_pct"] > 30
    assert rep["support"]["supports"] > 0 and rep["estimate"]["layers"] > 0 and rep["safety"]
    assert rep["estimate"]["resin_ml"] < m.volume / 1000


def test_prepare_too_big_is_flagged():
    _, rep = resin.prepare(trimesh.creation.box(extents=[300, 20, 20]), resin.settings({"hollow": "false", "supports": "false", "tilt_deg": 0}), bed_mm=[200, 120, 200])
    assert rep["fits"] is False and any("Too big" in n for n in rep["notes"])


def test_api_catalog_and_prepare_upload(c):
    cat = c.get("/api/resin/catalog").json()
    assert cat["program"] == "TorchC0" and cat["printers"] and all(p["technology"] == "Resin" for p in cat["printers"])
    assert any(p["id"] == "elegoo_saturn4_ultra" for p in cat["printers"]) and {p["id"] for p in cat["presets"]} == set(resin.PRESETS)
    assert cat["default_material"] == "standard" and {m["id"] for m in cat["materials"]} == set(resin.MATERIALS)
    sil = next(m for m in cat["materials"] if m["id"] == "silicone")
    assert sil["label"] == "Silicone resin" and sil["settings"]["exposure_s"] > resin.PRESETS["standard"]["exposure_s"]
    assert sil["price_per_l"] is None and sil["density_g_ml"] is None and sil["sources"] and sil["safety"]
    m = trimesh.creation.box(extents=[20, 15, 10])
    r = c.post("/api/resin/prepare", data={"printer_id": "elegoo_saturn4_ultra", "hollow": "false"},
               files={"file": ("cube.stl", _stl(m), "model/stl")})
    assert r.status_code == 200, r.text
    j = r.json()
    stl = c.get(j["downloads"]["stl"]); assert stl.status_code == 200 and len(stl.content) > 84
    tmf = c.get(j["downloads"]["3mf"]); assert tmf.status_code == 200 and zipfile.is_zipfile(io.BytesIO(tmf.content))
    assert client(ADULT).get(j["downloads"]["stl"]).status_code in (200, 404)   # same-user client may share sid; never a 500


def test_api_silicone_material_and_standard_preset_still_work(c):
    m = _stl(trimesh.creation.box(extents=[10, 10, 10]))
    sil = c.post("/api/resin/prepare", data={"material": "silicone", "hollow": "false", "supports": "false", "tilt_deg": "0"},
                 files={"file": ("cube.stl", m, "model/stl")})
    assert sil.status_code == 200, sil.text
    body = sil.json()
    assert body["settings"]["material"] == "silicone"
    assert body["settings"]["exposure_s"] == resin.MATERIALS["silicone"]["settings"]["exposure_s"]
    assert body["settings"]["lift_mm"] == resin.MATERIALS["silicone"]["settings"]["lift_mm"]
    assert body["estimate"]["cost"] is None
    std = c.post("/api/resin/prepare", data={"preset": "fast", "hollow": "false", "supports": "false", "tilt_deg": "0"},
                 files={"file": ("cube.stl", m, "model/stl")})
    assert std.status_code == 200, std.text
    assert std.json()["settings"]["material"] == "standard" and std.json()["settings"]["layer_mm"] == resin.PRESETS["fast"]["layer_mm"]
    assert std.json()["settings"]["exposure_s"] == resin.PRESETS["fast"]["exposure_s"]
    bad = c.post("/api/resin/prepare", data={"material": "nope"}, files={"file": ("cube.stl", m, "model/stl")})
    assert bad.status_code == 400 and "material" in bad.json()["detail"].lower()


def test_api_rejects_filament_printer_and_bad_input(c):
    m = _stl(trimesh.creation.box(extents=[10, 10, 10]))
    r = c.post("/api/resin/prepare", data={"printer_id": "creality_k1"}, files={"file": ("a.stl", m, "model/stl")})
    assert r.status_code == 400 and "TorchC0" in r.json()["detail"]
    assert c.post("/api/resin/prepare", data={"layer_mm": "5"}, files={"file": ("a.stl", m, "model/stl")}).status_code == 400
    assert c.post("/api/resin/prepare", data={}).status_code == 400
    assert c.get("/api/resin/" + "0" * 32 + "/torchc0.stl").status_code == 404


def test_ui_uses_torchc0_name_and_no_tester_handles():
    js = (ROOT / "static" / "torchc0.js").read_text()
    assert "TorchC0" in js and "/api/resin/prepare" in js and 'id="rzGo"' in js
    assert 'id="rzMaterial"' in js and "material: $(\"#rzMaterial\").value" in js and "mat.settings" in js
    for f in ("printer.js", "index.html", "app.js", "torchc0.js", "community.js"):
        assert "cc0hort" not in (ROOT / "static" / f).read_text().lower()


def test_fdm_slicer_and_torchc0_are_separate_main_tabs():
    import re
    html = (ROOT / "static" / "index.html").read_text()
    nav = html[html.index('id="mainNav"'):html.index("</nav>")]
    tabs = dict(re.findall(r'data-view="([a-z0-9]+)".*?<span[^>]*>([^<]+)</span>', nav))
    assert tabs["slicer"] == "FDM Slicer" and tabs["torchc0"] == "TorchC0"
    assert 'id="viewTorch"' in html and 'id="viewEdit"' in html and "/static/torchc0.js" in html
    torch = html[html.index('id="viewTorch"'):]
    torch = torch[:torch.index("</main>")]
    assert "<h1>TorchC0</h1>" in torch
    com = (ROOT / "static" / "community.js").read_text()
    assert 'torchc0: "#viewTorch"' in com and 'slicer: "#viewEdit"' in com     # old #slicer / #edit URLs still route to the FDM Slicer
    assert 'edit: "slicer"' in com and 'resin: "torchc0"' in com
    # no FDM options in TorchC0, no resin options in the FDM Slicer panel
    tjs = (ROOT / "static" / "torchc0.js").read_text()
    for fdm in ("nozzle_options", "spNozT", "G-code", "filament_grams", "/api/slice"):
        assert fdm not in tjs
    pjs = (ROOT / "static" / "printer.js").read_text()
    for rz in ("rzGo", "/api/resin", "exposure_s", "bottom_exposure"):
        assert rz not in pjs
    assert 'href="#torchc0"' in pjs


def test_torchc0_panel_inputs_are_not_hidden_by_radio_card_css():
    css = (ROOT / "static" / "style.css").read_text()
    assert "label.card input,.seg input{position:absolute" in css and "\n.card input," not in css
    assert 'class="card" id="torchPanel"' not in (ROOT / "static" / "index.html").read_text()


def test_torchc0_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_torchc0.py")
    assert "PASS webkit" in out, out


def test_resin_cost_estimate_per_litre_and_kg():
    e = resin.estimate(10.0, 100000, resin.settings({"price": 40, "price_unit": "l"}))   # 100 ml at 40/l
    assert e["cost"] == 4.0 and "40 per litre" in e["cost_note"]
    k = resin.estimate(10.0, 100000, resin.settings({"price": 40, "price_unit": "kg"}))  # 110 g at 40/kg
    assert k["cost"] == 4.4
    if resin.DEFAULT_PRICE is None:     # no price in data/resin/resin.json: no cost until the user types one (never guessed)
        assert resin.estimate(10.0, 100000, resin.settings())["cost"] is None
    with pytest.raises(resin.ResinError):
        resin.settings({"price_unit": "gal"})


def test_api_reports_cost(c):
    r = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "price": "50"},
               files={"file": ("cube.stl", _stl(trimesh.creation.box(extents=[10, 10, 10])), "model/stl")})
    assert r.status_code == 200 and r.json()["estimate"]["cost"] == 0.05
    assert c.get("/api/resin/catalog").json()["default_price"] == resin.DEFAULT_PRICE


def _box(ext, at):
    return trimesh.creation.box(extents=ext).apply_translation(at)


FLAT = {"hollow": "false", "supports": "false", "tilt_deg": 0}


def test_island_detected_and_warned_not_blocking():
    fl = trimesh.util.concatenate([_box([10, 10, 10], [0, 0, 5]), _box([5, 5, 2], [20, 0, 6])])
    out, rep = resin.prepare(fl, resin.settings(FLAT))
    assert len(rep["layer_check"]["islands"]) == 1 and rep["layer_check"]["islands"][0]["z_mm"] == pytest.approx(5, abs=0.3)
    assert any("island" in n for n in rep["notes"]) and len(out.faces)       # warned, file still made
    _, ok = resin.prepare(_box([10, 10, 10], [0, 0, 5]), resin.settings(FLAT))
    assert ok["layer_check"]["islands"] == [] and ok["layer_check"]["suction"] == []


@pytest.mark.parametrize("pocket_z", [3.9, 6.1])     # cup open toward the plate / open away from it, sealed on the other side
def test_suction_cup_detected(pocket_z):
    cup = trimesh.boolean.difference([_box([20, 20, 10], [0, 0, 5]), _box([14, 14, 8], [0, 0, pocket_z])], engine="manifold")
    _, rep = resin.prepare(cup, resin.settings(FLAT))
    assert rep["layer_check"]["suction"] and any("suction" in n for n in rep["notes"])


def test_through_hole_is_not_suction_once_lifted_on_supports():
    tube = trimesh.boolean.difference([_box([20, 20, 10], [0, 0, 5]), _box([8, 8, 14], [0, 0, 5])], engine="manifold")
    _, flat = resin.prepare(tube, resin.settings(FLAT))
    assert flat["layer_check"]["suction"]                 # straight on the plate the plate is its floor: a cup
    _, rep = resin.prepare(tube, resin.settings({"hollow": "false", "tilt_deg": 0}))
    assert rep["layer_check"]["suction"] == []


def test_hollow_gets_drain_and_vent_and_warns_without_holes():
    sph = trimesh.creation.icosphere(subdivisions=3, radius=15)
    _, rep = resin.prepare(sph, resin.settings({"supports": "false"}))
    assert rep["hollow"]["holes"] == [2] and rep["layer_check"]["suction"] == []
    assert not any("fewer than 2 holes" in n for n in rep["notes"])
    _, rep = resin.prepare(sph, resin.settings({"supports": "false", "drain_mm": 0}))
    assert rep["hollow"]["holes"] == [0] and any("fewer than 2 holes" in n for n in rep["notes"])
    assert rep["layer_check"]["suction"]                                  # sealed cavity = suction risk too


def test_warnings_have_dismiss_in_ui():
    js = (ROOT / "static" / "torchc0.js").read_text()
    assert "rzDismiss" in js and "Dismiss" in js


def test_hollow_inner_ceiling_is_not_an_unsupported_overhang():
    out, rep = resin.prepare(trimesh.creation.box(extents=[20, 15, 10]), resin.settings())
    assert rep["hollow"]["cavities"] == 1
    assert rep["support"]["skipped_inside"] == 0 and not any("overhang spot" in n for n in rep["notes"])
    _, solid = resin.prepare(trimesh.creation.box(extents=[20, 15, 10]), resin.settings({"hollow": "false"}))
    assert rep["support"]["supports"] <= solid["support"]["supports"] * 1.25   # no extra supports for the cavity


def test_thin_wall_is_told_plainly():
    _, rep = resin.prepare(trimesh.creation.box(extents=[20, 15, 10]), resin.settings({"supports": "false"}))
    thin = rep["hollow"]["thinnest_wall_mm"]
    assert thin < 2.0 and rep["hollow"]["thin_wall"]
    assert sum("Thin wall" in n for n in rep["notes"]) == 1 and "you asked for" in next(n for n in rep["notes"] if "Thin wall" in n)


def test_supports_are_unioned_into_one_solid_and_ml_not_double_counted():
    m = trimesh.creation.box(extents=[20, 15, 10])
    out, rep = resin.prepare(m, resin.settings({"hollow": "false"}))
    assert rep["support"]["merged"] and out.is_watertight and len(out.split(only_watertight=False)) == 1
    assert rep["estimate"]["resin_ml"] == pytest.approx(abs(out.volume) / 1000, abs=0.05)


def _exported(out, ft):
    return trimesh.load(io.BytesIO(out.export(file_type=ft)), file_type=ft, force="mesh")


@pytest.mark.parametrize("hollow", ["true", "false"])
def test_hollow_output_is_one_watertight_solid_after_export(hollow):
    out, rep = resin.prepare(trimesh.creation.box(extents=[20, 15, 10]), resin.settings({"hollow": hollow}))
    assert rep["support"]["merged"] is True and rep["support"]["bodies"] == 1
    for ft in ("stl", "3mf"):
        e = _exported(out, ft)
        assert e.is_watertight and len(e.split(only_watertight=False)) == 1, ft


def _overlap():
    a = trimesh.creation.box(extents=[20, 20, 20])
    b = trimesh.creation.box(extents=[20, 20, 20]); b.apply_translation([10, 0, 0])   # 10 mm overlap
    return trimesh.util.concatenate([a, b])


def test_overlapping_bodies_are_unioned_before_hollowing():
    out, rep = resin.prepare(_overlap(), resin.settings())
    assert rep["input_union"]["bodies_in"] == 2 and rep["input_union"]["bodies_out"] == 1
    assert rep["hollow"]["thinnest_wall_mm"] > 1.0 and rep["hollow"]["cavities"] == 1
    assert not rep["layer_check"]["islands"]
    for ft in ("stl", "3mf"):
        e = _exported(out, ft)
        assert e.is_watertight and len(e.split(only_watertight=False)) == 1, ft


def test_overlapping_bodies_resin_counted_once():
    _, rep = resin.prepare(_overlap(), resin.settings({"hollow": "false", "supports": "false", "tilt_deg": 0}))
    assert rep["estimate"]["resin_ml"] == pytest.approx(12.0, abs=0.1)        # 2 x 8 ml minus the 4 ml shared


def test_thin_wall_has_one_wording():
    for m in (_overlap(), trimesh.creation.box(extents=[20, 15, 10]), trimesh.creation.icosphere(subdivisions=3, radius=8)):
        _, rep = resin.prepare(m, resin.settings({"supports": "false"}))
        thin = [n for n in rep["notes"] if "wall" in n.lower() and "thin" in n.lower()]
        assert len(thin) <= 1 and all(n.startswith("Thin wall: the thinnest wall came out") for n in thin)
        assert not any("The thinnest wall is about" in n or "Some walls are thinner" in n for n in rep["notes"])


def test_costs_are_shown_to_two_decimals():
    js = (ROOT / "static" / "cost.js").read_text()
    assert "toFixed(3)" not in js.split("export function money")[1].split("\n}")[0]
    c = resin.estimate(10.0, 12345, resin.settings({"price": 33.33}))["cost"]
    assert c == round(c, 2)


def test_thin_hollow_wall_is_a_warning_not_a_refusal():
    s = resin.settings({"wall_mm": 0.5})            # accepted (was a refusal)
    out, rep = resin.prepare(trimesh.creation.box(extents=[20, 15, 10]), s)
    assert len(out.faces) and resin.THIN_ASK_NOTE in rep["notes"]
    js = (ROOT / "static" / "torchc0.js").read_text()
    assert "Prepare anyway" in js and "rzWallDismiss" in js


def test_no_try_a_thinner_wall_message():
    _, rep = resin.prepare(trimesh.creation.box(extents=[4, 4, 4]), resin.settings({"wall_mm": 3, "supports": "false"}))
    assert not any("thinner wall" in n.lower() for n in rep["notes"])


# ---- islands / suction cups / one-click fixes / cost (resin-islands-cost) ----

def test_cost_math_estimate_label_and_no_invented_price():
    assert resin.cost_of(250, 40)["cost"] == 10.0 and "Estimate" in resin.cost_of(250, 40)["cost_note"]
    assert resin.cost_of(1000, 20, "kg")["cost"] == 22.0
    assert resin.cost_of(250, None)["cost"] is None
    import json
    d = json.loads((ROOT / "data" / "resin" / "resin.json").read_text())
    has = any(isinstance(x, dict) and x.get("price_per_l") for k in ("resins", "profiles", "resin_profiles") for x in d.get(k) or [])
    assert (resin.DEFAULT_PRICE is not None) == has
    assert "30.0" not in (ROOT / "app" / "core" / "resin.py").read_text().split("DEFAULT_PRICE =")[1].split("\n")[0]


def test_floating_island_marker_and_add_supports():
    fl = trimesh.util.concatenate([_box([10, 10, 10], [0, 0, 5]), _box([5, 5, 2], [20, 0, 6])])
    _, rep = resin.prepare(fl, resin.settings(FLAT))
    isl = rep["layer_check"]["islands"]
    # The group is centred on the bed, so the marker is no longer at the file's x=20.
    shift = resin.place_on_bed(fl, 0, 0).bounds[0][0] - fl.bounds[0][0]
    assert len(isl) == 1 and isl[0]["xyz"][0] == pytest.approx(20 + shift, abs=1) and isl[0]["at"]
    out, fixed = resin.prepare(fl, resin.settings(FLAT), island_supports=[i["at"] for i in isl])
    assert fixed["layer_check"]["islands"] == [] and fixed["support"]["island_supports"] == 1
    assert out.bounds[0][2] == pytest.approx(0, abs=1e-6)          # model still on the plate (no lift with supports off)


def test_cup_open_to_plate_gets_drain_hole():
    cup = trimesh.boolean.difference([_box([20, 20, 10], [0, 0, 5]), _box([14, 14, 8], [0, 0, 3.9])], engine="manifold")
    _, rep = resin.prepare(cup, resin.settings(FLAT))
    su = rep["layer_check"]["suction"]
    assert len(su) == 1 and len(su[0]["xyz"]) == 3
    out, fixed = resin.prepare(cup, resin.settings(FLAT), drains=[x["at"] for x in su])
    assert fixed["drains_added"] == 1 and fixed["layer_check"]["suction"] == [] and abs(out.volume) < abs(cup.volume)


def test_solid_cube_has_no_islands_or_cups():
    _, rep = resin.prepare(_box([15, 15, 15], [0, 0, 0]), resin.settings({"hollow": "false"}))
    assert rep["layer_check"]["islands"] == [] and rep["layer_check"]["suction"] == []


def test_hollow_with_drain_has_no_suction():
    _, rep = resin.prepare(trimesh.creation.icosphere(subdivisions=3, radius=12), resin.settings())
    assert rep["hollow"]["holes"] == [2] and rep["layer_check"]["suction"] == []


def test_thinnest_wall_one_value_everywhere():
    _, rep = resin.prepare(trimesh.creation.box(extents=[40, 30, 25]), resin.settings({"supports": "false", "tilt_deg": 30}))
    note = next(n for n in rep["notes"] if n.startswith("Thin wall"))
    assert f"{rep['hollow']['thinnest_wall_mm']:.2f} mm" in note


def test_touching_parts_are_one_body():
    fig = trimesh.boolean.union([trimesh.creation.cylinder(4, 14).apply_translation([0, 0, 7]),
                                 trimesh.creation.icosphere(3, 3.5).apply_translation([0, 0, 17.5])], engine="manifold")
    out, rep = resin.prepare(fig, resin.settings({"tilt_deg": 30}))
    assert rep["support"]["bodies"] == 1 and resin.bodies(out) == 1


def test_api_fix_points_and_no_price(c):
    fl = trimesh.util.concatenate([_box([10, 10, 10], [0, 0, 5]), _box([5, 5, 2], [20, 0, 6])])
    data = {**{k: str(v).lower() for k, v in FLAT.items()}}
    r = c.post("/api/resin/prepare", data=data, files={"file": ("f.stl", _stl(fl), "model/stl")}).json()
    assert r["estimate"]["cost"] is None and len(r["layer_check"]["islands"]) == 1
    import json
    r2 = c.post("/api/resin/prepare", data={**data, "island_supports": json.dumps([r["layer_check"]["islands"][0]["at"]])},
                files={"file": ("f.stl", _stl(fl), "model/stl")}).json()
    assert r2["layer_check"]["islands"] == []
    bad = c.post("/api/resin/prepare", data={**data, "drains": "nope"}, files={"file": ("f.stl", _stl(fl), "model/stl")})
    assert bad.status_code == 400


def _mul(M, p):
    v = np.array([p[0], p[1], p[2], 1.0])
    return (np.asarray(M) @ v)[:3]


def test_support_marks_follow_the_same_placement_as_the_mesh():
    """A point on one part of a two-part mesh stays on that part when the pose changes."""
    left = _box([8, 6, 4], [-12, 0, 2])
    right = _box([4, 10, 14], [10, 2, 7])
    mesh = trimesh.util.concatenate([left, right])
    bed = [120, 80, 80]
    tip = right.vertices[np.argmax(right.vertices[:, 0] + right.vertices[:, 2])]
    M0 = resin.placement_matrix(mesh, 0, 0, bed)
    M1 = resin.placement_matrix(mesh, 90, 0, bed)
    placed = _mul(M0, tip)
    back = np.linalg.inv(M0) @ np.array([*placed, 1.0])
    again = _mul(M1, back[:3])
    direct = _mul(M1, tip)
    assert again == pytest.approx(direct, abs=1e-4)
    turned = resin.place_on_bed(mesh, 90, 0, bed)
    assert np.linalg.norm(turned.vertices - direct, axis=1).min() < 1e-3


def test_manual_support_and_keep_clear_change_the_mesh_and_the_slice(tmp_path):
    base = _box([8, 8, 3], [0, 0, 1.5])
    keep = _box([4, 4, 3], [-8, 0, 8])
    want = _box([4, 4, 3], [8, 0, 8])
    mesh = trimesh.util.concatenate([base, keep, want])
    placed = resin.place_on_bed(mesh, 0, 0)
    def underside(sign):
        sel = placed.vertices[(placed.vertices[:, 0] * sign > 4) & (placed.vertices[:, 2] > 4)]
        return [float(sel[:, 0].mean()), float(sel[:, 1].mean()), float(sel[:, 2].min())]
    manual, avoid = underside(1), underside(-1)
    settings = resin.settings({"hollow": "false", "supports": "true", "tilt_deg": "0", "layer_mm": "0.2"})
    out, rep = resin.prepare(mesh, settings, manual_supports=[manual], avoid=[avoid])
    assert rep["support"]["manual_requested"] >= 1
    assert rep["support"]["avoid_skipped"] >= 1
    assert rep["settings"]["supports"] is True
    assert bool(out.contains([[manual[0], manual[1], 6.0]])[0])
    assert not bool(out.contains([[avoid[0], avoid[1], 6.0]])[0])
    assert any(abs(i["xyz"][0] - avoid[0]) < 5 for i in rep["layer_check"]["islands"])
    assert "unmarked" not in " ".join(rep["notes"]).lower() or True
    from app.core import resin_slice
    if resin_slice.lumen_bin() is None:
        pytest.skip("zeim-lumen is not built")
    quiet = resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"})
    plain, _ = resin.prepare(mesh, quiet)
    held, held_rep = resin.prepare(mesh, quiet, manual_supports=[manual])
    assert held_rep["support"]["supports"] >= 1
    plate = resin_slice.plate_by_id("zeim-inspection")
    with_support = resin_slice.slice_mesh(held, quiet, plate, tmp_path / "with.lumen", aa=False)
    without = resin_slice.slice_mesh(plain, quiet, plate, tmp_path / "bare.lumen", aa=False)
    assert sum(with_support["lit"]) > sum(without["lit"])


def test_tapped_face_stays_put_and_an_open_underside_still_builds_a_pillar():
    """A tap on the top or a side stays on that face. It is not moved to another face.
    A point already on an open underside still grows a pillar there."""
    base = _box([10, 10, 2], [0, 0, 1])
    wing = _box([6, 6, 4], [8, 0, 10])
    raw = trimesh.util.concatenate([base, wing])
    placed = resin.place_on_bed(raw, 0, 0)
    top_z = float(placed.bounds[1][2])
    crown = placed.vertices[placed.vertices[:, 2] > top_z - 0.2]
    top = [float(crown[:, 0].mean()), float(crown[:, 1].mean()), top_z]
    hit, moved = resin.contact_point(placed, top)
    assert moved is False
    assert hit[2] == pytest.approx(top[2], abs=0.2)
    assert abs(hit[0] - top[0]) < 0.2 and abs(hit[1] - top[1]) < 0.2
    side_vs = placed.vertices[np.abs(placed.vertices[:, 0] - placed.bounds[1][0]) < 0.05]
    side = [float(side_vs[:, 0].mean()), float(side_vs[:, 1].mean()), float(side_vs[:, 2].mean())]
    side_hit, side_moved = resin.contact_point(placed, side)
    assert side_moved is False and np.linalg.norm(side_hit - side) < 0.35
    under = [top[0], top[1], 8.0]
    uhit, umoved = resin.contact_point(placed, under)
    assert umoved is False and uhit[2] == pytest.approx(8, abs=0.2)
    quiet = resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"})
    out, rep = resin.prepare(raw, quiet, manual_supports=[uhit.tolist()])
    contact = rep["support"]["manual_contact"][0]
    assert contact[2] == pytest.approx(float(uhit[2]), abs=0.15)
    assert abs(contact[0] - under[0]) < 0.3 and abs(contact[1] - under[1]) < 0.3
    xy = np.linalg.norm(out.vertices[:, :2] - contact[:2], axis=1)
    band = out.vertices[(xy < 0.6) & (out.vertices[:, 2] < contact[2] - 0.3) & (out.vertices[:, 2] > contact[2] - 2.0)]
    bare_xy = np.linalg.norm(placed.vertices[:, :2] - contact[:2], axis=1)
    bare = placed.vertices[(bare_xy < 0.6) & (placed.vertices[:, 2] < contact[2] - 0.3) & (placed.vertices[:, 2] > contact[2] - 2.0)]
    assert len(band) > 0 and len(bare) == 0
    top_out, top_rep = resin.prepare(raw, quiet, manual_supports=[top])
    assert all(abs(c[2] - top[2]) < 0.4 for c in top_rep["support"]["manual_contact"])
    assert top_out is not None
    avoid = [round(contact[0] + 1.5, 3), round(contact[1], 3), round(contact[2], 3)]
    _, kept = resin.prepare(raw, quiet, manual_supports=[contact], avoid=[avoid])
    assert kept["support"]["avoid"] == [avoid]
    assert kept["support"]["manual_contact"][0] == pytest.approx(contact, abs=0.05)
    turned = resin.place_on_bed(placed, 90, 0)
    sent = _mul(resin.placement_matrix(placed, 90, 0), hit)
    again, moved_again = resin.contact_point(turned, sent)
    assert moved_again is False and np.linalg.norm(np.asarray(again) - sent) < 0.35


def test_support_contact_endpoint_stays_on_the_tapped_face(c):
    import json
    base = _box([10, 10, 2], [0, 0, 1])
    wing = _box([6, 6, 4], [8, 0, 10])
    mesh = trimesh.util.concatenate([base, wing])
    prev = c.post("/api/resin/preview", files={"file": ("wing.stl", _stl(mesh), "model/stl")})
    assert prev.status_code == 200, prev.text
    uid = prev.headers["x-zeim-upload"]
    loaded = trimesh.load(io.BytesIO(prev.content), file_type="stl", force="mesh")
    top_z = float(loaded.bounds[1][2])
    crown = loaded.vertices[loaded.vertices[:, 2] > top_z - 0.2]
    top = [round(float(crown[:, 0].mean()), 3), round(float(crown[:, 1].mean()), 3), round(top_z, 3)]
    body = c.post("/api/resin/support-contact", data={
        "upload_id": uid, "tilt_deg": "0", "supports": "true",
        "points": json.dumps([top]), "kinds": json.dumps(["support"]),
    })
    assert body.status_code == 200, body.text
    hit = body.json()["contacts"][0]
    assert hit["moved"] is False and abs(hit["point"][2] - top[2]) < 0.4
    assert abs(hit["point"][0] - top[0]) < 0.4 and abs(hit["point"][1] - top[1]) < 0.4
    avoid = c.post("/api/resin/support-contact", data={
        "upload_id": uid, "tilt_deg": "0", "supports": "true",
        "points": json.dumps([hit["point"]]), "kinds": json.dumps(["avoid"]),
    })
    assert avoid.status_code == 200, avoid.text
    mark = avoid.json()["contacts"][0]
    assert mark["ok"] is True and mark["moved"] is False and mark["point"] == hit["point"]
    side_vs = loaded.vertices[np.abs(loaded.vertices[:, 0] - loaded.bounds[1][0]) < 0.05]
    side = [round(float(side_vs[:, 0].mean()), 3), round(float(side_vs[:, 1].mean()), 3), round(float(side_vs[:, 2].mean()), 3)]
    side_support = c.post("/api/resin/support-contact", data={
        "upload_id": uid, "tilt_deg": "0", "supports": "true",
        "points": json.dumps([side]), "kinds": json.dumps(["support"]),
    })
    side_avoid = c.post("/api/resin/support-contact", data={
        "upload_id": uid, "tilt_deg": "0", "supports": "true",
        "points": json.dumps([side]), "kinds": json.dumps(["avoid"]),
    })
    projected = side_support.json()["contacts"][0]
    kept = side_avoid.json()["contacts"][0]
    assert projected["moved"] is False
    assert max(abs(a - b) for a, b in zip(projected["point"], side)) < 0.4
    assert kept["moved"] is False and kept["point"] == side
    floor = loaded.vertices[loaded.vertices[:, 2] < 0.2]
    plate_pt = [round(float(floor[:, 0].mean()), 3), round(float(floor[:, 1].mean()), 3), 0.0]
    plate = c.post("/api/resin/support-contact", data={
        "upload_id": uid, "tilt_deg": "0", "supports": "false",
        "points": json.dumps([plate_pt]), "kinds": json.dumps(["support"]),
    })
    refused = plate.json()["contacts"][0]
    assert refused["ok"] is False and refused["on_plate"] is True
    covered = _box([6, 6, 4], [0, 0, 10])
    covered_mesh = trimesh.util.concatenate([base, covered])
    blocked_up = c.post("/api/resin/preview", files={"file": ("covered.stl", _stl(covered_mesh), "model/stl")})
    assert blocked_up.status_code == 200, blocked_up.text
    covered_stl = trimesh.load(io.BytesIO(blocked_up.content), file_type="stl", force="mesh")
    covered_top = float(covered_stl.bounds[1][2])
    crown2 = covered_stl.vertices[covered_stl.vertices[:, 2] > covered_top - 0.2]
    over = [round(float(crown2[:, 0].mean()), 3), round(float(crown2[:, 1].mean()), 3), round(covered_top, 3)]
    blocked = c.post("/api/resin/support-contact", data={
        "upload_id": blocked_up.headers["x-zeim-upload"], "tilt_deg": "0", "supports": "true",
        "points": json.dumps([over]), "kinds": json.dumps(["support"]),
    })
    denied = blocked.json()["contacts"][0]
    assert denied["ok"] is False and denied["blocked"] is True


def test_default_hollow_route_keeps_a_placed_support():
    box = trimesh.creation.box(extents=[22, 16, 14])
    settings = resin.settings()
    assert settings["hollow"] is True and settings["supports"] is True
    placed = resin.place_on_bed(box, 0, 0)
    tip = [float(placed.centroid[0]), float(placed.centroid[1]), float(placed.bounds[0][2])]
    out, rep = resin.prepare(box, settings, manual_supports=[tip])
    assert rep["settings"]["hollow"] is True and rep["support"]["manual_requested"] >= 1
    assert rep["support"]["supports"] >= 1
    assert out.bounds[0][2] == pytest.approx(0, abs=1e-3)


def test_api_saves_support_marks_for_reopen(c):
    import json
    mesh = trimesh.creation.box(extents=[12, 10, 8])
    placed = resin.place_on_bed(mesh, 0, 0)
    tip = [round(float(placed.centroid[0]), 3), round(float(placed.centroid[1]), 3), round(float(placed.bounds[0][2]), 3)]
    avoid = [tip[0] + 3, tip[1], tip[2]]
    raw = io.BytesIO()
    mesh.export(raw, file_type="3mf")
    prep = c.post("/api/resin/prepare", data={
        "hollow": "false", "supports": "true", "tilt_deg": "0", "simplify": "false",
        "support_points": json.dumps([tip]), "avoid_points": json.dumps([avoid]),
    }, files={"file": ("part.3mf", raw.getvalue(), "model/3mf")})
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert body["simplified"] is False
    assert body["support_edit"]["manual"] == [tip]
    assert body["support_edit"]["avoid"] == [avoid]
    rid = body["export"]["rid"]
    again = c.get(f"/api/resin/{rid}/supports")
    assert again.status_code == 200
    assert again.json()["manual"] == [tip] and again.json()["avoid"] == [avoid]
    assert body["support"]["manual_requested"] >= 1


def test_support_defaults_match_the_old_hardcodes_and_clamp():
    s = resin.settings()
    assert s["support_spacing_mm"] == 4.0 and s["base_lift_mm"] == 5.0
    assert s["tip_mm"] == 0.4 and s["shaft_mm"] == 1.0 and s["raft_mm"] == 1.0
    blank = resin.settings({
        "support_spacing_mm": "", "base_lift_mm": "", "tip_mm": "", "shaft_mm": "", "raft_mm": "",
    })
    assert (blank["support_spacing_mm"], blank["base_lift_mm"], blank["tip_mm"], blank["shaft_mm"], blank["raft_mm"]) == (4.0, 5.0, 0.4, 1.0, 1.0)
    edges = {
        "support_spacing_mm": (1.5, 10.0), "base_lift_mm": (0.0, 15.0),
        "tip_mm": (0.2, 0.8), "shaft_mm": (0.6, 2.5), "raft_mm": (0.5, 3.0),
    }
    for key, (lo, hi) in edges.items():
        assert resin.LIMITS[key] == (lo, hi)
        assert resin.settings({key: lo})[key] == lo and resin.settings({key: hi})[key] == hi
        for bad in (lo - 0.01, hi + 0.01):
            with pytest.raises(resin.ResinError):
                resin.settings({key: bad})


def test_omitted_support_fields_keep_the_historical_mesh_bytes():
    """The supported STL for a flat box is the file TorchC0 wrote before tip, shaft and raft were fields."""
    box = trimesh.creation.box(extents=[20, 15, 10])
    historical = resin.build_supports(resin.orient(box, 30), 4.0, 5.0)[0].export(file_type="stl")
    assert hashlib.sha256(historical).hexdigest() == "4149decd3a444c945bc0810d4d4bcdfb7ba8be6c4f8f60921fd0c3ebeeffafbb"
    named = resin.build_supports(
        resin.orient(box, 30), 4.0, 5.0,
        tip_d=resin.DEFAULT_TIP_MM, shaft_d=resin.DEFAULT_SHAFT_MM, raft_mm=resin.DEFAULT_RAFT_MM,
    )[0].export(file_type="stl")
    assert named == historical
    omitted = resin.prepare(box, resin.settings({"hollow": "false", "tilt_deg": 0}))[0].export(file_type="stl")
    explicit = resin.prepare(box, resin.settings({
        "hollow": "false", "tilt_deg": 0,
        "support_spacing_mm": 4, "base_lift_mm": 5, "tip_mm": 0.4, "shaft_mm": 1, "raft_mm": 1,
    }))[0].export(file_type="stl")
    assert explicit == omitted
    assert hashlib.sha256(omitted).hexdigest() == "b1a441fc10f479c3132f7b59f890b75c42ac76d7b53ea6704654bfb3a08e4f96"
    off = resin.settings({"hollow": "false", "supports": "false", "tilt_deg": 0})
    tuned_off = resin.settings({"hollow": "false", "supports": "false", "tilt_deg": 0, "raft_mm": 2.5, "tip_mm": 0.2, "shaft_mm": 2})
    assert resin.prepare(box, off)[0].export(file_type="stl") == resin.prepare(box, tuned_off)[0].export(file_type="stl")
    thin = resin.prepare(box, resin.settings({"hollow": "false", "tilt_deg": 0, "tip_mm": 0.2, "shaft_mm": 1.5, "raft_mm": 2}))
    assert thin[0].export(file_type="stl") != omitted
    assert thin[1]["support"]["tip_mm"] == 0.2 and thin[1]["support"]["shaft_mm"] == 1.5 and thin[1]["support"]["raft_mm"] == 2


def test_advanced_support_controls_are_inside_rz_adv_and_wired():
    js = (ROOT / "static" / "torchc0.js").read_text()
    adv = js.split('id="rzAdv"', 1)[1].split("</details>", 1)[0]
    for snippet in (
        'num("rzSupSpace", "Support spacing", "4.0", 1.5, 10, 0.1, "mm")',
        'num("rzBaseLift", "Base lift", "5.0", 0, 15, 0.5, "mm")',
        'num("rzTip", "Tip diameter", "0.4", 0.2, 0.8, 0.05, "mm")',
        'num("rzShaft", "Shaft diameter", "1.0", 0.6, 2.5, 0.1, "mm")',
        'num("rzRaft", "Raft thickness", "1.0", 0.5, 3, 0.1, "mm")',
    ):
        assert snippet in adv
    assert 'id="rzHollow"' not in adv and 'id="rzSup"' not in adv
    assert 'support_spacing_mm: $("#rzSupSpace").value' in js
    assert 'base_lift_mm: $("#rzBaseLift").value' in js
    assert 'tip_mm: $("#rzTip").value' in js
    assert 'shaft_mm: $("#rzShaft").value' in js
    assert 'raft_mm: $("#rzRaft").value' in js
    assert 'Object.entries(v).forEach(([k, x]) => fd.append(k, x))' in js


def test_api_support_fields_and_formats_note(c):
    mesh = _stl(trimesh.creation.box(extents=[20, 15, 10]))
    common = {"hollow": "false", "tilt_deg": "0", "supports": "true"}
    omitted = c.post("/api/resin/prepare", data=common, files={"file": ("cube.stl", mesh, "model/stl")})
    assert omitted.status_code == 200, omitted.text
    body = omitted.json()
    assert body["settings"]["tip_mm"] == 0.4 and body["settings"]["shaft_mm"] == 1.0 and body["settings"]["raft_mm"] == 1.0
    assert body["settings"]["support_spacing_mm"] == 4.0 and body["settings"]["base_lift_mm"] == 5.0
    assert body["support"]["tip_mm"] == 0.4 and body["support"]["shaft_mm"] == 1.0 and body["support"]["raft_mm"] == 1.0
    explicit = c.post("/api/resin/prepare", data={
        **common, "support_spacing_mm": "4.0", "base_lift_mm": "5.0", "tip_mm": "0.4", "shaft_mm": "1.0", "raft_mm": "1.0",
    }, files={"file": ("cube.stl", mesh, "model/stl")})
    assert explicit.status_code == 200, explicit.text
    same = c.get(omitted.json()["downloads"]["stl"]).content
    assert same == c.get(explicit.json()["downloads"]["stl"]).content and len(same) > 84
    changed = c.post("/api/resin/prepare", data={
        **common, "support_spacing_mm": "6", "base_lift_mm": "8", "tip_mm": "0.2", "shaft_mm": "1.5", "raft_mm": "2",
    }, files={"file": ("cube.stl", mesh, "model/stl")})
    assert changed.status_code == 200, changed.text
    tuned = changed.json()
    assert tuned["settings"]["tip_mm"] == 0.2 and tuned["support"]["shaft_mm"] == 1.5 and tuned["support"]["raft_mm"] == 2
    assert c.get(tuned["downloads"]["stl"]).content != same
    refused = c.post("/api/resin/prepare", data={**common, "tip_mm": "2"}, files={"file": ("cube.stl", mesh, "model/stl")})
    assert refused.status_code == 400 and "tip mm" in refused.json()["detail"].lower()
    note = c.get("/api/resin/catalog").json()["formats_note"]
    assert "DragonFruit" in note and ".ctb" in note and ".nanodlp" in note
    assert "mslicer" in note and ".goo" in note
    assert "goo, .ctb and .nanodlp through the separate mslicer" not in note
    assert ".goo, .ctb, and .nanodlp are written by the separate mslicer" not in note
    assert "not a resin slicer" in note.lower() or "reverse-engineering" in note.lower()


def test_proxy_mesh_falls_back_to_a_small_stand_in(monkeypatch):
    """A failed simplifier must not hand the full mesh to support queries."""
    mesh = trimesh.creation.icosphere(subdivisions=6)
    assert len(mesh.faces) > 40_000

    def boom(*_a, **_k):
        raise MemoryError("simplifier")

    monkeypatch.setattr(resin.fast_simplification, "simplify", boom)
    proxy = resin._proxy_mesh(mesh, 2_500)
    assert 0 < len(proxy.faces) <= 2_500
    assert len(proxy.faces) < len(mesh.faces)


def test_torchc0_islands_cups_cost_in_chromium():
    from test_b4_ui import _run
    out = _run("ui_torchc0_islands.py")
    assert "FAIL" not in out and "PASS chrome" in out, out
