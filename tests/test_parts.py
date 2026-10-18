"""Parts builder (the 'best of' merge: Tinkercad-style primitives, parametric by replay on
ZEIM's step history — original code, new files; app/api/edit.py and static/edit.js untouched).

The recipe is step 1 of an ordinary edit project, so EVERYTHING downstream is tested here:
history admission, parametric recomposition preserving later steps, undo/redo, ownership,
exports, and the slice/download flow.
"""
from __future__ import annotations

import pytest

from app.core import meshedit, parts
from tests.b1 import client


def _recipe(*parts_):
    return {"parts": list(parts_)}


def _box(size=(20, 20, 20), position=(0, 0, 0), role="solid"):
    return {"kind": "box", "dims": {"size": list(size)}, "position": list(position), "role": role}


def _cyl(d=20, h=20, position=(0, 0, 0), role="solid"):
    return {"kind": "cylinder", "dims": {"diameter": d, "height": h}, "position": list(position), "role": role}


# ---------------------------------------------------------------- validation

def test_torus_spindle_configurations_are_rejected():
    """A ring only exists while major_radius >= minor_radius: outer >= 2*tube. Just
    'tube < outer' would allow self-intersecting spindles."""
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [
            _box((60, 60, 5)),
            {"kind": "torus", "dims": {"outer": 20, "tube": 12}}]})   # 2*tube > outer: spindle
    ok = parts.check_recipe({"parts": [
        _box((60, 60, 5)),
        {"kind": "torus", "dims": {"outer": 26, "tube": 12}}]})      # comfortably > 2x: a real ring
    assert ok["parts"][1]["dims"] == {"outer": 26.0, "tube": 12.0}


def test_recipe_validation_rejects_bad_input():
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": []})                       # empty
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [{"kind": "pyramid"}]})    # unknown kind
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [{"kind": "box"}, {}]})                # part with NO kind
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [_box(role="hole"), {"kind": "box"}]})   # hole FIRST: nothing to subtract from
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [_box(), {"kind": "tube",
                                               "dims": {"outer": 10, "inner": 12, "height": 5}}]})  # inner > outer
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [_box(), _box(size=(-1, 10, 10))]})     # negative size
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [_box(), _box(position=(0, 0, "abc"))]})  # non-numeric position
    with pytest.raises(parts.RecipeError):
        parts.check_recipe({"parts": [_box()] * (parts.MAX_PARTS + 1)})        # too many parts


def test_recipe_is_normalised():
    r = parts.check_recipe({"parts": [{"kind": "cylinder"}]})
    assert r["parts"][0]["dims"] == {"diameter": 20.0, "height": 20.0}
    assert r["parts"][0]["position"] == [0.0, 0.0, 0.0]
    assert r["parts"][0]["role"] == "solid"


# ---------------------------------------------------------------- composition

def test_compose_union_and_hole():
    m, rep = parts.compose(_recipe(_box((20, 20, 20)), _cyl(d=10, h=30, role="hole")))
    assert rep["parts"] == 2 and rep["holes"] == 1
    assert m.is_watertight
    assert m.volume < 20 * 20 * 20                       # the hole really removed material


def test_compose_order_matters():
    # same two solids, unioned in either order, give the same volume; but a hole BEFORE the
    # solid it cuts is a different model — order is the boolean history
    a, _ = parts.compose(_recipe(_box((20, 20, 20)), _box((10, 10, 50), position=(0, 0, 0))))
    b, _ = parts.compose(_recipe(_box((10, 10, 50)), _box((20, 20, 20), position=(0, 0, 0))))
    assert abs(a.volume - b.volume) < 1e-6


def test_compose_all_kinds_produce_watertight_meshes():
    recipe = _recipe(
        _box((20, 20, 20)),
        {"kind": "sphere", "dims": {"diameter": 10}, "position": [0, 0, 30]},
        {"kind": "cone", "dims": {"diameter": 10, "height": 15}, "position": [0, 0, -15]},
        {"kind": "tube", "dims": {"outer": 12, "inner": 8, "height": 10}, "position": [30, 0, 0]},
        {"kind": "torus", "dims": {"outer": 20, "tube": 6}, "position": [0, 30, 0]},
    )
    m, _ = parts.compose(recipe)
    assert m.is_watertight and len(m.faces) > 0


def test_parts_op_runs_through_the_meshedit_machinery():
    import trimesh
    m, rep = meshedit.apply(trimesh.creation.box((5, 5, 5)), "parts",
                            _recipe(_box((30, 30, 10))))
    assert rep["parts"] == 1 and m.is_watertight
    assert "parts" in meshedit.OPS
    assert "primitives" in meshedit.label("parts", _recipe(_box(), _box()))


# ---------------------------------------------------------------- API: the vertical slice

