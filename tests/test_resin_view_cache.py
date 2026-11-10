"""Support taps must not copy a large mesh. The pick grid is built once."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bench(triangles):
    out = subprocess.check_output(
        ["node", str(ROOT / "tests/resin_view_check.mjs"), str(triangles)],
        text=True,
    )
    return json.loads(out)


def test_support_tap_reuses_one_mesh_and_hits_the_sheet():
    small = _bench(2000)
    assert small["rays_hit"] == 8
    assert small["legacy_bytes"] == 2000 * 9 * 4 * 10
    assert small["grid_ms"] < 2000
    assert small["eight_rays_ms"] < 2000
