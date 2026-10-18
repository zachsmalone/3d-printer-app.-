"""Parts builder: primitive-based composition (the best of Tinkercad's model), made parametric
by replaying it as an editable step on ZEIM's existing history (the best of Shapr3D's editing
model) — original code throughout; only public formats and conventions are used.

A RECIPE is an ordered list of parts. Each part is a primitive (box/cylinder/sphere/cone/
tube/torus) with explicit dimensions, a position and a rotation, and a ROLE:
  * "solid" — unioned onto the running shape;
  * "hole"  — subtracted from the running shape.
Order matters, exactly like a boolean history. The recipe is stored as step 1 of the project's
ops list, so every downstream mechanism works unchanged: editing the recipe re-replays the
step (parametric recomposition that PRESERVES any manual ops added after it), undo/redo,
named dimensions ($name in any numeric field), the safety checks, exports, slicing, sharing.
"""
from __future__ import annotations

import numpy as np
import trimesh

MAX_PARTS = 48          # compose cost is boolean count; keep it bounded
MIN_MM = 0.01           # same bounds as the editor's own primitive tools
MAX_MM = 5000.0
MAX_POS = 2500.0        # mm from origin — far beyond any print bed, but bounded
KINDS = ("box", "cylinder", "sphere", "cone", "tube", "torus")
ROLES = ("solid", "hole")


class RecipeError(ValueError):
    pass


def _num(v, name: str, lo: float = MIN_MM, hi: float = MAX_MM) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise RecipeError(f"{name} must be a number.")
    if not (lo <= v <= hi) or v != v or v in (float("inf"), float("-inf")):
        raise RecipeError(f"{name} must be {lo}..{hi}.")
    return v


def _vec3(v, name: str, lo: float, hi: float) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise RecipeError(f"{name} must be [x, y, z].")
    return [_num(x, f"{name}[{i}]", lo, hi) for i, x in enumerate(v)]


# ------------------------------------------------------------------ validation

def check_recipe(recipe) -> dict:
    """Validate + normalise a recipe. Raises RecipeError. No free-text fields exist in a
    recipe (kinds/roles/numbers only), so nothing here needs the language filter."""
    if not isinstance(recipe, dict):
        raise RecipeError("A recipe must be an object with a 'parts' list.")
    parts = recipe.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_PARTS:
        raise RecipeError(f"A recipe needs 1..{MAX_PARTS} parts.")
    out = []
    for i, p in enumerate(parts):
        if not isinstance(p, dict):
            raise RecipeError(f"Part {i + 1} must be an object.")
        kind = p.get("kind")
        if kind not in KINDS:
            raise RecipeError(f"Part {i + 1}: kind must be one of {' | '.join(KINDS)}.")
        role = p.get("role", "solid")
        if role not in ROLES:
            raise RecipeError(f"Part {i + 1}: role must be {' | '.join(ROLES)}.")
        if i == 0 and role == "hole":
            raise RecipeError("The first part must be a solid — there is nothing to subtract from yet.")
        d = _dims(kind, p.get("dims") or {}, f"Part {i + 1}")
        pos = _vec3(p.get("position") or [0, 0, 0], f"Part {i + 1} position", -MAX_POS, MAX_POS)
        rot = _vec3(p.get("rotation") or [0, 0, 0], f"Part {i + 1} rotation", -360.0, 360.0)
        out.append({"kind": kind, "role": role, "dims": d, "position": pos, "rotation": rot})
    return {"parts": out}


