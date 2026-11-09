"""Run the unmodified DragonFruit CLI. This module does not contain that program.

The binary is built from commit 97596a55882cb139bbcf96bb98b211f82ae4c5f0
(see third_party/dragonfruit/SOURCE.md). ZEIM passes a mesh, a plate, and
exposure numbers, and reads the file the binary writes. It does not patch
DragonFruit. Plate height and a binary anti-alias level are metadata, because
`slice run` has no build-height flag and the GOO encoder's default anti-alias
level is 8.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import trimesh

from app.core import resin_fileid, resin_slice

COMMIT = "97596a55882cb139bbcf96bb98b211f82ae4c5f0"
VERSION = "2.1.1"


class DragonFruitError(resin_slice.ResinSliceError):
    pass


def dragonfruit_bin() -> Path | None:
    return resin_slice.dragonfruit_bin()


def format_version(plate: dict, fmt: str) -> str:
    """Container revision DragonFruit should write. GOO is not selected here."""
    if fmt != "ctb":
        return ""
    version = (plate.get("native_version") or "").lower()
    if "v5enc" in version:
        return "v5enc"
    if "v5" in version:
        return "v5"
    return "v4"


def cli_mirrors(plate: dict) -> tuple[bool, bool]:
    """(mirror_x, mirror_y) for the DragonFruit flags.

    DragonFruit stores world +Y at image row 0. mslicer writes the low-Y row
    first. The bench compared the masks: a Y flip of DragonFruit's image lands
    on mslicer's pixels, aside from a one-pixel edge. No firmware document here
    picks a row as the front of the panel, so the wrapper matches mslicer.

    `--mirror-y` is that match. A catalog mirror_y of true asks for the opposite
    of the mslicer file, so it cancels the flag. Catalog mirror_x is added.
    """
    mx = plate.get("mirror_x")
    my = plate.get("mirror_y")
    if not isinstance(mx, bool) or not isinstance(my, bool):
        raise DragonFruitError(
            f"{plate.get('name', 'This plate')} has a mirror flag that is not true or false. "
            "TorchC0 will not guess a flip."
        )
    return mx, not my


def _metadata(plate: dict, settings: dict, fmt: str, version: str) -> str:
    height = plate["build_height_um"] / 1000.0
    payload = {
        "printer": {
            "name": plate.get("name") or "",
            "settingsMode": "simple",
            "buildVolumeMm": {"height": height},
        },
        "material": {
            "normalExposureSec": float(settings["exposure_s"]),
            "bottomExposureSec": float(settings["bottom_exposure_s"]),
            "bottomLayerCount": int(settings["bottom_layers"]),
            "liftDistanceMm": float(settings["lift_mm"]),
            "bottomLiftDistanceMm": float(settings["lift_mm"]),
            "liftSpeedMmMin": float(settings["lift_speed_mm_min"]),
            "bottomLiftSpeedMmMin": float(settings["lift_speed_mm_min"]),
            "retractSpeedMmMin": float(settings["lift_speed_mm_min"]),
            "bottomRetractSpeedMmMin": float(settings["lift_speed_mm_min"]),
        },
    }
    if fmt == "ctb":
        number = 5 if version in ("v5", "v5enc") else 4
        payload["ctb"] = {"version": number, "bedSizeZ": height}
    return json.dumps(payload, separators=(",", ":"))


def _aa_flag(aa: bool, aa_level: int) -> str:
    if not aa:
        return "Off"
    level = int(aa_level) if int(aa_level) in (2, 4, 8) else 4
    return f"{level}x"


def _centered_copy(stl: Path, plate: dict, dest: Path) -> int:
    """Plate-corner millimetres to DragonFruit's centre origin. The source file stays put."""
    mesh = trimesh.load(stl, file_type="stl", force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        raise DragonFruitError("The prepared model is not one mesh.")
    width = plate["build_width_um"] / 1000.0
    depth = plate["build_depth_um"] / 1000.0
    mesh.apply_translation([-width / 2.0, -depth / 2.0, 0.0])
    dest.write_bytes(mesh.export(file_type="stl"))
    return int(len(mesh.faces))


def slice_file(
    stl: Path,
    out: Path,
    plate: dict,
    settings: dict,
    fmt: str,
    *,
    aa: bool,
    aa_level: int = 4,
    cancel: threading.Event | None = None,
    placed: bool = False,
) -> dict:
    binary = dragonfruit_bin()
    if binary is None:
        raise DragonFruitError("The DragonFruit CLI is not installed.")
    resin_slice.require_sliceable(plate, engine="dragonfruit")
    version = format_version(plate, fmt)
    mirror_x, mirror_y = cli_mirrors(plate)
    width = int(plate["width_px"])
    height = int(plate["height_px"])
    build_w = plate["build_width_um"] / 1000.0
    build_d = plate["build_depth_um"] / 1000.0
    with tempfile.TemporaryDirectory(prefix="zeim-df-") as tmp:
        mesh_path = stl
        faces = None
        if placed:
            mesh_path = Path(tmp) / "centered.stl"
            faces = _centered_copy(stl, plate, mesh_path)
        cmd = [
            str(binary), "slice", "run", str(mesh_path),
            "-o", str(out),
            "--json",
            "--layer-height", str(settings["layer_mm"]),
            "--build-width-mm", str(build_w),
            "--build-depth-mm", str(build_d),
            "--source-width-px", str(width),
            "--source-height-px", str(height),
            "--anti-aliasing", _aa_flag(aa, aa_level),
            "--anti-aliasing-mode", "Coverage",
            "--blur-brush-radius-px", "0",
            "--z-blur-radius-layers", "0",
            "--z-blend-look-back", "0",
            "--sample-interval-ms", "0",
            "--metadata-json", _metadata(plate, settings, fmt, version),
        ]
        if version:
            cmd.extend(["--format-version", version])
        if mirror_x:
            cmd.append("--mirror-x")
        if mirror_y:
            cmd.append("--mirror-y")
        timeout = float(os.environ.get("ZEIM_DRAGONFRUIT_TIMEOUT_S", "180"))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=_limits,
        )
        out_b, err_b = _wait(proc, timeout, cancel)
    if proc.returncode != 0:
        tail = (err_b or out_b).decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else f"exit {proc.returncode}"
        raise DragonFruitError(f"DragonFruit failed: {detail[:400]}")
    text = out_b.decode("utf-8", "replace")
    start, end = text.find("{"), text.rfind("}")
    summary = None
    if start >= 0 and end > start:
        try:
            summary = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            summary = None
    if not isinstance(summary, dict) or "layers" not in summary:
        raise DragonFruitError("DragonFruit finished without a slice summary.")
    data = out.read_bytes()
    ident = resin_fileid.identify(data, fmt)
    layers = int(summary["layers"])
    if ident["layers_in_file"] is not None and ident["layers_in_file"] != layers:
        raise DragonFruitError("The file's layer count does not match the slicer's summary.")
    native = (plate.get("native_format") or "").lstrip(".").lower()
    catalog_x = plate.get("mirror_x") is True
    catalog_y = plate.get("mirror_y") is True
    return {
        "format": fmt,
        "extension": f".{fmt}",
        "bytes": len(data),
        "layers": layers,
        "width_px": int(summary.get("resolution_px", [width, height])[0]),
        "height_px": int(summary.get("resolution_px", [width, height])[1]),
        "ctb_container": version if fmt == "ctb" else "",
        "file_magic": ident["magic"],
        "layers_in_file": ident["layers_in_file"],
        "engine": "dragonfruit",
        "engine_license": "AGPL-3.0-or-later",
        "engine_commit": COMMIT,
        "engine_version": VERSION,
        "engine_requested": "dragonfruit",
        "engine_fallback": "",
        "triangles": summary.get("model_triangle_count"),
        "triangles_sent": faces,
        "native_format": plate.get("native_format") or "",
        "native_format_written": bool(native) and native == fmt,
        "hardware_tested": False,
        "mirror_applied": catalog_x or catalog_y,
        "mirror_x": catalog_x,
        "mirror_y": catalog_y,
        "y_convention": "mslicer",
        "anti_aliasing": bool(aa),
        "layer_height_um": int(round(float(settings["layer_mm"]) * 1000)),
        "normal_exposure_ms": int(round(float(settings["exposure_s"]) * 1000)),
        "bottom_exposure_ms": int(round(float(settings["bottom_exposure_s"]) * 1000)),
        "bottom_layer_count": int(settings["bottom_layers"]),
        "lift_slow_distance_um": int(round(float(settings["lift_mm"]) * 1000)),
        "lift_slow_speed_um_min": int(round(float(settings["lift_speed_mm_min"]) * 1000)),
        "timeout_s": timeout,
        "note": (
            "Sliced by the separate DragonFruit program (AGPL-3.0-or-later), unmodified, "
            f"commit {COMMIT}. "
            "The image rows follow mslicer's order: --mirror-y, unless the catalog mirror_y flag cancels it. "
            "Plate height is passed in the job metadata. Not printed on a machine. "
            "The container name is the catalog label, not a firmware test."
        ),
    }


def _limits() -> None:
    mem_mb = int(os.environ.get("ZEIM_DRAGONFRUIT_MEM_MB", "4096"))
    cpu_s = int(os.environ.get("ZEIM_DRAGONFRUIT_CPU_S", "180"))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    except (ValueError, OSError):
        return


def _wait(proc: subprocess.Popen, timeout: float, cancel: threading.Event | None) -> tuple[bytes, bytes]:
    deadline = time.monotonic() + timeout
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise resin_slice.ResinSliceCancelled("Slice cancelled.")
        if time.monotonic() > deadline:
            proc.kill()
            raise DragonFruitError("DragonFruit ran too long and was stopped.")
        time.sleep(0.05)
    assert proc.stdout is not None and proc.stderr is not None
    return proc.stdout.read(2_000_000), proc.stderr.read(2_000_000)
