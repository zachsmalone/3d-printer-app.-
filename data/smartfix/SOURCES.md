# Smart Fix mapping sources

This map links every `slicer_key` in `data/troubleshooting/problems.json` to a real PrusaSlicer 2.9 setting where one exists. Hardware, firmware, calibration, maintenance, and model-design actions are explicitly separated from slicer settings and must not be applied automatically.

## Verification status

- `verified`: The PrusaSlicer setting name and adjustment direction are supported by the cited source.
- `verified_setting_unverified_k1_range`: The PrusaSlicer setting is verified, but the K1-specific numeric range needs calibration and is marked unverified.
- `unverified`: The setting name, value range, or both could not be verified; ZEIM must not silently apply it.
- `not_slicer_setting`: The action is not a PrusaSlicer setting.

## Sources

- Prusa Knowledge Base — Stringing and oozing: identifies nozzle temperature and retraction settings as relevant fixes and explains their relationship to stringing.  
  https://help.prusa3d.com/article/stringing-and-oozing_1805
- Prusa Knowledge Base — Poor bridging: covers bridge flow and cooling; use it for bridge-flow guidance rather than inventing a universal fan percentage.  
  https://help.prusa3d.com/article/poor-bridging_1802
- Prusa Knowledge Base — Skirt and brim: documents brim use for first-layer stability and bed contact.  
  https://help.prusa3d.com/article/skirt-and-brim_133969
- Prusa Knowledge Base — Configuration Wizard: covers printer, filament, and print-setting profiles, including temperature-related configuration.  
  https://help.prusa3d.com/article/configuration-wizard_1754
- Prusa Knowledge Base — PrusaSlicer 2.9 (Legacy): the documentation category for PrusaSlicer 2.9.  
  https://help.prusa3d.com/category/prusaslicer-2-9-legacy_204
- Prusa Knowledge Base — Configuration and profiles: explains that profiles combine print, filament, and printer settings.  
  https://help.prusa3d.com/category/configuration-and-profiles_207
- Prusa Blog — PrusaSlicer 2.9 release notes: identifies PrusaSlicer 2.9 features, including seam-related improvements.  
  https://blog.prusa3d.com/prusaslicer-2-9-whats-new_107659/
- All3DP — PrusaSlicer retraction settings: documents `Retraction Length` and `Retraction Speed` as the relevant PrusaSlicer fields.  
  https://all3dp.com/2/prusaslicer-retraction-settings/

## K1 calibration

The Creality K1 uses a direct-drive extruder, so retraction should begin low and be tuned with a stringing test. The map’s K1 retraction ranges are starting ranges, not guaranteed settings; validate them with a test print before regular use.

## Unverified items

The following are intentionally not treated as verified one-to-one PrusaSlicer settings:

- `part_cooling_fan` — fan behavior is controlled through multiple PrusaSlicer settings.
- `print_speed` — PrusaSlicer uses separate speed fields and profiles.
- `first_layer_flow` — no verified universal PrusaSlicer key.
- `pressure_advance` — a printer-firmware/calibration feature, not a standard PrusaSlicer setting.
- `support_pattern` — confirm the available PrusaSlicer 2.9 pattern values and how tree supports are selected.
- `hole_expansion_compensation` — mapped to `hole_size_compensation`, but the exact key and range require verification in PrusaSlicer 2.9.
- `first_layer_line_width` and `line_width` — verify the exact PrusaSlicer 2.9 field names and safe ranges before applying.
- All K1-specific retraction, fan, speed, and compensation ranges — calibrate on the actual printer and filament.