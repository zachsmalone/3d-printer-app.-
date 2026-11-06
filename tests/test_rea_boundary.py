"""REA is MIT and is not a resin slicer. These checks record that boundary.

The live CLI checks run only when ZEIM_REA_BIN points at rea-agents 6.8.0.
They inspect ZEIM's own encoder and a .lumen file ZEIM wrote. They do not open
Lychee, CHITUBOX, DragonFruit, or mslicer.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest
import trimesh

from tests.b1 import ADULT, client

from app.core import resin, resin_slice, resin_sources

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "tools" / "zeim-lumen" / "target" / "release" / "zeim-lumen"


def test_catalog_names_the_three_sources_without_claiming_rea_slices():
    body = client(ADULT).get("/api/resin/catalog").json()
    by_id = {row["id"]: row for row in body["sources"]}
    assert by_id["lumen-format"]["used"] is True and ".lumen" in by_id["lumen-format"]["outputs"]
    assert by_id["df-plugin-elegoo"]["used"] is True and by_id["df-plugin-elegoo"]["outputs"] == []
    assert by_id["mslicer"]["used"] is False and by_id["mslicer"]["license"] == "GPL-3.0"
    assert by_id["dragonfruit"]["license"] == "AGPL-3.0-or-later" and by_id["dragonfruit"]["used"] is False
    rea = by_id["rea"]
    assert rea["version"] == "6.8.0" and rea["license"] == "MIT" and rea["used"] is False
    assert rea["outputs"] == []
    assert rea["commit"] == "a7574d4274728fcb0a13414d6ae43f1597864d94"
    assert "not a resin slicer" in body["formats_note"].lower() or "reverse-engineering" in body["formats_note"].lower()
    note = resin_sources.SOURCES_NOTE.lower()
    assert "mslicer" in note and "rea" in note and ".lumen" in note


@pytest.mark.skipif(not os.environ.get("ZEIM_REA_BIN"), reason="ZEIM_REA_BIN is not set")
@pytest.mark.skipif(not BIN.is_file(), reason="zeim-lumen is not built")
def test_rea_inspects_our_encoder_and_rejects_lumen(tmp_path):
    rea = os.environ["ZEIM_REA_BIN"]
    version = subprocess.check_output([rea, "--version"], text=True).strip()
    assert version == "6.8.0"
    rust = json.loads(subprocess.check_output([rea, "inspect-rust-binary", str(BIN), "--json"], text=True))
    subject = rust["normalized_result"]
    assert subject["format"] == "elf" and subject["architecture"] == "amd64"
    assert subject["rustc_commit"]["hashes"][0]["hash"].startswith("4d91de4e4")
    blob = json.dumps(rust).lower()
    assert "chitubox" not in blob and "lychee" not in blob

    mesh = resin.orient(trimesh.creation.box(extents=[4, 4, 0.4]), 0)
    settings = resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"})
    lumen = tmp_path / "sample.lumen"
    resin_slice.slice_mesh(mesh, settings, resin_slice.plate_by_id("zeim-inspection"), lumen, aa=False)
    proc = subprocess.run([rea, "inspect-artifact", str(lumen), "--json"], capture_output=True, text=True)
    assert proc.returncode != 0
    err = json.loads(proc.stdout)
    assert err["code"] == "target_unavailable"
    assert err["details"]["reason"] == "unsupported binary format"
    assert Path(rea).is_file()
