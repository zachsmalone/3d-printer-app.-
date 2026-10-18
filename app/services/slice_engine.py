"""In-app slicing: PrusaSlicer CLI wrapper, printer profiles, bed-fit check, G-code stats.

The engine is run as a separate process (never imported), so ZEIM does not link
against PrusaSlicer code. PrusaSlicer is AGPL-3.0 and is used unmodified;
see docs/licensing.md (never patch, modify or link it).
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger("zeim.slice")

SLICE_TIMEOUT_S = int(os.environ.get("PHOTO3D_SLICE_TIMEOUT", "300"))
SLICE_MEM_MB = int(os.environ.get("PHOTO3D_SLICE_MEM_MB", "2048"))
FIT_TOLERANCE_MM = 0.05


class SliceError(Exception):
    """Carries a stable machine code, a friendly message and an HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# --------------------------------------------------------------------------- profiles
_K1_INI = r"""
bed_shape = 0x0,220x0,220x220,0x220
max_print_height = 250
nozzle_diameter = 0.4
filament_diameter = 1.75
filament_type = PLA
filament_density = 1.24
temperature = 210
first_layer_temperature = 215
bed_temperature = 60
first_layer_bed_temperature = 60
layer_height = 0.2
first_layer_height = 0.2
perimeters = 2
top_solid_layers = 4
bottom_solid_layers = 4
fill_density = 15%
gcode_flavor = marlin2
use_relative_e_distances = 1
layer_gcode = G92 E0
retract_length = 0.8
retract_speed = 40
start_gcode = G28\nM140 S[first_layer_bed_temperature]\nM104 S[first_layer_temperature]\nM190 S[first_layer_bed_temperature]\nM109 S[first_layer_temperature]
end_gcode = M104 S0\nM140 S0\nG91\nG1 Z10 F600\nG90\nM84
"""


@dataclass(frozen=True)
class PrinterProfile:
    id: str
    name: str
    bed_x: float
    bed_y: float
    max_z: float
    nozzle: float
    filament: str
    ini: str

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "bed_mm": [self.bed_x, self.bed_y, self.max_z],
                "nozzle_mm": self.nozzle, "filament": self.filament}


CREALITY_K1 = PrinterProfile("creality_k1", "Creality K1", 220.0, 220.0, 250.0, 0.4, "PLA", _K1_INI)
PROFILES = {CREALITY_K1.id: CREALITY_K1}
DEFAULT_PROFILE = CREALITY_K1.id


def merge_ini(base: str, overrides: dict) -> str:
    """Base PrusaSlicer ini with keys replaced (or added). Values never contain newlines from users: all are numbers/enums."""
    out, seen = [], set()
    for line in base.strip().splitlines():
        k = line.split("=", 1)[0].strip()
        if "=" in line and k in overrides:
            out.append(f"{k} = {overrides[k]}"); seen.add(k)
        else:
            out.append(line)
    out += [f"{k} = {v}" for k, v in overrides.items() if k not in seen]
    return "\n".join(out) + "\n"


def profile_for(printer_id=None, nozzle=None, opts: dict | None = None, base_ini: str | None = None):
    """(PrinterProfile, settings) for a catalog printer + nozzle + slicer panel. THE single place slicing config is built."""
    from app.services import print_setup as ps
    try:
        s = ps.settings_for(printer_id, nozzle, opts)
    except ps.SetupError as e:
        raise SliceError("bad_settings", str(e), 400)
    x, y, z = ps.bed_of(s["printer_id"])
    ini = merge_ini(base_ini or _K1_INI, ps.ini_overrides(s))      # includes filament_density for the chosen material (grams estimate)
    return PrinterProfile(s["printer_id"], s["printer"], x, y, z, s["nozzle"], s["material"], ini), s


def get_profile(profile_id: str) -> PrinterProfile:
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise SliceError("unknown_profile", "That printer isn't set up yet. Available printers: "
                         + ", ".join(p.name for p in PROFILES.values()) + ".", 400)


