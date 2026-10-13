"""Audit small blockers (reports/HQ/release-readiness.md #9, #14, #15)."""
import re
from pathlib import Path
import numpy as np, pytest
from app.services import slicer

ROOT = Path(__file__).resolve().parent.parent
K1 = ROOT / "app/profiles/creality_k1.ini"


def test_model_that_fits_the_k1_bed_is_not_refused():
    assert slicer.bed_fit([100, 76, 3], (220, 220), K1) is None
    assert slicer.bed_fit([210, 100, 5], (220, 220), K1) is None


def test_rotated_fit_counts():
    assert slicer.bed_fit([240, 100, 3], (250, 210)) is None       # 240 x 100 fits a 250 x 210 bed


@pytest.mark.parametrize("ext", [[250, 188, 3], [100, 100, 300]])
def test_too_big_is_a_friendly_refusal_with_guidance(ext):
    r = slicer.bed_fit(ext, (220, 220), K1)
    assert r["ok"] is False and r["code"] == "too_big" and r["available"] is True
    m = r["message"]
    assert "too big for your printer's bed" in m and "Split" in m and "Scale" in m
    assert "220 × 220 mm" in m and "slicer failed" not in m.lower()


def test_slice_model_refuses_before_running_the_slicer(tmp_path, monkeypatch):
    monkeypatch.setattr(slicer, "status", lambda: {"available": True, "path": "/nonexistent"})
    called = []
    monkeypatch.setattr(slicer.subprocess, "run", lambda *a, **k: called.append(a))
    class M:
        def solid(self):
            import trimesh
            b = trimesh.creation.box([250, 180, 3]); return b.vertices, b.faces
    r = slicer.slice_model(M(), tmp_path, bed=(220, 220), profile_ini=K1)
    assert r["code"] == "too_big" and not called


def test_mode_select_keeps_its_label_on_phones():
    css = (ROOT / "static/style.css").read_text()
    assert not re.search(r"\.topbar \.modepick label[^{]*\{display:none", css)
    assert re.search(r"\.topbar \.modepick label\{position:absolute;width:1px", css)


def test_axe_is_vendored_and_ui_scripts_never_skip_it():
    assert (ROOT / "tests/vendor/axe.min.js").stat().st_size > 100_000
    for f in (ROOT / "tests").glob("ui_*.py"):
        t = f.read_text()
        assert "/workspace/a11y-tools" not in t.split('"""', 2)[-1], f.name
        assert "SKIP axe" not in t and "if not os.path.exists(AXE): return" not in t, f.name


def test_moderation_page_never_shows_object_object():
    js = (ROOT / "static/moderation.js").read_text()
    assert "j.detail || r.statusText" not in js and "function errText" in js


def test_no_school_features_in_docs():
    for name in ("README.md", "ROADMAP.md"):
        for line in (ROOT / name).read_text().splitlines():
            if "removed" in line.lower() or "not planned" in line.lower():
                continue
            assert not re.search(r"classroom|teacher|class students|school address", line, re.I), (name, line)


def test_new_slice_engine_too_big_also_suggests_split():
    from app.services import slice_engine as eng
    with pytest.raises(eng.SliceError) as e:
        eng.check_fits((440, 100, 100), eng.CREALITY_K1)
    assert "Split" in e.value.message and "Scale" in e.value.message and "50%" in e.value.message
