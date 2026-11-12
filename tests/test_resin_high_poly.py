"""TorchC0 prepare on a CI-sized watertight mesh, under the production memory cap.

The mesh is one shell of about 694k triangles, roughly 130 x 165 x 75 mm: the same
class as the Oni mask that ran out of memory. The wrinkled shell is the one that
used to run out of memory; the smooth one did not. This does not print on a machine.
There is no hardware test.
"""
from app.api.resin import RESIN_MEM_MB
from app.core.guard import Tripped
from app.services import procjob
from tests.resin_high_poly_job import run_case, run_detail


def test_high_poly_prepare_fits_the_production_cap():
    results = {}
    for kind in ("supports", "hollow", "both"):
        try:
            results[kind] = procjob.call(run_case, (kind,), timeout=240, mem_mb=RESIN_MEM_MB)
        except Tripped as exc:
            raise AssertionError(f"{kind} hit the production cap: {exc}") from None
    for kind, row in results.items():
        assert row["faces_in"] == 694_400
        assert row["faces_out"] >= row["faces_in"]
        # The prepare child uses at most 2 CPUs. 180 s is under the 240 s kill, with room
        # for a slower runner. The detailed shell is the one that used to sit on that kill.
        assert row["seconds"] < 180
        assert row["kept"] >= 0.85
        assert row["rss_mb"] < 2800
    assert results["supports"]["pillars"] >= 80 and results["supports"]["touch"] >= 0.5
    assert results["supports"]["raft_span"] > 20
    assert results["both"]["pillars"] >= 80 and results["both"]["touch"] >= 0.5
    assert results["hollow"]["saved"] > 40 and results["both"]["saved"] > 40
    # Printed by pytest -s and kept here so a failure still shows the measurements.
    print(results)


def test_detailed_hollow_fits_the_production_cap():
    """Wrinkled 694k-triangle shell: hollow, and hollow with supports, under the prepare cap.

    The smooth mesh in the test above hollows without this fix. This one did not:
    sampling every wrinkle down to the voxel pitch peaked near 3.7 GB.
    """
    results = {}
    for kind in ("hollow", "both"):
        try:
            results[kind] = procjob.call(run_detail, (kind,), timeout=240, mem_mb=RESIN_MEM_MB)
        except Tripped as exc:
            raise AssertionError(f"{kind} hit the production cap: {exc}") from None
    for kind, row in results.items():
        assert row["faces_in"] == 694_400
        assert row["faces_out"] >= row["faces_in"]
        assert row["seconds"] < 180
        assert row["rss_mb"] < RESIN_MEM_MB
        assert row["kept"] >= 0.99
        assert row["saved"] > 50
        assert row["holes"] == [2]
        assert row["wall_mm"] >= 2.0 - row["pitch_mm"]
    assert results["both"]["pillars"] >= 80 and results["both"]["touch"] >= 0.5
    print(results)
