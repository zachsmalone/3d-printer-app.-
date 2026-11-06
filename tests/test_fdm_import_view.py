"""Large binary STL: the view is a counted triangle sample. The file's triangles are not replaced."""
import struct

import numpy as np

from app.core import plate
from app.services.editproj import iter_binary_stl_preview


def _stl(n: int) -> bytes:
    rec = np.zeros(n, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["v"][:, 0, 0] = np.arange(n)
    raw = rec.tobytes()
    return b"x" * 80 + struct.pack("<I", n) + raw


def test_view_progress_counts_triangles_and_stops_at_the_sample():
    data = _stl(1000)
    events = list(iter_binary_stl_preview(data, max_faces=100))
    views = [e for e in events if e["phase"] == "view"]
    assert views[0]["done"] < views[-1]["done"]
    assert views[-1]["done"] == views[-1]["total"] == 1000
    assert all("percent" not in e for e in events)
    ready = events[-1]
    assert ready["phase"] == "preview_ready"
    assert ready["triangles"] == 1000
    assert ready["preview"]["decimated"] is True
    assert ready["preview"]["authoritative"] is False
    idx = np.frombuffer(__import__("base64").b64decode(ready["preview"]["bodies"][0]["indices"]), dtype="<u4")
    assert len(idx) // 3 <= 100
    assert struct.unpack_from("<I", data, 80)[0] == 1000


def test_small_stl_preview_keeps_every_triangle():
    data = _stl(20)
    ready = list(iter_binary_stl_preview(data, max_faces=100))[-1]
    assert ready["preview"]["decimated"] is False
    idx = np.frombuffer(__import__("base64").b64decode(ready["preview"]["bodies"][0]["indices"]), dtype="<u4")
    assert len(idx) // 3 == 20


def test_large_mesh_is_not_split_on_open(monkeypatch):
    import trimesh
    monkeypatch.setattr(plate, "MAX_SPLIT_FACES", 10)
    a = trimesh.creation.box((1, 1, 1))
    b = a.copy()
    b.apply_translation((10, 0, 0))
    m = trimesh.util.concatenate([a, b])
    assert len(m.faces) > 10
    assert len(plate.objects(m, None)) == 1
    monkeypatch.setattr(plate, "MAX_SPLIT_FACES", 10**9)
    assert len(plate.objects(m, None)) == 2