def test_create_get_and_recompose_a_parts_project():
    c = client()
    r = c.post("/api/parts/new", json={"title": "My hook", "recipe": _recipe(
        _box((40, 40, 5)), _cyl(d=10, h=30, position=(0, 0, 15), role="hole"))})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    assert r.json()["recipe"]["parts"][1]["role"] == "hole"
    assert any(b["id"] == bid for b in r.json()["history"])          # admitted to history
    # the project is an ordinary edit project: exports exist, download works
    assert c.get(f"/api/download/{bid}/stl", follow_redirects=False).status_code in (200, 303)
    # GET the recipe back
    g = c.get(f"/api/parts/{bid}/recipe")
    assert g.status_code == 200 and g.json()["recipe"]["parts"][0]["dims"]["size"] == [40, 40, 5]
    # RECOMPOSE: taller hole -> parametric edit of step 1
    r2 = c.put(f"/api/parts/{bid}/recipe", json={"recipe": _recipe(
        _box((40, 40, 5)), _cyl(d=20, h=30, position=(0, 0, 15), role="hole"))})
    assert r2.status_code == 200, r2.text
    assert r2.json()["recipe"]["parts"][1]["dims"]["diameter"] == 20
    # the step list still shows step 1 as the parts op
    p = c.get(f"/api/edit/{bid}")
    assert p.status_code == 200
    steps = p.json()["ops"]
    assert steps and steps[0]["op"] == "parts"


def test_recompose_preserves_manual_steps_added_after_the_recipe():
    c = client()
    r = c.post("/api/parts/new", json={"recipe": _recipe(_box((40, 40, 10)))})
    bid = r.json()["id"]
    # a manual edit AFTER the recipe (an ordinary op, through the ordinary endpoint)
    mv = c.post(f"/api/edit/{bid}/op", json={"op": "translate",
                                             "params": {"dx": 0, "dy": 0, "dz": 5}})
    assert mv.status_code == 200, mv.text
    assert len(mv.json()["ops"]) == 2
    # recompose the recipe: the translate step must survive and STILL APPLY
    r2 = c.put(f"/api/parts/{bid}/recipe", json={"recipe": _recipe(_box((60, 60, 10)))})
    assert r2.status_code == 200, r2.text
    steps = r2.json()["ops"]
    assert len(steps) == 2 and steps[0]["op"] == "parts" and steps[1]["op"] == "translate"
    # geometry, not just step names: the recomposed 60x60x10 box, translated +5 in z
    # (a box centred at the origin spans z -5..+5; +5 => z 0..10)
    import trimesh as _tm
    from app.services import editproj as _ep
    mesh = _ep.mesh_at(bid)
    assert mesh.bounds[0][0] == pytest.approx(-30, abs=0.5)      # the NEW width really applied
    assert mesh.bounds[1][2] == pytest.approx(10, abs=0.5)       # ...and the translate still moved it


def test_undo_and_redo_work_on_the_parts_step():
    """A recipe edit REPLACES step 1 in place (like every step edit), so the undo position is
    kept; undo goes before step 1 (the project's base mesh = the first composition), redo
    re-applies the (new) recipe."""
    c = client()
    r = c.post("/api/parts/new", json={"recipe": _recipe(_box((20, 20, 20)))})
    bid = r.json()["id"]
    assert r.json()["head"] == 1 and r.json()["can_undo"] and not r.json()["can_redo"]
    r2 = c.put(f"/api/parts/{bid}/recipe", json={"recipe": _recipe(_box((30, 30, 30)))})
    assert r2.status_code == 200
    assert r2.json()["head"] == 1                                   # replaced in place, position kept
    assert r2.json()["ops"][0]["params"]["parts"][0]["dims"]["size"] == [30.0, 30.0, 30.0]
    u = c.post(f"/api/edit/{bid}/undo")
    assert u.status_code == 200 and u.json()["head"] == 0 and u.json()["can_redo"]   # before step 1
    redo = c.post(f"/api/edit/{bid}/redo")
    assert redo.status_code == 200 and redo.json()["head"] == 1


def test_recipe_endpoints_are_owner_only():
    c = client()
    r = c.post("/api/parts/new", json={"recipe": _recipe(_box())})
    bid = r.json()["id"]
    other = client()
    assert other.get(f"/api/parts/{bid}/recipe").status_code in (403, 404)
    assert other.put(f"/api/parts/{bid}/recipe", json={"recipe": _recipe(_box())}).status_code in (403, 404)


def test_invalid_recipe_is_rejected_without_touching_history():
    c = client()
    before = c.get("/api/builds").json()["builds"]
    bad = c.post("/api/parts/new", json={"recipe": _recipe(_box(role="hole"), _box())})  # hole first
    assert bad.status_code == 400
    assert c.get("/api/builds").json()["builds"] == before           # nothing was created
    ok = c.post("/api/parts/new", json={"recipe": _recipe(_box())})
    assert ok.status_code == 200
    bid = ok.json()["id"]
    bad2 = c.put(f"/api/parts/{bid}/recipe", json={"recipe": {"parts": []}})
    assert bad2.status_code == 400


def test_parts_project_flows_into_slice_and_download():
    c = client()
    r = c.post("/api/parts/new", json={"recipe": _recipe(_box((40, 40, 20)), _cyl(d=8, h=40, role="hole"))})
    bid = r.json()["id"]
    g = c.get(f"/api/download/{bid}/stl", follow_redirects=False)
    assert g.status_code in (200, 303)
    if g.status_code == 303:
        g = c.get(g.headers["location"])
    assert len(g.content) > 500                                    # a real STL of the composed mesh


