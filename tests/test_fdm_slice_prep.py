"""FDM slice prep stays faithful: no extra mesh load without a plate, G-code bytes unchanged, truthful timeout."""
import subprocess

from app.api import slice as slice_api
from app.services import filament_slots as fs
from app.services import slice_engine as eng


def test_plate_slice_does_not_load_the_mesh_without_a_layout(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("mesh loaded")

    monkeypatch.setattr("app.services.editproj.mesh_at", boom)
    monkeypatch.setattr("app.services.history.store.get", lambda _bid: {"kind": "edit", "head": 0})
    assert slice_api.plate_on_bed("abc", None) == (None, [])


def test_keep_gcode_line_matches_strip():
    body = "T0\nG1 X1\nM104 S200 T3\nM109 S200\nM600\n"
    plan = fs.plan([], fs.parse_slots(None))
    assert "".join(line for line in body.splitlines(keepends=True) if fs.keep_gcode_line(line, plan)) == fs.strip_unused_heads(body, plan)


def test_timeout_names_the_slicer_stage_and_does_not_blame_startup(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        err = subprocess.TimeoutExpired("prusa-slicer", 300)
        err.stdout = "10 => Processing triangulated mesh\n30 => Preparing infill\n"
        err.stderr = ""
        raise err

    monkeypatch.setattr(subprocess, "run", boom)
    try:
        eng.run_engine("/usr/bin/prusa-slicer", tmp_path / "a.ini", tmp_path / "m.stl", tmp_path / "o.gcode")
    except eng.SliceError as e:
        assert e.code == "slice_timeout" and e.status == 504
        assert "Preparing infill" in e.message
        assert "not changed" in e.message
        assert "couldn't start" not in e.message
    else:
        raise AssertionError("expected SliceError")


def test_timeout_with_no_output_is_still_not_the_model(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(subprocess.TimeoutExpired("x", 1)))
    try:
        eng.run_engine("/usr/bin/prusa-slicer", tmp_path / "a.ini", tmp_path / "m.stl", tmp_path / "o.gcode")
    except eng.SliceError as e:
        assert e.code == "slicer_unavailable" and "isn't your model" in e.message
    else:
        raise AssertionError("expected SliceError")
