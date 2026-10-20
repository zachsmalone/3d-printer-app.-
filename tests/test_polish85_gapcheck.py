"""Print-in-place gap check: separate parts closer than the safe clearance get a plain warning that never blocks."""
import os
import trimesh
from app.services import willprint

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def two_blocks(gap):
    a = trimesh.creation.box((10, 10, 10)); b = trimesh.creation.box((10, 10, 10)); b.apply_translation([10 + gap, 0, 0])
    return trimesh.util.concatenate([a, b])


def test_tight_gap_warns_but_does_not_block():
    r = willprint.check(two_blocks(0.15), "creality_k1", 0.4, slices_ok=True)
    g = r["checks"]["gaps"]
    assert g["ok"] is False and abs(g["min_gap_mm"] - 0.15) < 0.03
    assert "0.15 mm apart and may fuse together. Aim for at least 0.3 mm" in g["warning"]
    assert r["warnings"] == [g["warning"]] and r["verdict"] == "yes" and r["label"] == "Will print"   # non-blocking


def test_safe_gap_single_body_and_far_parts_are_quiet():
    for m in (two_blocks(0.5), trimesh.creation.box((10, 10, 10)), two_blocks(20)):
        assert willprint.check(m, "creality_k1", 0.4, slices_ok=True)["checks"]["gaps"]["ok"] is True


def test_badge_has_slice_anyway_dismiss():
    js = open(os.path.join(ROOT, "static/printer.js")).read()
    assert "Got it, slice anyway" in js and "sessionStorage" in js and "data-gapok" in js


def test_gap_check_is_fast_on_an_unmerged_stl():
    """STLs load with unshared vertices; the gap check used to treat every triangle as a part (16 s on a lithophane,
    which also kept the test server from shutting down)."""
    import time
    m = trimesh.creation.icosphere(subdivisions=6, radius=20)            # 81k faces
    m = trimesh.Trimesh(m.triangles.reshape(-1, 3), __import__("numpy").arange(len(m.faces) * 3).reshape(-1, 3), process=False)
    t = time.time(); g = willprint.part_gaps(m, 0.3)
    assert time.time() - t < 5 and g["ok"] is True
