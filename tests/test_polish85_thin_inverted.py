"""Will-it-print badge + print check: thin-spot false alarms (same shell, opposite face within 18 deg, >= 2 spots),
inside-out models never 'Will print', and a thin-wall check that runs out of memory says 'thin-wall check skipped'."""
import numpy as np, trimesh, shapely.geometry as sg, manifold3d as mf
from app.services import willprint
from app.core import thickness, meshedit, printcheck


def _m(m): return mf.Manifold(mf.Mesh(np.asarray(m.vertices, np.float32), np.asarray(m.faces, np.uint32)))
def _t(x): g = x.to_mesh(); return trimesh.Trimesh(g.vert_properties[:, :3], g.tri_verts)


def fin(t):
    b = trimesh.creation.box((30, 30, 5)); f = trimesh.creation.box((t, 20, 10)); f.apply_translation([0, 0, 7.5])
    return _t(_m(b) + _m(f))


def wall(t):
    o = trimesh.creation.box((30, 30, 20)); i = trimesh.creation.box((30 - 2 * t, 30 - 2 * t, 20)); i.apply_translation([0, 0, 1])
    return _t(_m(o) - _m(i))


def badge(m): return willprint.check(m, "creality_k1", 0.4, slices_ok=True)


def test_real_fins_and_thin_wall_still_caught_by_badge_and_print_check():
    for m in (fin(0.06), fin(0.25), wall(0.3)):
        assert badge(m)["label"] == "Might print: thin walls"
        assert thickness.analyze(m, 0.42)["verdict"] != "ok"


def test_star_tips_deboss_sliver_and_overlapping_shells_are_not_thin():
    star = sg.Polygon([(np.cos(a) * (20 if i % 2 == 0 else 7), np.sin(a) * (20 if i % 2 == 0 else 7))
                       for i, a in enumerate(np.linspace(0, 2 * np.pi, 10, endpoint=False) + np.pi / 2)])
    plate = trimesh.creation.box((60, 20, 3))
    deb, _ = meshedit.op_text(plate, {"text": "Kobi", "height": 10, "depth": 1.0, "mode": "deboss"})
    a = trimesh.creation.box((20, 20, 20)); b = trimesh.creation.box((20, 20, 20)); b.apply_translation([10, 5, 0.2])
    for m in (trimesh.creation.extrude_polygon(star, 5), deb, trimesh.util.concatenate([a, b])):
        assert badge(m)["label"] == "Will print"
        assert thickness.analyze(m, 0.42)["verdict"] == "ok"


def test_inside_out_cube_is_not_will_print():
    c = trimesh.creation.box((20, 20, 20)); c.invert()
    r = badge(c)
    assert r["label"] != "Will print" and r["checks"]["inside_out"]["ok"] is False
    assert any("inside out" in t for t in r["tips"])
    assert badge(trimesh.creation.box((20, 20, 20)))["label"] == "Will print"


def test_out_of_memory_thin_check_says_skipped_after_a_good_slice(monkeypatch):
    from app.core import guard
    def boom(*a, **k): raise MemoryError()
    monkeypatch.setattr(guard, "run", boom)
    r = badge(trimesh.creation.box((20, 20, 20)))
    assert r["label"] == "Sliced OK; thin-wall check skipped" and r["checks"]["thin_wall"]["skipped"] == "limit"
    pc = printcheck.run(trimesh.creation.box((20, 20, 20)), (220, 220, 250))      # was a 500 MemoryError
    assert any("skipped" in i.lower() for i in pc["issues"])


def test_print_check_warns_on_inside_out_cube():
    c = trimesh.creation.box((20, 20, 20)); c.invert()
    assert any("inside out" in i for i in printcheck.run(c, (220, 220, 250))["issues"])
    assert not any("inside out" in i for i in printcheck.run(trimesh.creation.box((20, 20, 20)), (220, 220, 250))["issues"])
