"""Ren's QA 2026-10-12 (reports/qa/originals-and-regression-2026-10-12.md) bugs 1-2: Hollow enforces / warns about the minimum wall;
Simplify and the analysis never call a mesh with hidden non-manifold edges watertight."""
import os
import numpy as np, pytest, trimesh
from app.core import meshedit as me

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bowtie():
    """Two closed tetrahedra sharing one edge through DUPLICATE vertices: looks watertight unmerged, has a non-manifold edge once merged."""
    a = trimesh.creation.box((1, 1, 1)); b = trimesh.creation.box((1, 1, 1)); b.apply_translation((1, 1, 0))
    return trimesh.Trimesh(np.vstack([a.vertices, b.vertices]), np.vstack([a.faces, b.faces + len(a.vertices)]), process=False)


def test_analysis_counts_non_manifold_edges_hidden_by_duplicate_vertices():
    a = me.analyze(_bowtie())
    assert a["nonmanifold_edges"] > 0 and a["watertight"] is False


def test_simplify_never_reports_a_broken_result_as_watertight():
    m = trimesh.creation.icosphere(4)
    out, r = me.op_simplify(m, {"keep_ratio": 0.5})
    assert r["watertight"] == me._strict_ok(out) and "kept_pct" in r and "% kept" in r["message"]
    assert r["nonmanifold_edges"] == me._nonmanifold(out)
    if not r["watertight"]:
        assert "NOT watertight" in r["warning"]


@pytest.mark.skipif(not me.have_hollow(), reason="hollow deps missing")
def test_hollow_vase_enforces_the_minimum_wall_and_warns_about_thin_spots():
    m = trimesh.load(os.path.join(ROOT, "static", "sample_model.stl"))
    out, r = me.op_hollow(m, {"wall": 2})
    assert r["wall_p1_mm"] >= 2 - r["resolution_mm"]                          # QA expectation: p1 >= wall - one voxel (was 1.23)
    if r["wall_min_probe_mm"] < 2 - r["resolution_mm"]:
        assert "thinnest spot" in r["warning"] and r["note"]                  # any thinner spot is reported, never silent
