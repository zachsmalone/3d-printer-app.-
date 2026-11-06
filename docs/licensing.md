# Licensing notes

> This is the ZEIM team's reading of the licences involved. It is not legal advice.

## PrusaSlicer (AGPL-3.0) — decision 2026-10-13 (Zach)
ZEIM follows the same model as MakerWorld, which slices in the cloud with Bambu Studio (AGPL) while keeping its own platform private.

- **ZEIM's own code stays private.** ZEIM does not publish its own source code, and the repository's visibility is not changed.
- **PrusaSlicer is used unmodified, as a separate program.** ZEIM runs the stock `prusa-slicer` command-line program in its own process and reads the files it writes. ZEIM never imports, links or embeds PrusaSlicer code.
- **ZEIM shares only PrusaSlicer's own source.** The credits page names PrusaSlicer, its licence (AGPL-3.0), that it is unmodified, and links to its upstream source at https://github.com/prusa3d/PrusaSlicer.

### Rule for everyone working on ZEIM
**Nobody may modify, patch, fork-and-ship, or link PrusaSlicer's code into ZEIM.** No copying its source files into this repo, no Python/C bindings to its libraries, no patched builds. PrusaSlicer is only ever called as a separate, unmodified program through its command line. If a change would need any of that, stop and ask Zach first; it would change these licence obligations.

## Photo check (NudeNet 320n)

Uploaded photos are checked in-process. The dependency is the PyPI package `nudenet` 3.4.2, whose package metadata says MIT, plus `onnxruntime` 1.23.2 (MIT). The weights are the bundled `320n.onnx` file (about 12 MB), the NudeNet v3.4 detector based on Ultralytics YOLOv8n. The NudeNet GitHub repository is AGPL-3.0, and YOLOv8 is AGPL-3.0. ZEIM does not copy that Python or the YOLOv8 training code into this repo. The check runs on the CPU. Photos are not sent to another service for it.

This note is not legal advice.

## Copyright (DMCA) takedowns
The Terms page has a copyright takedown section with a placeholder contact.
TODO: register a DMCA designated agent with the US Copyright Office (small fee; needs Zach's OK before paying), then put the agent's contact in `static/terms.html#copyright`.

## Legal pages
Decision 2026-10-12 (Zach): ZEIM launches with no lawyers. Terms, Privacy and Rules are plain-words pages based on common free templates. Keep every statement true (18+ only, free, no payments, photo moderation, users can delete their own stuff) and do not add compliance claims.

## CAD workspace (2026-10-18)
The CAD workspace (`static/cad.html`, `static/cad.js`, `static/cad.css`, `app/core/sketch.py`, `app/core/cadops.py`, `app/api/cad.py`) is original ZEIM code.

- **Inspiration only.** Its layout ideas (tool rail with shortcuts, editable History, Items with visibility, view cube, section view, measure, sketch tools and constraints) come from watching how desktop/tablet CAD apps such as Shapr3D behave publicly (screenshots, public docs, videos). No Shapr3D code, icons, images, wording or styling were copied. Icons are ZEIM's own inline SVG; colours come from the ZEIM theme.
- **Solver is first-principles.** The sketch constraint solver is plain nonlinear least squares over residual functions written for ZEIM. Per ROADMAP.md, nobody working on it read or re-expressed ZEIMCad (GPL) or SolveSpace (GPL) code.
- **Libraries used (all permissive, already in requirements/static):**
  | Library | Licence | Used for |
  |---|---|---|
  | manifold3d | Apache-2.0 | extrude, revolve, booleans, Minkowski (fillet/chamfer), patterns |
  | shapely | BSD-3-Clause | sketch profile regions, offset, trim intersections |
  | scipy | BSD-3-Clause | `least_squares` for the constraint solver |
  | numpy | BSD-3-Clause | maths |
  | trimesh | MIT | mesh handling, body splitting |
  | three.js (+ OrbitControls) | MIT | 3D view in the browser |
  No new dependency was added.

## Resin layer files (2026-11-05)

TorchC0 writes `.lumen` v1 with the unmodified Open Resin Alliance reference crate `lumen-format` 1.0.0, commit `4f25f7bcf77c487447e28b8918eb8017e986cc78`, licence MIT OR Apache-2.0. The crate is vendored under `third_party/open-resin-alliance/lumen-format/` with its licence files. ZEIM code does not modify it. Plate width, height and pixel pitch for the Elegoo rows in `app/core/lumen_plates.json` are copied from `df-plugin-elegoo` commit `be59b1597ac5f5551ddbdae97145f584f05be056` (MIT). Preview images from that plugin are not copied. `.goo`, `.ctb`, and `.nanodlp` are written by a separate program, connorslade/mslicer v0.10.1, commit `2d639519eedf4269a341fb6d5508901e06d99d48`, licence GPL-3.0 only (not or-later). The source is vendored at `third_party/mslicer/` with `LICENSE` and `ZEIM-CHANGES.md` (the `--ctb` flag and the mid-slab sample). ZEIM's Python starts that binary and reads the file it writes. It does not copy the slicer into `app/`, and it does not relicense `app/`. Shipping the binary is not a claim that running it in another process removes GPL-3.0 obligations for that program. The corresponding source for the program ZEIM runs is the vendored tree.

Not incorporated:

- DragonFruit, AGPL-3.0-or-later, including its Rust slicing engine. It is not run.
- `df-plugin-ctb` (MIT) because it includes AES key material for encrypted CTB. mslicer's own `.ctb` writer is the one ZEIM runs. That is not a copy of the plugin's key routine, and a written file is not a claim that a printer's firmware accepts it.
- ChiTuBox and Lychee importers, Anycubic encoders, and VoxelShift's encrypted-CTB conversion.
- morluto/rea (`rea-agents` 6.8.0, commit `a7574d4274728fcb0a13414d6ae43f1597864d94`) is MIT, but it is a reverse-engineering tool rather than a slicer. Its disclaimer refuses circumvention of technical protection and copying of proprietary code and assets. Optional analysis engines it can launch include GPL and LGPL programs that ZEIM does not bundle. It was run only on ZEIM's own `zeim-lumen` binary and on a `.lumen` file ZEIM wrote. It is not run on Lychee, CHITUBOX, or the copyleft slicers.

This note is not legal advice.
