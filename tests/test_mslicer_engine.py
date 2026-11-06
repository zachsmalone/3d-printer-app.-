"""mslicer writes .goo and .ctb. The file checks read magic and, for GOO, the layer count.

Nothing here was sent to a printer.
"""
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import trimesh

from tests.b1 import ADULT, client

from app.core import resin, resin_fileid
from app.services import mslicer_engine

pytestmark = pytest.mark.skipif(mslicer_engine.mslicer_bin() is None, reason="mslicer binary is not built")


def _stl():
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    return mesh.export(file_type="stl")


def _wait(c, job_id):
    deadline = time.time() + 60
    status = {"status": "queued"}
    while time.time() < deadline and status["status"] in ("queued", "running"):
        time.sleep(0.05)
        status = c.get(f"/api/resin/jobs/{job_id}").json()
    return status


def test_goo_roundtrip_and_independent_layer_count():
    c = client(ADULT)
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("box.stl", _stl(), "model/stl")})
    assert prep.status_code == 200, prep.text
    rid = prep.json()["export"]["rid"]
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection", "file_format": "goo", "anti_alias": "false"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    assert status["report"]["engine"] == "mslicer"
    assert status["report"]["layers"] == 5
    assert status["report"]["hardware_tested"] is False
    assert status["report"]["native_format_written"] is False
    down = c.get(status["download"])
    assert down.status_code == 200
    assert down.headers["content-disposition"].endswith('.goo"') or ".goo" in down.headers["content-disposition"]
    ident = resin_fileid.identify(down.content, "goo")
    assert ident["magic"] == "GOO" and ident["layers_in_file"] == 5
    assert struct.unpack_from(">I", down.content, resin_fileid.GOO_LAYER_COUNT_OFFSET)[0] == 5


def test_ctb_v4_and_v5_magics():
    c = client(ADULT)
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("box.stl", _stl(), "model/stl")})
    rid = prep.json()["export"]["rid"]
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection", "file_format": "ctb"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    assert status["report"]["ctb_container"] == "legacy"
    data = c.get(status["download"]).content
    assert resin_fileid.identify(data, "ctb")["magic"] == "CTB-v4"
    assert struct.unpack_from("<I", data, 0)[0] == resin_fileid.CTB_V4

    plate = {
        "id": "synthetic-v5", "name": "Synthetic v5", "kind": "upstream-geometry",
        "native_format": ".ctb", "native_version": "v5enc",
        "width_px": 64, "height_px": 48,
        "build_width_um": 32000, "build_depth_um": 24000, "build_height_um": 40000,
    }
    stl = Path(tempfile.mkdtemp()) / "box.stl"
    stl.write_bytes(_stl())
    out = stl.with_suffix(".ctb")
    report = mslicer_engine.slice_file(
        stl, out, plate, resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"}),
        "ctb", aa=False,
    )
    assert report["ctb_container"] == "v5"
    assert resin_fileid.identify(out.read_bytes(), "ctb")["magic"] == "CTB-v5"


def _cli(stl: Path, out: Path, extents):
    binary = mslicer_engine.mslicer_bin()
    mesh = trimesh.creation.box(extents=extents)
    stl.write_bytes(mesh.export(file_type="stl"))
    proc = subprocess.run(
        [str(binary), "--quiet",
         "--platform-resolution", "64, 48",
         "--platform-size", "32, 24, 40",
         "--layer-height", "0.2",
         "--ctb", "legacy",
         "--mesh", str(stl), str(out)],
        capture_output=True, text=True, check=False,
    )
    return proc


def test_volume_warning_uses_the_placed_mesh(tmp_path):
    """A model that fits must not be reported as cut off. One that does not fit must be."""
    fits = _cli(tmp_path / "fits.stl", tmp_path / "fits.goo", (8, 8, 1))
    assert fits.returncode == 0, fits.stderr
    assert "cut off" not in fits.stdout
    assert '"layers":5' in fits.stdout
    hangs = _cli(tmp_path / "hangs.stl", tmp_path / "hangs.goo", (40, 8, 1))
    assert hangs.returncode == 0, hangs.stderr
    assert "cut off" in hangs.stdout
