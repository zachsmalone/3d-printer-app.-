"""Batch 1: derived exports follow the mesh, including when the step index does not change."""
import os

import pytest
import trimesh

from tests.b1 import box_stl, client

from app.core import exporters
from app.services import editproj
from app.services.history import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def new_edit(c, title="Box"):
    r = c.post("/api/edit/new", files={"file": ("b.stl", box_stl(), "application/octet-stream")}, data={"title": title})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def extent_of(path):
    m = trimesh.load(path, file_type="stl")
    return max(float(x) for x in m.extents)


def test_undo_then_different_edit_refreshes_export_at_the_same_head():
    c = client()
    bid = new_edit(c)
    editproj.add_op(bid, "scale", {"factor": 2, "pivot": "origin"})
    editproj.ensure_exports(bid)
    assert extent_of(store.dir(bid) / "model.stl") == pytest.approx(20, abs=0.05)
    editproj.undo(bid)  # head moves back; the file is still the ×2 mesh until the next export
    editproj.add_op(bid, "scale", {"factor": 3, "pivot": "origin"})
    assert store.get(bid)["head"] == 1
    editproj.ensure_exports(bid)
    assert extent_of(store.dir(bid) / "model.stl") == pytest.approx(30, abs=0.05)


def test_dimension_change_refreshes_export_without_a_new_head():
    c = client()
    bid = new_edit(c)
    assert c.put(f"/api/edit/{bid}/dims", json={"dims": {"s": 2}}).status_code == 200
    made = c.post(f"/api/edit/{bid}/op", json={"op": "scale", "params": {"factor": "$s", "pivot": "origin"}})
    assert made.status_code == 200, made.text
    assert max(made.json()["stats"]["size_mm"]) == pytest.approx(20, abs=0.05)
    head = store.get(bid)["head"]
    changed = c.put(f"/api/edit/{bid}/dims", json={"dims": {"s": 3}})
    assert changed.status_code == 200, changed.text
    assert store.get(bid)["head"] == head
    assert max(changed.json()["stats"]["size_mm"]) == pytest.approx(30, abs=0.05)
    stl = c.get(f"/api/download/{bid}/stl")
    assert stl.status_code == 200, stl.text
    m = trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl")
    assert max(float(x) for x in m.extents) == pytest.approx(30, abs=0.05)


def test_text_that_no_longer_passes_is_left_out_of_the_warm_cache_and_the_export():
    c = client()
    bid = new_edit(c)
    made = c.post(f"/api/edit/{bid}/op", json={"op": "text", "params": {"text": "Hello", "height": 5, "depth": 1, "mode": "emboss", "face": "top"}})
    assert made.status_code == 200, made.text
    editproj.ensure_exports(bid)
    with_text = (store.dir(bid) / "model.stl").read_bytes()
    plain = exporters.to_stl(editproj.as_model(editproj.mesh_at(bid, head=0), "Box"))
    assert with_text != plain
    meta = store.get(bid)
    meta["ops"][0]["params"]["text"] = "sh1t"  # stored before the current word list
    store.save(meta)
    skipped = editproj.mesh_at(bid)
    base = editproj.mesh_at(bid, head=0)
    assert len(skipped.faces) == len(base.faces)
    editproj.ensure_exports(bid)
    exported = (store.dir(bid) / "model.stl").read_bytes()
    assert exported != with_text
    loaded = trimesh.load(store.dir(bid) / "model.stl", file_type="stl")
    assert len(loaded.faces) == len(base.faces)
    assert any(w.startswith("Left out of the model:") for w in store.get(bid).get("warnings") or [])


def test_a_changed_text_rule_drops_the_warm_mesh(monkeypatch):
    c = client()
    bid = new_edit(c)
    made = c.post(f"/api/edit/{bid}/op", json={"op": "text", "params": {"text": "Hello", "height": 5, "depth": 1, "mode": "emboss", "face": "top"}})
    assert made.status_code == 200, made.text
    base_faces = len(editproj.mesh_at(bid, head=0).faces)
    assert len(editproj.mesh_at(bid).faces) != base_faces
    real = editproj._replay_safe

    def veto(o):
        if o.get("op") == "text":
            return False
        return real(o)

    monkeypatch.setattr(editproj, "_replay_safe", veto)
    assert len(editproj.mesh_at(bid).faces) == base_faces


def test_cad_exit_is_save_aware_in_source():
    html = open(os.path.join(ROOT, "static/cad.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "static/cad.js"), encoding="utf-8").read()
    assert 'aria-label="Exit workspace"' in html
    assert "zeimSave.leave" in js
