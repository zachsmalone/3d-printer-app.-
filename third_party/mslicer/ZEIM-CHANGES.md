# ZEIM changes to mslicer

Upstream: https://github.com/connorslade/mslicer tag `v0.10.1`, commit `2d639519eedf4269a341fb6d5508901e06d99d48`.

Licence: GNU GPL-3.0 only, the text in `LICENSE`. These changes are GPL-3.0 as well. They are not part of ZEIM's proprietary Python.

## What changed

- `slicer/bin/slicer/args.rs`: added `--ctb legacy|v5` (default `legacy`) and `--placed`.
- `slicer/bin/slicer/main.rs`: `.ctb` used to select `CtbFormat::Unknown`, and the exporter then hit `unreachable!`. The flag now selects unencrypted v4 (`0x12FD0106`) or mslicer's encrypted v5 (`0x12FD0107`). After a successful slice the CLI prints one JSON line with layer count and plate pixels. The out-of-volume warning now uses the mesh after it is seated, centered, and scaled into pixels. The previous check used the pre-placement bounds, so a centered model (negative millimetres) was always reported as cut off. `--placed` keeps a mesh that is already in plate millimetres, origin at the minimum corner. Without it, the CLI still recenters.
- `slicer/src/slicer/raster/mod.rs`: each layer is sampled at the middle of its slab. The file still records the layer at `(index + 1) * layer_height` (the top of that slab). Sampling at `index * layer_height` put the first plane on the bed, where a flat bottom is discarded, so the first layer was empty and every mask was one layer below its label.

No other crate was edited. The GUI, remote print, and format crates are the upstream sources.