# --------------------------------------------------------------------------- STL bounds
def stl_bounds(path: Path) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """(min_xyz, max_xyz) of a binary or ASCII STL. Raises SliceError if unreadable."""
    bad = SliceError("bad_model", "That file doesn't look like a valid STL model. "
                     "Please export it as an STL and try again.", 400)
    size = path.stat().st_size
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    with open(path, "rb") as f:
        head = f.read(84)
        is_binary = len(head) == 84 and 84 + struct.unpack("<I", head[80:84])[0] * 50 == size
        if is_binary:
            if size == 84:
                raise bad
            rec = struct.Struct("<12fH")
            while True:
                chunk = f.read(rec.size * 20000)
                if not chunk:
                    break
                for r in rec.iter_unpack(chunk):
                    for v in range(3):
                        for a in range(3):
                            c = r[3 + v * 3 + a]
                            if c < lo[a]:
                                lo[a] = c
                            if c > hi[a]:
                                hi[a] = c
        else:
            f.seek(0)
            pat = re.compile(rb"^\s*vertex\s+(\S+)\s+(\S+)\s+(\S+)", re.I)
            for line in f:
                m = pat.match(line)
                if not m:
                    continue
                try:
                    xyz = [float(g) for g in m.groups()]
                except ValueError:
                    raise bad
                for a in range(3):
                    lo[a] = min(lo[a], xyz[a])
                    hi[a] = max(hi[a], xyz[a])
    if not all(math.isfinite(v) for v in lo + hi):
        raise bad
    return (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])


def check_fits(dims: tuple[float, float, float], profile: PrinterProfile) -> None:
    x, y, z = dims
    limits = (profile.bed_x, profile.bed_y, profile.max_z)
    if all(d <= l + FIT_TOLERANCE_MM for d, l in zip(dims, limits)):
        return
    scale = min(l / d for d, l in zip(dims, limits) if d > 0)
    pct = max(1, int(math.floor(scale * 100)))
    raise SliceError(
        "too_big",
        f"This model is {x:.0f} × {y:.0f} × {z:.0f} mm, but the {profile.name} can only print up to "
        f"{profile.bed_x:.0f} × {profile.bed_y:.0f} × {profile.max_z:.0f} mm. "
        f"Try scaling it down to about {pct}% or smaller in the Edit tab (Scale), or cut it into pieces with Edit → Split "
        f"and print them one at a time, then slice it again (or turn on shrink-to-fit and ZEIM will do it for you).",
        422,
    )


# --------------------------------------------------------------------------- engine
def find_engine() -> Optional[str]:
    names = [os.environ.get("PHOTO3D_SLICER", "")] + ["prusa-slicer", "prusa-slicer-console", "prusaslicer"]
    for n in names:
        if n:
            p = shutil.which(n)
            if p:
                return p
    return None


def _slice_rlimits():
    """Cap the slicer process's memory (RLIMIT_AS) so one huge mesh can't OOM the host.
    Default 2048 MB, env-tunable (PHOTO3D_SLICE_MEM_MB, 0 = off)."""
    import resource
    mb = SLICE_MEM_MB
    if mb <= 0:
        return
    resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024, mb * 1024 * 1024))


def run_engine(engine: str, ini: Path, model: Path, out: Path, timeout: int = SLICE_TIMEOUT_S, center=(110, 110)) -> None:
    # Argument list, no shell: nothing user-controlled is interpreted.
    # model is an STL or a PrusaSlicer-friendly 3MF (paint-on support enforcers/blockers).
    cmd = [engine, "--export-gcode", "--center", f"{center[0]:g},{center[1]:g}", "--load", str(ini), "--output", str(out), str(model)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, preexec_fn=_slice_rlimits)
    except subprocess.TimeoutExpired:
        raise SliceError("slice_timeout", "Slicing took too long and was stopped. Try a smaller or "
                         "simpler model.", 504)
    except OSError:
        log.exception("could not start slicer")
        raise SliceError("slicer_unavailable", "The slicer couldn't be started on this server.", 503)
    tail = (proc.stderr or "")[-600:] + (proc.stdout or "")[-600:]
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        log.error("slicer failed rc=%s: %s", proc.returncode, tail)
        if "could not fit" in tail.lower():
            raise SliceError("too_big", "This model doesn't fit on the printer bed. Try scaling it down, or cut it into pieces with Edit → Split.", 422)
        raise SliceError("slice_failed", "The slicer couldn't process this model. If it has holes or "
                         "broken surfaces, run Fix in the Edit tab and try again.", 500)


