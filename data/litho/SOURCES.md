# Lithophane specification sources

These are sourced starting specifications for ZEIM lithophanes. Final thickness, opening diameter, and backlight choice should be validated with the user’s printer, filament, and actual light source.

## Thickness and material

- American Filament recommends a cool-white backlight and minimum/maximum lithophane thicknesses close to 0.6 mm and 2.8 mm.  
  https://americanfilament.us/pages/beginners-guide-to-lithophanes
- American Filament also recommends a dedicated lithophane slicing profile, a 0.4 mm nozzle, and a slow initial layer.  
  https://americanfilament.us/pages/beginners-guide-to-lithophanes
- Filament Picks recommends white PLA rather than clear PLA for a classic black-and-white lithophane and suggests starting around 0.12 mm layers with a 0.4 mm nozzle.  
  https://filamentpicks.com/best-filament-for-lithophanes-bambu-lab/
- A Bambu Lab community thread reports using approximately 3.6 mm thickness for dark areas to render properly and mentions a 0.6-0.8 mm minimum-thickness range. This supports treating darker or colored filament as needing a larger maximum-thickness range, not as a universal rule.  
  https://forum.bambulab.com/t/show-your-best-lithopanes-be-it-standard-or-colour/80242
- A Prusa forum discussion confirms that PETG can be used for lithophanes, while noting that PLA is more commonly recommended for visual quality.  
  https://forum.prusa3d.com/forum/english-forum-general-discussion-announcements-and-releases/lithophanes-in-petg/

## Light sources

- Super Bright LEDs explains that E12 bases have a 12 mm diameter and E26 bases have a 26 mm diameter; E12 bulbs are commonly used for decorative lighting and night lights.  
  https://www.superbrightleds.com/blog/understanding-light-bulb-base-types-screw-bases.html
- GE Lighting provides a general guide to bulb sizes, shapes, and codes.  
  https://www.gelighting.com/inform/guide-light-bulb-sizes-types-shapes-and-codes
- Snapmaker documents a 156 mm x 120 mm USB-C powered backlight board for color lithophanes.  
  https://wiki.snapmaker.com/en/snapmaker_orca/color_lithophane_printing_instructions
- Lithophane Lights documents LED light panels for lithophanes and discusses long-life LED panels.  
  https://lithophanelights.com/blog/

## Globe lithophanes

No single universal globe diameter or opening diameter was found in the reviewed sources. ZEIM therefore treats globe size as a parameter derived from the chosen light source and printer build volume. The opening rules use the documented E12/E26 base diameters plus practical clearance, and LED-puck openings use the measured puck diameter plus clearance.

## CMYK lithophanes

- Bambu Lab documents CMYK color lithophanes as separate color layers and recommends a 0.15 mm first layer height.  
  https://wiki.bambulab.com/en/knowledge-sharing/cmyk-color-lithophane-printing-instructions
- Snapmaker likewise documents CMYK color lithophane printing, including a 156 mm x 120 mm USB-C powered backlight board.  
  https://wiki.snapmaker.com/en/snapmaker_orca/color_lithophane_printing_instructions
