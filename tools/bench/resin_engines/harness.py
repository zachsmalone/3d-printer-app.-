"""Side-by-side bench of mslicer and DragonFruit. Does not import ZEIM slice code.

Both engines are separate processes. DragonFruit is not vendored: point
``ZEIM_DRAGONFRUIT_BIN`` at a binary built outside this repository.
UVtools is the independent reader (``UVTOOLS_CMD``). Nothing is printed.

Usage (from the repo root):
  python3 tools/bench/resin_engines/harness.py
  python3 tools/bench/resin_engines/harness.py --runs 3 --out tools/bench/resin_engines/results/raw.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.bench.resin_engines.compare import against_expected, expected_mask, layer_delta, rects_for, solid_mask
from tools.bench.resin_engines.fixtures import ASYM, BOX, SCULPT, ensure_meshes, translate_corner, write_stl

# TorchC0 "standard" preset (app/core/resin.py). Supports off. Anti-aliasing off.
LAYER_MM = 0.05
EXPOSURE_S = 2.5
BOTTOM_EXPOSURE_S = 30.0
BOTTOM_LAYERS = 5
LIFT_MM = 6.0
LIFT_SPEED = 65.0

# Plate numbers are the Elegoo rows ZEIM already copies from df-plugin-elegoo
# (app/core/lumen_plates.json). Build width/depth are pixel count times pitch.
PRINTERS = [
    {
        "id": "jupiter",
        "name": "ELEGOO Jupiter",
        "family": "Jupiter",
        "width_px": 5448,
        "height_px": 3064,
        "build_width_mm": 277.848,
        "build_depth_mm": 156.264,
        "build_height_mm": 300.0,
        "extension": "ctb",
        "df_format_version": "v4",
        "ms_ctb": "legacy",
        "catalog_native": "ctb v5",
        "catalog_mirror_x": False,
        "catalog_mirror_y": False,
    },
    {
        "id": "saturn2",
        "name": "ELEGOO Saturn 2",
        "family": "Saturn",
        "width_px": 7680,
        "height_px": 4320,
        "build_width_mm": 218.88,
        "build_depth_mm": 123.12,
        "build_height_mm": 250.0,
        "extension": "ctb",
        "df_format_version": "v4",
        "ms_ctb": "legacy",
        "catalog_native": "ctb v5enc",
        "catalog_mirror_x": False,
        "catalog_mirror_y": True,
    },
    {
        "id": "mars5",
        "name": "ELEGOO Mars 5",
        "family": "Mars",
        "width_px": 4098,
        "height_px": 2560,
        "build_width_mm": 143.43,
        "build_depth_mm": 89.6,
        "build_height_mm": 165.0,
        "extension": "goo",
        "df_format_version": None,
        "ms_ctb": None,
        "catalog_native": "goo",
        "catalog_mirror_x": False,
        "catalog_mirror_y": True,
    },
]

MESH_NOTES = {"box": BOX["note"], "asymmetric": ASYM["note"], "sculpt": SCULPT["note"]}


def metadata_json() -> str:
    payload = {
        "printer": {"settingsMode": "simple"},
        "material": {
            "normalExposureSec": EXPOSURE_S,
            "bottomExposureSec": BOTTOM_EXPOSURE_S,
            "bottomLayerCount": BOTTOM_LAYERS,
            "liftDistanceMm": LIFT_MM,
            "bottomLiftDistanceMm": LIFT_MM,
            "liftSpeedMmMin": LIFT_SPEED,
            "bottomLiftSpeedMmMin": LIFT_SPEED,
            "retractSpeedMmMin": LIFT_SPEED,
            "bottomRetractSpeedMmMin": LIFT_SPEED,
        },
        "ctb": {"version": 4},
    }
    return json.dumps(payload, separators=(",", ":"))


def drop_file_cache(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except OSError:
        pass
    os.close(fd)


def binary_and_libs(binary: Path) -> list[Path]:
    found = [binary]
    try:
        proc = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=False)
    except OSError:
        return found
    for line in proc.stdout.splitlines():
        parts = line.split("=>")
        token = (parts[1] if len(parts) > 1 else parts[0]).strip().split(" ")[0]
        if token.startswith("/"):
            found.append(Path(token))
    return found


def _drain(pipe, sink: list[bytes]) -> None:
    try:
        sink.append(pipe.read())
    finally:
        pipe.close()


def _child_hwm_kb(pid: int) -> int | None:
    """Post-exec high-water RSS. wait4's ru_maxrss includes the pre-exec fork of this process."""
    try:
        text = Path(f"/proc/{pid}/status").read_text()
    except OSError:
        return None
    name = ""
    hwm = None
    for line in text.splitlines():
        if line.startswith("Name:"):
            name = line.split()[-1]
        elif line.startswith("VmHWM:"):
            hwm = int(line.split()[1])
    if hwm is None:
        return None
    if name == "slicer" or name.startswith("dragonfruit"):
        return hwm
    return None


