# Troubleshooting library — batch 2 sources

Batch 2 expands `data/troubleshooting/problems.json` from 10 to 25 FDM problems. Manufacturer documentation is prioritized; calibration-dependent values are marked **needs calibration**.

## Sources

- Creality, “3D Printing Problems Explained: 10 Common Issues and Proven Fixes.” Used for common FDM failure categories, symptoms, and general fixes.  
  https://www.creality.com/blog/most-common-3d-printing-problems
- Prusa, “Everything about nozzles with a different diameter.” Used for the 80 percent maximum layer-height rule.  
  https://blog.prusa3d.com/everything-about-nozzles-with-a-different-diameter_8344/
- Bambu Lab community guidance on line width and layer-height ranges. Used as directional guidance for the 75-150 percent line-width and 20-70 percent layer-height ranges.  
  https://www.reddit.com/r/BambuLab/comments/1ez3rt8/nozzle_size_and_minmax_line_width_and_layer_height/
- Bambu Lab forum discussion on extrusion width. Used to document that line width depends on nozzle size, flow, speed, and nozzle height.  
  https://forum.bambulab.com/t/why-can-a-0-4mm-nozzle-print-0-8mm/37142

## Batch 2 additions

Adds poor bridging, sagging overhangs, difficult supports, first-layer gaps, nozzle clogs, heat creep, filament grinding, spaghetti failures, curling, dimensional accuracy, rough top surfaces, infill/perimeter gaps, visible layer lines, brittle parts, and mid-print stoppage.

## Calibration rule

Retraction, pressure advance/linear advance, flow ratio, Z offset, input shaping, drying, and firmware behavior vary by printer and filament. Smart Fix should propose a direction and magnitude, then require confirmation or a calibration print before automatically applying a change.
