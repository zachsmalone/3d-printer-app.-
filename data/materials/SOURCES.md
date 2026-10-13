# Filament materials library — batch 3 sources

Manufacturer documentation takes priority. Where a value depends on a particular filament brand, additive package, printer hotend, or ambient conditions, ZEIM should treat it as a starting range and require calibration.

## General sources

- Prusa material guides and Bambu Lab filament documentation are the preferred first references for nozzle temperature, bed temperature, enclosure, drying, and nozzle compatibility.
- Creality’s nozzle guide identifies 0.4 mm as the general-purpose default and discusses nozzle/material considerations.  
  https://www.creality.com/blog/3d-printer-nozzle-guide-types-sizes
- Prusa’s nozzle guide documents the relationship between nozzle diameter, layer height, and line width.  
  https://blog.prusa3d.com/everything-about-nozzles-with-a-different-diameter_8344/
- Bambu Lab documents nozzle sizes and filament/accessory guidance.  
  https://wiki.bambulab.com/en/filament-acc/acc/nozzles

## Safety

- PLA, PETG, TPU, ABS, ASA, PC, nylon, and composite filaments vary substantially by brand and additive package. Use the filament manufacturer’s safety data and ventilation guidance.
- ABS and ASA produce more significant fumes than PLA; use ventilation and avoid breathing emissions.
- Carbon-fiber, glow, and wood-filled filaments can be abrasive; use a hardened nozzle where the filament manufacturer recommends one.
- 3D-printed parts are not automatically food-safe. Food safety requires a certified food-contact material, a documented manufacturing process, and appropriate post-processing; a normal FDM print is not food-safe by default.
- Do not place flame-based candles inside PLA or PETG enclosures. Use LED light sources for printed night lights.

## Calibration

All temperature, bed-temperature, drying, flow, retraction, pressure-advance, and speed values are starting ranges. Mark unverified brand-specific values as **needs calibration** in the app.
