"""print-core: printer + nozzle picker, slicer uses the chosen printer (one slicing path), full settings panel,
universal export + Open in, and the 'Will it print?' badge."""
import re
from pathlib import Path

import pytest
import trimesh

from tests.b1 import client, ADULT
from app.services import print_setup as ps, slice_engine as eng, willprint
from app.api import printsetup

ROOT = Path(__file__).resolve().parent.parent
HAVE_SLICER = bool(eng.find_engine())


def box_bytes(x, y, z):
    return trimesh.creation.box((x, y, z)).export(file_type="stl")


@pytest.fixture
def fake_engine(monkeypatch):
    calls = []
    def fake_run(engine, ini, stl, out, timeout=0, center=(110, 110)):
        calls.append({"ini": ini.read_text(), "center": center})
        out.write_text("; filament used [mm] = 1234.5\n; total filament used [g] = 3.70\n; estimated printing time (normal mode) = 12m 5s\n")
    monkeypatch.setattr(eng, "find_engine", lambda: "/usr/bin/fake")
    monkeypatch.setattr(eng, "run_engine", fake_run)
    return calls


def ini_dict(text):
    return dict(l.split(" = ", 1) for l in text.splitlines() if " = " in l)


# ---- 1) picker ------------------------------------------------------------------------------------------------------
def test_catalog_has_18_printers_nozzles_and_k1_default():
    j = client().get("/api/printers/catalog").json()
    assert len(j["printers"]) == 75 and j["nozzles"] == [0.2, 0.4, 0.6, 0.8, 1.0]
    assert j["default"] == {"printer_id": "creality_k1", "nozzle": 0.4}
    resin = [p for p in j["printers"] if p["technology"] == "Resin"]
    assert resin and all(p["nozzles"] == [] and p["stock_nozzle_mm"] is None for p in resin)


def test_resolve_rules():
    assert ps.resolve() == ("creality_k1", 0.4)
    assert ps.resolve("elegoo_mars4", 0.4) == ("elegoo_mars4", None)        # resin: no nozzle
    with pytest.raises(ps.SetupError):
        ps.resolve("creality_k1", 0.5)
    with pytest.raises(ps.SetupError):
        ps.resolve("bambu_a1_mini", 1.0)                                    # Bambu documents 0.2-0.8 only
    with pytest.raises(ps.SetupError):
        ps.resolve("prusa_mk4", 0.2)
    with pytest.raises(ps.SetupError):
        ps.resolve("nope", 0.4)


def test_anonymous_choice_is_browser_only_and_signed_up_choice_is_saved_on_the_profile():
    a = client()
    assert a.get("/api/me/printer").json() == {"signed_up": False, "stored": "browser", "printer_id": "creality_k1", "nozzle": 0.4, "saved": False}
    r = a.put("/api/me/printer", json={"printer_id": "bambu_a1_mini", "nozzle": 0.6}).json()
    assert r["stored"] == "browser" and a.get("/api/me/printer").json()["printer_id"] == "creality_k1"
    assert a.put("/api/me/printer", json={"printer_id": "bambu_a1_mini", "nozzle": 0.3}).status_code == 400
    c = client(ADULT)
    assert c.put("/api/me/printer", json={"printer_id": "prusa_mk4", "nozzle": 0.6}).json()["stored"] == "profile"
    assert c.get("/api/me/printer").json()["printer_id"] == "prusa_mk4" and c.get("/api/me").json()["printer"] == {"printer_id": "prusa_mk4", "nozzle": 0.6}


def test_signup_can_carry_the_optional_printer():
    c = client({**ADULT, "printer_id": "elegoo_saturn3", "nozzle": 0.4})
    assert c.get("/api/me/printer").json() == {"signed_up": True, "stored": "profile", "printer_id": "elegoo_saturn3", "nozzle": None, "saved": True}
    c2 = client({**ADULT, "printer_id": "bad_printer"})                      # an optional bad choice never blocks sign-up
    assert c2.get("/api/me/printer").json()["printer_id"] == "creality_k1"


