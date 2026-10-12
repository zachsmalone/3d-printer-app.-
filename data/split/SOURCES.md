# Split specification sources

This document records the public guidance used to select the starting dimensions in `split-specs.json`. These are calibration starting points for a Creality K1 with a 0.4 mm nozzle; final dimensions should be validated with a material- and printer-specific fit coupon.

## Magnet pockets

- TotalElement recommends starting about 0.10-0.15 mm oversize on diameter for a magnet press fit, or 0.20-0.30 mm oversize for a glued fit, with about 0.1-0.2 mm additional depth.  
  https://totalelement.com/blogs/working-with-neodymium-magnets/magnet-pocket-clearance-for-3d-prints
- Sovol recommends matching the slot depth to the magnet thickness and lightly sanding the magnet and slot before gluing.  
  https://www.sovol3d.com/blogs/news/how-to-use-magnets-in-3d-printed-models
- Sovol's FDM tolerance guide lists starting clearance ranges of 0.15-0.25 mm for PLA and 0.20-0.30 mm for PETG.  
  https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit

## Dovetails

- Snapmaker's fitting guidance recommends a 0.3-0.5 mm gap for printed parts that must fit together, while noting that exact requirements depend on printer, material, and feature size.  
  https://www.snapmaker.com/blog/3d-printing-tolerances/
- Sinterit advises beginning around 0.4-0.6 mm clearance for larger FDM assemblies, while SLA can often use 0.1-0.2 mm.  
  https://sinterit.com/3d-printing-guide/design-for-3d-printing/tolerances-3d-printing/
- Sovol's material-specific FDM ranges (PLA 0.15-0.25 mm; PETG 0.20-0.30 mm) are used as the closer starting range for the relatively small Split dovetail.  
  https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit

## Alignment pins

- Markforged identifies dowel pins as a standard way to align 3D-printed fixture components before fastening or bonding.  
  https://markforged.com/resources/learn/design-for-additive-manufacturing-plastics-composites/3d-printing-strategies-for-composites/composites-3d-printing-design-tips
- Forerunner 3D recommends two dowel features, converting one round hole to a slot when features are far apart, orienting the slot toward the other hole, and adding chamfers to aid alignment.  
  https://forerunner3d.com/design-guide-for-using-dowel-holes-in-3d-printed-parts/
- Forerunner 3D also warns that printed holes are not consistently accurate enough for exact press or slip fits without secondary reaming; the Split specification therefore treats pin fits as coupon-calibrated rather than guaranteed.  
  https://forerunner3d.com/design-guide-for-using-dowel-holes-in-3d-printed-parts/

## Resin

- Forge Labs gives typical SLA tolerance guidance of plus or minus 0.25 percent, with a minimum of plus or minus 0.25 mm for standard parts; resin therefore warrants smaller clearances than FDM but still requires validation.  
  https://forgelabs.com/design-guides/sla
- Xometry notes that small resin holes can seal and thin pins can be fragile, and gives 1 mm as a minimum reliable pin diameter.  
  https://xometry.pro/en-eu/articles/3d-printing-sla-design-tips/
- Protolabs Network emphasizes drainage holes for hollow resin parts to prevent trapped uncured resin.  
  https://www.hubs.com/knowledge-base/how-design-parts-sla-3d-printing/