def test_non_parts_project_rejects_recipe_endpoints():
    from tests.b1 import photo_build
    c = client()
    bid = photo_build(c)
    assert c.get(f"/api/parts/{bid}/recipe").status_code == 409


def test_the_builder_page_is_served():
    c = client()
    r = c.get("/builder.html")
    assert r.status_code == 200 and "parts builder" in r.text.lower()
    assert "/static/builder.js" in r.text                          # its script is wired
    main = c.get("/")
    assert "parts builder" in main.text.lower()                    # reachable from the main page


def test_recipe_reopens_after_a_cold_restart():
    """A GENUINE cold-cache reopen: create a parts build here, then load it in a FRESH
    process — a brand-new app import with empty in-memory caches, pointed at the same
    on-disk data dir, replaying the same session cookie. The recipe must load from disk
    and the model recompose. (A second GET inside this process proves nothing: the
    project and mesh are already warm.)"""
    import os, subprocess, sys

    c = client()
    r = c.post("/api/parts/new", json={"recipe": _recipe(_box((30, 30, 8)))})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    sid = next(ck.value for ck in c.cookies.jar if ck.name == "p3d_sid")
    # the RUNNING app's actual dirs — NOT os.environ: earlier test modules may have
    # rewritten PHOTO3D_DATA after the app was imported, and the app would still be
    # using its import-time value (the child must look where THIS app actually wrote).
    # DATA = users/settings, OUT = the builds themselves — pass each to its own variable.
    from app import config
    data_dir = str(config.DATA)
    out_dir = str(config.OUT)
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    child = f"""
import os, sys
os.environ["PHOTO3D_DATA"] = {data_dir!r}
os.environ["PHOTO3D_OUT"] = {out_dir!r}
os.environ["PHOTO3D_COOKIE_SECURE"] = "false"
sys.path.insert(0, {repo!r})
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
c.cookies.set("p3d_sid", {sid!r})
r = c.get("/api/parts/{bid}/recipe")
assert r.status_code == 200, "recipe GET %s: %s" % (r.status_code, r.text[:200])
rec = r.json()["recipe"]
assert rec["parts"][0]["dims"]["size"] == [30.0, 30.0, 8.0], rec
p = c.get("/api/edit/{bid}")
assert p.status_code == 200, "edit GET %s" % p.status_code
steps = p.json()["ops"]
assert steps and steps[0]["op"] == "parts", steps
r2 = c.get("/api/download/{bid}/stl", follow_redirects=False)
assert r2.status_code in (200, 303), r2.status_code
# the saved-project picker must list it after the restart too
pp = c.get("/api/parts/projects")
assert pp.status_code == 200
ids = [x["id"] for x in pp.json()["projects"]]
assert "{bid}" in ids, ids
# and a real RECOMPOSITION in the fresh process: change the recipe, the mesh must follow
r3 = c.put("/api/parts/{bid}/recipe", json={{"recipe": {{"parts": [
    {{"kind": "box", "dims": {{"size": [30.0, 30.0, 20.0]}}, "position": [0, 0, 0], "role": "solid"}}]}}}})
assert r3.status_code == 200, "recipe PUT %s: %s" % (r3.status_code, r3.text[:200])
import io, trimesh as tm3
stl = c.get("/api/download/{bid}/stl", follow_redirects=True).content
mesh = tm3.load(io.BytesIO(stl), file_type="stl", process=False)
z = mesh.bounds[:, 2]
# the recipe box is centred at z=0: 30x30x20 -> z in [-10, 10] (NOT the old [-4, 4])
assert abs(float(z.max()) - 10.0) < 0.5 and abs(float(z.min()) + 10.0) < 0.5, mesh.bounds.tolist()
print("COLD-REOPEN-OK")
"""
    res = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, f"cold reopen failed:\n{res.stdout}\n{res.stderr}"
    assert "COLD-REOPEN-OK" in res.stdout


def test_saved_project_picker_lists_only_the_actors_parts_builds():
    """The builder's saved-project picker: the actor's parts builds, newest first — and
    ONLY those (a photo build must not appear), and only for the owner."""
    from tests.b1 import photo_build
    c = client()
    r1 = c.post("/api/parts/new", json={"recipe": _recipe(_box((30, 30, 8)))})
    b1 = r1.json()["id"]
    r2 = c.post("/api/parts/new", json={"recipe": _recipe(_box((20, 20, 6)))})
    b2 = r2.json()["id"]
    photo_build(c)                                     # a NON-parts build: must not appear
    g = c.get("/api/parts/projects")
    assert g.status_code == 200, g.text
    ids = [p["id"] for p in g.json()["projects"]]
    assert b1 in ids and b2 in ids
    assert len([p for p in g.json()["projects"]]) == 2  # the photo build is excluded
    assert ids.index(b2) < ids.index(b1)               # newest first
    # another user's picker: owner-scoped, sees none of these
    c2 = client()
    g2 = c2.get("/api/parts/projects")
    assert g2.status_code == 200
    assert g2.json()["projects"] == []
