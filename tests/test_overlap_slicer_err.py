"""Overlap note in /api/repair (non-blocking) + slicer startup failures don't blame the model."""
import subprocess
from pathlib import Path

import pytest
import trimesh
from fastapi.testclient import TestClient

from app.main import app

from app.core import stlrepair
from app.services import slice_engine as eng


def _two(offset):
    a = trimesh.creation.box((10, 10, 10)); b = trimesh.creation.box((10, 10, 10)); b.apply_translation(offset)
    return trimesh.util.concatenate([a, b])


def test_overlap_note_present_and_dismissible():
    _, rep = stlrepair.repair_mesh(_two((4, 3, 2)))
    assert rep["notes"] and rep["notes"][0]["code"] == "overlapping_bodies"
    assert rep["notes"][0]["dismissible"] and "aren't joined" in rep["notes"][0]["text"]


def test_no_note_for_separate_or_single():
    assert stlrepair.repair_mesh(_two((30, 0, 0)))[1]["notes"] == []
    assert stlrepair.repair_mesh(trimesh.creation.box((5, 5, 5)))[1]["notes"] == []


@pytest.fixture
def client():
    return TestClient(app)


def test_repair_api_returns_note_200(client):
    data = _two((4, 3, 2)).export(file_type="stl")
    r = client.post("/api/repair", files={"file": ("o.stl", data, "model/stl")})
    assert r.status_code == 200, r.text
    assert r.json()["notes"][0]["code"] == "overlapping_bodies"


def test_repair_js_renders_dismissible_notes():
    js = (Path(__file__).parents[1] / "static/repair.js").read_text()
    assert "j.notes" in js and "rp-note-x" in js


class _P:
    def __init__(self, rc, err="", out=""): self.returncode, self.stderr, self.stdout = rc, err, out


def _run(monkeypatch, tmp_path, fn):
    monkeypatch.setattr(subprocess, "run", fn)
    with pytest.raises(eng.SliceError) as e:
        eng.run_engine("/x/prusa-slicer", tmp_path / "a.ini", tmp_path / "m.stl", tmp_path / "o.gcode")
    return e.value


@pytest.mark.parametrize("fn", [
    lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("nope")),
    lambda *a, **k: _P(127, "prusa-slicer: error while loading shared libraries: libGLU.so.1: cannot open shared object file"),
    lambda *a, **k: _P(-11),
    lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("x", 1)),
])
def test_startup_failures_dont_blame_model(monkeypatch, tmp_path, fn):
    e = _run(monkeypatch, tmp_path, fn)
    assert e.code == "slicer_unavailable" and e.status == 503
    assert "isn't your model" in e.message and "Fix" not in e.message


def test_real_model_failure_still_model_error(monkeypatch, tmp_path):
    e = _run(monkeypatch, tmp_path, lambda *a, **k: _P(1, "Slicing model... error: empty layers"))
    assert e.code == "slice_failed"
    e = _run(monkeypatch, tmp_path, lambda *a, **k: _P(1, "Objects could not fit on the bed"))
    assert e.code == "too_big"


def test_api_slice_startup_message(monkeypatch, client):
    def boom(*a, **k): raise eng.SliceError("slicer_unavailable", eng.SLICER_ENV_MSG, 503)
    monkeypatch.setattr(eng, "run_engine", boom)
    monkeypatch.setattr(eng, "find_engine", lambda: "/x/prusa-slicer")
    stl = trimesh.creation.box((10, 10, 10)).export(file_type="stl")
    r = client.post("/api/slice", files={"file": ("b.stl", stl, "model/stl")})
    assert r.status_code == 503, r.text
    assert "isn't your model" in r.json()["detail"]["message"]