def test_picker_ui_in_account_and_signup():
    html, js, cjs = (ROOT / "static/index.html").read_text(), (ROOT / "static/printer.js").read_text(), (ROOT / "static/community.js").read_text()
    assert 'id="accPrinter"' in html and "/static/printer.js" in html
    assert "localStorage.setItem(KEY" in js and '"/api/me/printer"' in js
    assert 'pickerHTML("su"' in cjs and "...(pick || {})" in cjs


# ---- 2) slicer uses the chosen printer ------------------------------------------------------------------------------
@pytest.mark.parametrize("pid", sorted(ps._catalog()))
def test_every_fdm_printer_gets_its_bed_and_nozzle(pid):
    if ps.printer_public(pid)["technology"] == "Resin":
        with pytest.raises(eng.SliceError):
            eng.profile_for(pid, None, {})
        return
    for n in ps.printer_public(pid)["nozzles"]:
        prof, s = eng.profile_for(pid, n, {})
        d = ini_dict(prof.ini); x, y, z = ps.bed_of(pid); sp = ps.nozzle_spec(n)
        assert d["bed_shape"] == f"0x0,{x:g}x0,{x:g}x{y:g},0x{y:g}" and d["max_print_height"] == f"{z:g}"
        assert float(d["nozzle_diameter"]) == n and float(d["extrusion_width"]) == sp["line_width_mm"]["recommended"]
        assert float(d["layer_height"]) == sp["layer_height_mm"]["recommended"]          # Standard preset = sourced starting value
        assert n * 0.25 - 1e-9 <= float(d["layer_height"]) <= n * 0.75 + 1e-9


def test_nozzle_specs_drive_the_picker():
    """data/nozzles/nozzle-specs.json: only supported sizes, manufacturer values, 1.0 mm + unprofiled = Advanced."""
    opts = lambda pid: {o["mm"]: o for o in ps.nozzle_options(pid)}
    k1, a1, mk4, ender = opts("creality_k1"), opts("bambu_a1_mini"), opts("prusa_mk4"), opts("creality_ender3_v3")
    assert list(k1) == [0.2, 0.4, 0.6, 0.8, 1.0] and list(a1) == [0.2, 0.4, 0.6, 0.8] and list(mk4) == [0.4, 0.6, 0.8]
    assert k1[0.2]["profiled"] and k1[0.4]["profiled"] and k1[0.6]["advanced"] and k1[1.0]["advanced"]
    assert k1[1.0]["note"] == "Advanced: calibrate before use" and all(not o["advanced"] for o in a1.values())
    assert ender[0.4]["profiled"] and ender[0.2]["advanced"]                              # no family data: only the stock nozzle is profiled
    assert k1[0.2]["manufacturer"]["pla_flow_ratio"] == 0.98 and k1[0.2]["manufacturer_name"] == "Creality"
    s = ps.settings_for("creality_k1", 0.2, {})
    assert (s["layer_height"], s["line_width"], s["max_volumetric_speed"]) == (0.1, 0.22, 3.0)
    assert ini_dict(eng.profile_for("creality_k1", 0.2, {})[0].ini)["max_volumetric_speed"] == "3"
    js = (ROOT / "static/printer.js").read_text()
    assert "nozzle_options" in js and "advanced_note" in js and "manufacturer_name" in js


def test_layer_height_is_limited_to_25_to_75_percent_of_the_nozzle():
    assert eng.profile_for("creality_k1", 0.8, {"layer_height": "0.6"})[1]["layer_height"] == 0.6
    with pytest.raises(eng.SliceError):                                                  # 0.2 mm spec max is 0.14 (< 75 %)
        eng.profile_for("creality_k1", 0.2, {"layer_height": "0.15"})
    for bad in ("0.19", "0.61", "0.15"):
        with pytest.raises(eng.SliceError):
            eng.profile_for("creality_k1", 0.8, {"layer_height": bad})


