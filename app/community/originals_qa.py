"""QA overrides for the ZEIM Originals, kept in git because library/originals is not.
Source: Ren Ishikawa, reports/qa/originals-and-regression-2026-10-12.md (geometry + a generic PrusaSlicer profile; NOT test prints)."""

# overhang > ~10% of surface area facing down past 45 degrees: the slicer will need supports
NEEDS_SUPPORTS = {"dino-phone-stand", "ember-baby-dragon", "flower-fidget-spinner", "horn-dino-band-popper",
                  "pumpkin-trinket-jar", "sleepy-loaf-cat", "turtle-trinket-jar"}

# tiny footprint on the bed (sleepy-loaf-cat 36.6 mm², chubby-penguin-scarf 124.7 mm²): may come loose or tip over
LOW_CONTACT = {"sleepy-loaf-cat": "Small contact with the bed (about 37 mm²): print with a brim (5-8 mm) so it doesn't come loose or tip over.",
               "chubby-penguin-scarf": "Small contact with the bed (about 125 mm²): print with a brim (5 mm) so it doesn't come loose or tip over."}

# the single layout plate is bigger than a 220 x 220 mm bed: offer the per-plate files instead (tools/originals_plates.py)
PLATES = {"rain-guard-bird-feeder": ["rain-guard-bird-feeder_plate1.stl", "rain-guard-bird-feeder_plate2.stl"]}