def run_timed(cmd: list[str], timeout_s: float) -> dict:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, out_chunks)),
        threading.Thread(target=_drain, args=(proc.stderr, err_chunks)),
    ]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    timed_out = False
    peak_kb = 0
    while True:
        hwm = _child_hwm_kb(proc.pid)
        if hwm is not None:
            peak_kb = max(peak_kb, hwm)
        if proc.poll() is not None:
            break
        if time.monotonic() - started > timeout_s:
            timed_out = True
            proc.kill()
            break
        time.sleep(0.002)
    for thread in threads:
        thread.join()
    wall = time.monotonic() - started
    return {
        "returncode": proc.returncode if proc.returncode is not None else proc.wait(),
        "stdout": b"".join(out_chunks).decode("utf-8", "replace"),
        "stderr": b"".join(err_chunks).decode("utf-8", "replace"),
        "wall_s": wall,
        "peak_rss_kb": peak_kb,
        "timed_out": timed_out,
    }


def parse_mslicer(text: str) -> dict:
    faces = re.findall(r"face: (\d+)", text)
    summary = None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                summary = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    engine_s = None
    match = re.search(r"Finished in ([0-9.]+)(ms|s|µs)", text)
    if match:
        value = float(match.group(1))
        unit = match.group(2)
        engine_s = value / 1000.0 if unit == "ms" else value / 1e6 if unit == "µs" else value
    return {
        "triangles": int(faces[-1]) if faces else None,
        "summary": summary,
        "engine_s": engine_s,
    }


def slice_mslicer(binary: Path, stl: Path, out: Path, printer: dict) -> list[str]:
    cmd = [
        str(binary),
        "--quiet",
        "--platform-resolution",
        f"{printer['width_px']}, {printer['height_px']}",
        "--platform-size",
        f"{printer['build_width_mm']}, {printer['build_depth_mm']}, {printer['build_height_mm']}",
        "--layer-height",
        str(LAYER_MM),
        "--first-layers",
        str(BOTTOM_LAYERS),
        "--transition-layers",
        "0",
        "--exposure-time",
        str(EXPOSURE_S),
        "--first-exposure-time",
        str(BOTTOM_EXPOSURE_S),
        "--lift-distance",
        str(LIFT_MM),
        "--first-lift-distance",
        str(LIFT_MM),
        "--lift-speed",
        str(LIFT_SPEED),
        "--first-lift-speed",
        str(LIFT_SPEED),
        "--retract-speed",
        str(LIFT_SPEED),
        "--first-retract-speed",
        str(LIFT_SPEED),
        "--supersample",
        "1",
        "--placed",
        "--mesh",
        str(stl),
        str(out),
    ]
    if printer["extension"] == "ctb":
        cmd[1:1] = ["--ctb", printer["ms_ctb"]]
    return cmd


def slice_dragonfruit(binary: Path, stl: Path, out: Path, printer: dict, extra: list[str] | None = None) -> list[str]:
    cmd = [
        str(binary),
        "slice",
        "run",
        str(stl),
        "-o",
        str(out),
        "--json",
        "--layer-height",
        str(LAYER_MM),
        "--build-width-mm",
        str(printer["build_width_mm"]),
        "--build-depth-mm",
        str(printer["build_depth_mm"]),
        "--source-width-px",
        str(printer["width_px"]),
        "--source-height-px",
        str(printer["height_px"]),
        "--anti-aliasing",
        "Off",
        "--anti-aliasing-mode",
        "Coverage",
        "--blur-brush-radius-px",
        "0",
        "--z-blur-radius-layers",
        "0",
        "--z-blend-look-back",
        "0",
        "--sample-interval-ms",
        "0",
        "--metadata-json",
        metadata_json(),
    ]
    if printer.get("df_format_version"):
        cmd.extend(["--format-version", printer["df_format_version"]])
    if extra:
        cmd.extend(extra)
    return cmd


