"""mslicer writes .goo and .ctb. The file checks read magic and, for GOO, the layer count.

Nothing here was sent to a printer.
"""
import hashlib
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import pytest
import trimesh

from tests.b1 import ADULT, client

from app.core import resin, resin_fileid, resin_slice
from app.services import mslicer_engine

pytestmark = pytest.mark.skipif(mslicer_engine.mslicer_bin() is None, reason="mslicer binary is not built")


def _stl():
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    return mesh.export(file_type="stl")


def _wait(c, job_id):
    deadline = time.time() + 90
    status = {"status": "queued"}
    while time.time() < deadline and status.get("status") in ("queued", "running", None):
        time.sleep(0.05)
        body = c.get(f"/api/resin/jobs/{job_id}").json()
        if "status" not in body:
            continue
        status = body
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
    container = status["report"]["ctb_container"]
    assert container == ("v4" if status["report"]["engine"] == "dragonfruit" else "legacy")
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


def _runs(data):
    """GOO layer runs. Independent of the slicer's own summary line."""
    color = 0
    off = 0
    n = len(data)
    while off < n:
        head = data[off]
        kind = head >> 6
        width_bits = (head >> 4) & 0x03
        length = 0
        if kind == 0:
            color = 0
        elif kind == 1:
            off += 1
            color = data[off]
        elif kind == 2:
            diff_type = (head >> 4) & 0x03
            diff = head & 0x0F
            if diff_type & 1:
                off += 1
                length = data[off]
            else:
                length = 1
            color = (color - diff) & 255 if diff_type & 2 else (color + diff) & 255
        else:
            color = 255
        if kind != 2:
            base = head & 0x0F
            if width_bits == 0:
                length = base
            elif width_bits == 1:
                length = base + (data[off + 1] << 4)
                off += 1
            elif width_bits == 2:
                length = base + (data[off + 1] << 12) + (data[off + 2] << 4)
                off += 2
            else:
                length = base + (data[off + 1] << 20) + (data[off + 2] << 12) + (data[off + 3] << 4)
                off += 3
        off += 1
        yield length, color


def _goo_layers(blob):
    assert blob[4:12] == bytes([0x07, 0x00, 0x00, 0x00, 0x44, 0x4C, 0x50, 0x00])
    count = struct.unpack_from(">I", blob, resin_fileid.GOO_LAYER_COUNT_OFFSET)[0]
    width = struct.unpack_from(">H", blob, resin_fileid.GOO_LAYER_COUNT_OFFSET + 4)[0]
    pos = 0x2FB95
    layers = []
    for _ in range(count):
        floats = struct.unpack_from(">15f", blob, pos + 2)
        assert blob[pos + 64:pos + 66] == b"\r\n"
        data_len = struct.unpack_from(">I", blob, pos + 66)[0] - 2
        assert blob[pos + 70] == 0x55
        payload = blob[pos + 71:pos + 71 + data_len]
        end = pos + 71 + data_len
        assert blob[end + 1:end + 3] == b"\r\n"
        box = [10**9, 10**9, -1, -1]
        seen = lit = 0
        for length, color in _runs(payload):
            if color:
                lit += length
                _cover(seen, length, width, box)
            seen += length
        layers.append({"z": floats[1], "exposure": floats[2], "lift": floats[7], "lit": lit,
                       "origin": [box[0], box[1]] if box[2] >= 0 else None})
        pos = end + 3
    return layers


def _cover(start, length, width, box):
    y, x = divmod(start, width)
    left = length
    while left:
        take = min(width - x, left)
        box[0] = min(box[0], x)
        box[1] = min(box[1], y)
        box[2] = max(box[2], x + take - 1)
        box[3] = max(box[3], y)
        left -= take
        y += 1
        x = 0


