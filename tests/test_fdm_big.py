"""FDM Slicer tab: very big binary STLs (2M+ triangles) open, render and slice (fdm_big=1 → core/fdmlean.py)."""
import struct
import subprocess
from pathlib import Path

import pytest
import trimesh

from tests import b1  # noqa: F401
from tests.b1 import ADULT, client

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def c():
    return client(ADULT)


def _ball():
    return trimesh.creation.uv_sphere(radius=30, count=[80, 80])


def test_shrink_makes_a_valid_smaller_binary_stl():
    from app.core import fdmlean
    m = _ball()
    data = m.export(file_type="stl")
    assert fdmlean.faces_if_big(data, 2000) == len(m.faces)
    out, n, k = fdmlean.shrink(data, 2000)
    assert n == len(m.faces) and 0 < k <= 2000
    assert struct.unpack_from("<I", out, 80)[0] == k and len(out) == 84 + 50 * k
    s = trimesh.load(trimesh.util.wrap_as_stream(out), file_type="stl")
    assert abs(s.extents - m.extents).max() < 3


def test_small_ascii_or_capped_files_are_left_alone():
    from app.core import fdmlean
    m = _ball()
    assert fdmlean.faces_if_big(m.export(file_type="stl"), 10**6) == 0
    assert fdmlean.faces_if_big(trimesh.exchange.stl.export_stl_ascii(m).encode(), 10) == 0
    assert fdmlean.faces_if_big(b"x" * 50, 10) == 0


def test_slice_stays_off_until_the_full_check(c, monkeypatch):
    import json
    import struct
    from app.core import fdmlean
    from app.services import editproj
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 2000)
    monkeypatch.setattr(editproj, "start_full_check", lambda bid: None)
    data = _ball().export(file_type="stl")
    faces = struct.unpack_from("<I", data, 80)[0]
    r = c.post("/api/edit/new", files={"file": ("big.stl", data, "model/stl")}, data={"fdm_big": "true", "progress": "1"})
    assert r.status_code == 200, r.text
    assert "ndjson" in r.headers["content-type"]
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    views = [e for e in lines if e["phase"] == "view"]
    assert views and views[-1]["done"] == views[-1]["total"] == faces
    assert all("percent" not in e for e in lines)
    assert all(e["done"] <= e["total"] for e in views)
    last = lines[-1]
    assert last["phase"] == "interactive" and last["slice_ready"] is False and "percent" not in last
    pid = last["project"]["id"]
    blocked = c.post("/api/slice", data={"model_id": pid})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "model_pending"
    editproj.finish_full_check(pid)
    ready = c.get(f"/api/edit/{pid}")
    assert ready.status_code == 200
    assert ready.json()["slice_ready"] is True
    assert ready.json()["analysis"]["triangles"] == faces


def test_edit_new_keeps_every_triangle(c, monkeypatch):
    import struct
    from app.core import fdmlean
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 2000)
    data = _ball().export(file_type="stl")
    faces = struct.unpack_from("<I", data, 80)[0]
    r = c.post("/api/edit/new", files={"file": ("big.stl", data, "model/stl")}, data={"fdm_big": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slice_ready"] is False
    assert body["analysis"]["triangles"] == faces
    assert not any("simplified copy" in w for w in body.get("warnings", []))
    r2 = c.post("/api/edit/new", files={"file": ("big.stl", data, "model/stl")})
    assert r2.status_code == 200, r2.text
    assert r2.json()["analysis"]["triangles"] == faces
    assert not any("simplified copy" in w for w in r2.json().get("warnings", []))


def test_empty_first_layer_has_its_own_code(monkeypatch, tmp_path):
    from app.services import slice_engine as eng
    out = tmp_path / "o.gcode"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "There is an object with no extrusions in the first layer."))
    with pytest.raises(eng.SliceError) as e:
        eng.run_engine("prusa-slicer", tmp_path / "a.ini", tmp_path / "m.stl", out)
    assert e.value.code == "first_layer_empty"


def test_sources_wire_the_fdm_only_path():
    edit = (ROOT / "static/edit.js").read_text()
    assert 'fd.append("fdm_big", "true")' in edit
    for other in ("static/cad.js", "static/community.js", "static/handoff.js", "static/torchc0.js"):
        p = ROOT / other
        if p.exists():
            assert "fdm_big" not in p.read_text()
    sl = (ROOT / "app/api/slice.py").read_text()
    assert 'e.code != "first_layer_empty"' in sl and '"supports": "auto"' in sl
    assert "max_tasks_per_child=1" in (ROOT / "app/services/willprint.py").read_text()


def test_heavy_fdm_requests_trim_the_heap():
    from app.core import memtrim
    memtrim.trim()                                    # must never raise, glibc or not
    assert "background.add_task(memtrim.trim)" in (ROOT / "app/api/slice.py").read_text()
    assert "background.add_task(memtrim.trim)" in (ROOT / "app/api/edit.py").read_text()


def test_shrink_runs_in_a_fresh_interpreter_not_a_server_fork(monkeypatch):
    from app.core import fdmlean
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 2000)
    out, n, k = fdmlean.shrink_isolated(_ball().export(file_type="stl"))
    assert n == len(_ball().faces) and 0 < k <= 2000 and len(out) == 84 + 50 * k
    assert "guard.run(fdmlean" not in (ROOT / "app/api/edit.py").read_text()
