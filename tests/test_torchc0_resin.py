"""TorchC0 (ZEIM's resin program): settings, orient, supports, hollow + drain, estimates, API and UI wiring."""
import io
import zipfile
from pathlib import Path

import pytest
import trimesh

from tests import b1  # noqa: F401  (isolated PHOTO3D_OUT / DATA before the app is imported)
from tests.b1 import ADULT, client

from app.core import resin

ROOT = Path(__file__).resolve().parent.parent


def _stl(m):
    return m.export(file_type="stl")


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
    for bad in ({"preset": "x"}, {"material": "x"}, {"layer_mm": 1}, {"exposure_s": "abc"}, {"tilt_deg": 90}):
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
    assert len(isl) == 1 and isl[0]["xyz"][0] == pytest.approx(20, abs=1) and isl[0]["at"]
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
    _, rep = resin.prepare(trimesh.creation.box(extents=[40, 30, 25]), resin.settings({"supports": "false"}))
    note = next(n for n in rep["notes"] if n.startswith("Thin wall"))
    assert f"{rep['hollow']['thinnest_wall_mm']:.2f} mm" in note


def test_touching_parts_are_one_body():
    fig = trimesh.boolean.union([trimesh.creation.cylinder(4, 14).apply_translation([0, 0, 7]),
                                 trimesh.creation.icosphere(3, 3.5).apply_translation([0, 0, 17.5])], engine="manifold")
    out, rep = resin.prepare(fig, resin.settings())
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


def test_torchc0_islands_cups_cost_in_chromium():
    from test_b4_ui import _run
    out = _run("ui_torchc0_islands.py")
    assert "FAIL" not in out and "PASS chrome" in out, out
