# FEAT9: multi-material / AMS colours per part with correct tool changes

Status: planning doc. Not built.

## Where things stand
- Multi-colour 3MF files are merged into one mesh for slicing today (said on the Slicer page).
- Zach's Creality K1 has a single extruder, so there is no hardware here to test tool changes on.
  Generating tool-change G-code that nobody can test would be the kind of untested claim we avoid.

## What it needs
1. Keep parts/regions separate on the plate and let the user assign a filament slot to each.
2. Pass per-object extruder assignments to PrusaSlicer (it supports multi-extruder and MMU profiles) and
   use printer profiles with the right tool-change/purge settings.
3. Show purge waste and time honestly in the estimate.
4. Bambu AMS: tool changes are handled by Bambu's own G-code and firmware; a correct file needs Bambu's
   profiles, and sending needs the authorised route (see FEAT3).
5. Hardware test on each printer family (Prusa MMU, Bambu AMS, Creality CFS/K1 with a multi-colour add-on).

## Decision needed (Zach)
Which multi-material printer to target first, and who can test it. Until then this stays parked.
