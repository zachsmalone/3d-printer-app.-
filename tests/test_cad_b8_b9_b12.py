"""QA B8 / B9 / B12 (cad-workspace-qa-2026-10-18): CAD import units, size warning after a unit conversion,
Save-as-version history / colour warning / import title."""
import io
import os
import re

import trimesh

from tests import b1  # noqa: F401  (isolated PHOTO3D_OUT / DATA before the app is imported)
from tests.b1 import ADULT, client, gen

from app.core import meshedit
from app.services.history import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    return open(os.path.join(ROOT, "static", name), encoding="utf-8").read()


def _cube(side):
    m = trimesh.creation.box((side, side, side)); m.apply_translation((side / 2,) * 3)
    return m.export(file_type="stl")


def _new(c, data, units="mm", **form):
    return c.post("/api/edit/new", files={"file": ("part.stl", io.BytesIO(data), "model/stl")},
                  data={"units": units, "auto_delete_oldest": "true", **form})


# ---------------------------------------------------------------- B9
def test_b9_size_warning_uses_the_converted_size():
    c = client(ADULT)
    r = _new(c, _cube(1.0), units="in"); assert r.status_code == 200, r.text
    j = r.json()
    assert j["stats"]["size_mm"] and max(j["stats"]["size_mm"]) == __import__("pytest").approx(25.4, abs=1e-3)
    assert not any("only" in w and "across" in w for w in j["warnings"]), j["warnings"]
    r = _new(c, _cube(0.02), units="m"); assert r.status_code == 200, r.text
    assert not any("across" in w for w in r.json()["warnings"]), r.json()["warnings"]
    # the warning still fires when the converted size really is tiny / huge
    w = _new(c, _cube(1.0), units="mm").json()["warnings"]
    assert any("only 1 mm across" in x for x in w), w
    w = _new(c, _cube(100.0), units="in").json()["warnings"]      # 2540 mm
    assert any("2540 mm across" in x for x in w), w


def test_b9_load_mesh_judges_the_scaled_size_but_returns_the_unscaled_mesh():
    m, w = meshedit.load_mesh(_cube(1.0), "stl", units_scale=25.4)
    assert max(m.extents) == __import__("pytest").approx(1.0) and not w
    assert meshedit.load_mesh(_cube(1.0), "stl")[1]                 # default (mm) keeps the old hint
    assert meshedit.size_warnings(25.4) == [] and meshedit.size_warnings(0.5) and meshedit.size_warnings(2000)


def test_b9_multi_upload_uses_the_converted_size_too():
    c = client(ADULT)
    r = c.post("/api/edit/multi", files=[("files", ("a.stl", io.BytesIO(_cube(1.0)), "model/stl")),
                                             ("files", ("b.stl", io.BytesIO(_cube(0.5)), "model/stl"))],
               data={"mode": "plate", "units": "in", "auto_delete_oldest": "true"})
    assert r.status_code == 200, r.text
    assert not any("only" in w and "across" in w for w in r.json()["project"]["warnings"]), r.json()["project"]["warnings"]


# ---------------------------------------------------------------- B8
def test_b8_cad_open_menu_has_a_units_picker_sent_with_the_import():
    html, js = _src("cad.html"), _src("cad.js")
    sel = re.search(r'<select id="cwUnits"[^>]*>(.*?)</select>', html, re.S)
    assert sel, "units picker missing from the CAD Open menu"
    vals = re.findall(r'<option value="(\w+)"', sel.group(1))
    assert vals[:3] == ["mm", "cm", "in"] and set(vals) <= set(meshedit.UNIT_MM)
    assert html.index('id="cwUnits"') < html.index('id="cwImport"')       # chosen before picking the file
    imp = js[js.index("async function importFile"):]; imp = imp[:imp.index("\n}\n")]
    assert 'fd.append("units"' in imp and "#cwUnits" in imp


def test_b8_api_honours_the_units_the_cad_picker_sends():
    c = client(ADULT)
    for u, k in (("mm", 1.0), ("cm", 10.0), ("in", 25.4)):
        j = _new(c, _cube(2.0), units=u).json()
        assert abs(max(j["stats"]["size_mm"]) - 2.0 * k) < 1e-3, (u, j["stats"]["size_mm"])
        assert (u == "mm") == (not any(o["op"] == "scale" for o in j["ops"]))


