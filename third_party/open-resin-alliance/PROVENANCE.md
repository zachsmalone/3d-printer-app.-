# Open Resin Alliance components used by TorchC0

This is a record of what was copied or linked, and what was left out. It is not legal advice.

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