# --------------------------------------------------------------------------- G-code stats
_TIME_LINE = re.compile(r"^;\s*estimated printing time \(normal mode\)\s*=\s*(.+?)\s*$")
_TOTAL_G = re.compile(r"^;\s*total filament used \[g\]\s*=\s*([\d.]+)")
_G = re.compile(r"^;\s*filament used \[g\]\s*=\s*([\d.,\s]+?)\s*$")
_TOKEN = re.compile(r"(\d+)\s*([dhms])")
_UNIT = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text: str) -> Optional[int]:
    toks = _TOKEN.findall(text)
    return sum(int(n) * _UNIT[u] for n, u in toks) if toks else None


def humanize(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = [f"{d}d"] if d else []
    if h or d:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    if not (d or h):
        parts.append(f"{s}s")
    return " ".join(parts)


def parse_gcode_stats(path: Path) -> tuple[Optional[int], Optional[float]]:
    """(print_time_seconds, filament_grams) from PrusaSlicer's G-code comments."""
    seconds: Optional[int] = None
    total: Optional[float] = None
    summed: Optional[float] = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if not line.startswith(";"):
                continue
            m = _TIME_LINE.match(line)
            if m:
                seconds = parse_duration(m.group(1))
                continue
            m = _TOTAL_G.match(line)
            if m:
                total = float(m.group(1))
                continue
            m = _G.match(line)
            if m:
                try:
                    summed = sum(float(v) for v in m.group(1).split(",") if v.strip())
                except ValueError:
                    pass
    grams = total if total is not None else summed
    return seconds, (round(grams, 2) if grams is not None else None)


# --------------------------------------------------------------------------- orchestration
@dataclass
class SliceResult:
    gcode: Path
    print_time_seconds: Optional[int]
    filament_grams: Optional[float]
    size_mm: tuple[float, float, float]
    profile: PrinterProfile


def slice_model_path(model: Path, profile: PrinterProfile, out_gcode: Path, *,
                    bounds_stl: Path | None = None) -> SliceResult:
    """Slice an STL or a paint-on-supports 3MF. Bed-fit uses `bounds_stl` (the plain model) when given,
    so painted enforcer/blocker volumes never change the size check."""
    src = bounds_stl or model
    lo, hi = stl_bounds(src) if src.suffix.lower() == ".stl" else _mesh_bounds(src)
    size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    check_fits(size, profile)
    engine = find_engine()
    if engine is None:
        raise SliceError("slicer_unavailable", "Slicing isn't available on this server yet "
                         "(PrusaSlicer isn't installed). You can still download your model and slice it "
                         "on your own computer.", 503)
    out_gcode.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zeim-slice-") as td:
        ini = Path(td) / "profile.ini"
        ini.write_text(profile.ini.strip() + "\n")
        run_engine(engine, ini, model, out_gcode, center=(profile.bed_x / 2, profile.bed_y / 2))
    seconds, grams = parse_gcode_stats(out_gcode)
    return SliceResult(out_gcode, seconds, grams, size, profile)


def _mesh_bounds(path: Path) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Bounds of a mesh file via trimesh (used for 3MF when no separate STL is given)."""
    import trimesh
    try:
        m = trimesh.load(str(path), force="mesh")
        if m.bounds is None:
            raise ValueError
        lo, hi = m.bounds
        return (float(lo[0]), float(lo[1]), float(lo[2])), (float(hi[0]), float(hi[1]), float(hi[2]))
    except Exception:
        raise SliceError("bad_model", "That file doesn't look like a valid 3D model. Please try again.", 400)


def slice_stl(stl: Path, profile: PrinterProfile, out_gcode: Path) -> SliceResult:
    return slice_model_path(stl, profile, out_gcode)
