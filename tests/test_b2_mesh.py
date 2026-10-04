"""Ren Ishikawa's mesh audit (qa/mesh_audit.md, 2026-10-04): hollow void shells, Simplify/Cut silent damage, extreme aspect ratio,
base_mm=0, lithophane border vs requested width."""
import io, os
import numpy as np, pytest, trimesh
from PIL import Image
from app.core import geometry, meshedit
from tests import b1
from tests.b1 import client, ADULT, ADMIN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VASE = os.path.join(ROOT, "static", "sample_model.stl")


def _gear_mesh():
    """Same gear/bracket as reports/qa_samples/make_samples.py (the file Ren used: 58,976 triangles), rebuilt here so the tests need no extra file."""
    from shapely.geometry import Point, Polygon
    pts = []
    for i in range(24 * 4):
        a = 2 * np.pi * i / 96; r = 30 if i % 4 in (1, 2) else 26
        pts.append((r * np.cos(a), r * np.sin(a)))
    p = Polygon(pts).difference(Point(0, 0).buffer(8, 128))
    for k in range(6):
        a = 2 * np.pi * k / 6; p = p.difference(Point(15 * np.cos(a), 15 * np.sin(a)).buffer(3, 128))
    g = trimesh.creation.extrude_polygon(p, 8)
    while len(g.faces) < 25000:
        g = g.subdivide()
    return trimesh.load(io.BytesIO(g.export(file_type="stl")), file_type="stl", force="mesh")      # through binary STL, like the real file


GEARM = None
def gear():
    global GEARM
    GEARM = GEARM or _gear_mesh()
    return GEARM.copy()


def pieces(m):
    ps = m.split(only_watertight=False)
    return len(ps), sum(1 for c in ps if c.volume < 0)


# ---------------------------------------------------------------- hollow
def test_hollow_vase_has_no_sealed_micro_voids_and_reports_the_real_wall():
    m = trimesh.load(VASE, force="mesh")
    out, rep = meshedit.apply(m, "hollow", {"wall": 2, "drain_diameter": 3})
    n, voids = pieces(out)
    assert n == 1 and voids == 0 and out.is_watertight                       # was 333 shells (332 sealed voids/slivers)
    assert rep["cavity_fragments_dropped"] > 100 and rep["thinnest_wall_mm"] is not None
    assert rep["thinnest_wall_mm"] >= 1.0                                    # the audit measured 0.21 mm from the slivers
    a = meshedit.analyze(out); assert a["components"] == 1 and a["internal_voids"] == 0


def test_hollow_keeps_one_intended_cavity_and_analyze_counts_it():
    out, rep = meshedit.apply(trimesh.creation.icosphere(subdivisions=3, radius=30), "hollow", {"wall": 3})
    assert pieces(out) == (2, 1) and rep["cavity_fragments_dropped"] == 0 and rep["thinnest_wall_mm"] >= 2.0
    assert meshedit.analyze(out)["internal_voids"] == 1                      # the UI shows "1 sealed void"


def test_hollow_warns_when_the_real_wall_is_thinner_than_asked():
    out, rep = meshedit.apply(trimesh.load(VASE, force="mesh"), "hollow", {"wall": 2, "drain_diameter": 3})
    assert rep["thinnest_wall_mm"] < 0.75 * 2 and "thinnest wall" in rep["note"]      # honest: this vase is thin in places


# ---------------------------------------------------------------- simplify / cut
def test_simplify_gear_stays_manifold_and_says_when_the_target_was_not_met():
    m = gear()
    out, rep = meshedit.apply(m, "simplify", {"keep_ratio": 0.5})
    a = meshedit.analyze(out)
    assert out.is_watertight and a["nonmanifold_edges"] == 0 and rep["watertight"] is True      # was: watertight False, 2 non-manifold edges
    assert rep["target_met"] is False and "only" in rep["note"] and "keep 50%" in rep["note"]  # was: silent success with -2.4%


def test_simplify_that_works_does_not_cry_wolf():
    out, rep = meshedit.apply(trimesh.creation.icosphere(subdivisions=4), "simplify", {"keep_ratio": 0.5})
    assert rep["target_met"] is True and "note" not in rep and out.is_watertight and len(out.faces) < 0.6 * 5120


