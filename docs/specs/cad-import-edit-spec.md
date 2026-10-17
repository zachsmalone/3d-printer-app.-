# CAD: import-and-edit specification

## Goal

An editor that stands next to Shapr3D in capability for the things a maker actually does — sketch,
extrude, cut, fillet, text, holes, patterns — with one thing Shapr3D does not offer: **any file you
import stays fully editable**. In Shapr3D, geometry made elsewhere comes in as a dead reference you
can only position; in ZEIM, an imported STL/OBJ/3MF becomes the base of a living feature tree that
the user keeps editing.

## Honest scope statement

STL/OBJ are meshes, not parametric B-rep. ZEIM does not pretend to convert them into Shapr3D-style
parametric solids. The approach here is **parametric-over-mesh**: the imported mesh is an immutable
base; every feature the user adds (sketch extrude, hole, text, fillet, boolean, transform) is stored
as an editable step in a feature tree and replayed non-destructively on top of that base. That is
exactly the gap users hit in Shapr3D — "I made it elsewhere, now I can't add to it" — and it is
achievable with the architecture already in this repo.

What this is not (yet): full B-rep CAD, STEP import with parametric history, and exact analytic
fillets on arbitrary mesh edges. Those are long-term items, listed at the end, not promised.

## What exists today (foundation)

The editor is already a non-destructive op-history replay system:

- `app/services/editproj.py`: `add_op` / `undo` / `redo` / `goto`, `mesh_at(bid, head)` rebuilds any
  state from the original file + op list; the original is always kept.
- `app/core/meshedit.py`: op registry (translate/rotate/scale/mirror, boolean union/difference/
  intersection via manifold3d, cut/split, hollow, base/brim, text emboss, repair, simplify,
  smart-split, plate).
- Multi-step parametrization already proven by lithophane/relief generation.

## Phase 1: the editable feature tree (the differentiator)

- A visible panel listing every step (import base + each op) with its parameters.
- Click any past step: edit its parameters, and everything after it replays automatically.
- Delete a step, reorder adjacent steps (with a warning when replay changes the result).
- Branching is out of scope; a linear tree with undo/redo jump points is enough.
- Effort: mostly UI over the existing replay engine; the engine already guarantees replay safety
  (`_replay_safe`).

## Phase 2: sketch → solid

- Sketch on a plane: the bed, a face of the imported mesh, or an offset/work plane.
- Entities: line, polyline, circle, arc, rectangle, polygon, text (reuse the existing text engine).
- Constraints (v1): snap to grid/endpoints/midpoints, horizontal/vertical, parallel, concentric.
  Full constraint solving is later; snapping + numeric input covers most maker sketches.
- Extrude (add or subtract), revolve, and sweep along a path — each becomes a boolean op against the
  imported base via manifold3d.
- Sketches are stored as steps in the tree, so an imported file plus a sketch is re-editable later.

## Phase 3: engineering features

- Hole feature: through / blind / countersink / counterbore, placed on a face or a sketch point.
- Linear and circular patterns (array of any feature).
- Fillet/chamfer v1: mesh approximation (offset + rebuild), clearly labelled as approximate; exact
  analytic fillets need B-rep (long-term).
- Measure and units (mm/cm/in already exist), snap-to-face/edge/vertex.

## Phase 4: import fidelity

- 3MF: keep colours/materials per object through edit and export (today multi-colour is merged away).
- OBJ with materials; STL unchanged.
- Larger meshes: keep the >150k-triangle simplified preview, full-resolution export.

## Long-term (explicitly not promised)

- STEP import via a B-rep kernel, exact fillets/chamfers, constraint solving, assemblies.

## Test plan

- Every phase: property tests that a feature tree replayed N times is byte-identical; deleting and
  re-adding a mid-chain step gives the same mesh as doing it in that order from scratch; every
  feature works on the same fixture set (clean mesh, holed mesh, >150k-triangle mesh, imported 3MF).
- UI tests follow the existing `tests/ui_*.py` pattern.
