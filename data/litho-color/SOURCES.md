# CMYK colour lithophane sources

This specification describes an **experimental, untested** stacked subtractive CMYK colour-lithophane workflow for Bambu AMS and Creality CFS systems. Colour output depends strongly on filament translucency, backlight brightness and colour temperature, layer height, and the thickness of each colour layer; use a step wedge before printing a full image.

## Sources

- Bambu Lab Wiki — CMYK color lithophane printing instructions: describes the stacked CMYK method, recommended filament order, layer-height guidance, and backlight considerations.  
  https://wiki.bambulab.com/en/knowledge-sharing/cmyk-color-lithophane-printing-instructions
- Snapmaker Wiki — Color lithophane printing instructions: provides additional guidance for CMYK colour lithophanes, including filament selection and backlight setup.  
  https://wiki.snapmaker.com/en/snapmaker_orca/color_lithophane_printing_instructions
- Creality — CFS Color Filament System: relevant for multi-colour filament selection and CFS-based printing workflows.  
  https://www.creality.com/pages/cfs-color-filament-system

## What is unverified

- The exact per-colour thickness values in `litho-color-specs.json` are starting calibration values, not guaranteed results.
- Colour mixing, brightness, and filament compatibility must be validated with a physical step wedge and test print.
- AMS/CFS slot assignments, slicer colour-change behavior, and backlight brightness need printer-specific testing.
- The listed filament examples are candidates, not verified recommendations; test the actual spools before production prints.

## Backlight guidance

Use a diffuse white LED panel or light box. Start with a cool-white source around 5000-6500 K, keep the light evenly distributed, and increase brightness gradually. Avoid bare LEDs and high-power incandescent bulbs near PLA.