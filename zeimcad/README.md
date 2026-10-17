# ZEIMCad

A Rust translation of [SolveSpace](https://github.com/solvespace/solvespace), the
parametric 2D/3D CAD, with a ZEIM-specific extension: **imported files are editable
as if they were created organically** (an imported mesh becomes the base of a
living feature tree).

## Provenance and license

- Upstream: SolveSpace, Copyright 2008-2013 Jonathan Westhues and contributors.
- Upstream license: GPL-3.0-or-later. This translation is a derivative work and is
  licensed GPL-3.0-or-later (see LICENSE).
- The ZEIM web application is separate software and is not derived from this code.
- Translation method: source-assisted (the upstream C++ source is public), not
  binary decompilation. Every translated function keeps the original naming
  (`Vector::WithMagnitude` -> `Vector::with_magnitude`) so it can be audited
  against its C++ counterpart.

## Status

Translated so far (from `src/dsc.h` + `src/util.cpp`):
- `Vector`, `Vector4`, `Point2d`, `Quaternion` - the complete math core
- `Mat4` (MakeMatrix/MultMatrix) and `BandedMatrix::Solve`
- Self-checking `zeimcad` binary (grows each iteration toward the full app)

Next modules, bottom-up: `expr` (symbolic algebra) -> `sketch` (data model) ->
`system`/`constrainteq` (solver) -> `mesh`/`polygon` -> `importmesh` ->
platform/render/UI.

## Build and test

```sh
cargo test
cargo build --release
./target/release/zeimcad --self-check
```

Windows binary (ZEIMCad.exe):

```sh
cargo build --release --target x86_64-pc-windows-gnu
# produces target/x86_64-pc-windows-gnu/release/zeimcad.exe
```
