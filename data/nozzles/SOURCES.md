# Nozzle specification sources

These are sourced starting values for the ZEIM nozzle picker. Manufacturer profiles take priority; where a manufacturer does not publish a profile for a nozzle/material combination, the app should expose a conservative starting value and require calibration.

## Manufacturer profiles

- Creality documents official 0.2 mm nozzle parameter profiles for the K1, K1 Max, K1C, and K1 SE. Its table specifies a 0.04-0.14 mm layer-height limit, 0.10 mm recommended layer height, 0.22 mm default line width, 0.98 flow ratio for Hyper PLA, 0.97 flow ratio for CR-PETG, 3 mm3/s maximum volumetric speed for Hyper PLA, and 2.5 mm3/s for CR-PETG.  
  https://wiki.creality.com/en/k1-flagship-series/k1-series-general-documents/nozzle-parameter
- Bambu Lab documents nozzle diameters of 0.2, 0.4, 0.6, and 0.8 mm.  
  https://wiki.bambulab.com/en/filament-acc/acc/nozzles
- Prusa explains that layer height should not exceed about 80 percent of nozzle diameter; for a 0.4 mm nozzle, that is about 0.32 mm, and for 0.6 mm it is about 0.48 mm.  
  https://blog.prusa3d.com/everything-about-nozzles-with-a-different-diameter_8344/
- Creality describes the 0.4 mm nozzle as the general-purpose default for FDM printers.  
  https://www.creality.com/blog/3d-printer-nozzle-guide-types-sizes

## Derived ranges

- Bambu community guidance commonly places line width around 75-150 percent of nozzle diameter and layer height around 20-70 percent of nozzle diameter. ZEIM uses these as practical ranges, while retaining Prusa’s 80 percent layer-height ceiling.  
  https://www.reddit.com/r/BambuLab/comments/1ez3rt8/nozzle_size_and_minmax_line_width_and_layer_height/
- Prusa notes that extrusion width depends on nozzle size, flow rate, speed, and nozzle height above the previous layer; it should not be treated as a fixed multiple of nozzle diameter.  
  https://forum.bambulab.com/t/why-can-a-0-4mm-nozzle-print-0-8mm/37142

## Printer nozzle availability

- Creality’s official wiki provides 0.2 mm profiles for K1, K1 Max, K1C, and K1 SE; 0.4 mm is the standard/default K1-family size. Larger K1-compatible nozzles, including 0.6, 0.8, and 1.0 mm, are commercially available, but ZEIM labels non-official-profile combinations as requiring calibration.  
  https://wiki.creality.com/en/k1-flagship-series/k1-series-general-documents/nozzle-parameter  
  https://www.th3dstudio.com/product/k1-k1-max-brass-nozzles-0-4mm-0-6mm-0-8mm-1-0mm-sizes/
- Bambu Lab documents 0.2, 0.4, 0.6, and 0.8 mm nozzles; 0.4 mm is the common shipped default.  
  https://wiki.bambulab.com/en/filament-acc/acc/nozzles
- Prusa documents alternate nozzle sizes and the geometric relationship between nozzle diameter, line width, and layer height; confirm model-specific availability before showing an option in the picker.  
  https://blog.prusa3d.com/everything-about-nozzles-with-a-different-diameter_8344/

## Material cautions

- TPU generally requires slower printing, minimal retraction, and a direct-drive extruder; small nozzles and large nozzles both add difficulty.
- ABS and ASA require enclosure, ventilation, and careful cooling; they are more warp-prone than PLA or PETG.
- Volumetric flow limits depend on the hotend, material, temperature, and nozzle diameter. A larger nozzle does not guarantee that a printer can sustain proportionally higher flow.
