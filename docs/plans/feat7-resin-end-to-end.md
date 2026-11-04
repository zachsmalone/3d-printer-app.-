# FEAT7: native resin supports and end-to-end resin slicing in TorchC0

Status: planning doc. Not shipped as half-work.

## What already exists
- `app/core/resin.py` builds pillar supports with a raft, with a support-spacing (density) slider of 1.5–10 mm.
- Tip and shaft sizes are fixed in code (`build_supports(tip_d=0.4, shaft_d=1.0)`); there is no touchpoint slider.
- TorchC0 exports a supported STL. It does not write printer layer files (.ctb, .pwmx, .goo, etc.), so users
  finish in their resin printer's own slicer.

## What "end-to-end" needs
1. A touchpoint (tip diameter) slider: small, about 0.2–0.8 mm, plumbed into `build_supports`. Low risk.
2. Better support placement: overhang/island detection and branch or tree supports. Medium.
3. Writing native layer files: render each layer to a bitmap and encode the printer's format.

## Licence and cost
| Route | Licence | Notes |
|---|---|---|
| UVtools encoders | AGPL-3.0 | Using its code in the server would require releasing ZEIM's source under AGPL |
| Other open encoders (e.g. community .ctb/.goo writers) | Mostly GPL/AGPL; some formats are encrypted | Same licence question; encrypted formats (newer .ctb) need keys we must not extract |
| Write our own encoders from public format docs | Ours | Only for documented, unencrypted formats (e.g. Elegoo .goo has a published spec) |
| Hand off to the printer's slicer (today) | n/a | Honest and safe |

Cost: no licence fees for the open routes; the cost is engineering time and hardware testing on each printer
(a resin layer file that is wrong can damage the FEP film or the screen).

## Decision needed (Zach)
- Which resin printer(s) to target first, and whether there is one to test on. Nothing ships as
  "slices end-to-end" until a print from it has been hardware-tested.
- Recommended order: touchpoint slider behind a default-off flag → .goo encoder for one tested printer.
