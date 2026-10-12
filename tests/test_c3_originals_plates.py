"""Ren's QA 2026-10-12 items 3-4: rain-guard-bird-feeder as per-plate files that fit a 220 x 220 mm K1 bed, a validator that checks the
WHOLE plate, and the catalog's needs-supports / low-contact (brim) flags."""
from pathlib import Path
import pytest
from app import config
from tests.b1 import client, ADULT
from tests.test_c2_originals import REAL


@pytest.mark.skipif(not (REAL / "originals_manifest.json").exists(), reason="real ZEIM Originals library not installed here (it is not in git)")
def test_real_library_qa_flags_supports_brims_and_rain_guard_plates(monkeypatch):
    from app.community import originals_qa
    monkeypatch.setattr(config, "ORIGINALS", REAL)
    o = {i["id"][3:]: i for i in client(ADULT).get("/api/showcase?tab=free").json()["items"] if i.get("original")}
    assert {s for s, i in o.items() if i["needs_supports"]} == originals_qa.NEEDS_SUPPORTS and len(originals_qa.NEEDS_SUPPORTS) == 7
    assert "brim" in o["sleepy-loaf-cat"]["low_contact"] and "brim" in o["chubby-penguin-scarf"]["low_contact"]
    rg = o["rain-guard-bird-feeder"]
    if all((REAL / f).exists() for f in originals_qa.PLATES["rain-guard-bird-feeder"]):
        assert rg["plates"] and [f["name"] for f in rg["files"]] == originals_qa.PLATES["rain-guard-bird-feeder"]
        import sys; sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import validate_originals
        assert all(r["pass"] for r in validate_originals.check(REAL))


def test_plate_packer_splits_a_too_long_plate_and_the_validator_checks_the_whole_plate(tmp_path):
    import sys, trimesh; sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import originals_plates as op
    parts = [trimesh.creation.box((140, 140, 10)), trimesh.creation.box((140, 140, 10)), trimesh.creation.box((60, 30, 10))]
    for k, p in enumerate(parts): p.apply_translation((0, k * 150, 0))
    assert not op.plate_fits(trimesh.util.concatenate(parts))                    # 140 x 440: largest part fits, the plate does not
    plates = op.pack(parts)
    assert len(plates) >= 2 and all(op.plate_fits(trimesh.util.concatenate(pl)) for pl in plates)
    assert sum(len(pl) for pl in plates) == 3
