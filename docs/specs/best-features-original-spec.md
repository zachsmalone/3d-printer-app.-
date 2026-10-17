# Best features, made original: Shapr3D, Tinkercad, Nomad Sculpt, FreeCAD

## Goal and guardrails

Take the standout features of the CADs makers actually use and build them in ZEIM as
**original implementations on our mesh-first architecture**. Policy: we study how a feature
behaves, then write our own code, our own names, our own UI text and assets. We never copy
code, text, icons or assets from any product; GPL-licensed code (the SolveSpace port) stays
in the separate ZEIMCad project and never enters this app; and we do not decompile anything.
This is a practical original-implementation policy, not a legal opinion.

## What each tool is best at, and what we take

### Shapr3D - direct, dimensioned editing on faces
Best-in-class: tap a face, pull it, type a dimension. Sketches drive extrudes; everything
stays editable. Verified behavior (official docs, checked 2026-10-17):
- STEP/IGS/X_T imports arrive as **fully editable solids** - "become fully editable solids"
  (https://shapr3d.com/blog/import-files-into-shapr3d).
- STL/OBJ mesh imports are **not face-editable**: "can only be scaled, positioned, and
  oriented using the Transform tool" and are "not editable via Direct Modeling"
  (https://shapr3d.com/blog/import-files-into-shapr3d,
  https://help.shapr3d.com/en/articles/7701203-move-scale-rotate-and-mirror-bodies).
- Sketch-driven modeling: "Add a 2D sketch" then extrude
  (https://shapr3d.com/how-tos/sketch-modeling/step-2-draw-the-sketch).

**ZEIM takes:** the face-pick-then-dimension interaction, applied to meshes - which is
exactly the gap Shapr3D leaves for 3D printing users. `on_face` (shipped, see below) is
the first move: pick a detected plane, add a boss or cut a hole/pocket with a typed
diameter and depth. Next: drag a detected face to extrude it with a typed dimension.

### Tinkercad - primitives, combining, alignment
Best-in-class: a box of primitives, drag/combine, holes as shapes subtracted, snap/align
tools, and the smallest possible learning curve (https://tinkercad.com - official feature
tour, checked 2026-10-17). Weakness we already knew from research: complex imported meshes
degrade.

**ZEIM takes:** the primitive workbench feel (already have booleans/primitives in the op
registry), plus Tinkercad's alignment helpers as mesh ops: align-to-face, snap-to-bed,
evenly-space. Our import pipeline is the differentiator Tinkercad lacks.

### Nomad Sculpt - sculpting on meshes
Best-in-class: clay/crease/flatten/move brushes, voxel remeshing, symmetry, decimation
(official manual: https://nomadsculpt.com/manual/, checked 2026-10-17).

**ZEIM takes (later):** sculpt-lite - a small brush set (flatten, inflate, smooth) over
the existing mesh, symmetry, and a decimate-then-detail workflow that fits printing.
This is the biggest new subsystem; schedule after the feature tree.

### FreeCAD - parametric sketches and constraints
Best-in-class: constraint-driven sketches that drive solids; parameters everywhere
(https://freecad.org - official docs, checked 2026-10-17).

**ZEIM takes (later):** the constraint solver as a long-term item - either our own or the
separate GPL ZEIMCad tool as an isolated service (same isolation pattern as the PrusaSlicer
CLI). Before that, cheap wins: named dimensions on ops (already how our ops store params)
and a spreadsheet-style parameter panel that edits op params directly.

## Shipped in this change: `on_face` (backend; UI pending)

A Shapr3D-style face edit, mesh-native and original. **Scope note:** this places dimensioned
boxes/cylinders on a detected plane; it does not yet extrude an existing face, and the anchor
is a fixed workplane (a stored normal + point), not an associative face reference - a later
translate/rotate of the model does not move it. No UI yet; it needs the feature-tree panel
and a face-pick gesture to be usable.

- `POST /api/edit/{bid}/op` with `op: "on_face"`: place a dimensioned box or cylinder on a
  picked face; `mode: add` (boss/rib) or `mode: cut` (hole/pocket, with a small skim above
  the plane so the boolean is clean).
- Anchored to the face's **plane** (normal + point from the feature detector), never to
  triangle ids - so it survives retriangulation and replays deterministically; undo/redo
  come free from the op history.
- Off-model spots are refused with a clear error instead of silently doing nothing.
- Tests: `tests/test_on_face.py` (11 cases: volumes, through-cuts, pockets, malformed plane
  vectors, detached-add and empty-cut refusal over holes, plane-anchor survival across a
  verified retriangulation, full API flow with undo/redo and an export round trip).
- Suite status: all targeted tests pass; the wider suite shows only the pre-existing
  browser (playwright) failures; test_litho_shapes.py cannot run in the current sandbox
  (memory limit - it passed on the dev machine and is untouched by this change).

## Priority order

1. Face-tree panel (Copilot, in progress) - makes detected features pickable in the UI.
2. Drag-to-extrude a picked face with a typed dimension (extends on_face).
3. Tinkercad-style align/snap helpers as ops.
4. Sketch profiles: polyline/rect/circle on a picked plane -> extrude add/cut (reuses on_face's
   plane anchoring).
5. Sculpt-lite brush set with symmetry.
6. Constraint solving (long-term; separate project or own solver).