def test_api_slice_uses_the_chosen_printer_and_centres_on_its_bed(fake_engine):
    r = client().post("/api/slice", files={"file": ("m.stl", box_bytes(20, 20, 20))}, data={"printer_id": "bambu_a1_mini", "nozzle": "0.2"})
    assert r.status_code == 200, r.text
    j = r.json(); d = ini_dict(fake_engine[-1]["ini"])
    assert j["printer_id"] == "bambu_a1_mini" and j["nozzle"] == 0.2 and d["nozzle_diameter"] == "0.2"
    assert fake_engine[-1]["center"] == (90.0, 90.0) and d["bed_shape"].endswith("0x180")


def test_too_big_for_the_chosen_printer_is_refused(fake_engine):
    r = client().post("/api/slice", files={"file": ("m.stl", box_bytes(200, 200, 20))}, data={"printer_id": "bambu_a1_mini"})
    assert r.status_code == 422 and "A1 mini" in r.json()["detail"]["message"]


def test_the_two_slicing_paths_are_merged(monkeypatch):
    """/api/print/slice (Studio builds) runs through slice_engine.profile_for + run_engine, like POST /api/slice."""
    src = (ROOT / "app/services/slicer.py").read_text()
    assert "eng.profile_for(" in src and "eng.run_engine(" in src and "subprocess.run(cmd" not in src.split("def slice_model")[1]
    seen = []
    real = eng.profile_for
    monkeypatch.setattr(eng, "profile_for", lambda *a, **k: seen.append(a) or real(*a, **k))
    from app.services import slicer
    from app.core.geometry import Model
    if not slicer.status()["available"]:
        pytest.skip("no slicer")
    import numpy as np, tempfile
    m = trimesh.creation.box((10, 10, 10))
    model = Model.__new__(Model)
    model.solid = lambda: (np.asarray(m.vertices), np.asarray(m.faces))
    r = slicer.slice_model(model, Path(tempfile.mkdtemp()), printer_id="prusa_mini_plus", nozzle=0.6)
    assert r["ok"], r
    assert seen and seen[0][0] == "prusa_mini_plus" and r["settings"]["nozzle"] == 0.6


# ---- 3) settings panel ----------------------------------------------------------------------------------------------
def test_panel_settings_reach_the_slicer(fake_engine):
    form = {"printer_id": "creality_k1", "nozzle": "0.4", "layer_height": "0.12", "walls": "3", "top_bottom": "5", "infill": "35",
            "infill_pattern": "gyroid", "supports": "everywhere", "brim": "5", "speed": "90", "material": "PETG"}
    j = client().post("/api/slice", files={"file": ("m.stl", box_bytes(10, 10, 10))}, data=form).json()
    d = ini_dict(fake_engine[-1]["ini"])
    assert (d["layer_height"], d["perimeters"], d["top_solid_layers"], d["fill_density"], d["fill_pattern"]) == ("0.12", "3", "5", "35%", "gyroid")
    assert d["support_material"] == "1" and d["support_material_buildplate_only"] == "0" and d["brim_width"] == "5" and d["perimeter_speed"] == "90"
    assert (d["temperature"], d["bed_temperature"], d["filament_type"]) == ("240", "90", "PETG")       # materials.json PETG
    assert j["print_time_human"] == "12m 5s" and j["filament_grams"] == 3.7 and j["filament_mm"] == 1234.5


@pytest.mark.parametrize("pattern,ini", [("grid", "grid"), ("gyroid", "gyroid"), ("honeycomb", "honeycomb"), ("cubic", "cubic"), ("lines", "line"), ("lightning", "lightning"), ("rectilinear", "rectilinear")])
def test_infill_patterns_map_to_prusaslicer(pattern, ini):
    assert ini_dict(eng.profile_for(None, None, {"infill_pattern": pattern})[0].ini)["fill_pattern"] == ini


