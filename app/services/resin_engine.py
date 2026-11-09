"""Choose the separate program that writes a TorchC0 printer file.

DragonFruit is the default for `.ctb` and `.nanodlp`. `.goo` stays on mslicer.
`ZEIM_RESIN_ENGINE=mslicer` forces mslicer. If DragonFruit is selected and fails,
and the plate does not need a catalog mirror, the same job is sliced again with
mslicer. A mirrored plate is not sent to mslicer, because that program would
leave the flip out.
"""
from __future__ import annotations

import threading
from pathlib import Path

from app.core import resin_slice
from app.services import dragonfruit_engine, mslicer_engine


def slice_printer_file(
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
    kind = mslicer_engine.output_format(fmt)
    requested = resin_slice.configured_resin_engine()
    if resin_slice.writer_for(kind) != "dragonfruit":
        report = mslicer_engine.slice_file(
            stl, out, plate, settings, kind, aa=aa, cancel=cancel, placed=placed,
        )
        if kind == "goo" or requested == "mslicer":
            report["engine_requested"] = "mslicer"
            report["engine_fallback"] = ""
        else:
            report["engine_requested"] = "dragonfruit"
            report["engine_fallback"] = "DragonFruit CLI is not installed."
        return report
    try:
        return dragonfruit_engine.slice_file(
            stl, out, plate, settings, kind, aa=aa, aa_level=aa_level,
            cancel=cancel, placed=placed,
        )
    except resin_slice.ResinSliceCancelled:
        raise
    except dragonfruit_engine.DragonFruitError as exc:
        if plate.get("kind") != "inspection" and (
            plate.get("mirror_x") is True or plate.get("mirror_y") is True
        ):
            raise
        report = mslicer_engine.slice_file(
            stl, out, plate, settings, kind, aa=aa, cancel=cancel, placed=placed,
        )
        report["engine_requested"] = "dragonfruit"
        report["engine_fallback"] = str(exc)[:300]
        report["note"] = (
            "DragonFruit failed and TorchC0 sliced this file with mslicer instead. "
            + str(report.get("note") or "")
        )
        return report
