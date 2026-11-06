# ZEIM changes to mslicer

Upstream: https://github.com/connorslade/mslicer tag `v0.10.1`, commit `2d639519eedf4269a341fb6d5508901e06d99d48`.

Licence: GNU GPL-3.0 only, the text in `LICENSE`. These changes are GPL-3.0 as well. They are not part of ZEIM's proprietary Python.

## What changed

- `slicer/bin/slicer/args.rs`: added `--ctb legacy|v5` (default `legacy`).
- `slicer/bin/slicer/main.rs`: `.ctb` used to select `CtbFormat::Unknown`, and the exporter then hit `unreachable!`. The flag now selects unencrypted v4 (`0x12FD0106`) or mslicer's encrypted v5 (`0x12FD0107`). After a successful slice the CLI prints one JSON line with layer count and plate pixels.

No other crate was edited. The GUI, remote print, and format crates are the upstream sources.
