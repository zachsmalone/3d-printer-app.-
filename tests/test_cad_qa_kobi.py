"""Regressions for Kobi's CAD QA (B1-B15) and the runtime ceiling (CADRT-1 / B1 / B4)."""
import resource

import numpy as np
import pytest
import trimesh
from scipy.spatial import cKDTree

from app.core import cadops, guard, meshedit, sculptws
from app.services import willprint


def _sq(x0, w=20):
    pts = [(x0, 0), (x0 + w, 0), (x0 + w, w), (x0, w)]
    return {"entities": [{"id": f"s{i}", "type": "line", "p0": list(pts[i]), "p1": list(pts[(i + 1) % 4])} for i in range(4)]}


def _rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _hog():
    return np.ones((400_000_000,), np.float64).sum()          # 3.2 GB


def _boom():
    raise ValueError("x")


def test_guard_trips_cleanly_and_parent_memory_flat():
    before = _rss_mb()
    with pytest.raises(guard.Tripped):
        guard.run(_hog, mem_mb=300)
    assert _rss_mb() - before < 200
    assert guard.run(abs, -2) == 2
    with pytest.raises(ValueError):
        guard.run(_boom)


def test_b1_willprint_big_mesh_skipped_cleanly():
    big = trimesh.creation.icosphere(subdivisions=7, radius=20)    # 327 680 faces
    before = _rss_mb()
    r = willprint.check(big, slices_ok=True)
    assert r["checks"]["thin_wall"]["skipped"] == "too_detailed" and r["verdict"] == "unchecked"      # N3: never "Will print"
    assert "Will print" not in r["label"] and "thin-wall check skipped" in r["label"]
    assert _rss_mb() - before < 300
    assert willprint.check(trimesh.creation.box((0.5, 0.5, 0.5)), slices_ok=True)["verdict"] != "yes"   # B11 size floor


def test_b4_remesh_estimate_exact_and_refused():
    cube = trimesh.creation.box((20, 20, 20)); cube.apply_translation((10, 10, 10))
    with pytest.raises(meshedit.OpError, match="triangles"):
        meshedit.apply(cube, "remesh", {"edge": 0.15})                # 786k actual: refused up front
    out, _ = meshedit.apply(cube, "remesh", {"edge": 1.0})
    assert len(out.faces) <= sculptws.MAX_REMESH_FACES


def test_b2_touching_new_body_refused_union_works():
    m, _ = meshedit.apply(trimesh.Trimesh(), "sketch_extrude", {"sketch": _sq(0), "distance": 20})
    with pytest.raises(meshedit.OpError, match="touch"):
        meshedit.apply(m, "sketch_extrude", {"sketch": _sq(20), "distance": 20, "mode": "new"})
    j, _ = meshedit.apply(m, "sketch_extrude", {"sketch": _sq(20), "distance": 20, "mode": "join"})
    assert abs(j.volume - 16000) < 1
    with pytest.raises(meshedit.OpError, match="touch"):
        meshedit.apply(m, "pattern", {"kind": "linear", "count": 2, "step": [20, 0, 0], "fuse": False})


def test_b3_fillet_boss_watertight_or_refused():
    top = {"origin": [0, 0, 10], "normal": [0, 0, 1]}
    m, _ = meshedit.apply(trimesh.Trimesh(), "sketch_extrude", {"sketch": _sq(0, 40), "distance": 10})
    m, _ = meshedit.apply(m, "sketch_extrude", {"sketch": {"entities": [{"id": "k", "type": "circle", "c": [10, 15], "r": 6}]},
                                               "plane": top, "distance": 8, "mode": "join"})
    try:
        out, _ = meshedit.apply(m, "round_edges", {"radius": 1, "style": "fillet"})
    except meshedit.OpError:
        return
    mm = out.copy(); mm.merge_vertices()
    assert mm.is_watertight and len(cadops.bodies(out)) == 1


def test_b5_b6_symmetry_about_model_centre_and_exact():
    s = trimesh.creation.icosphere(subdivisions=4, radius=10); s.apply_translation((10, 10, 10))
    for brush in ("draw", "inflate", "pinch", "grab"):
        out, _ = sculptws.op_sculpt_stroke(s, {"brush": brush, "radius": 4, "strength": 0.8, "points": [[10.8, 10, 20], [11.5, 10.5, 19.9]],
                                               "normal": [0, 0, 1], "delta": [1, 0, 1], "symmetry_x": True})
        v = out.vertices
        q = v.copy(); q[:, 0] = 20 - q[:, 0]
        assert cKDTree(v).query(q)[0].max() < 1e-6, brush
        moved = np.linalg.norm(v - s.vertices, axis=1) > 1e-6
        assert (s.vertices[moved][:, 0] < 10).any() and (s.vertices[moved][:, 0] > 10).any()