def uvtools(uv: Path, args: list[str], timeout_s: float = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(uv), "--no-progress", "--quiet", *args],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def parse_properties(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key and " " not in key:
            found[key] = value.strip()
    return found


KEEP_PROPS = (
    "Version",
    "IsMagicValid",
    "ResolutionX",
    "ResolutionY",
    "DisplayWidth",
    "DisplayHeight",
    "MachineZ",
    "LayerHeight",
    "LayerCount",
    "BottomLayerCount",
    "ExposureTime",
    "BottomExposureTime",
    "LiftHeight",
    "BottomLiftHeight",
    "LiftSpeed",
    "BottomLiftSpeed",
    "RetractSpeed",
    "AntiAliasing",
    "FileFormat",
    "LayerImageFormat",
)


def inspect_file(uv: Path, path: Path, work: Path) -> dict:
    prop = uvtools(uv, ["print-properties", str(path)])
    parsed = parse_properties(prop.stdout + "\n" + prop.stderr)
    info = {
        "bytes": path.stat().st_size if path.is_file() else 0,
        "uvtools_ok": prop.returncode == 0 and bool(parsed.get("LayerCount") or parsed.get("ResolutionX")),
        "uvtools_returncode": prop.returncode,
        "properties": {key: parsed[key] for key in KEEP_PROPS if key in parsed},
        "uvtools_error": "" if prop.returncode == 0 else (prop.stderr or prop.stdout)[-500:],
        "magic_hex": path.read_bytes()[:8].hex() if path.is_file() else "",
    }
    info["layers_reported"] = _int(parsed.get("LayerCount"))
    info["resolution"] = [_int(parsed.get("ResolutionX")), _int(parsed.get("ResolutionY"))]
    return info


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def sample_indexes(mesh: str, layers: int) -> list[int]:
    if layers <= 0:
        return []
    last = layers - 1
    if mesh == "box":
        picks = [0, layers // 2, last]
    elif mesh == "asymmetric":
        picks = [0, int(2.0 / LAYER_MM), int(8.0 / LAYER_MM), last]
    else:
        picks = [0, layers // 2, last]
    out = []
    for index in picks:
        if 0 <= index <= last and index not in out:
            out.append(index)
    return out


def read_layer(uv: Path, sliced: Path, index: int, dest: Path) -> np.ndarray | None:
    if dest.exists():
        for child in dest.iterdir():
            child.unlink()
    else:
        dest.mkdir(parents=True)
    proc = uvtools(uv, ["extract", str(sliced), str(dest), "--content", "Layers", "--index", str(index)])
    if proc.returncode != 0:
        return None
    pngs = list(dest.glob("*.png"))
    if not pngs:
        return None
    return np.array(Image.open(pngs[0]).convert("L"))


def compare_case(uv: Path, printer: dict, mesh: str, outputs: dict[str, Path], work: Path) -> dict:
    report: dict = {"layers": {}}
    images: dict[str, dict[int, np.ndarray]] = {"mslicer": {}, "dragonfruit": {}}
    inspections = {}
    for engine, path in outputs.items():
        inspections[engine] = inspect_file(uv, path, work)
        report["file"] = report.get("file", {})
        report["file"][engine] = inspections[engine]
    # Sample from the layer count UVtools read, else from the file we were given.
    for engine, path in outputs.items():
        layers = inspections[engine]["layers_reported"]
        if not layers:
            continue
        for index in sample_indexes(mesh, layers):
            image = read_layer(uv, path, index, work / f"layer-{engine}-{index}")
            if image is None:
                images[engine][index] = None  # type: ignore[assignment]
                continue
            images[engine][index] = image
    indexes = sorted(set(images["mslicer"]) | set(images["dragonfruit"]))
    for index in indexes:
        z_mm = (index + 0.5) * LAYER_MM
        entry: dict = {"z_mm": z_mm, "analytic_rects": rects_for(mesh, z_mm)}
        masks = {}
        for engine in ("mslicer", "dragonfruit"):
            image = images[engine].get(index)
            if image is None:
                entry[engine] = {"decoded": False}
                continue
            mask, levels = solid_mask(image)
            masks[engine] = mask
            pixel_mm_x = printer["build_width_mm"] / printer["width_px"]
            pixel_mm_y = printer["build_depth_mm"] / printer["height_px"]
            levels["area_mm2"] = levels["solid_pixels"] * pixel_mm_x * pixel_mm_y
            expected = expected_mask(
                engine,
                mesh,
                z_mm,
                printer["build_width_mm"],
                printer["build_depth_mm"],
                printer["width_px"],
                printer["height_px"],
            )
            if expected is not None and expected.shape == mask.shape:
                levels["versus_analytic"] = against_expected(mask, expected)
            entry[engine] = levels
        if "mslicer" in masks and "dragonfruit" in masks and masks["mslicer"].shape == masks["dragonfruit"].shape:
            entry["between_engines"] = layer_delta(masks["mslicer"], masks["dragonfruit"])
        report["layers"][str(index)] = entry
    return report


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def one_slice(engine: str, binary: Path, stl: Path, out: Path, printer: dict, timeout_s: float, cold_paths: list[Path] | None) -> dict:
    if cold_paths:
        for path in cold_paths:
            drop_file_cache(path)
        drop_file_cache(stl)
    if engine == "mslicer":
        cmd = slice_mslicer(binary, stl, out, printer)
    elif engine == "dragonfruit":
        cmd = slice_dragonfruit(binary, stl, out, printer)
    else:
        raise ValueError(engine)
    timed = run_timed(cmd, timeout_s)
    record = {
        "wall_s": timed["wall_s"],
        "peak_rss_kb": timed["peak_rss_kb"],
        "returncode": timed["returncode"],
        "timed_out": timed["timed_out"],
    }
    combined = timed["stdout"] + "\n" + timed["stderr"]
    if engine == "mslicer":
        parsed = parse_mslicer(combined)
        record["engine_s"] = parsed["engine_s"]
        record["triangles"] = parsed["triangles"]
        record["summary"] = parsed["summary"]
    else:
        payload = _json_object(timed["stdout"])
        if payload:
            record["engine_s"] = payload.get("wall_s")
            record["triangles"] = payload.get("model_triangle_count")
            record["layers"] = payload.get("layers")
            record["summary"] = {
                key: payload.get(key)
                for key in ("layers", "model_triangle_count", "wall_s", "total_s", "layers_per_second", "format", "resolution_px")
            }
    if timed["returncode"] != 0:
        record["error_tail"] = combined[-800:]
    return record


def expected_layers(mesh_info: dict) -> int:
    height = mesh_info["max_mm"][2] - mesh_info["min_mm"][2]
    return int(math.ceil(height / LAYER_MM - 1e-9))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bench mslicer against DragonFruit")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=600)
    parser.add_argument("--out", type=Path, default=HERE / "results" / "raw.json")
    parser.add_argument("--printers", default="jupiter,saturn2,mars5")
    parser.add_argument("--meshes", default="box,asymmetric,sculpt")
    parser.add_argument("--skip-pixels", action="store_true")
    args = parser.parse_args()

    ms_bin = Path(os.environ.get("ZEIM_MSLICER_BIN", ROOT / "third_party/mslicer/target/release/slicer"))
    df_bin = Path(os.environ.get("ZEIM_DRAGONFRUIT_BIN", "/home/ubuntu/dragonfruit/rust/dragonfruit-cli/target/release/dragonfruit-cli"))
    uv_bin = Path(os.environ.get("UVTOOLS_CMD", "/home/ubuntu/uvtools/UVtoolsCmd"))
    for label, path in (("mslicer", ms_bin), ("dragonfruit", df_bin), ("uvtools", uv_bin)):
        if not path.is_file():
            raise SystemExit(f"{label} binary not found: {path}")

    cache = HERE / "cache"
    work = HERE / "work"
    work.mkdir(parents=True, exist_ok=True)
    print("generating meshes", flush=True)
    meshes = ensure_meshes(cache)
    for name, info in meshes.items():
        print(f"  {name}: {info['triangles']} triangles, z {info['min_mm'][2]}..{info['max_mm'][2]}", flush=True)

    wanted_printers = [p for p in PRINTERS if p["id"] in set(args.printers.split(","))]
    wanted_meshes = [name for name in args.meshes.split(",") if name in meshes]
    cold_libs = {
        "mslicer": binary_and_libs(ms_bin),
        "dragonfruit": binary_and_libs(df_bin),
    }
    cases = []
    for printer in wanted_printers:
        corner_dir = cache / printer["id"]
        corner_dir.mkdir(parents=True, exist_ok=True)
        for mesh_name in wanted_meshes:
            info = meshes[mesh_name]
            corner = corner_dir / f"{mesh_name}.stl"
            write_stl(corner, translate_corner(info["tris"], printer["build_width_mm"], printer["build_depth_mm"]))
            case = {
                "printer": printer["id"],
                "printer_name": printer["name"],
                "mesh": mesh_name,
                "input_triangles": info["triangles"],
                "expected_layers": expected_layers(info),
                "engines": {},
            }
            for engine, binary, stl in (
                ("mslicer", ms_bin, corner),
                ("dragonfruit", df_bin, info["path"]),
            ):
                print(f"slice {printer['id']} {mesh_name} {engine}", flush=True)
                runs = {"cold": [], "warm": []}
                out_path = work / f"{printer['id']}-{mesh_name}-{engine}.{printer['extension']}"
                for phase, cold in (("cold", True), ("warm", False)):
                    for index in range(args.runs):
                        record = one_slice(
                            engine,
                            binary,
                            stl,
                            out_path,
                            printer,
                            args.timeout_s,
                            cold_libs[engine] if cold else None,
                        )
                        record["index"] = index
                        runs[phase].append(record)
                        print(
                            f"  {phase} {index}: wall {record['wall_s']:.3f}s rss {record['peak_rss_kb']}kB rc {record['returncode']}",
                            flush=True,
                        )
                        if record["returncode"] != 0:
                            break
                ok = [row for row in runs["cold"] + runs["warm"] if row["returncode"] == 0]
                case["engines"][engine] = {
                    "runs": runs,
                    "median_wall_s": {
                        "cold": median([row["wall_s"] for row in runs["cold"] if row["returncode"] == 0]),
                        "warm": median([row["wall_s"] for row in runs["warm"] if row["returncode"] == 0]),
                    },
                    "median_engine_s": {
                        "cold": median([row["engine_s"] for row in runs["cold"] if row["returncode"] == 0 and row.get("engine_s") is not None]),
                        "warm": median([row["engine_s"] for row in runs["warm"] if row["returncode"] == 0 and row.get("engine_s") is not None]),
                    },
                    "median_peak_rss_kb": {
                        "cold": median([row["peak_rss_kb"] for row in runs["cold"] if row["returncode"] == 0]),
                        "warm": median([row["peak_rss_kb"] for row in runs["warm"] if row["returncode"] == 0]),
                    },
                    "triangles_reported": next((row.get("triangles") for row in ok if row.get("triangles")), None),
                    "output": str(out_path) if out_path.is_file() else "",
                    "output_bytes": out_path.stat().st_size if out_path.is_file() else 0,
                }
            if not args.skip_pixels:
                outputs = {}
                for engine in ("mslicer", "dragonfruit"):
                    path = work / f"{printer['id']}-{mesh_name}-{engine}.{printer['extension']}"
                    if path.is_file() and case["engines"][engine]["runs"]["warm"] and case["engines"][engine]["runs"]["warm"][-1]["returncode"] == 0:
                        outputs[engine] = path
                if len(outputs) == 2:
                    print(f"compare {printer['id']} {mesh_name}", flush=True)
                    case["compare"] = compare_case(uv_bin, printer, mesh_name, outputs, work / "px")
            cases.append(case)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            # Checkpoint so a later timeout still leaves numbers.
            args.out.write_text(json.dumps({"cases": cases}, indent=2))

    probes = run_probes(ms_bin, df_bin, uv_bin, meshes, work)
    cpu = ""
    try:
        cpu = subprocess.run(["lscpu"], capture_output=True, text=True, check=False).stdout
    except OSError:
        cpu = ""
    model = ""
    for line in cpu.splitlines():
        if line.startswith("Model name:"):
            model = line.split(":", 1)[1].strip()
    document = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {"cpu_model": model, "cpus": os.cpu_count()},
        "settings": {
            "layer_mm": LAYER_MM,
            "exposure_s": EXPOSURE_S,
            "bottom_exposure_s": BOTTOM_EXPOSURE_S,
            "bottom_layers": BOTTOM_LAYERS,
            "lift_mm": LIFT_MM,
            "lift_speed_mm_min": LIFT_SPEED,
            "anti_aliasing": "off",
            "supports": "none",
            "orientation": "as generated, no extra rotation",
            "mirror_applied": False,
            "container_note": (
                "Timed runs write unencrypted CTB v4 for Jupiter and Saturn 2, and GOO for Mars 5, "
                "so UVtools can read both engines. Catalog native containers are probed separately. "
                "Catalog mirror flags are not applied; both engines are asked not to mirror."
            ),
        },
        "printers": wanted_printers,
        "meshes": {
            name: {
                "triangles": meshes[name]["triangles"],
                "min_mm": meshes[name]["min_mm"],
                "max_mm": meshes[name]["max_mm"],
                "note": MESH_NOTES[name],
                "expected_layers": expected_layers(meshes[name]),
            }
            for name in wanted_meshes
        },
        "bins": {"mslicer": str(ms_bin), "dragonfruit": str(df_bin), "uvtools": str(uv_bin)},
        "cases": cases,
        "probes": probes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2))
    print(f"wrote {args.out}", flush=True)


def run_probes(ms_bin: Path, df_bin: Path, uv_bin: Path, meshes: dict, work: Path) -> dict:
    """One-shot checks that are not part of the timed median."""
    printer = dict(PRINTERS[0])
    box = meshes["box"]["path"]
    corner = work / "probe-box-corner.stl"
    write_stl(corner, translate_corner(meshes["box"]["tris"], printer["build_width_mm"], printer["build_depth_mm"]))
    probes: dict = {"containers": [], "mirrors": [], "lumen": {}}
    variants = [
        ("mslicer", "v5", {**printer, "ms_ctb": "v5", "extension": "ctb"}),
        ("dragonfruit", "v5", {**printer, "df_format_version": "v5", "extension": "ctb"}),
        ("dragonfruit", "v5enc", {**printer, "df_format_version": "v5enc", "extension": "ctb"}),
        ("dragonfruit", "lumen", {**printer, "df_format_version": None, "extension": "lumen"}),
    ]
    for engine, label, plate in variants:
        out = work / f"probe-{engine}-{label}.{plate['extension']}"
        if engine == "mslicer":
            cmd = slice_mslicer(ms_bin, corner, out, plate)
        else:
            cmd = slice_dragonfruit(df_bin, box, out, plate)
        timed = run_timed(cmd, 180)
        entry = {
            "engine": engine,
            "label": label,
            "returncode": timed["returncode"],
            "wall_s": timed["wall_s"],
            "bytes": out.stat().st_size if out.is_file() else 0,
            "magic_hex": out.read_bytes()[:8].hex() if out.is_file() else "",
        }
        if plate["extension"] != "lumen" and out.is_file():
            info = inspect_file(uv_bin, out, work)
            entry["uvtools_ok"] = info["uvtools_ok"]
            entry["properties"] = info["properties"]
            entry["uvtools_error"] = info["uvtools_error"]
        else:
            data = out.read_bytes()[:4] if out.is_file() else b""
            entry["lumen_magic"] = data.decode("ascii", "replace")
            probes["lumen"] = entry
        if label != "lumen":
            probes["containers"].append(entry)
        print(f"probe {engine} {label}: rc {timed['returncode']} bytes {entry['bytes']} magic {entry['magic_hex']}", flush=True)

    # Mirror: DragonFruit flags only. mslicer CLI has no mirror switch.
    asym = meshes["asymmetric"]["path"]
    for flag in ("--mirror-x", "--mirror-y"):
        out = work / f"probe-mirror{flag}.ctb"
        cmd = slice_dragonfruit(df_bin, asym, out, printer, extra=[flag])
        timed = run_timed(cmd, 180)
        entry = {"flag": flag, "returncode": timed["returncode"], "wall_s": timed["wall_s"]}
        if timed["returncode"] == 0:
            image = read_layer(uv_bin, out, int(8.0 / LAYER_MM), work / f"mirror{flag}")
            if image is not None:
                mask, levels = solid_mask(image)
                ys, xs = np.nonzero(mask)
                entry["tower_bbox"] = {
                    "x0": int(xs.min()),
                    "x1": int(xs.max()),
                    "y0": int(ys.min()),
                    "y1": int(ys.max()),
                    "pixels": levels["solid_pixels"],
                }
        probes["mirrors"].append(entry)
        print(f"probe mirror {flag}: {entry.get('tower_bbox')}", flush=True)
    return probes


if __name__ == "__main__":
    main()