def test_simplify_refuses_instead_of_returning_a_broken_surface(monkeypatch):
    import fast_simplification as fs
    real = fs.simplify
    def broken(v, f, **k):
        ov, of = real(v, f, **k); return ov, of[:-3]                           # punches a hole
    monkeypatch.setattr(fs, "simplify", broken)
    with pytest.raises(meshedit.OpError, match="left unchanged"):
        meshedit.apply(trimesh.creation.icosphere(subdivisions=4), "simplify", {"keep_ratio": 0.5})


@pytest.mark.parametrize("z", [2.0, 4.0, 6.0])
def test_cut_gear_gives_a_closed_piece(z):
    out, rep = meshedit.apply(gear(), "cut", {"axis": "z", "position": z, "keep": "above"})
    assert out.is_watertight and rep["watertight"] is True and meshedit.analyze(out)["boundary_edges"] == 0     # was 2,520-21,207 open edges, no warning


def test_cut_warns_when_the_result_is_open(monkeypatch):
    box = trimesh.creation.box(extents=(20, 20, 20))
    real = meshedit._new
    out, rep = meshedit.apply(box, "cut", {"axis": "z", "position": 0, "keep": "above"})
    assert rep["watertight"] is True and rep["warning"] == ""
    # an input that cannot be closed (a lone triangle fan) keeps the existing, explicit "left open" warning
    tri = trimesh.Trimesh([[0, 0, -1], [10, 0, 1], [0, 10, 1]], [[0, 1, 2]], process=False)
    out2, rep2 = meshedit.apply(tri, "cut", {"axis": "z", "position": 0})
    assert rep2["warning"] and "open" in rep2["message"]


# ---------------------------------------------------------------- aspect ratio / base / border
def _img(w, h):
    b = io.BytesIO(); Image.fromarray((np.random.default_rng(1).random((h, w, 3)) * 255).astype("uint8")).save(b, "PNG"); return b.getvalue()


def test_extreme_aspect_ratio_is_refused_without_using_a_history_slot():
    c = client(ADULT)
    r = b1.gen(c, data=_img(10, 1000), name="strip.png", ctype="image/png", mode="relief")
    assert r.status_code == 400 and "very long and thin" in r.json()["detail"] and "Crop" in r.json()["detail"]
    assert c.get("/api/builds").json()["builds"] == []


def test_long_thin_picture_builds_but_warns_and_stays_small():
    c = client(ADULT)
    r = b1.gen(c, data=_img(60, 600), name="tall.png", mode="relief", resolution="300")
    assert r.status_code == 200, r.text
    j = r.json(); assert any("long and thin" in w for w in j["info"]["warnings"])
    assert j["stats"]["triangles"] < 1_500_000


def test_cell_cap_keeps_big_requests_bounded():
    im = Image.new("RGB", (1000, 100))
    assert np.prod(np.asarray(geometry._resize(im, 600)).shape[:2]) <= geometry.MAX_CELLS
    im2 = Image.new("RGB", (100, 1000)); small = geometry._resize(im2, 600)
    assert small.width * small.height <= geometry.MAX_CELLS


@pytest.mark.parametrize("mode", ["relief", "popart"])
def test_base_zero_is_clamped_and_said_out_loud(mode):
    c = client(ADULT)
    r = b1.gen(c, mode=mode, beginner="false", base_mm="0")
    assert r.status_code == 200, r.text
    j = r.json()
    assert geometry.check_params(Image.new("RGB", (50, 50)), mode, {"base_mm": 0})[0]["base_mm"] == geometry.MIN_BASE_MM
    assert any("base of 0 mm can't be printed" in w for w in j["info"]["warnings"])


def test_lithophane_requested_width_is_the_outside_width_with_border():
    im = Image.open(b1.SAMPLE).convert("RGB")
    for border in (3.0, 6.0, 0.0):
        m = geometry.build(im, "lithophane", {"width_mm": 100.0, "border_mm": border, "resolution": 120})
        v = m.bodies[0].vertices
        assert abs((v[:, 0].max() - v[:, 0].min()) - 100.0) < 0.01, border      # was 106.3 for border 3
        if border: assert abs(m.info["border_cells"] * m.info["pitch_mm"] - border) < m.info["pitch_mm"]
