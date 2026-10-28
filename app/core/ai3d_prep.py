"""Photo prep before TripoSR.

The steps live in workers/ai3d/prep.py so the worker image and the app share one implementation.
The main ZEIM image does not copy the rest of workers/. Dockerfile copies this one file to
/app/workers/ai3d/prep.py, which is where this loader looks (parents[2] of this module).
Import runs at startup even when ZEIM_2D3D_ENABLED=0, so the file has to be in the image.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "workers" / "ai3d" / "prep.py"
_spec = importlib.util.spec_from_file_location("zeim_ai3d_prep", _PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load photo prep from {_PATH}")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

prepare_image = _mod.prepare_image
