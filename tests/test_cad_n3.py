"""N3 (Kobi): guarded children must not be starved by the server's reserved-but-unused address space,
and a skipped / timed-out check must never read 'Will print'. CADRT-8 (never above the hard limit) still holds."""
import subprocess
import sys
import textwrap

import numpy as np
import pytest
import trimesh

from app.core import guard, thickness
from app.services import willprint


def _py(code, timeout=180):
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, (r.stdout[-800:], r.stderr[-1500:])
    return r.stdout


def test_n3_child_budget_does_not_shrink_with_parent_reserved_address_space():
    """Server soft cap 300 MB above its VmSize, plus 'reserved' mmaps: a child that needs 600 MB still runs."""
    out = _py("""
        import mmap, resource, time, numpy as np
        from app.core import guard
        def need(mb):
            a = np.ones(mb * 2**20 // 8); return int(a.sum())
        hold = [mmap.mmap(-1, 64 << 20) for _ in range(8)]          # 512 MB reserved, never touched (like old arenas)
        resource.setrlimit(resource.RLIMIT_AS, (guard._vm_bytes() + 300 * 2**20, resource.RLIM_INFINITY))
        t = time.time()
        print("RAN", guard.run(need, 600, mem_mb=1000) == 600 * 2**20 // 8, round(time.time() - t, 1))
        try:
            guard.run(need, 1500, mem_mb=400); print("NOTRIP")
        except guard.Tripped as e:
            print("TRIPPED", e)                                     # the per-child budget is still enforced
        assert guard.MAX_CHILDREN == 2
    """)
    assert "RAN True" in out and "TRIPPED memory" in out, out


def test_n3_cadrt8_never_above_the_hard_limit_and_refuses_fast():
    out = _py("""
        import resource, time, numpy as np
        from app.core import guard
        vm = guard._vm_bytes()
        resource.setrlimit(resource.RLIMIT_AS, (vm + 500 * 2**20, vm + 500 * 2**20))      # `ulimit -v` style (soft = hard)
        hard = resource.getrlimit(resource.RLIMIT_AS)[1]
        assert guard._clamp(vm + 10_000 * 2**20) <= hard
        assert guard.run(abs, -3) == 3
        try:
            guard.run(np.ones, (200_000_000,)); print("NOTRIP")                            # 1.6 GB > hard
        except guard.Tripped:
            print("TRIPPED")
        resource.setrlimit(resource.RLIMIT_AS, (guard._vm_bytes() + 2**20, guard._vm_bytes() + 2**20))
        t = time.time()
        try:
            guard.run(abs, -1); print("RAN")
        except guard.Tripped:
            print("REFUSED", time.time() - t < 2)
    """)
    assert "TRIPPED" in out and "REFUSED True" in out, out


def test_n3_kobi_repro_printcheck_sphere_near_the_soft_cap():
    """Kobi's hr.py in small: 20k-face sphere, VmSize pushed close to a 4.5 GB-style soft cap -> verdict in seconds."""
    out = _py("""
        import mmap, resource, time, trimesh
        from app.core import guard, thickness
        m = trimesh.creation.icosphere(subdivisions=5, radius=10)          # 20 480 faces
        cap = guard._vm_bytes() + 1600 * 2**20
        resource.setrlimit(resource.RLIMIT_AS, (cap, resource.RLIM_INFINITY))
        hold = []
        while guard._vm_bytes() < cap - 200 * 2**20:
            hold.append(mmap.mmap(-1, 64 << 20))
        t = time.time()
        r = guard.run(thickness.analyze, m, 0.8, mem_mb=1200, timeout=60)
        print("VERDICT", r.get("verdict"), time.time() - t < 20)
    """)
    assert "VERDICT ok True" in out, out


def test_n3_batched_rays_match_one_shot_and_stay_small():
    m = trimesh.creation.icosphere(subdivisions=4, radius=10)
    pts, fi = trimesh.sample.sample_surface(m, 700, seed=3)
    nn = m.face_normals[fi]; org = pts - nn * 1e-3
    loc1, ir1, _ = m.ray.intersects_location(org, -nn, multiple_hits=False)
    loc2, ir2 = thickness.first_hits(m, org, -nn, chunk=128)
    a = dict(zip(ir1.tolist(), map(tuple, np.round(loc1, 6)))); b = dict(zip(ir2.tolist(), map(tuple, np.round(loc2, 6))))
    assert a == b and len(a) > 600


@pytest.mark.parametrize("why", ["trip", "busy"])
def test_n3_badge_never_says_will_print_when_thin_wall_check_did_not_run(monkeypatch, why):
    def boom(*a, **k):
        raise guard.Tripped("timeout") if why == "trip" else guard.Busy()
    monkeypatch.setattr(guard, "run", boom)
    cube = trimesh.creation.box((20, 20, 20))
    r = willprint.check(cube, slices_ok=True)
    assert r["checks"]["thin_wall"]["skipped"] == "limit"
    assert r["verdict"] == "unchecked" and "Will print" not in r["label"] and "couldn't check" in r["label"]
    assert any("thin" in t.lower() for t in r["tips"])
    r = willprint.check(cube, slices_ok=None)
    assert r["verdict"] == "unchecked" and "Will print" not in r["label"]
    assert willprint.check(cube, slices_ok=False)["verdict"] == "no"          # a real failure still wins


def test_n3_badge_still_says_will_print_when_the_check_ran():
    r = willprint.check(trimesh.creation.box((20, 20, 20)), slices_ok=True)
    assert r["verdict"] == "yes" and r["label"] == "Will print"


def test_n3_showcase_worst_plate_order_knows_unchecked():
    import inspect
    from app.api import printsetup
    assert '["no", "maybe", "unchecked", "likely", "yes"]' in inspect.getsource(printsetup)


def test_n3_big_model_message_says_too_large_not_no_triangles():
    big = trimesh.creation.icosphere(subdivisions=7, radius=20)        # 327 680 faces
    r = thickness.analyze(big, 0.8)
    assert r["ok"] is False and "too large to analyse fully" in r["reason"] and "No triangles" not in r["reason"]
    assert "327,680" in r["reason"]
    r = thickness.analyze(trimesh.Trimesh(), 0.8)
    assert "no triangles" in r["reason"].lower()
