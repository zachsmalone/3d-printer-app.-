"""Task 06 (adapted to the current slicer): fit=true shrinks a too-big model to the bed with a 2 mm margin,
never enlarges, refuses absurd shrinks, and reports the scale in the response."""
import pytest
import trimesh

from app.api import slice as sl
from app.services import slice_engine as eng
from tests.test_print_core import box_bytes, fake_engine, client  # noqa: F401  (fixture)

LIMITS = (220.0, 220.0, 250.0)


def test_fit_scale_uses_xy_margin_each_side():
    assert sl.fit_scale((440, 100, 50), LIMITS) == pytest.approx(216 / 440)


def test_fit_scale_uses_z_margin_on_top():
    assert sl.fit_scale((100, 100, 500), LIMITS) == pytest.approx(248 / 500)


def test_already_fits_is_untouched_even_inside_margin():
    assert sl.fit_scale((219, 50, 50), LIMITS) == 1.0


def test_never_enlarges():
    assert sl.fit_scale((5, 5, 5), LIMITS) == 1.0


def _post(c, x, y, z, **data):
    return c.post("/api/slice", files={"file": ("m.stl", box_bytes(x, y, z))},
                  data={"printer_id": "creality_k1", **data})


def test_fit_flag_scales_and_reports(fake_engine):
    c = client()
    r = _post(c, 300, 100, 100, fit="true"); assert r.status_code == 200, r.text
    j = r.json(); s = j["scaling"]
    assert s["scaled"] is True and s["scale"] == pytest.approx(216 / 300, abs=1e-3) and s["margin_mm"] == 2.0
    assert s["original_size_mm"] == [300.0, 100.0, 100.0] and j["scaled_pct"] == pytest.approx(72.0, abs=0.1)
    assert j["model_size_mm"][0] == pytest.approx(216.0, abs=0.01)
    m = trimesh.load(trimesh.util.wrap_as_stream(c.get(j["downloads"]["stl"]).content), file_type="stl")
    assert m.extents[0] / m.extents[1] == pytest.approx(3.0)            # proportions kept


def test_small_model_with_fit_is_unchanged(fake_engine):
    j = _post(client(), 40, 40, 40, fit="true").json()
    assert j["scaling"]["scaled"] is False and j["scaling"]["scale"] == 1.0 and j["scaled_pct"] is None
    assert j["model_size_mm"] == [40.0, 40.0, 40.0]


def test_without_fit_still_refuses_with_hint(fake_engine):
    r = _post(client(), 300, 100, 100)
    assert r.status_code == 422 and "shrink-to-fit" in r.text and not fake_engine


def test_absurd_shrink_is_refused_as_units_mixup(fake_engine):
    r = _post(client(), 5000, 10, 10, fit="true")
    assert r.status_code == 422 and "cannot_fit" in r.text and "units" in r.text and not fake_engine


def test_legacy_scale_to_fit_flag_still_works(fake_engine):
    j = _post(client(), 300, 100, 100, scale_to_fit="true").json()
    assert j["scaling"]["scaled"] is True