def test_supports_modes_and_presets_and_temps_clamped():
    o = lambda s: ini_dict(eng.profile_for(None, None, {"supports": s})[0].ini)
    assert o("off")["support_material"] == "0" and o("auto")["support_material_buildplate_only"] == "1"
    draft, fine = (eng.profile_for(None, None, {"preset": p})[1] for p in ("draft", "fine"))
    assert draft["layer_height"] > fine["layer_height"] and draft["infill_pattern"] == "lightning"
    assert eng.profile_for(None, None, {"preset": "strong"})[1]["walls"] == 4
    with pytest.raises(eng.SliceError):
        eng.profile_for("creality_k1", 0.4, {"nozzle_temp": "400"})                # K1 max 300 C (catalog)
    assert ps.material_temps("TPU") == {"nozzle_c": 230, "first_layer_nozzle_c": 230, "bed_c": 65, "first_layer_bed_c": 65}


def test_panel_ui_has_beginner_and_advanced():
    js = (ROOT / "static/printer.js").read_text()
    for s in ("spBeginner", "spAdvanced", "spPreset", "spPattern", "spSup", "spMat", "spNozT", "spBedT", "print_time_human", "filament_grams"):
        assert s in js


@pytest.mark.skipif(not HAVE_SLICER, reason="PrusaSlicer not installed")
def test_real_slice_with_gyroid_on_a_0_6_nozzle_reports_time_and_filament():
    r = client().post("/api/slice", files={"file": ("m.stl", box_bytes(15, 15, 8))},
                      data={"printer_id": "prusa_mk4", "nozzle": "0.6", "infill_pattern": "gyroid", "preset": "draft"})
    assert r.status_code == 200, r.text
    j = r.json(); assert j["print_time_seconds"] > 0 and j["filament_grams"] > 0 and j["will_print"]["verdict"] == "yes"


# ---- 4) universal export --------------------------------------------------------------------------------------------
def test_exports_are_sized_for_the_printer(fake_engine):
    c = client()
    j = c.post("/api/slice", files={"file": ("m.stl", box_bytes(300, 100, 50))}, data={"printer_id": "creality_k1", "scale_to_fit": "true"}).json()
    assert j["scaled_pct"] and j["scaled_pct"] < 75
    stl = c.get(j["downloads"]["stl"]); m = trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl")
    assert max(m.extents) <= 220 and m.bounds[0][2] == pytest.approx(0, abs=1e-4) and (m.bounds[0][0] + m.bounds[1][0]) / 2 == pytest.approx(110, abs=0.01)
    three = c.get(j["downloads"]["3mf"]); assert three.status_code == 200 and three.content[:2] == b"PK"
    assert c.get(j["downloads"]["gcode"]).status_code == 200
    assert c.get("/api/slice/" + "0" * 32 + "/model.obj").status_code == 404


def test_open_in_uses_no_undocumented_schemes_and_no_accounts():
    j = client().get("/api/printers/catalog").json()
    labels = {o["label"] for o in j["open_in"]}
    assert {"Creality Print", "Bambu Studio", "PrusaSlicer", "ELEGOO slicer", "Anycubic slicer", "another slicer (3MF)", "any slicer (STL)"} == labels
    assert all(o["scheme"] is None and o["steps"] and o["format"] in ("3mf", "stl") for o in j["open_in"])
    js = (ROOT / "static/printer.js").read_text()
    assert "download=" in js and "://open" not in js and "oauth" not in js.lower()


