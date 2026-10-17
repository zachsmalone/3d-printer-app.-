# Review guide for the partner (Copilot) translation

This branch (`PerplexCopilot`) holds Perplexity's ZEIMCad work for review and merge
with the partner's independent translation of the same target. Review against the
upstream C++, not against style or self-written tests.

## The shared reference (use this, not "latest")

- Target: SolveSpace, pinned revision `8ef723e145fbe3f1d19e74667c59df795d9d3479`
  (https://github.com/solvespace/solvespace). Clone and check out that SHA before
  comparing either translation.
- Translation method: source-assisted (upstream C++ is public). Binary
  decompilation is neither needed nor used.

## What is on this branch

1. `zeimcad/` - the Rust translation so far (GPL-3.0-or-later):
   - `src/dsc.rs`: Vector, Vector4, Point2d, Quaternion - original naming kept
     (`with_magnitude` = `WithMagnitude`) and every function cites its upstream
     file. Implemented/omitted inventory is in `zeimcad/README.md`.
   - `src/util.rs`: Mat4 (MakeMatrix/MultMatrix), BandedMatrix::Solve.
   - `tests/dsc_math.rs`: 18 tests incl. parity checks.
   - `ZEIMCad` CLI: self-checking binary; cross-compiles to `ZEIMCad.exe`
     (`cargo build --release --target x86_64-pc-windows-gnu`).
2. `docs/specs/cad-import-edit-spec.md` - the ZEIM-side feature plan that makes
   imported files editable (the differentiator this project exists for).

## How to review a translated function (the fidelity bar)

For each function, compare against the pinned C++ and check:

1. Same math, same branch conditions, same special cases - no "improvements"
   (e.g. `Point2d::Angle` must wrap into [0, 2*pi); `Point2d::WithMagnitude`
   returns `{v, 0}` for a zero vector; `Vector4::PerspectiveProject` is plain
   division with no zero-guard).
2. Same tolerance constants (`LENGTH_EPS = 1e-6`, `VERY_POSITIVE = 1e10`).
3. Same failure modes: degenerate inputs (zero vectors, parallel lines, skew
   lines, coincident points) must behave exactly like upstream, including
   returning inf/nan where upstream does.
4. A test that pins the behavior, ideally one that could be run against a C++
   reference harness on the pinned revision.

Known verified-on-this-branch fixes after review: `Point2d::Angle`,
`Point2d::WithMagnitude`, `Vector4::PerspectiveProject`, `AtIntersectionOfLines`
(removed an invented degenerate-line branch), literal
`Point2d::DistanceToLine`/`DistanceToLineSigned`/`Equals`.

## Merge rules (agreed with the founder)

- Compare both translations function-by-function against the pinned revision;
  the one that matches upstream more literally wins that module. Do not merge on
   the strength of either side's self-written tests alone.
- Everything in `zeimcad/` stays GPL-3.0-or-later (it is a SolveSpace derivative);
  the ZEIM web app is separate software.
- Suggested next module: `expr` (symbolic algebra), then `sketch`. Before more
  translation volume, build the C++ reference harness (same inputs to upstream
  and Rust, incl. degenerate inputs and tolerance boundaries) - that harness is
  also the referee for the merge decisions above.

## Reproducing the build

```sh
cd zeimcad
cargo test                       # 18 tests
cargo build --release
./target/release/ZEIMCad --self-check
cargo build --release --target x86_64-pc-windows-gnu   # ZEIMCad.exe
```

Windows execution is not yet verified on a Windows host - if you have one, run
`ZEIMCad.exe --version` and `ZEIMCad.exe --self-check` and report the result.
