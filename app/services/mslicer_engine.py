"""Run mslicer's GPL-3.0 `slicer` binary. This module does not contain that program.

The binary and its source live in `third_party/mslicer` (upstream v0.10.1 plus the
`--ctb` flag described in that directory's ZEIM-CHANGES.md). ZEIM passes a mesh
path, plate millimetres, and exposure numbers on the command line and reads the
file the binary writes.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import threading
from pathlib import Path

from app.core import resin_fileid, resin_slice

ROOT = Path(__file__).resolve().parents[2]


class MSlicerError(resin_slice.ResinSliceError):
    pass


def mslicer_bin() -> Path | None:
    env = os.environ.get("ZEIM_MSLICER_BIN", "").strip()
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path("/usr/local/bin/mslicer-slicer"))
    candidates.append(ROOT / "third_party" / "mslicer" / "target" / "release" / "slicer")
    for path in candidates:
        if path.is_file():
            return path
    return None


def output_format(fmt: str) -> str:
    key = (fmt or "").strip().lower().lstrip(".")
    if key in ("", "lumen", "lmn"):
        return "lumen"
    if key in ("goo", "ctb", "nanodlp"):
        return key
    resin_slice.reject_format(key)
    return key


def ctb_kind_for(plate: dict) -> str:
    """Which mslicer CTB container matches this plate row, if any."""
    native = (plate.get("native_format") or "").lstrip(".").lower()
    version = (plate.get("native_version") or "").lower()
    if plate.get("kind") == "inspection" or not native:
        return "legacy"
    if native != "ctb":
        raise MSlicerError(
            f"{plate['name']} stock file is .{native}. TorchC0 will not write a .ctb and call it that printer's file."
        )
    if version == "v2":
        raise MSlicerError(
            f"{plate['name']} is listed as CTB v2. mslicer writes unencrypted v4 or encrypted v5, not v2. "
            "TorchC0 will not save a v4 file as if it were that v2 file."
        )
    if "v5" in version:
        return "v5"
    return "legacy"


def require_format_plate(plate: dict, fmt: str) -> str:
    """Return the mslicer --ctb value. Raise when the plate's stock file is a different extension."""
    resin_slice.require_sliceable(plate, engine="mslicer")
    native = (plate.get("native_format") or "").lstrip(".").lower()
    inspection = plate.get("kind") == "inspection" or not native
    if fmt == "goo":
        if not inspection and native != "goo":
            shown = f".{native}" if native else "unknown"
            raise MSlicerError(
                f"{plate['name']} stock file is {shown}. TorchC0 will not write a .goo and call it that printer's file."
            )
        return "legacy"
    if fmt == "ctb":
        return ctb_kind_for(plate)
    if fmt == "nanodlp":
        if not inspection and native not in ("", "nanodlp"):
            raise MSlicerError(
                f"{plate['name']} stock file is .{native}. TorchC0 will not write a .nanodlp and call it that printer's file."
            )
        return "legacy"
    raise MSlicerError(f".{fmt} is not an mslicer output.")