def test_first_layer_is_the_slab_above_the_bed(tmp_path):
    """A round solid sitting on z=0 used to get an empty first layer: the plane was the bed, and the flat bottom was dropped."""
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=5.0)
    stl = tmp_path / "ball.stl"
    stl.write_bytes(mesh.export(file_type="stl"))
    out = tmp_path / "ball.goo"
    proc = subprocess.run(
        [str(mslicer_engine.mslicer_bin()), "--quiet",
         "--platform-resolution", "64, 48",
         "--platform-size", "32, 24, 40",
         "--layer-height", "0.5",
         "--first-layers", "2",
         "--transition-layers", "0",
         "--exposure-time", "2.5",
         "--first-exposure-time", "30",
         "--lift-distance", "6",
         "--first-lift-distance", "6",
         "--lift-speed", "65",
         "--first-lift-speed", "65",
         "--retract-speed", "65",
         "--first-retract-speed", "65",
         "--ctb", "legacy",
         "--mesh", str(stl), str(out)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    layers = _goo_layers(out.read_bytes())
    assert len(layers) == 20
    assert all(layer["lit"] > 0 for layer in layers)
    assert layers[0]["z"] == pytest.approx(0.5, abs=1e-3)
    assert layers[-1]["z"] == pytest.approx(10.0, abs=1e-3)
    assert layers[0]["exposure"] == pytest.approx(30, abs=1e-3)
    assert layers[2]["exposure"] == pytest.approx(2.5, abs=1e-3)
    assert layers[0]["lift"] == pytest.approx(6, abs=1e-3)
    # The mask is the interior of the slab, so the bed layer is smaller than the equator and larger than a point.
    assert layers[0]["lit"] > 4
    assert max(layer["lit"] for layer in layers) > layers[0]["lit"]


def test_jupiter_ctb_is_reachable_through_the_api():
    c = client(ADULT)
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    prep = c.post("/api/resin/prepare", data={"printer_id": "elegoo_jupiter", "hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("box.stl", mesh.export(file_type="stl"), "model/stl")})
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert body["triangles"] == 12 and body["simplified"] is False
    rid = body["export"]["rid"]
    blocked = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "lumen"})
    assert blocked.status_code == 400
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "ctb"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    report = status["report"]
    assert report["hardware_tested"] is False and report["native_format_written"] is True
    assert report["engine"] == resin_slice.writer_for("ctb")
    assert report["file_magic"] == "CTB-v5"
    assert report["layer_height_um"] == 200 and report["normal_exposure_ms"] == 2500
    assert report["bottom_exposure_ms"] == 30000 and report["bottom_layer_count"] == 5
    assert report["mirror_applied"] is False
    assert "not printed" in report["note"].lower()
    down = c.get(status["download"])
    assert report["engine"] in down.headers["content-disposition"]
    data = down.content
    assert resin_fileid.identify(data, "ctb")["magic"] == "CTB-v5"


def test_ctb_v2_plate_is_refused():
    reason = resin_slice.block_reason(resin_slice.plate_by_id("elegoo-mars-2-ctb"), "ctb")
    assert "v2" in reason.lower()
    c = client(ADULT)
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0"},
                  files={"file": ("box.stl", mesh.export(file_type="stl"), "model/stl")})
    rid = prep.json()["export"]["rid"]
    refused = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-mars-2-ctb", "file_format": "ctb"})
    assert refused.status_code == 400
    assert "printer" in refused.text.lower()


def test_volume_warning_uses_the_placed_mesh(tmp_path):
    """A model that fits must not be reported as cut off. One that does not fit must be."""
    fits = _cli(tmp_path / "fits.stl", tmp_path / "fits.goo", (8, 8, 1))
    assert fits.returncode == 0, fits.stderr
    assert "cut off" not in fits.stdout
    assert '"layers":5' in fits.stdout
    hangs = _cli(tmp_path / "hangs.stl", tmp_path / "hangs.goo", (40, 8, 1))
    assert hangs.returncode == 0, hangs.stderr
    assert "cut off" in hangs.stdout


def test_selected_printer_rejects_a_different_machine():
    """Mars 5 is not Mars 5 Ultra. Jupiter SE is not Jupiter, even with the same bed numbers."""
    c = client(ADULT)
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    stl = mesh.export(file_type="stl")
    ultra = c.post("/api/resin/prepare", data={"printer_id": "elegoo_mars5_ultra", "hollow": "false", "supports": "false", "tilt_deg": "0"},
                   files={"file": ("box.stl", stl, "model/stl")})
    assert ultra.status_code == 200, ultra.text
    rid = ultra.json()["export"]["rid"]
    other = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-mars-5-goo", "file_format": "goo"})
    assert other.status_code == 400
    assert "mars 5 ultra" in other.text.lower() and "different machine" in other.text.lower()
    own = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-mars-5-ultra-ctb", "file_format": "ctb"})
    assert own.status_code == 400
    detail = own.text.lower()
    assert "pixel" in detail
    if resin_slice.writer_for("ctb") != "dragonfruit":
        assert "mirror" in detail
    photon = c.post("/api/resin/prepare", data={"printer_id": "anycubic_photon_mono_m7", "hollow": "false", "supports": "false", "tilt_deg": "0"},
                    files={"file": ("box.stl", stl, "model/stl")})
    refused = c.post(f"/api/resin/{photon.json()['export']['rid']}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "ctb"})
    assert refused.status_code == 400 and "no slice plate" in refused.text.lower()
    se = c.post("/api/resin/prepare", data={"printer_id": "elegoo_jupiter_se", "hollow": "false", "supports": "false", "tilt_deg": "0"},
                files={"file": ("box.stl", stl, "model/stl")})
    se_rid = se.json()["export"]["rid"]
    crossed = c.post(f"/api/resin/{se_rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "ctb"})
    assert crossed.status_code == 400 and "different machine" in crossed.text.lower()
    mirrored = c.post(f"/api/resin/{se_rid}/slice", data={"plate_id": "elegoo-jupiter-se-ctb", "file_format": "ctb"})
    if resin_slice.writer_for("ctb") == "dragonfruit":
        assert mirrored.status_code == 200, mirrored.text
        mirrored_status = _wait(c, mirrored.json()["job_id"])
        assert mirrored_status["status"] == "done", mirrored_status
        assert mirrored_status["report"]["engine"] == "dragonfruit"
        assert mirrored_status["report"]["mirror_applied"] is True
        assert mirrored_status["report"]["mirror_y"] is True
    else:
        assert mirrored.status_code == 400 and "mirror" in mirrored.text.lower()


def _arrow():
    """A bar with a tall peg on +X and a tab on +Y. Not symmetric, so a mirror fails."""
    bar = trimesh.creation.box(extents=[40, 8, 2])
    bar.apply_translation([0, 0, 1])
    peg = trimesh.creation.box(extents=[8, 8, 6])
    peg.apply_translation([16, 0, 5])
    tab = trimesh.creation.box(extents=[8, 8, 2])
    tab.apply_translation([0, 8, 1])
    return trimesh.util.concatenate([bar, peg, tab])


def _ctb_key():
    text = Path("third_party/mslicer/format/ctb_format/src/v5/mod.rs").read_text()
    def take(name, n):
        body = text[text.index(f"const {name}"):]
        nums = [int(tok, 16) for tok in body.replace(",", " ").split() if tok.startswith("0x")]
        return bytes(nums[:n])
    return take("ENCRYPT_KEY", 32), take("ENCRYPT_IV", 16)


def _aes(data, key, iv):
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return dec.update(data) + dec.finalize()


def _xor(data, seed, layer):
    out = bytearray(data)
    init = (seed * 0x2D83CDAC + 0xD8A83423) & 0xFFFFFFFF
    key = ((layer * 0x1E1530CD + 0xEC3D47CD) * init) & 0xFFFFFFFF
    index = 0
    for i in range(len(out)):
        out[i] ^= (key >> (8 * index)) & 0xFF
        index += 1
        if index & 3 == 0:
            key = (key + init) & 0xFFFFFFFF
            index = 0
    return bytes(out)


def _ctb_runs(data):
    offset = 0
    while offset < len(data):
        value = data[offset]
        length = 1
        if value & 0x80:
            value &= 0x7F
            offset += 1
            nxt = data[offset]
            if nxt & 0x80 == 0:
                length = nxt
            elif nxt & 0xC0 == 0x80:
                length = ((nxt & 0x3F) << 8) + data[offset + 1]
                offset += 1
            elif nxt & 0xE0 == 0xC0:
                length = ((nxt & 0x1F) << 16) + (data[offset + 1] << 8) + data[offset + 2]
                offset += 2
            elif nxt & 0xF0 == 0xE0:
                length = ((nxt & 0xF) << 24) + (data[offset + 1] << 16) + (data[offset + 2] << 8) + data[offset + 3]
                offset += 3
            else:
                raise AssertionError("bad ctb run")
        offset += 1
        if value:
            value = (value << 1) | 1
        yield length, value


def _ctb_v4_runs(data):
    """Gray runs in an unencrypted CTB layer. High bit means a length follows."""
    offset = 0
    while offset < len(data):
        code = data[offset]
        offset += 1
        value = (code & 0x7F) << 1
        if code & 0x80 == 0:
            length = 1
        else:
            b0 = data[offset]
            offset += 1
            if b0 & 0x80 == 0:
                length = b0
            elif b0 & 0xC0 == 0x80:
                length = ((b0 & 0x7F) << 8) | data[offset]
                offset += 1
            elif b0 & 0xE0 == 0xC0:
                length = ((b0 & 0x1F) << 16) | (data[offset] << 8) | data[offset + 1]
                offset += 2
            elif b0 & 0xF0 == 0xE0:
                length = ((b0 & 0x0F) << 24) | (data[offset] << 16) | (data[offset + 1] << 8) | data[offset + 2]
                offset += 3
            else:
                raise AssertionError("bad ctb run")
        yield length, value


def _ctb_v4_view(raw):
    """Unencrypted CTB (magic 0x12FD0106), including DragonFruit's version-5 file."""
    size = struct.unpack_from("<3f", raw, 8)
    _total_h, layer_h, exposure, bottom = struct.unpack_from("<4f", raw, 28)
    bottom_layers = struct.unpack_from("<I", raw, 48)[0]
    width, height = struct.unpack_from("<2I", raw, 52)
    layers_off, count = struct.unpack_from("<2I", raw, 64)
    params_off = struct.unpack_from("<I", raw, 84)[0]
    lift = struct.unpack_from("<f", raw, params_off + 8)[0]
    xor_key = struct.unpack_from("<I", raw, 100)[0]
    layers = []
    for i in range(count):
        rec = layers_off + i * 0x24
        address, data_len, page = struct.unpack_from("<III", raw, rec + 12)
        pos = page * (1 << 32) + address
        blob = raw[pos:pos + data_len]
        if xor_key:
            blob = _xor(blob, xor_key, i)
        box = [10**9, 10**9, -1, -1]
        seen = 0
        for length, value in _ctb_v4_runs(blob):
            if value:
                _cover(seen, length, width, box)
            seen += length
        assert seen == width * height, (i, seen, width * height)
        z = struct.unpack_from("<f", raw, pos - 0x54)[0]
        exp = struct.unpack_from("<f", raw, pos - 0x54 + 4)[0]
        layers.append({"z": z, "exposure": exp, "origin": [box[0], box[1]], "end": [box[2], box[3]]})
    return {"plate": size, "total_h": _total_h, "layer_h": layer_h, "exposure": exposure,
            "bottom": bottom, "bottom_layers": bottom_layers, "lift": lift, "width": width,
            "height": height, "layers": layers}


def _ctb_view(raw):
    """Header fields and each layer's lit bbox. The key is read from the vendored writer, not copied here."""
    if struct.unpack_from("<I", raw, 0)[0] == 0x12FD0106:
        return _ctb_v4_view(raw)
    assert struct.unpack_from("<I", raw, 0)[0] == 0x12FD0107
    settings_size, settings_off = struct.unpack_from("<II", raw, 4)
    sig_size, sig_off = struct.unpack_from("<II", raw, 20)
    key, iv = _ctb_key()
    plain = _aes(raw[settings_off:settings_off + settings_size], key, iv)
    checksum = struct.unpack_from("<Q", plain, 0)[0]
    digest = hashlib.sha256(checksum.to_bytes(8, "little")).digest()
    assert _aes(raw[sig_off:sig_off + sig_size], key, iv)[:32] == digest
    o = 8
    table = struct.unpack_from("<I", plain, o)[0]; o += 4
    plate = struct.unpack_from("<3f", plain, o); o += 12
    o += 8
    total_h, layer_h, exposure, bottom = struct.unpack_from("<4f", plain, o); o += 16
    o += 4  # light off
    bottom_layers = struct.unpack_from("<I", plain, o)[0]; o += 4
    width, height = struct.unpack_from("<2I", plain, o); o += 8
    count = struct.unpack_from("<I", plain, o)[0]; o += 4
    o += 8 + 4 + 4  # previews, print time, projector
    o += 8  # bottom lift height and speed
    lift = struct.unpack_from("<f", plain, o)[0]
    o += 12  # lift, lift speed, retract speed
    o += 12 + 4 + 4 + 4  # material, bottom light off, skip, pwm pair
    xor_key = struct.unpack_from("<I", plain, o)[0]
    layers = []
    for i in range(count):
        ref = table + i * 16
        page = struct.unpack_from("<I", raw, ref + 4)[0]
        pos = page * (1 << 32) + struct.unpack_from("<I", raw, ref)[0]
        z, exp = struct.unpack_from("<2f", raw, pos + 4)
        data_off, data_len = struct.unpack_from("<I", raw, pos + 16)[0], struct.unpack_from("<I", raw, pos + 24)[0]
        enc_off, enc_len = struct.unpack_from("<I", raw, pos + 32)[0], struct.unpack_from("<I", raw, pos + 36)[0]
        blob = bytearray(raw[data_off:data_off + data_len])
        if enc_len:
            blob[enc_off:enc_off + enc_len] = _aes(bytes(blob[enc_off:enc_off + enc_len]), key, iv)
        if xor_key:
            blob = bytearray(_xor(blob, xor_key, i))
        box = [10**9, 10**9, -1, -1]
        seen = 0
        for length, value in _ctb_runs(blob):
            if value:
                _cover(seen, length, width, box)
            seen += length
        assert seen == width * height
        layers.append({"z": z, "exposure": exp, "origin": [box[0], box[1]], "end": [box[2], box[3]]})
    return {"plate": plate, "total_h": total_h, "layer_h": layer_h, "exposure": exposure,
            "bottom": bottom, "bottom_layers": bottom_layers, "lift": lift, "width": width,
            "height": height, "layers": layers}


def test_jupiter_slice_matches_the_prepared_bed(tmp_path):
    """The file's plate is Jupiter, and the pixels sit where prepare put the mesh."""
    c = client(ADULT)
    prep = c.post("/api/resin/prepare", data={
        "printer_id": "elegoo_jupiter", "hollow": "false", "supports": "false",
        "tilt_deg": "0", "tilt_y_deg": "0", "simplify": "false", "layer_mm": "0.2",
    }, files={"file": ("arrow.stl", _arrow().export(file_type="stl"), "model/stl")})
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert body["simplified"] is False
    assert body["settings"]["tilt_deg"] == 0 and body["settings"]["supports"] is False
    rid = body["export"]["rid"]
    stl = trimesh.load(trimesh.util.wrap_as_stream(c.get(f"/api/resin/{rid}/torchc0.stl").content), file_type="stl", force="mesh")
    assert stl.bounds[0][2] == pytest.approx(0, abs=1e-3)
    bed = body["size_mm"]
    mid = (stl.bounds[0] + stl.bounds[1]) / 2
    assert mid[0] == pytest.approx(277.848 / 2, abs=0.05)
    assert mid[1] == pytest.approx(156.264 / 2, abs=0.05)
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "ctb", "anti_alias": "false"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    assert status["report"]["plate_name"] == "Jupiter"
    view = _ctb_view(c.get(status["download"]).content)
    assert view["plate"][0] == pytest.approx(277.848, abs=0.01)
    assert view["plate"][1] == pytest.approx(156.264, abs=0.01)
    assert view["plate"][2] == pytest.approx(300, abs=0.01)
    assert view["layer_h"] == pytest.approx(0.2, abs=1e-3)
    assert view["exposure"] == pytest.approx(2.5, abs=1e-3)
    assert view["bottom"] == pytest.approx(30, abs=1e-3)
    assert view["bottom_layers"] == 5
    assert view["lift"] == pytest.approx(6, abs=1e-3)
    ppm_x = view["width"] / 277.848
    ppm_y = view["height"] / 156.264
    high = [layer for layer in view["layers"] if layer["z"] > 4]
    low = [layer for layer in view["layers"] if layer["z"] < 2]
    assert high and low
    # The peg is the only geometry above 4 mm, and it is on the +X side of the prepared mesh.
    peg = stl.vertices[stl.vertices[:, 2] > 4]
    assert peg[:, 0].mean() > mid[0]
    got = high[0]["origin"][0]
    expect = peg[:, 0].min() * ppm_x
    assert got == pytest.approx(expect, abs=2)
    tab = stl.vertices[(stl.vertices[:, 1] > mid[1] + 2) & (stl.vertices[:, 2] < 3)]
    assert len(tab)
    low_end_y = max(layer["end"][1] for layer in low)
    assert low_end_y == pytest.approx(tab[:, 1].max() * ppm_y, abs=2)
    assert bed[2] == pytest.approx(8.0, abs=0.2)


def test_default_hollow_and_supports_keep_the_settings(tmp_path):
    """The UI defaults are on. The file uses those settings and the prepared position."""
    c = client(ADULT)
    mesh = trimesh.creation.box(extents=[20, 16, 12])
    prep = c.post("/api/resin/prepare", data={"printer_id": "elegoo_jupiter", "layer_mm": "0.2"},
                  files={"file": ("cube.stl", mesh.export(file_type="stl"), "model/stl")})
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert body["settings"]["hollow"] is True and body["settings"]["supports"] is True
    assert body["settings"]["exposure_s"] == 2.5 and body["settings"]["lift_mm"] == 6
    assert body["layer_check"]["lift_mm"] == pytest.approx(6, abs=1e-6)
    assert body["support"]["supports"] > 0
    rid = body["export"]["rid"]
    stl = trimesh.load(trimesh.util.wrap_as_stream(c.get(f"/api/resin/{rid}/torchc0.stl").content), file_type="stl", force="mesh")
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "ctb", "anti_alias": "false"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    view = _ctb_view(c.get(status["download"]).content)
    assert view["exposure"] == pytest.approx(body["settings"]["exposure_s"], abs=1e-3)
    assert view["bottom"] == pytest.approx(body["settings"]["bottom_exposure_s"], abs=1e-3)
    assert view["lift"] == pytest.approx(body["settings"]["lift_mm"], abs=1e-3)
    assert view["layer_h"] == pytest.approx(body["settings"]["layer_mm"], abs=1e-3)
    assert view["layers"][0]["exposure"] == pytest.approx(30, abs=1e-3)
    ppm_x = view["width"] / view["plate"][0]
    ppm_y = view["height"] / view["plate"][1]
    lit = [layer for layer in view["layers"] if layer["end"][0] >= 0]
    union = [min(layer["origin"][0] for layer in lit), min(layer["origin"][1] for layer in lit),
             max(layer["end"][0] for layer in lit), max(layer["end"][1] for layer in lit)]
    # DragonFruit maps the bed onto width-1 pixels, so an edge can sit about two pixels off mslicer's scale.
    assert union[0] == pytest.approx(stl.bounds[0][0] * ppm_x, abs=4)
    assert union[1] == pytest.approx(stl.bounds[0][1] * ppm_y, abs=4)
    assert union[2] == pytest.approx(stl.bounds[1][0] * ppm_x, abs=4)
    assert union[3] == pytest.approx(stl.bounds[1][1] * ppm_y, abs=4)
    assert lit[-1]["z"] == pytest.approx(stl.bounds[1][2], abs=view["layer_h"] + 1e-3)


def test_placed_flag_does_not_recenter(tmp_path):
    mesh = trimesh.creation.box(extents=[4, 4, 1])
    mesh.apply_translation([4, 4, 0.5])
    stl = tmp_path / "corner.stl"
    out = tmp_path / "corner.goo"
    stl.write_bytes(mesh.export(file_type="stl"))
    binary = mslicer_engine.mslicer_bin()
    cmd = [str(binary), "--quiet", "--platform-resolution", "64, 48", "--platform-size", "32, 24, 40",
           "--layer-height", "0.5", "--ctb", "legacy", "--placed", "--mesh", str(stl), str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    layer = _goo_layers(out.read_bytes())[0]
    assert layer["origin"][0] < 16
    plain = [arg for arg in cmd if arg != "--placed"]
    centered = subprocess.run(plain, capture_output=True, text=True, check=False)
    assert centered.returncode == 0, centered.stderr
    assert _goo_layers(out.read_bytes())[0]["origin"][0] > 20
