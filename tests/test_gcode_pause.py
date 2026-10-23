"""'Pause at this layer' (app/services/gcode_pause.py + GET /api/slice/{id}/gcode-paused) and the parser's per-layer
offsets used by the code panel. Layer numbers must match the preview (static/gcode-parse.js)."""
import json, os, shutil, subprocess, tempfile, uuid
from pathlib import Path
import pytest
from app.services import gcode_pause as gp
ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "tests/fixtures/gcode/mini.gcode"
PS = "/workspace/tools/prusaslicer/prusa-slicer"


def _paused(src, layers, cmd):
    d = Path(tempfile.mkdtemp()); out = d / "o.gcode"
    done = gp.insert_pauses(Path(src), out, layers, cmd)
    return out.read_text(), done


@pytest.mark.parametrize("pid,fw,cmd", [
    ("creality_k1", "klipper", "PAUSE"), ("creality_k1_max", "klipper", "PAUSE"), ("creality_ender3_v3_ke", "klipper", "PAUSE"),
    ("voron_24_300", "klipper", "PAUSE"), ("creality_ender3_v3_se", "marlin", "M600"), ("sovol_sv06", "marlin", "M600"),
    ("prusa_mk4", "prusa", "M601"), ("bambu_a1", "bambu", "M400 U1"), ("ultimaker_s5", "unknown", None), (None, "unknown", None)])
def test_firmware_guess(pid, fw, cmd):
    f = gp.firmware_for(pid)
    assert f["firmware"] == fw and f["command"] == cmd and cmd in (None, *f["commands"]) and f["note"]


@pytest.mark.parametrize("cmd", list(gp.COMMANDS))
def test_pause_per_firmware_lands_at_layer_start(cmd):
    txt, done = _paused(MINI, [2], cmd)
    lines = txt.splitlines(); i = lines.index(cmd)
    assert [d["layer"] for d in done] == [2] and abs(done[0]["z"] - 0.4) < 1e-6
    assert lines[i - 1].startswith("; ZEIM: pause inserted at the start of layer 2")
    assert lines[i + 1] == ";LAYER_CHANGE" and lines[i + 2] == ";Z:0.4"     # before the layer change; layer 1 is all before it
    assert txt.replace(f"; ZEIM: pause inserted at the start of layer 2 (Z 0.40 mm) with {cmd}\n{cmd}\n", "") == MINI.read_text()


def test_multiple_pauses_bad_input_and_original_untouched():
    before = MINI.read_bytes()
    txt, done = _paused(MINI, [3, 1, 2, 99], "M600")
    assert [d["layer"] for d in done] == [1, 2, 3] and txt.count("\nM600\n") + txt.startswith("M600\n") == 3
    assert MINI.read_bytes() == before
    with pytest.raises(ValueError):
        gp.insert_pauses(MINI, Path(tempfile.mktemp()), [1], "M600\nG28")