def slice_file(stl: Path, out: Path, plate: dict, settings: dict, fmt: str, *, aa: bool,
               cancel: threading.Event | None = None) -> dict:
    binary = mslicer_bin()
    if binary is None:
        raise MSlicerError(
            "The mslicer slicer binary is not built. From third_party/mslicer run "
            "`cargo build --release -p slicer --bin slicer` (Rust 1.87 or newer)."
        )
    ctb = require_format_plate(plate, fmt)
    width, height = int(plate["width_px"]), int(plate["height_px"])
    sx = plate["build_width_um"] / 1000.0
    sy = plate["build_depth_um"] / 1000.0
    sz = plate["build_height_um"] / 1000.0
    cmd = [
        str(binary), "--quiet",
        "--platform-resolution", f"{width}, {height}",
        "--platform-size", f"{sx}, {sy}, {sz}",
        "--layer-height", str(settings["layer_mm"]),
        "--first-layers", str(int(settings["bottom_layers"])),
        "--transition-layers", "0",
        "--exposure-time", str(settings["exposure_s"]),
        "--first-exposure-time", str(settings["bottom_exposure_s"]),
        "--lift-distance", str(settings["lift_mm"]),
        "--first-lift-distance", str(settings["lift_mm"]),
        "--lift-speed", str(settings["lift_speed_mm_min"]),
        "--first-lift-speed", str(settings["lift_speed_mm_min"]),
        # TorchC0 has one travel speed. mslicer also asks for a retract speed.
        "--retract-speed", str(settings["lift_speed_mm_min"]),
        "--first-retract-speed", str(settings["lift_speed_mm_min"]),
        "--supersample", "8" if aa else "1",
        "--ctb", ctb,
        "--mesh", str(stl),
        str(out),
    ]
    timeout = float(os.environ.get("ZEIM_MSLICER_TIMEOUT_S", "180"))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=_limits,
    )
    try:
        deadline_note = timeout
        out_b, err_b = _wait(proc, timeout, cancel)
    except resin_slice.ResinSliceCancelled:
        raise
    if proc.returncode != 0:
        tail = (err_b or out_b).decode("utf-8", "replace").strip().splitlines()
        detail = tail[-1] if tail else f"exit {proc.returncode}"
        raise MSlicerError(f"mslicer failed: {detail[:400]}")
    text = out_b.decode("utf-8", "replace")
    summary = None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                summary = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    if not summary or summary.get("program") != "mslicer":
        raise MSlicerError("mslicer finished without its summary line.")
    data = out.read_bytes()
    ident = resin_fileid.identify(data, fmt)
    if ident["layers_in_file"] is not None and ident["layers_in_file"] != summary["layers"]:
        raise MSlicerError("The file's layer count does not match the slicer's summary.")
    native = (plate.get("native_format") or "").lstrip(".").lower()
    return {
        "format": fmt,
        "extension": f".{fmt}",
        "bytes": len(data),
        "layers": int(summary["layers"]),
        "width_px": int(summary["width"]),
        "height_px": int(summary["height"]),
        "ctb_container": ctb if fmt == "ctb" else "",
        "file_magic": ident["magic"],
        "layers_in_file": ident["layers_in_file"],
        "engine": "mslicer",
        "engine_license": "GPL-3.0",
        "engine_commit": "2d639519eedf4269a341fb6d5508901e06d99d48",
        "engine_version": "v0.10.1",
        "native_format": plate.get("native_format") or "",
        "native_format_written": bool(native) and native == fmt,
        "hardware_tested": False,
        "mirror_applied": False,
        "mirror_x": bool(plate.get("mirror_x")),
        "mirror_y": bool(plate.get("mirror_y")),
        "anti_aliasing": bool(aa),
        "layer_height_um": int(round(float(settings["layer_mm"]) * 1000)),
        "normal_exposure_ms": int(round(float(settings["exposure_s"]) * 1000)),
        "bottom_exposure_ms": int(round(float(settings["bottom_exposure_s"]) * 1000)),
        "bottom_layer_count": int(settings["bottom_layers"]),
        "lift_slow_distance_um": int(round(float(settings["lift_mm"]) * 1000)),
        "lift_slow_speed_um_min": int(round(float(settings["lift_speed_mm_min"]) * 1000)),
        "timeout_s": deadline_note,
        "note": (
            "Sliced by the separate mslicer program (GPL-3.0). "
            "Retract speed is the same as the lift speed because TorchC0 has one travel speed. "
            "Transition layers are 0. Not printed on a machine. "
            "The container name is the catalog label, not a firmware test. "
            "Catalog mirror flags are reported and are not written into the file."
        ),
    }


def _limits() -> None:
    mem_mb = int(os.environ.get("ZEIM_MSLICER_MEM_MB", "4096"))
    cpu_s = int(os.environ.get("ZEIM_MSLICER_CPU_S", "120"))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
    except (ValueError, OSError):
        return


def _wait(proc: subprocess.Popen, timeout: float, cancel: threading.Event | None) -> tuple[bytes, bytes]:
    import time
    deadline = time.monotonic() + timeout
    while proc.poll() is None:
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise resin_slice.ResinSliceCancelled("Slice cancelled.")
        if time.monotonic() > deadline:
            proc.kill()
            raise MSlicerError("mslicer ran too long and was stopped.")
        time.sleep(0.05)
    assert proc.stdout is not None and proc.stderr is not None
    return proc.stdout.read(2_000_000), proc.stderr.read(2_000_000)