# ---- 5) Will it print? ----------------------------------------------------------------------------------------------
def test_badge_geometry_checks():
    ok = willprint.check(trimesh.creation.box((20, 20, 20)), "creality_k1", 0.4, slices_ok=True)
    assert ok["verdict"] == "yes" and ok["checks"]["bed_fit"]["ok"] and ok["checks"]["thin_wall"]["ok"]
    big = willprint.check(trimesh.creation.box((250, 20, 20)), "creality_k1", 0.4)
    assert big["verdict"] == "no" and big["checks"]["bed_fit"]["fit_scale_pct"] == 88
    thin = willprint.check(trimesh.creation.box((60, 0.3, 30)), "creality_k1", 0.4)
    assert thin["verdict"] == "maybe" and thin["checks"]["thin_wall"]["ok"] is False and thin["checks"]["thin_wall"]["min_mm"] == 0.42
    assert willprint.check(trimesh.creation.box((60, 0.3, 30)), "creality_k1", 0.2)["checks"]["thin_wall"]["ok"] is True
    failed = willprint.check(trimesh.creation.box((20, 20, 20)), slices_ok=False, slice_message="broken")
    assert failed["verdict"] == "no" and "broken" in failed["tips"]


def test_showcase_badge_endpoint():
    c = client()
    items = [i for i in c.get("/api/showcase", params={"tab": "free"}).json()["items"] if i.get("files")]
    assert items
    r = c.get(f"/api/showcase/{items[0]['id']}/willprint", params={"printer_id": "bambu_a1_mini", "nozzle": "0.4"}).json()
    assert r["printer_id"] == "bambu_a1_mini" and r["checks"]["bed_fit"]["ok"] in (True, False) and r["checks"]["slices"]["ok"] is None
    assert c.get("/api/showcase/nope/willprint").status_code == 404
    if HAVE_SLICER:
        s = c.get(f"/api/showcase/{items[0]['id']}/willprint", params={"slice": "true"}).json()
        assert s["checks"]["slices"]["ok"] in (True, False)
    cjs = (ROOT / "static/community.js").read_text()
    assert "showcaseBadges" in cjs and "itWill" in cjs and "itSliceCheck" in cjs


def test_build_badge_is_owner_only(fake_engine, tmp_path, monkeypatch):
    from app.services.history import store
    assert client().get("/api/willprint/build/abc123").status_code in (400, 404)


def test_one_plate_bed_check_uses_the_chosen_printer():
    from tests.test_comm_features import U, _cube
    c = U("Mp")
    two = [("files", (f"p{n}.stl", _cube(120), "model/stl")) for n in range(2)]
    k1max = c.post("/api/edit/multi", files=two, data={"mode": "plate", "printer_id": "creality_k1_max"}).json()     # 300 x 300 bed
    mini = c.post("/api/edit/multi", files=two, data={"mode": "plate", "printer_id": "bambu_a1_mini"}).json()       # 180 x 180 bed
    assert k1max["plate"]["fits"] is True and mini["plate"]["fits"] is False and mini["plate"]["bed_mm"][:2] == [180.0, 180.0]
    assert c.post("/api/edit/multi", files=two, data={"mode": "plate", "printer_id": "nope"}).status_code == 400
    assert 'fd.append("printer_id", P.pref.printer_id)' in (ROOT / "static/edit.js").read_text()


def test_willprint_worker_exits_when_the_server_dies(tmp_path):
    """The geometry worker process must not outlive a killed server (orphans once filled the box's memory)."""
    import subprocess, sys, time, os
    big = tmp_path / "big.stl"; big.write_bytes(trimesh.creation.icosphere(subdivisions=6).export(file_type="stl"))
    assert big.stat().st_size > 2_000_000
    code = ("import asyncio,os,sys; from app.services import willprint as w; asyncio.run(w.check_file_async(sys.argv[1]));"
            "print([p.pid for p in w._pool._processes.values()][0], flush=True); os._exit(0)")
    out = subprocess.run([sys.executable, "-c", code, str(big)], cwd=ROOT, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PHOTO3D_WILLPRINT_INLINE": ""})
    pid = int(out.stdout.strip().splitlines()[-1])
    for _ in range(50):
        try:
            os.kill(pid, 0); time.sleep(0.2)
        except ProcessLookupError:
            break
    else:
        os.kill(pid, 9); raise AssertionError("worker outlived the server")
