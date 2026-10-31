"""Ordinary 8-9 MB STL/3MF files must reach TorchC0 instead of failing as "too big" (415/422)."""
import io

import numpy as np
import trimesh

from app.api import resin as resin_api
from app.core import resin
from app.services import uploadsafe


def _sphere(count):
    return trimesh.creation.uv_sphere(radius=50, count=[count, count])


def test_normal_3mf_passes_the_upload_gate():
    buf = io.BytesIO()
    _sphere(370).export(buf, file_type="3mf")          # ~7.9 MB zip, ~47 MB model XML, 545k triangles
    data = buf.getvalue()
    assert len(data) < 9 * 1024 * 1024
    uploadsafe.check(data, max_bytes=50 * 1024 * 1024)  # used to raise archive_too_big (32 MB XML cap) -> 415


def test_large_meshes_are_simplified_for_prepare(monkeypatch):
    monkeypatch.setattr(resin_api, "RESIN_MAX_FACES", 5000)
    m = _sphere(80)
    lo, note = resin_api._fit_faces(m)
    assert len(lo.faces) <= 5200 and lo.is_watertight and "simplified copy" in note
    small = trimesh.creation.box(extents=(10, 10, 10))
    same, note = resin_api._fit_faces(small)
    assert same is small and note == ""


def test_batched_ray_queries_match_unbatched():
    m = _sphere(40)
    pts = np.random.default_rng(0).uniform(-60, 60, (137, 3))
    assert (resin._in_batches(m.contains, pts, n=7) == m.contains(pts)).all()
    dirs = np.tile([0, 0, -1.0], (len(pts), 1))
    assert (resin._in_batches(m.ray.intersects_any, pts, dirs) == m.ray.intersects_any(pts, dirs)).all()


def test_3mf_prepare_returns_print_files():
    buf = io.BytesIO()
    _sphere(60).export(buf, file_type="3mf")
    stl = resin_api._to_stl(buf.getvalue())
    out_stl, out_3mf, rep = resin_api._work(stl, "stl", resin.settings({}), None)
    assert len(out_stl) > 1000 and out_3mf[:2] == b"PK" and rep["program"] == resin.NAME