def _node_layers(path):
    js = ("const {GcodeParser}=require(process.argv[1]);const o=[];const p=new GcodeParser({onLayer:L=>o.push([L.z,L.byte,L.line])});"
          "p.push(require('fs').readFileSync(process.argv[2],'utf8'));p.end();console.log(JSON.stringify(o))")
    r = subprocess.run(["node", "-e", js, str(ROOT / "static/gcode-parse.js"), str(path)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def prusa_gcode():
    if not (shutil.which("node") and os.path.exists(PS)):
        pytest.skip("node or PrusaSlicer missing")
    import trimesh
    d = Path(tempfile.mkdtemp()); stl = d / "m.stl"
    m = trimesh.creation.box([20, 20, 6]).union(trimesh.creation.cylinder(4, 8).apply_translation([0, 0, 7]))
    m.export(stl)
    r = subprocess.run([PS, "--export-gcode", "--layer-height", "0.2", "--support-material", "--gcode-flavor", "marlin2",
                        "--retract-lift", "0.4", "--center", "100,100", "-o", str(d / "m.gcode"), str(stl)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    return d / "m.gcode"


def test_prusaslicer_layers_match_preview_and_offsets(prusa_gcode):
    js = _node_layers(prusa_gcode); data = prusa_gcode.read_bytes(); text = data.decode()
    assert len(js) == text.count(";LAYER_CHANGE") > 30     # z-hops (retract lift) never make layers
    for z, b, ln in js:                                    # each layer's offset is its ;LAYER_CHANGE line, byte AND line number agree
        assert data[b:b + 13] == b";LAYER_CHANGE" and text.splitlines()[ln] == ";LAYER_CHANGE"
    n = 17
    txt, done = _paused(prusa_gcode, [n, 25], "PAUSE")
    assert [d["layer"] for d in done] == [n, 25] and abs(done[0]["z"] - js[n - 1][0]) < 1e-3
    lines = txt.splitlines(); i = lines.index("PAUSE")
    assert lines[i + 1] == ";LAYER_CHANGE" and lines[i + 2] == f";Z:{js[n - 1][0]:g}"


def test_offsets_with_non_ascii_and_chunks(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node missing")
    src = MINI.read_text().replace(";TYPE:Skirt", ";TYPE:Skirt ; größe ✓ 🙂", 1)
    p = tmp_path / "u.gcode"; p.write_text(src, encoding="utf-8"); data = p.read_bytes()
    for z, b, ln in _node_layers(p):
        assert data.decode().splitlines()[ln] == data[b:].decode().splitlines()[0]


def test_paused_download_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config
    from app.main import app
    monkeypatch.setattr(config, "DATA", tmp_path)
    sid = uuid.uuid4().hex; d = tmp_path / "slices" / sid; d.mkdir(parents=True); shutil.copy(MINI, d / "model.gcode")
    c = TestClient(app)
    r = c.get(f"/api/slice/{sid}/gcode-paused", params={"layers": "2,3", "cmd": "PAUSE"})
    assert r.status_code == 200 and r.text.count("\nPAUSE\n") == 2 and "zeim-model-with-pauses.gcode" in r.headers["content-disposition"]
    assert (d / "model.gcode").read_bytes() == MINI.read_bytes()
    assert c.get(f"/api/slice/{sid}/gcode-paused", params={"layers": "2", "cmd": "G28"}).status_code == 422
    assert c.get(f"/api/slice/{sid}/gcode-paused", params={"layers": "x", "cmd": "M600"}).status_code == 422
    assert c.get(f"/api/slice/{sid}/gcode-paused", params={"layers": ",".join(map(str, range(1, 60))), "cmd": "M600"}).status_code == 422
    assert c.get("/api/slice/../gcode-paused", params={"layers": "2", "cmd": "M600"}).status_code == 404
    r = c.get(f"/api/slice/{sid}/gcode", headers={"Range": "bytes=10-29"})   # the code panel reads layers lazily by byte range
    assert r.status_code == 206 and r.content == MINI.read_bytes()[10:30]


def test_problem_markers_find_overhang_and_island(tmp_path):
    import trimesh
    from app.services import gcode_hints
    t = trimesh.creation.box([10, 10, 10]).apply_translation([0, 0, 5])
    shelf = trimesh.creation.box([30, 30, 2]).apply_translation([0, 0, 11])   # wide shelf over the post -> downward faces at z=10
    float_ = trimesh.creation.box([4, 4, 4]).apply_translation([30, 0, 8])     # separate part starting at z=6
    p = tmp_path / "m.stl"; trimesh.util.concatenate([t, shelf, float_]).export(p)
    ms = gcode_hints.markers(p, "off", {"checks": {"thin_wall": {"ok": False}}})
    kinds = {(m["kind"], m["z"]) for m in ms}
    assert ("island", 6.0) in kinds and any(k == "overhang" and abs(z - 10) < 0.6 for k, z in kinds)
    assert any(m["kind"] == "thin" and m["z"] is None for m in ms)
    assert gcode_hints.markers(tmp_path / "missing.stl") == []