def _dims(kind: str, d: dict, where: str) -> dict:
    if not isinstance(d, dict):
        raise RecipeError(f"{where}: dims must be an object.")
    if kind == "box":
        return {"size": _vec3(d.get("size") or [20, 20, 20], f"{where} size", MIN_MM, MAX_MM)}
    if kind in ("cylinder", "cone"):
        return {"diameter": _num(d.get("diameter", 20), f"{where} diameter"),
                "height": _num(d.get("height", 20), f"{where} height")}
    if kind == "sphere":
        return {"diameter": _num(d.get("diameter", 20), f"{where} diameter")}
    if kind == "tube":
        out = {"outer": _num(d.get("outer", 24), f"{where} outer diameter"),
               "inner": _num(d.get("inner", 16), f"{where} inner diameter"),
               "height": _num(d.get("height", 20), f"{where} height")}
        if out["inner"] >= out["outer"]:
            raise RecipeError(f"{where}: tube inner diameter must be smaller than outer.")
        return out
    if kind == "torus":
        out = {"outer": _num(d.get("outer", 30), f"{where} outer diameter"),
               "tube": _num(d.get("tube", 6), f"{where} tube diameter")}
        if out["tube"] >= out["outer"]:
            raise RecipeError(f"{where}: torus tube diameter must be smaller than outer.")
        return out
    raise RecipeError(f"{where}: unknown kind")      # unreachable


# ------------------------------------------------------------------ geometry

def _part_mesh(part: dict) -> trimesh.Trimesh:
    k, d = part["kind"], part["dims"]
    if k == "box":
        m = trimesh.creation.box(extents=d["size"])
    elif k == "cylinder":
        m = trimesh.creation.cylinder(radius=d["diameter"] / 2, height=d["height"], sections=64)
    elif k == "sphere":
        m = trimesh.creation.uv_sphere(radius=d["diameter"] / 2, count=[48, 32])
    elif k == "cone":
        m = trimesh.creation.cone(radius=d["diameter"] / 2, height=d["height"], sections=64)
    elif k == "tube":
        if d["inner"] >= d["outer"]:
            raise RecipeError("Tube: inner diameter must be smaller than outer.")
        m = trimesh.creation.annulus(r_min=d["inner"] / 2, r_max=d["outer"] / 2, height=d["height"], sections=64)
    elif k == "torus":
        if d["tube"] >= d["outer"]:
            raise RecipeError("Torus: tube diameter must be smaller than outer diameter.")
        m = trimesh.creation.torus(major_radius=(d["outer"] - d["tube"]) / 2,
                                   minor_radius=d["tube"] / 2,
                                   major_sections=96, minor_sections=32)
    else:
        raise RecipeError(f"unknown kind {k}")        # unreachable
    T = np.eye(4)
    T[:3, :3] = trimesh.transformations.euler_matrix(
        *np.radians(part["rotation"]), axes="sxyz")[:3, :3]
    T[:3, 3] = part["position"]
    m.apply_transform(T)
    return m


def compose(recipe: dict) -> tuple[trimesh.Trimesh, dict]:
    """Build the mesh from a validated recipe. Solids union in order, holes subtract in
    order — a boolean history, exactly like the step list it becomes part of."""
    recipe = check_recipe(recipe)
    running = None
    for i, p in enumerate(recipe["parts"]):
        mesh = _part_mesh(p)
        if running is None:
            running = mesh                      # first part (always solid — checked)
            continue
        try:
            op = trimesh.boolean.union if p["role"] == "solid" else trimesh.boolean.difference
            running = op([running, mesh], engine="manifold")
        except Exception as e:
            raise RecipeError(f"Part {i + 1} ({p['kind']}): boolean failed ({e}).")
        if running is None or len(running.faces) == 0:
            raise RecipeError(f"Part {i + 1}: the result is empty (nothing left to print).")
    if running is None:
        raise RecipeError("empty recipe")
    return running, {"parts": len(recipe["parts"]),
                    "solids": sum(1 for p in recipe["parts"] if p["role"] == "solid"),
                    "holes": sum(1 for p in recipe["parts"] if p["role"] == "hole")}


def op_parts(m: trimesh.Trimesh, params: dict) -> tuple[trimesh.Trimesh, dict]:
    """The 'parts' history op: replace the mesh with the recipe's composition. The input mesh
    is deliberately unused — the recipe is the source of truth (the base mesh it came from is
    just the first composition, kept so the project has a real file)."""
    del m
    out, rep = compose(params or {})
    return out, rep
