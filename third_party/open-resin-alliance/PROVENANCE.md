# Resin sources inspected for TorchC0

This is a record of what was copied or linked, and what was left out. It is not legal advice.
The three requested sources are Open Resin Alliance, connorslade/mslicer, and morluto/rea.

## morluto/rea

| | |
|---|---|
| Repository | https://github.com/morluto/rea |
| Commit read | `a7574d4274728fcb0a13414d6ae43f1597864d94` |
| Package | `rea-agents` 6.8.0, MIT, copyright 2026 morluto |
| What it is | A reverse-engineering CLI and MCP. Targets include native binaries, JavaScript, .NET, Android, firmware, and several container types. |
| Resin output | None. The tree has no resin slicer, no layer-mask encoder, and no `.ctb` / `.goo` / `.lumen` writer. |
| Checked locally | `rea inspect-rust-binary` on `zeim-lumen` reported ELF amd64 and rustc commit `4d91de4e48198da2e33413efdcd9cd2cc0c46688` (Rust 1.85.0). `rea inspect-artifact` on a generated `.lumen` file returned `unsupported binary format`. |
| Not done | REA was not aimed at Lychee, CHITUBOX, encrypted CTB, DragonFruit, or mslicer. Its disclaimer refuses DRM circumvention and copying protected code and assets. Optional GPL/LGPL engines (GDB, Unicorn, Frida) are not bundled. The npm package is not vendored. |

## Used

| Component | Commit | Licence | How ZEIM uses it |
|---|---|---|---|
| [LumenFormat](https://github.com/Open-Resin-Alliance/LumenFormat) crate `lumen-format` 1.0.0 | `4f25f7bcf77c487447e28b8918eb8017e986cc78` | MIT OR Apache-2.0 (see `lumen-format/LICENSE-MIT` and `LICENSE-APACHE`) | Unmodified reference encoder and decoder. `tools/zeim-lumen` depends on the vendored crate and writes `.lumen` v1. |
| [df-plugin-elegoo](https://github.com/Open-Resin-Alliance/df-plugin-elegoo) printer geometry | `be59b1597ac5f5551ddbdae97145f584f05be056` | MIT (`df-plugin-elegoo-LICENSE`) | Resolution, pixel pitch and Z height only, copied into `app/core/lumen_plates.json`. No preview images. |

The Elegoo plugin's encoder is not compiled. It is a module of the AGPL DragonFruit slicer, and its stock output is `.goo` / `.ctb`, which TorchC0 does not write.

## Not used

| Component | Licence | Why it is not in this tree |
|---|---|---|
| DragonFruit | AGPL-3.0-or-later | The slicer and its Rust engine. Serving a modified copy would be a new decision about publishing ZEIM source. |
| connorslade/mslicer `v0.10.1` | GPL-3.0 | The resin slicer (`.ctb`, `.goo`, `.nanodlp`, `.svg`). Linking or shipping it inside ZEIM is a separate licensing choice. Not approved by the PrusaSlicer CLI decision. |
| df-plugin-ctb | MIT | Encoder for CTB, including AES key material for the encrypted container. Not copied. |
| df-plugin-chitubox | MIT | ChiTuBox project import. Not copied. |
| df-plugin-lys | MIT | Lychee project import. Not copied. |
| df-plugin-anycubic | MIT | Photon/AFF/AFZ encoder bound to the AGPL engine. Printer images are used there without stated permission. Not copied. |
| VoxelShift | Apache-2.0 | Converts CTB, including encrypted CTB. Not copied. |
| Odyssey | GPL-3.0 | Firmware. Not copied. Documented consumer of `.lumen`. |
| Orion | Apache-2.0 | Printer UI, not a slicer. Not copied. |