# ---------------------------------------------------------------- B12
def test_b12_save_as_version_keeps_history_and_the_source_is_unchanged():
    c = client(ADULT)
    v1 = _new(c, _cube(20.0)).json()["id"]
    assert c.post(f"/api/edit/{v1}/op", json={"op": "scale", "params": {"factor": 1.5}}).status_code == 200
    assert c.post(f"/api/edit/{v1}/op", json={"op": "translate", "params": {"dz": 3}}).status_code == 200
    src_before = store.get(v1)
    r = c.post("/api/edit/new", data={"from_build": v1, "title": "Bracket v2", "auto_delete_oldest": "true"})
    assert r.status_code == 200, r.text
    j = r.json(); v2 = j["id"]
    assert v2 != v1 and j["title"] == "Bracket v2"
    assert [o["op"] for o in j["ops"]] == ["scale", "translate"] and j["head"] == 2
    assert j["base"]["type"] == "upload"                             # not "from a build (kept as-is)"
    assert not any("Colours" in w for w in j["warnings"]), j["warnings"]
    assert abs(max(j["stats"]["size_mm"]) - 30.0) < 1e-3
    # an earlier step of v2 is still editable, and changing it leaves v1 alone
    r = c.put(f"/api/edit/{v2}/step/1", json={"params": {"factor": 2.0}})
    assert r.status_code == 200, r.text
    assert abs(max(r.json()["stats"]["size_mm"]) - 40.0) < 1e-3
    after = store.get(v1)
    assert after["ops"] == src_before["ops"] and after["head"] == src_before["head"]
    assert abs(max(after["stats"]["size_mm"]) - 30.0) < 1e-3
    assert (store.dir(v2) / "original.stl").read_bytes() == (store.dir(v1) / "original.stl").read_bytes()


def test_b12_redo_tail_is_not_copied():
    c = client(ADULT)
    v1 = _new(c, _cube(20.0)).json()["id"]
    c.post(f"/api/edit/{v1}/op", json={"op": "scale", "params": {"factor": 2}})
    c.post(f"/api/edit/{v1}/undo")
    j = c.post("/api/edit/new", data={"from_build": v1, "auto_delete_oldest": "true"}).json()
    assert j["ops"] == [] and j["head"] == 0 and not j["can_redo"]


def test_b12_cad_design_version_keeps_its_cad_steps():
    c = client(ADULT)
    sq = {"entities": [{"id": "a", "type": "line", "p0": [0, 0], "p1": [20, 0]}, {"id": "b", "type": "line", "p0": [20, 0], "p1": [20, 20]},
                       {"id": "c", "type": "line", "p0": [20, 20], "p1": [0, 20]}, {"id": "d", "type": "line", "p0": [0, 20], "p1": [0, 0]}],
          "constraints": []}
    r = c.post("/api/cad/new", json={"op": "sketch_extrude", "params": {"sketch": sq, "plane": "XY", "distance": 10}, "title": "Block",
                                      "auto_delete_oldest": True})
    assert r.status_code == 200, r.text
    v1 = r.json()["id"]
    j = c.post("/api/edit/new", data={"from_build": v1, "title": "Block v2", "auto_delete_oldest": "true"}).json()
    assert j["base"]["type"] == "cad" and [o["op"] for o in j["ops"]] == ["sketch_extrude"]
    assert c.get(f"/api/cad/{j['id']}/scene").status_code == 200
    from app.services import editproj                                 # also after a restart (nothing cached)
    editproj._BASES.clear(); editproj._STATES.clear()
    j3 = c.post("/api/edit/new", data={"from_build": j["id"], "title": "Block v3", "auto_delete_oldest": "true"})
    assert j3.status_code == 200, j3.text
    assert [o["op"] for o in j3.json()["ops"]] == ["sketch_extrude"] and abs(j3.json()["stats"]["size_mm"][2] - 10) < 1e-3


def test_b12_colour_warning_only_for_multi_colour_builds():
    c = client(ADULT)
    one = gen(c, mode="relief"); assert one.status_code == 200, one.text
    j = c.post("/api/edit/new", data={"from_build": one.json()["id"], "auto_delete_oldest": "true"}).json()
    assert not any("Colours" in w for w in j["warnings"]), j["warnings"]
    many = gen(c, mode="popart", levels="4"); assert many.status_code == 200, many.text
    j = c.post("/api/edit/new", data={"from_build": many.json()["id"], "auto_delete_oldest": "true"}).json()
    assert any("Colours" in w for w in j["warnings"]), j["warnings"]


def test_b12_cad_import_title_is_not_my_design_nor_the_file_name():
    js = _src("cad.js")
    f = js[js.index("function importTitle"):]; f = f[:f.index("\n}\n")]
    assert '"Imported model"' in f and '"My design"' in f and "S.bid" in f
    imp = js[js.index("async function importFile"):]; imp = imp[:imp.index("\n}\n")]
    assert 'fd.append("title", importTitle())' in imp and "f.name" not in imp
    c = client(ADULT)
    r = c.post("/api/edit/new", files={"file": ("MiaJohnson.stl", io.BytesIO(_cube(20.0)), "model/stl")},
               data={"title": "Imported model", "auto_delete_oldest": "true"})
    assert r.json()["title"] == "Imported model" and "MiaJohnson" not in r.text