def test_b7_fix_mesh_warns_on_nonflat_fill():
    c = trimesh.creation.box((20, 20, 20))
    adj = c.face_adjacency
    k = np.nonzero(np.abs(np.einsum("ij,ij->i", c.face_normals[adj[:, 0]], c.face_normals[adj[:, 1]])) < 0.5)[0][0]
    keep = np.ones(len(c.faces), bool); keep[adj[k]] = False
    out, rep = meshedit.apply(trimesh.Trimesh(c.vertices, c.faces[keep], process=False), "repair", {})
    if abs(abs(out.volume) - 8000) > 1:
        assert "warning" in rep


def test_b10_inside_out_refused():
    c = trimesh.creation.box((10, 10, 10)); c.invert()
    with pytest.raises(meshedit.OpError, match="inside-out"):
        cadops._to_manifold(c)


def test_b14_b15_label_and_import_order():
    import subprocess, sys
    assert cadops.label("pattern", {"body": 0, "kind": "linear", "count": 3}).endswith("Body 1")
    for mod in ("sculptws", "cadops"):
        r = subprocess.run([sys.executable, "-c", f"import app.core.{mod}; from app.core import meshedit; "
                            "assert 'remesh' in meshedit.OPS and 'pattern' in meshedit.OPS"], capture_output=True)
        assert r.returncode == 0, r.stderr


def test_b1_b4_api_paths_end_cleanly():
    """Big sphere through /api/slice and a 0.15 mm remesh through the edit API: no 500, no big memory jump, scene kept."""
    import io, os, shutil
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    sample = "/workspace/qa/cadws_kobi/samples/sphere_540k.stl"
    data = open(sample, "rb").read() if os.path.exists(sample) else \
        trimesh.creation.icosphere(subdivisions=7, radius=40).export(file_type="stl")
    before = _rss_mb()
    if shutil.which("prusa-slicer") or shutil.which("PrusaSlicer"):
        r = c.post("/api/slice", files={"file": ("sphere.stl", io.BytesIO(data), "model/stl")}, data={"printer_id": "creality_k1"})
        assert r.status_code < 500, r.text[:300]
        if r.status_code == 200 and "will_print" in r.json():
            assert r.json()["will_print"]["checks"]["thin_wall"].get("skipped")
    assert _rss_mb() - before < 1500
    cube = trimesh.creation.box((20, 20, 20)); cube.apply_translation((10, 10, 10))
    j = c.post("/api/edit/new", files={"file": ("c.stl", io.BytesIO(cube.export(file_type="stl")), "model/stl")}).json()
    r = c.post(f"/api/edit/{j['id']}/op", json={"op": "remesh", "params": {"edge": 0.15}})
    assert r.status_code in (400, 422) and "triangles" in r.text
    assert c.get(f"/api/cad/{j['id']}/scene").status_code == 200


def test_cadrt8_guard_respects_tighter_parent_limit():
    """Under `ulimit -v` the guard must clamp (never raise the limit) and still work or refuse kindly."""
    import subprocess, sys, textwrap
    code = textwrap.dedent("""
        import resource, numpy as np
        from app.core import guard
        vm = guard._vm_bytes()
        resource.setrlimit(resource.RLIMIT_AS, (vm + 700 * 2**20, vm + 700 * 2**20))
        assert guard.run(abs, -3) == 3                       # works under the inherited limit
        try:
            guard.run(np.ones, (400_000_000,)); print("NOTRIP")
        except guard.Tripped:
            print("TRIPPED")
        resource.setrlimit(resource.RLIMIT_AS, (guard._vm_bytes() + 2**20, resource.getrlimit(resource.RLIMIT_AS)[1]))
        try:
            guard.run(abs, -1); print("RAN")
        except guard.Tripped:
            print("REFUSED")
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    assert "TRIPPED" in r.stdout and ("REFUSED" in r.stdout or "RAN" in r.stdout)


def test_cadrt9_concurrency_cap_and_more_ops_guarded(monkeypatch):
    for op in ("align", "face_offset", "body_transform", "sculpt_stroke"):
        assert op in meshedit.HEAVY_OPS
    for _ in range(guard.MAX_CHILDREN):
        guard._slots.acquire()
    monkeypatch.setattr(guard, "WAIT_S", 0.2)
    try:
        with pytest.raises(guard.Busy):
            guard.run(abs, -1)
        big = trimesh.creation.icosphere(subdivisions=6)
        with pytest.raises(meshedit.OpError, match="busy"):
            meshedit.apply(big, "translate", {"dx": 1})
    finally:
        for _ in range(guard.MAX_CHILDREN):
            guard._slots.release()
    assert guard.run(abs, -1) == 1
