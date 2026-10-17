# ZEIMCad

A Rust translation of [SolveSpace](https://github.com/solvespace/solvespace), the
parametric 2D/3D CAD. Planned ZEIM extension: **imported files become editable as
if they were created organically** (an imported mesh as the base of a living
feature tree). This is a planned feature, not an implemented capability today.

## Provenance and license

- Upstream: SolveSpace, Copyright 2008-2013 Jonathan Westhues and contributors.
- Reference revision: `8ef723e145fbe3f1d19e74667c59df795d9d3479` (all translation
  and comparison work targets this pinned commit).
- Upstream license: GPL-3.0-or-later. This translation is a derivative work and is
  licensed GPL-3.0-or-later (see LICENSE). Distributing ZEIMCad.exe requires the
  GPL-compliant corresponding source for that exact build, including build
  instructions - this repository is that source.
- Translation method: source-assisted (the upstream C++ source is public), not
  binary decompilation. Every translated function keeps the original naming
  (`Vector::WithMagnitude` -> `Vector::with_magnitude`) and cites its upstream
  file, so it can be audited against its C++ counterpart.

## Status: initial partial port

Translated so far, from `src/dsc.h` + `src/util.cpp`:

- `Vector` - implemented: From, Element, Equals, EqualsExactly, Plus, Minus,
  Negated, Cross, DirectionCosineWith, Dot, Normal, RotatedAbout (both forms),
  DotInToCsys, ScaleOutOfCsys, InPerspective, DistanceToLine, DistanceToPlane,
  OnLineSegment, ClosestPointOnLine, Magnitude, MagSquared, WithMagnitude,
  ScaledBy, Project2d, ProjectXy, Project4d, DivProjected, ClosestOrtho,
  MakeMaxMin, ClampWithin, OutsideAndNotOn, BoundingBoxesDisjoint,
  AtIntersectionOfPlanes (2 planes), ClosestPointBetweenLines,
  AtIntersectionOfLines, AtIntersectionOfPlaneAndLine.
  Omitted (not yet translated): BoundingBoxIntersectsLine, the 3-plane
  intersection, ProjectInto/ProjectVectorInto and the hParam/SK-dependent
  constructors (they need the sketch/solver modules).
- `Vector4`, `Point2d`, `Quaternion` - complete method sets.
- `Mat4` (MakeMatrix/MultMatrix), `BandedMatrix::Solve`,
  `LENGTH_EPS`/`VERY_POSITIVE` constants.
- Self-checking `ZEIMCad` CLI binary.

Not yet translated (the remaining ~55k lines of core): the symbolic expression
system (`expr`), the sketch data model (`sketch.h`), the constraint solver
(`system`, `constrainteq`), mesh/boolean/polygon (`mesh`, `polygon`), file
formats and mesh import (`file`, `importmesh`), platform/render/UI. There is no
CAD interface, no file import, and no visual-parity evidence yet.

## Verification status

- 18 Rust tests, all passing, including parity checks (rotation matrix vs
  quaternion, line/plane intersections, banded solver residuals, literal
  translations of `Point2d::DistanceToLine`/`DistanceToLineSigned`/`Equals`).
- `ZEIMCad.exe` is cross-compiled for `x86_64-pc-windows-gnu`; PE format and
  architecture verified with binutils. **Windows execution is not yet verified**
  (needs a Windows host or CI job running `ZEIMCad.exe --version` and
  `--self-check`).
- Parity is currently established against the upstream C++ source by reading and
  literal translation, not yet by a differential harness. Next verification step:
  a C++ reference harness on the pinned revision that feeds identical inputs to
  upstream and Rust, including degenerate inputs and tolerance boundaries.

## Build and test

```sh
cargo test
cargo build --release
./target/release/ZEIMCad --self-check
```

Windows binary (ZEIMCad.exe):

```sh
cargo build --release --target x86_64-pc-windows-gnu
# produces target/x86_64-pc-windows-gnu/release/ZEIMCad.exe
```

## Roadmap

Bottom-up module order: `expr` -> `sketch` -> `system`/`constrainteq` ->
`mesh`/`polygon` -> `importmesh` -> platform/render/UI. A parallel Copilot
translation exists; both are compared against the same pinned upstream revision
and shared fixtures, and the more faithful implementation wins module by module.
