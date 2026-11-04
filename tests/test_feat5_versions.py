"""FEAT5: saved versions of an edit project. Additive storage only; restore saves the current state first."""
import io
import sqlite3

import pytest
import trimesh
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


def _project(c):
    cube = trimesh.creation.box((20, 20, 20)); cube.apply_translation((10, 10, 10))
    j = c.post("/api/edit/new", files={"file": ("c.stl", io.BytesIO(cube.export(file_type="stl")), "model/stl")}).json()
    return j["id"]


def _flow():
    c = TestClient(app)
    bid = _project(c)
    assert c.get(f"/api/edit/{bid}/versions").json()["versions"] == []
    v = c.post(f"/api/edit/{bid}/versions", json={"label": "Plain cube"}).json()
    assert v["version"]["label"] == "Plain cube" and v["version"]["steps"] == 0
    p = c.post(f"/api/edit/{bid}/op", json={"op": "scale", "params": {"factor": 2, "pivot": "origin"}}).json()
    assert p["head"] == 1
    r = c.post(f"/api/edit/{bid}/versions/1/restore")
    assert r.status_code == 200, r.text
    assert r.json()["head"] == 0 and len(r.json()["ops"]) == 0
    vs = c.get(f"/api/edit/{bid}/versions").json()["versions"]
    assert [x["n"] for x in vs] == [1, 2] and vs[1]["steps"] == 1 and vs[1]["label"].startswith("Before restoring")
    assert c.post(f"/api/edit/{bid}/versions/9/restore").status_code == 422
    other = TestClient(app)                       # someone else can't read or save versions
    assert other.get(f"/api/edit/{bid}/versions").status_code in (403, 404)
    assert other.post(f"/api/edit/{bid}/versions", json={}).status_code in (403, 404)
    assert c.post(f"/api/edit/{bid}/versions", json={"label": "<b>"}).status_code == 400
    return bid


def test_versions_json_mode():
    _flow()


def test_versions_db_mode_uses_additive_table(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_MODE", "db")
    monkeypatch.setattr(config, "DATA", tmp_path)
    db.reset()
    try:
        bid = _flow()
        n = db.conn().execute("SELECT COUNT(*) FROM build_versions WHERE bid=?", (bid,)).fetchone()[0]
        assert n == 2
    finally:
        db.reset()


def test_schema_change_is_additive_on_an_existing_db(tmp_path, monkeypatch):
    """An old database (builds table with rows, no build_versions) keeps every row and gains the new table."""
    path = tmp_path / "zeim.sqlite3"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE builds(id TEXT PRIMARY KEY, owner_sid TEXT, visibility TEXT NOT NULL DEFAULT 'private', created TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, saved INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL);"
                      "INSERT INTO builds VALUES('b1','s','private','2026-01-01',0,0,'{}');")
    old.commit(); old.close()
    monkeypatch.setattr(config, "DATA", tmp_path)
    db.reset()
    try:
        c = db.conn()
        assert c.execute("SELECT id FROM builds").fetchall() == [("b1",)]
        assert c.execute("SELECT name FROM sqlite_master WHERE name='build_versions'").fetchone()
    finally:
        db.reset()


def test_schema_has_no_destructive_statements():
    s = db._SCHEMA.upper()
    assert "DROP " not in s and "ALTER " not in s and "DELETE " not in s
