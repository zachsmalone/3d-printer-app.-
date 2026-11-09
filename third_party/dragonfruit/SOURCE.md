# DragonFruit source offer

ZEIM runs DragonFruit as a separate, unmodified program. ZEIM does not link it, does not copy its source into `app/`, and does not patch it. This file is ZEIM's notice. It is not DragonFruit's source, and it does not relicense ZEIM.

This is the same shape as ZEIM's PrusaSlicer note in `docs/licensing.md`. It is not legal advice.

## The program ZEIM runs

| | |
|---|---|
| Program | `dragonfruit-cli` 2.1.1 |
| Repository | https://github.com/Open-Resin-Alliance/DragonFruit |
| Commit | `97596a55882cb139bbcf96bb98b211f82ae4c5f0` |
| Branch that contained it | `dev` (2026-11-08). Tag `v0.3.1` is an ancestor. `main` is not this commit. |
| Licence | AGPL-3.0-or-later for the application. The plugin directories are MIT and are compiled into this binary, so the binary as a whole is the AGPL program. |
| What ZEIM calls | `slice run`. The Next.js UI, the Tauri shell, and the support authoring tools are not run. |

Source for that exact commit, including the MIT plugins it records as submodules:

https://github.com/Open-Resin-Alliance/DragonFruit/tree/97596a55882cb139bbcf96bb98b211f82ae4c5f0

Plugin commits that commit links, which the build checks out:

| Path | Upstream | Commit |
|---|---|---|
| `plugins/ctb` | https://github.com/Open-Resin-Alliance/df-plugin-ctb | `44861de1509584c3d8c3c58172d863dc79d376ab` |
| `plugins/elegoo` | https://github.com/Open-Resin-Alliance/df-plugin-elegoo | `be59b1597ac5f5551ddbdae97145f584f05be056` |
| `plugins/lumen` | https://github.com/Open-Resin-Alliance/LumenFormat | `109d7d444c9714d8d41f3e3e0ddb47e21eaa1eda` |
| `plugins/anycubic` | https://github.com/Open-Resin-Alliance/df-plugin-anycubic | `cb7b9c92e66d5904ba1afbdd955c74c8697dca20` |
| `plugins/athena` | in the DragonFruit tree | same commit as the application |

The encoder list is not stored in git. The build runs `node scripts/generate-plugin-registry.mjs` in that checkout, then `cargo build --release --bin dragonfruit-cli` from `rust/dragonfruit-cli`. `tools/dragonfruit/build.sh` is that sequence. Rust 1.97.0, which the repository's `rust-toolchain.toml` names.

ZEIM's wrapper passes plate height, exposure, and anti-aliasing on the command line. It does not edit DragonFruit.

## What still uses other programs

- `.goo` stays on mslicer (GPL-3.0). The bench wrote GOO `V3.0` from mslicer and `V1.2` from DragonFruit. UVtools read both. No Mars 5 firmware has accepted `V1.2` here, so TorchC0 does not switch `.goo`.
- `.lumen` stays on the vendored `lumen-format` crate (MIT OR Apache-2.0) via `tools/zeim-lumen`. DragonFruit can write a `LUMN` file. Its layers were not shown to match ZEIM's writer, so TorchC0 does not switch `.lumen`.

## Orientation

The bench (pull request 172) sliced the same solids on both engines. DragonFruit stores world +Y at image row 0. mslicer writes the low-Y row first. After a Y flip of DragonFruit's image, the masks matched aside from a one-pixel edge that comes from mapping the bed onto `width` pixels (mslicer) or `width - 1` pixels (DragonFruit). No printer manual or ChiTu/Elegoo container spec in this tree says which row is the front of the panel. TorchC0 therefore passes `--mirror-y` so DragonFruit's file matches the mslicer files ZEIM already produces. A catalog `mirror_y: true` asks for the opposite of that file, so the wrapper turns `--mirror-y` off in that case. A catalog `mirror_x: true` adds `--mirror-x`. A mirror value that is not a boolean is still refused. `.goo` is still mslicer, which has no mirror flag, so a mirrored GOO plate is still refused.

Nothing here was printed.
