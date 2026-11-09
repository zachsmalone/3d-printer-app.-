"""Rasterise a prepared TorchC0 mesh into layer masks and write a LUMEN v1 file.

The file container is the Open Resin Alliance `lumen-format` crate (MIT OR Apache-2.0),
invoked as `tools/zeim-lumen`. The mesh-to-mask step is ZEIM code. `.ctb` and
`.nanodlp` are written by the separate unmodified DragonFruit CLI. `.goo` stays
on the separate mslicer program. Neither engine is linked into this process.

Physical units: the mesh is millimetres, Z up, plate at the minimum Z. LUMEN stores
micrometres, milliseconds and micrometres per minute. One TorchC0 lift becomes the
LUMEN slow lift, and the fast lift distance is 0. Retract uses that same distance
and speed, because TorchC0 has one travel. Upstream mirror flags are recorded and
not applied to the pixels.

This does not write .ctb, .goo, .lys, .photon or a zip, and it does not start a printer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from skimage.draw import polygon as sk_polygon

from app.core.lumen_head import LumenHeadError, read_head

MAX_PIXELS = 12_000_000
# mslicer is a separate process. Saturn 2 is 33,177,600 px and peaked near 520 MB
# on a 910,180-triangle mesh, inside the 4096 MB mslicer address limit.
# Plates above this stay refused until they are measured. This is not a global uncap.
MSLICER_MAX_PIXELS = 34_000_000
MAX_LAYERS = 2500
MAX_FACES = 400_000
AA_LEVELS = (2, 4)
STRIP_ROWS = 32
REJECTED_FORMATS = {
    "ctbx": "CHITUBOX .ctbx is not written. mslicer writes .ctb v4 or v5, not .ctbx.",
    "lys": "Lychee .lys is not written.",
    "lyt": "Lychee .lyt is not written.",
    "photon": "Photon .photon is not written.",
    "photons": "Photon .photons is not written.",
    "pws": "Anycubic .pws is not written.",
    "pw0": "Anycubic .pw0 is not written.",
    "pwmx": "Anycubic .pwmx is not written.",
    "pmx2": "Anycubic .pmx2 is not written.",
    "aff": "Anycubic .aff is not written.",
    "afz": "Anycubic .afz is not written.",
    "zip": "TorchC0 does not pack a zip and call it a printer file.",
    "svg": "An SVG layer stack is not written.",
}


class ResinSliceError(ValueError):
    """A slice request that cannot be completed. The message is safe to show."""


class ResinSliceCancelled(ResinSliceError):
    pass


def dragonfruit_bin() -> Path | None:
    env = os.environ.get("ZEIM_DRAGONFRUIT_BIN", "").strip()
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path("/usr/local/bin/dragonfruit-cli"))
    for path in candidates:
        if path.is_file():
            return path
    return None


def configured_resin_engine() -> str:
    """`ZEIM_RESIN_ENGINE=dragonfruit|mslicer`. Anything else stays on the default."""
    choice = os.environ.get("ZEIM_RESIN_ENGINE", "dragonfruit").strip().lower()
    if choice in ("dragonfruit", "mslicer"):
        return choice
    return "dragonfruit"


def writer_for(fmt: str) -> str:
    """Which separate program writes this printer file.

    `.lumen` is ZEIM's own encoder. `.goo` stays on mslicer because DragonFruit's
    GOO header is version V1.2 and mslicer's is V3.0, and that has not been
    accepted by a printer here. `.ctb` and `.nanodlp` use DragonFruit when it is
    the selected engine and the binary is installed.
    """
    key = (fmt or "").strip().lower().lstrip(".")
    if key in ("", "lmn"):
        key = "lumen"
    if key == "lumen":
        return "lumen"
    if key == "goo":
        return "mslicer"
    if key in ("ctb", "nanodlp") and configured_resin_engine() == "dragonfruit" and dragonfruit_bin() is not None:
        return "dragonfruit"
    return "mslicer"


def lumen_bin() -> Path | None:
    env = os.environ.get("ZEIM_LUMEN_BIN", "").strip()
    if env:
        path = Path(env)
        return path if path.is_file() else None
    built = Path(__file__).resolve().parents[2] / "tools" / "zeim-lumen" / "target" / "release" / "zeim-lumen"
    return built if built.is_file() else None


def load_plates() -> dict:
    raw = json.loads((Path(__file__).resolve().parent / "lumen_plates.json").read_text())
    return raw


def plate_by_id(plate_id: str) -> dict:
    for plate in load_plates()["plates"]:
        if plate["id"] == plate_id:
            return plate
    raise ResinSliceError("Unknown plate. Pick one from the LUMEN plate list.")


def require_sliceable(plate: dict, *, engine: str = "lumen") -> None:
    """Reject a plate this engine will not raster, before any file is written.

    `.lumen` is rasterised in this process and stays at `MAX_PIXELS`.
    mslicer has its own pixel ceiling and its own memory limit. A plate mslicer
    can run is not refused because the in-process cap is lower.
    """
    width, height = int(plate["width_px"]), int(plate["height_px"])
    pixels = width * height
    if engine == "lumen":
        cap = MAX_PIXELS
    elif engine in ("mslicer", "dragonfruit"):
        cap = MSLICER_MAX_PIXELS
    else:
        raise ResinSliceError(f"Unknown slice engine {engine}.")
    if pixels <= 0 or pixels > cap:
        if engine in ("mslicer", "dragonfruit"):
            raise ResinSliceError(
                f"{plate['name']} is {width}×{height} px ({pixels:,} pixels). "
                f"Printer-file slices are capped at {cap:,} pixels so they stay inside the memory limit. "
                f"The .lumen cap is {MAX_PIXELS:,} and does not apply to this file."
            )
        native = plate.get("native_format") or "its stock file"
        raise ResinSliceError(
            f"{plate['name']} is {width}×{height} px ({pixels:,} pixels). "
            f"TorchC0 slices plates up to {cap:,} pixels into .lumen, and it does not write {native}."
        )


# Advertised bed sizes and the geometry table can differ by a rounded millimetre.
# Saturn 3 is 250 mm in the printer list and 249.7 mm in the plate row.
BED_MATCH_MM = 0.35


def plate_bed_mm(plate: dict) -> tuple[float, float, float]:
    return (
        float(plate["build_width_um"]) / 1000.0,
        float(plate["build_depth_um"]) / 1000.0,
        float(plate["build_height_um"]) / 1000.0,
    )


def beds_match(bed_mm, plate: dict) -> bool:
    if not bed_mm or len(bed_mm) < 3:
        return False
    return all(abs(float(a) - b) <= BED_MATCH_MM for a, b in zip(bed_mm, plate_bed_mm(plate)))


def plates_for_printer(brand: str, model: str, bed_mm) -> list[dict]:
    """Plates whose manufacturer, model name, and bed are this printer.

    Mars 5 and Mars 5 Ultra are not the same plate. Jupiter and Jupiter SE share a bed
    and stay apart because the model name has to match.
    """
    want_brand = (brand or "").casefold()
    want_model = model or ""
    found = []
    for plate in load_plates()["plates"]:
        if plate.get("kind") == "inspection":
            continue
        if (plate.get("manufacturer") or "").casefold() != want_brand:
            continue
        if (plate.get("name") or "") != want_model:
            continue
        if not beds_match(bed_mm, plate):
            continue
        found.append(plate)
    return found


def _mirror_axes(plate: dict) -> tuple[list[str], bool]:
    """Catalog axes that are true, and whether either flag is not a boolean."""
    axes = []
    uncertain = False
    for key, label in (("mirror_x", "X"), ("mirror_y", "Y")):
        value = plate.get(key)
        if not isinstance(value, bool):
            uncertain = True
        elif value:
            axes.append(label)
    return axes, uncertain


def block_reason(plate: dict, fmt: str) -> str:
    """Why this file must not be written for this plate. Empty when it may.

    DragonFruit can mirror `.ctb` and `.nanodlp` when both catalog flags are
    booleans. `.goo` stays on mslicer, which does not flip pixels, so a mirrored
    GOO plate is still refused. A flag that is not true or false is refused for
    every format.
    """
    key = (fmt or "").strip().lower().lstrip(".")
    if key == "lmn":
        key = "lumen"
    parts: list[str] = []
    if plate.get("kind") != "inspection":
        axes, uncertain = _mirror_axes(plate)
        writer = writer_for(key) if key in ("lumen", "goo", "ctb", "nanodlp") else ""
        if uncertain and (plate.get("mirror_x") or plate.get("mirror_y")):
            parts.append(
                f"{plate['name']} has a mirror flag that is not true or false. "
                "TorchC0 will not guess a flip, so it will not write this file."
            )
        elif axes and writer != "dragonfruit":
            parts.append(
                f"{plate['name']} is listed with a mirrored image ({' and '.join(axes)}). "
                "mslicer does not flip pixels, and TorchC0 will not write an unmirrored file "
                "for that catalog."
            )
    native = (plate.get("native_format") or "").lstrip(".").lower()
    version = (plate.get("native_version") or "").lower()
    width, height = int(plate["width_px"]), int(plate["height_px"])
    pixels = width * height
    if key == "lumen":
        if pixels > MAX_PIXELS:
            stock = plate.get("native_format") or "its stock file"
            parts.append(
                f"{plate['name']} is {width}×{height} px ({pixels:,} pixels). "
                f"TorchC0 slices plates up to {MAX_PIXELS:,} pixels into .lumen, and it does not write {stock}."
            )
    elif key in ("goo", "ctb", "nanodlp"):
        if plate.get("kind") != "inspection" and native and native != key:
            parts.append(
                f"{plate['name']} stock file is .{native}. "
                f"TorchC0 will not write a .{key} and call it that printer's file."
            )
        if key == "ctb" and version == "v2":
            parts.append(
                f"{plate['name']} is listed as CTB v2. mslicer writes unencrypted v4 or encrypted v5, not v2."
            )
        if pixels > MSLICER_MAX_PIXELS:
            parts.append(
                f"{plate['name']} is {width}×{height} px ({pixels:,} pixels), "
                f"above the {MSLICER_MAX_PIXELS:,} pixel cap, so it is not sliced."
            )
    else:
        parts.append(f".{key} is not a slice file TorchC0 writes.")
    return " ".join(parts)


def plate_for_ui(plate: dict) -> dict:
    row = dict(plate)
    row["blocks"] = {fmt: block_reason(plate, fmt) for fmt in ("lumen", "goo", "ctb", "nanodlp")}
    return row


def refuse_for_printer(plate: dict, fmt: str, printer: dict | None) -> None:
    """The slice plate has to be the printer the mesh was prepared on."""
    if printer:
        matches = plates_for_printer(printer.get("brand") or "", printer.get("model") or "", printer.get("bed_mm"))
        if plate.get("id") not in {row["id"] for row in matches}:
            who = f"{printer.get('brand', '')} {printer.get('model', '')}".strip() or "The selected printer"
            if not matches:
                raise ResinSliceError(
                    f"{who} has no slice plate with this name and bed. "
                    "TorchC0 will not write a file for a different machine."
                )
            theirs = ", ".join(row["name"] for row in matches)
            raise ResinSliceError(
                f"{who} uses {theirs}. {plate.get('manufacturer', '')} {plate.get('name', '')} is a different machine. "
                "TorchC0 will not write that file."
            )
    elif plate.get("kind") != "inspection":
        raise ResinSliceError(
            "Choose the printer this file is for. TorchC0 will not slice a commercial plate without that printer."
        )
    reason = block_reason(plate, fmt)
    if reason:
        raise ResinSliceError(reason)


def reject_format(fmt: str) -> None:
    key = (fmt or "").strip().lower().lstrip(".")
    if key in ("", "lumen", "lmn", "goo", "ctb", "nanodlp"):
        return
    detail = REJECTED_FORMATS.get(key)
    if detail:
        raise ResinSliceError(detail)
    raise ResinSliceError(
        f".{key} is not a file TorchC0 writes. It writes .lumen, and, through the separate mslicer program, .goo, .ctb, or .nanodlp. "
        "It does not write Lychee, Photon, .ctbx, or a zip renamed as a printer file."
    )


def _um(mm: float, what: str) -> int:
    v = float(mm) * 1000.0
    if not math.isfinite(v) or v < 0 or v > 5_000_000:
        raise ResinSliceError(f"{what} is out of range.")
    return int(round(v))


def _ms(seconds: float, what: str) -> int:
    v = float(seconds) * 1000.0
    if not math.isfinite(v) or v < 0 or v > 3_600_000:
        raise ResinSliceError(f"{what} is out of range.")
    return int(round(v))


def _shift_ring(coords, ox: float, oy: float):
    return [(float(x) + ox, float(y) + oy) for x, y in coords]


def _to_plate(poly: Polygon, ox: float, oy: float) -> Polygon:
    holes = [_shift_ring(ring.coords, ox, oy) for ring in poly.interiors]
    return Polygon(_shift_ring(poly.exterior.coords, ox, oy), holes)


def _map_polygon(poly: Polygon, to_3d: np.ndarray) -> Polygon:
    def world(coords):
        out = []
        for c in coords:
            v = to_3d @ np.array([float(c[0]), float(c[1]), 0.0, 1.0], dtype=float)
            out.append((float(v[0]), float(v[1])))
        return out

    holes = [world(ring.coords) for ring in poly.interiors]
    mapped = Polygon(world(poly.exterior.coords), holes)
    if not mapped.is_valid:
        mapped = mapped.buffer(0)
    return mapped


def _section_polygons(mesh: trimesh.Trimesh, z: float, ox: float, oy: float):
    section = mesh.section(plane_origin=[0.0, 0.0, float(z)], plane_normal=[0.0, 0.0, 1.0])
    if section is None:
        return []
    planar, to_3d = section.to_2D()
    to_3d = np.asarray(to_3d, dtype=float)
    geoms = []
    for poly in planar.polygons_full or []:
        if poly.is_empty:
            continue
        mapped = _map_polygon(poly, to_3d)
        if mapped.is_empty:
            continue
        geoms.append(_to_plate(mapped, ox, oy) if mapped.geom_type == "Polygon" else mapped)
    if not geoms:
        return []
    merged = unary_union(geoms)
    if merged.is_empty:
        return []
    if isinstance(merged, Polygon):
        return [merged]
    if isinstance(merged, MultiPolygon):
        return [g for g in merged.geoms if isinstance(g, Polygon) and not g.is_empty]
    return []


def _paint(tile: np.ndarray, ring, pitch_x: float, pitch_y: float, scale: int, y0: int, value: int) -> None:
    rows, cols = [], []
    for x, y in ring:
        cols.append((x / pitch_x) * scale)
        rows.append((y / pitch_y - y0) * scale)
    if len(rows) < 3:
        return
    rr, cc = sk_polygon(rows, cols, shape=tile.shape)
    tile[rr, cc] = value


def _raster(polys, width: int, height: int, pitch_x: float, pitch_y: float, scale: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if not polys:
        return mask
    for y0 in range(0, height, STRIP_ROWS):
        y1 = min(height, y0 + STRIP_ROWS)
        tile = np.zeros(((y1 - y0) * scale, width * scale), dtype=np.uint8)
        for poly in polys:
            _paint(tile, poly.exterior.coords, pitch_x, pitch_y, scale, y0, 255)
            for hole in poly.interiors:
                _paint(tile, hole.coords, pitch_x, pitch_y, scale, y0, 0)
        if scale == 1:
            mask[y0:y1] = tile
        else:
            # Tile pixels are 0 or 255, so the block mean is already a 0–255 coverage.
            block = tile.reshape(y1 - y0, scale, width, scale).sum(axis=(1, 3))
            mask[y0:y1] = np.clip(np.rint(block / (scale * scale)), 0, 255).astype(np.uint8)
    return mask


def _thumb(mask: np.ndarray, path: Path) -> None:
    image = Image.fromarray(mask, mode="L")
    image.thumbnail((160, 160))
    image.save(path, format="PNG")


def slice_mesh(mesh: trimesh.Trimesh, settings: dict, plate: dict, out_path: Path, *,
               aa: bool = False, aa_level: int = 4, thumb_dir: Path | None = None,
               cancel: threading.Event | None = None, progress=None) -> dict:
    """Write `out_path` as a .lumen file. Returns the inspection report."""
    blocked = block_reason(plate, "lumen")
    if blocked:
        raise ResinSliceError(blocked)
    binary = lumen_bin()
    if binary is None:
        raise ResinSliceError("The LUMEN encoder is not built on this machine (tools/zeim-lumen).")
    if len(mesh.faces) > MAX_FACES:
        raise ResinSliceError(f"This mesh has {len(mesh.faces):,} triangles. The slice limit is {MAX_FACES:,}.")
    if not np.isfinite(mesh.vertices).all():
        raise ResinSliceError("The mesh has invalid coordinates.")
    require_sliceable(plate)
    width, height = int(plate["width_px"]), int(plate["height_px"])
    pitch_x = plate["build_width_um"] / width / 1000.0
    pitch_y = plate["build_depth_um"] / height / 1000.0
    plate_w = plate["build_width_um"] / 1000.0
    plate_d = plate["build_depth_um"] / 1000.0
    plate_h = plate["build_height_um"] / 1000.0
    bounds = np.asarray(mesh.bounds, dtype=float)
    size = bounds[1] - bounds[0]
    if size[0] > plate_w + 1e-3 or size[1] > plate_d + 1e-3 or size[2] > plate_h + 1e-3:
        raise ResinSliceError(
            f"The model is {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} mm. "
            f"{plate['name']} is {plate_w:.1f} × {plate_d:.1f} × {plate_h:.1f} mm."
        )
    if size[2] <= 1e-6:
        raise ResinSliceError("The model has no height to slice.")
    layer_mm = float(settings["layer_mm"])
    layers = int(math.ceil(size[2] / layer_mm - 1e-9))
    if layers < 1 or layers > MAX_LAYERS:
        raise ResinSliceError(
            f"This would be {layers} layers at {layer_mm:g} mm. The limit is {MAX_LAYERS}. Use a thicker layer."
        )
    scale = 1
    if aa:
        if aa_level not in AA_LEVELS:
            raise ResinSliceError("Anti-aliasing is 2× or 4× coverage, or off.")
        if width * aa_level > 20_000:
            raise ResinSliceError(
                f"Anti-aliasing at {aa_level}× does not fit this {width} px plate. Slice with anti-aliasing off."
            )
        scale = aa_level
    ox = (plate_w - size[0]) / 2.0 - bounds[0, 0]
    oy = (plate_d - size[1]) / 2.0 - bounds[0, 1]
    layer_um = _um(layer_mm, "Layer height")
    exposure_ms = _ms(settings["exposure_s"], "Exposure")
    bottom_ms = _ms(settings["bottom_exposure_s"], "Bottom exposure")
    lift_um = _um(settings["lift_mm"], "Lift")
    lift_speed = _um(settings["lift_speed_mm_min"], "Lift speed")
    bottom_layers = min(layers, int(settings["bottom_layers"]))
    # TorchC0 has one lift. LUMEN's fast segment stays 0. Retract repeats the lift.
    note = (
        "Lift is one TorchC0 move, stored as the LUMEN slow lift. The fast lift distance is 0. "
        "Retract distance and speed match that lift, because TorchC0 has no separate retract. "
        "Upstream mirror flags are not applied to the pixels."
    )
    pixel_um = plate.get("pixel_um")
    if pixel_um is not None:
        pixel_um = int(pixel_um)
    from app.core import resin as resin_mod
    estimate = resin_mod.estimate(float(size[2]), float(abs(mesh.volume)), settings)
    preview = None
    t_raster = 0.0
    lit, sha = [], []
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zeim-lumen-") as tmp:
        tmp_path = Path(tmp)
        job_path = tmp_path / "job.json"
        preview_path = tmp_path / "preview.png"
        proc = None
        try:
            # Raster the first layer before starting the encoder so a geometry error
            # does not leave a half-written file. The rest streams into the encoder.
            z0 = float(bounds[0, 2])

            def one(index: int):
                if cancel is not None and cancel.is_set():
                    raise ResinSliceCancelled("Slice cancelled.")
                z = z0 + (index + 0.5) * layer_mm
                polys = _section_polygons(mesh, z, ox, oy)
                return _raster(polys, width, height, pitch_x, pitch_y, scale)

            t0 = time.perf_counter()
            first = one(0)
            t_raster += time.perf_counter() - t0
            if progress:
                progress(1, layers, "raster")
            # Preview is a real PNG of layer 0, downscaled. The crate checks the PNG signature.
            thumb0 = Image.fromarray(first, mode="L")
            thumb0.thumbnail((200, 125))
            thumb0.save(preview_path, format="PNG")
            job = {
                "width": width,
                "height": height,
                "layer_count": layers,
                "build_width_um": int(plate["build_width_um"]),
                "build_depth_um": int(plate["build_depth_um"]),
                "build_height_um": int(plate["build_height_um"]),
                "layer_height_um": layer_um,
                "normal_exposure_ms": exposure_ms,
                "bottom_exposure_ms": bottom_ms,
                "bottom_layer_count": bottom_layers,
                "transition_layer_count": 0,
                "lift_slow_distance_um": lift_um,
                "lift_slow_speed_um_min": lift_speed,
                "retract_fast_distance_um": lift_um,
                "retract_fast_speed_um_min": lift_speed,
                "printer_name": plate["name"],
                "manufacturer": plate.get("manufacturer") or "ZEIM",
                "pixel_size_um": pixel_um,
                "aa_enabled": bool(aa),
                "aa_level": scale,
                "material_name": settings.get("material") or "standard",
                "material_density_g_ml": settings.get("density_g_ml"),
                "estimated_print_time_sec": int(estimate["print_seconds"]),
                "estimated_resin_volume_ml": float(estimate["resin_ml"]),
                "preview_png": str(preview_path),
                "profile_note": note,
            }
            job_path.write_text(json.dumps(job))
            proc = subprocess.Popen(
                [str(binary), "encode", "--job", str(job_path), "--out", str(out_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            err: list[bytes] = []

            def _drain():
                err.append(proc.stderr.read() if proc.stderr is not None else b"")

            drainer = threading.Thread(target=_drain, daemon=True)
            drainer.start()

            def consume(index: int, mask: np.ndarray):
                digest = hashlib.sha256(mask.tobytes()).hexdigest()
                lit.append(int(np.count_nonzero(mask)))
                sha.append(digest)
                if thumb_dir is not None:
                    _thumb(mask, Path(thumb_dir) / f"{index:04d}.png")
                try:
                    proc.stdin.write(np.ascontiguousarray(mask).tobytes())
                except BrokenPipeError as exc:
                    raise ResinSliceError("The LUMEN encoder stopped while writing a layer.") from exc

            consume(0, first)
            for index in range(1, layers):
                t1 = time.perf_counter()
                mask = one(index)
                t_raster += time.perf_counter() - t1
                consume(index, mask)
                if progress:
                    progress(index + 1, layers, "raster")
            proc.stdin.close()
            deadline = time.monotonic() + 240
            while proc.poll() is None:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    raise ResinSliceCancelled("Slice cancelled.")
                if time.monotonic() > deadline:
                    proc.kill()
                    raise ResinSliceError("Encoding the .lumen file took too long.")
                time.sleep(0.05)
            code = proc.returncode
            drainer.join(timeout=2)
            stderr = b"".join(err).decode("utf-8", "replace")
            if code != 0:
                tail = stderr.strip().splitlines()[-1] if stderr.strip() else f"exit {code}"
                raise ResinSliceError(f"LUMEN encoder failed: {tail}")
        except ResinSliceCancelled:
            if proc is not None and proc.poll() is None:
                proc.kill()
            if out_path.exists():
                out_path.unlink()
            raise
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
    data = out_path.read_bytes()
    if data[:2] == b"PK" or data[:4] != b"LUMN" or data[-8:-4] != b"LEND":
        raise ResinSliceError("The encoder did not write a LUMEN file.")
    try:
        head = read_head(data)
    except LumenHeadError as exc:
        raise ResinSliceError(str(exc)) from exc
    if head["layers"] != layers or head["width"] != width or head["layer_height_um"] != layer_um:
        raise ResinSliceError("The written HEAD does not match the slice.")
    return {
        "format": "lumen",
        "format_version": "1.0",
        "extension": ".lumen",
        "media_type": "application/vnd.openresin.lumen",
        "bytes": len(data),
        "layers": layers,
        "width_px": width,
        "height_px": height,
        "layer_height_um": layer_um,
        "normal_exposure_ms": exposure_ms,
        "bottom_exposure_ms": bottom_ms,
        "bottom_layer_count": bottom_layers,
        "transition_layer_count": 0,
        "lift_slow_distance_um": lift_um,
        "lift_slow_speed_um_min": lift_speed,
        "retract_fast_distance_um": lift_um,
        "retract_fast_speed_um_min": lift_speed,
        "anti_aliasing": bool(aa),
        "aa_level": scale,
        "plate_id": plate["id"],
        "plate_name": plate["name"],
        "native_format": plate.get("native_format") or "",
        "native_format_written": False,
        "hardware_tested": False,
        "mirror_applied": False,
        "mirror_x": bool(plate.get("mirror_x")),
        "mirror_y": bool(plate.get("mirror_y")),
        "lit": lit,
        "sha256": sha,
        "head": head,
        "seconds_raster": round(t_raster, 4),
        "estimate": estimate,
        "note": note,
        "machine_file": True,
        "machine_file_kind": "lumen",
    }
