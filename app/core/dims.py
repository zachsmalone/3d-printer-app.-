"""Named dimensions: a project keeps {name: number}; a step's numeric parameter may be the string "$name".

The stored step keeps the "$name" text; the real number is substituted every time the history is replayed, so changing a
dimension updates every step that uses it. Text and plate-editor steps are never substituted.
"""
from __future__ import annotations

import math
import re

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
MAX_DIMS = 50
LIMIT = 10_000.0
SKIP_OPS = ("text", "plate")


class DimError(ValueError):
    pass


def check_dims(dims) -> dict:
    if not isinstance(dims, dict):
        raise DimError("dimensions must be an object of name: number")
    if len(dims) > MAX_DIMS:
        raise DimError(f"at most {MAX_DIMS} named dimensions")
    out = {}
    for k, v in dims.items():
        if not isinstance(k, str) or not NAME_RE.match(k):
            raise DimError(f"'{k}' is not a valid name (letters, digits, underscore; max 32; not starting with a digit)")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > LIMIT:
            raise DimError(f"'{k}' must be a number between -{LIMIT:g} and {LIMIT:g}")
        out[k] = float(v)
    return out


def used_names(params) -> set[str]:
    found: set[str] = set()

    def walk(x):
        if isinstance(x, str) and x.startswith("$"):
            found.add(x[1:])
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(params)
    return found


def resolve(op: str, params: dict, dims: dict | None):
    """Return params with every "$name" replaced by its number. Unknown names raise DimError."""
    if op in SKIP_OPS:
        return params
    dims = dims or {}

    def sub(x):
        if isinstance(x, str) and x.startswith("$"):
            name = x[1:]
            if name not in dims:
                raise DimError(f"unknown dimension '${name}'")
            return dims[name]
        if isinstance(x, dict):
            return {k: sub(v) for k, v in x.items()}
        if isinstance(x, list):
            return [sub(v) for v in x]
        return x
    return sub(params)
