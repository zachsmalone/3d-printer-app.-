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

## Resin layer files (2026-11-06)

Two encoders run. Neither is a claim that a print has been made.

`.lumen` v1 uses the unmodified Open Resin Alliance crate `lumen-format` 1.0.0, commit `4f25f7bcf77c487447e28b8918eb8017e986cc78`, licence MIT OR Apache-2.0, vendored under `third_party/open-resin-alliance/lumen-format/`. Plate pixel sizes come from `df-plugin-elegoo` commit `be59b1597ac5f5551ddbdae97145f584f05be056` (MIT). That plugin's GOO/CTB encoder is not compiled, because it is a module of the AGPL DragonFruit engine.

`.goo`, `.ctb`, and `.nanodlp` are written by mslicer `slicer`, GPL-3.0, tag `v0.10.1`, commit `2d639519eedf4269a341fb6d5508901e06d99d48`, plus the `--ctb` change in `third_party/mslicer/ZEIM-CHANGES.md`. That whole directory is GPL-3.0. The licence text in that tree is the GNU GPL version 3, 29 June 2007. Section 0 says mere network interaction, with no transfer of a copy, is not conveying. Section 1 defines Corresponding Source as the source needed to generate, install, run, and modify the work. Section 5 says a compilation of a covered work with other separate and independent works, which are not combined into a larger program, is an aggregate, and the GPL then does not apply to the other parts. Section 6 requires Corresponding Source when the object code is conveyed.

What this repository does: `app/` only executes that binary with arguments and files. No mslicer source is copied into `app/`. The Docker image builds the binary and copies `third_party/mslicer` to `/usr/local/share/zeim/mslicer-source`, which is the Corresponding Source of that program, including the ZEIM patch. `.ctb` v4 is the unencrypted container (magic `0x12FD0106`). `.ctb` v5 is mslicer's own encrypted container (magic `0x12FD0107`). Plates listed as CTB v2 are refused, because this engine does not write v2 and a v4 file is not relabelled as v2.

The owner decision that this layout does not settle: if the subprocess is treated as one combined program with the rest of ZEIM, GPL-3.0 section 5(c) would require the whole conveyed work to be GPL-3.0. This branch does not relicense `app/`. It relies on the programs staying separate. That is a structural choice, not a court ruling.

Not incorporated:

- DragonFruit, AGPL-3.0-or-later. Its slicing engine is the host the MIT format plugins compile into. AGPL section 13 requires offering the corresponding source of a modified AGPL program to users who interact with it remotely. mslicer already writes the printer files, so that engine is the one TorchC0 runs.
- `df-plugin-ctb` is not copied on its own. `.ctb` comes from mslicer's GPL writer, not from that plugin's key material.
- ChiTuBox and Lychee programs, assets, and UI are not copied.
- morluto/rea (`rea-agents` 6.8.0, commit `a7574d4274728fcb0a13414d6ae43f1597864d94`) is MIT and is a reverse-engineering tool, not a slicer. It is not pointed at a proprietary slicer. Optional GPL and LGPL engines it can launch are not bundled.

This note is not legal advice.
