"""QA B11: the Will-print badge must not say "Will print" when walls are far below one line or the slice used ~0 g."""
import trimesh

from app.services import willprint


def _box_with_fin(fin=0.06):
    """20 mm cube with a 0.06 mm thick, 12 mm fin on top: a small share of the surface (< 5 %) but unprintable."""
    base = trimesh.creation.box((20, 20, 20)).subdivide().subdivide().subdivide()
    f = trimesh.creation.box((12, fin, 4)); f.apply_translation([0, 0, 12])
    return trimesh.util.concatenate([base, f])


def test_few_spots_far_below_one_line_is_not_will_print():
    r = willprint.check(_box_with_fin(), "creality_k1", 0.4, slices_ok=True)
    th = r["checks"]["thin_wall"]
    assert th["thin_fraction"] <= willprint.THIN_FAIL_FRACTION      # the old 5 % rule alone let this pass
    assert th["ok"] is False and th["thin_count"] >= willprint.THIN_MIN_SPOTS and th["thinnest_mm"] < 0.42
    assert r["verdict"] == "maybe" and r["label"] == "Might print: thin walls"
    assert any("thinnest about" in t for t in r["tips"])


def test_zero_gram_slice_is_not_will_print():
    r = willprint.check(trimesh.creation.box((20, 20, 20)), "creality_k1", 0.4, slices_ok=True, filament_g=0.0)
    assert r["verdict"] == "maybe" and r["label"] == "Might print: almost no filament"
    assert any("0.00 g" in t for t in r["tips"])
    ok = willprint.check(trimesh.creation.box((20, 20, 20)), "creality_k1", 0.4, slices_ok=True, filament_g=7.1)
    assert ok["verdict"] == "yes" and ok["label"] == "Will print"


def test_already_fixed_cases_keep_working():
    tiny = willprint.check(trimesh.creation.box((0.5, 0.5, 0.5)), "creality_k1", 0.4, slices_ok=True, filament_g=0.0)
    assert tiny["label"] == "Might print: thin walls"
    assert not any("thinnest about" in t for t in tiny["tips"])     # 0.5 mm isn't under the 0.42 mm line
    s = trimesh.creation.icosphere(subdivisions=6)                   # 81 920 faces -> fine; force the size cap below
    old = willprint.THIN_MAX_FACES
    try:
        willprint.THIN_MAX_FACES = 1000
        s.apply_scale(10)
        big = willprint.check(s, "creality_k1", 0.4, slices_ok=True, filament_g=5.0)
    finally:
        willprint.THIN_MAX_FACES = old
    assert big["verdict"] == "unchecked" and big["label"] == "Sliced OK; couldn't check thin walls"   # N3: never "Will print"
    ok = willprint.check(trimesh.creation.box((20, 20, 20)), "creality_k1", 0.4, slices_ok=True)
    assert ok["label"] == "Will print"
