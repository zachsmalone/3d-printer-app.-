"""Large STL: the browser draws a sample before the upload finishes. The stored file keeps every triangle."""
import base64
import json
import struct
import subprocess
from pathlib import Path

import numpy as np
import trimesh

from tests import b1  # noqa: F401
from tests.b1 import ADULT, client
from app.services.editproj import iter_binary_stl_preview

ROOT = Path(__file__).resolve().parent.parent


def _client():
    return client(ADULT)


def _indexed_stl(n: int) -> bytes:
    rec = np.zeros(n, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["v"][:, 0, 0] = np.arange(n, dtype=np.float32)
    rec["v"][:, 1, 1] = 1
    rec["v"][:, 2, 2] = 1
    return b"x" * 80 + struct.pack("<I", n) + rec.tobytes()


def test_js_sample_matches_the_server_preview(tmp_path):
    data = _indexed_stl(1000)
    path = tmp_path / "t.stl"
    path.write_bytes(data)
    out = subprocess.check_output(
        ["node", str(ROOT / "tests/stl_sample_check.mjs"), "sample", str(path), "100"],
        text=True,
    )
    js = json.loads(out)
    events = list(iter_binary_stl_preview(data, max_faces=100))
    pos = np.frombuffer(base64.b64decode(events[-1]["preview"]["bodies"][0]["positions"]), dtype="<f4")
    py_ids = [int(pos[i]) for i in range(0, len(pos), 9)]
    assert js["triangles"] == 1000
    assert js["decimated"] is True
    assert js["ids"] == py_ids
    assert len(py_ids) <= 100
    assert struct.unpack_from("<I", data, 80)[0] == 1000


def test_line_parser_joins_a_split_line_without_the_quadratic_copy():
    out = subprocess.check_output(["node", str(ROOT / "tests/stl_sample_check.mjs"), "lines"], text=True)
    assert json.loads(out)["ms"] < 3000


def test_client_view_omits_the_mesh_and_keeps_every_triangle(monkeypatch):
    import time
    from app.core import fdmlean
    from app.services import editproj
    from app.services.history import store
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 200)
    monkeypatch.setattr(editproj, "start_full_check", lambda bid: None)
    c = _client()
    mesh = trimesh.creation.uv_sphere(radius=30, count=[40, 40])
    data = mesh.export(file_type="stl")
    faces = struct.unpack_from("<I", data, 80)[0]
    assert faces > 200
    r = c.post("/api/edit/new", files={"file": ("big.stl", data, "model/stl")},
               data={"fdm_big": "true", "progress": "1", "client_view": "1"})
    assert r.status_code == 200, r.text
    assert len(r.content) < 200_000
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    assert lines[-1]["phase"] == "interactive" and lines[-1]["slice_ready"] is False
    project = lines[-1]["project"]
    assert project["preview"]["bodies"] == []
    assert project["preview"]["authoritative"] is False
    assert project["analysis"]["triangles"] == faces
    assert "positions" not in r.text
    pid = project["id"]
    original = store.dir(pid) / "original.stl"
    for _ in range(50):
        if original.is_file() and original.stat().st_size == len(data):
            break
        time.sleep(0.02)
    assert original.read_bytes() == data
    stored = json.loads((store.dir(pid) / "preview.json").read_text())
    assert stored["bodies"] and stored["bodies"][0]["positions"]
    brief = c.get(f"/api/edit/{pid}?brief=1")
    assert brief.status_code == 200
    assert brief.json()["preview"]["bodies"] == []
    assert "positions" not in brief.text
    full = c.get(f"/api/edit/{pid}")
    assert full.json()["preview"]["bodies"][0]["positions"]
    blocked = c.post("/api/slice", data={"model_id": pid})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "model_pending"
    editproj.finish_full_check(pid)
    ready = c.get(f"/api/edit/{pid}?brief=1")
    assert ready.json()["slice_ready"] is True
    assert ready.json()["analysis"]["triangles"] == faces
    assert original.read_bytes() == data


def test_sources_send_client_view_only_after_a_local_sample():
    edit = (ROOT / "static/edit.js").read_text()
    assert 'fd.append("client_view", "1")' in edit
    assert "sampleBinaryStl" in edit
    assert "Preparing the view…" in edit
    assert "Drawing the model…" in edit
    assert "Uploading…" in edit
    assert "seconds" not in (ROOT / "static/stl-sample.js").read_text()
