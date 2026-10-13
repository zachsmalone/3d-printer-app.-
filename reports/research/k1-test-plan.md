# Creality K1 real-print test plan

Use this checklist on a real Creality K1 with a 0.4 mm nozzle. Run the tests in order where possible. Record the result as **Pass**, **Pass with notes**, or **Fail**, and save photographs or screenshots for any failure.

Do not treat a successful on-screen preview as a pass. A test passes only when the physical print matches the expected result.

## Before starting

- Clean the build plate according to Creality’s guidance.
- Confirm the K1 is level/zeroed and the nozzle is clean.
- Use dry filament; note the brand, material, color, and diameter.
- Record nozzle size, layer height, line width, bed temperature, nozzle temperature, and print speed.
- Export from ZEIM using **Open in your slicer**, then slice with the intended slicer profile.
- Start with PLA unless a test specifically calls for PETG.

## Test 1 — Bed fit and export

**Print:** A simple 180 x 180 x 10 mm flat calibration plate, oriented flat on the bed.

**Purpose:** Confirm that a near-bed-sized ZEIM export fits the K1 build plate and slices without clipping.

**What to look for:**

- The model is centered and does not extend beyond the printable area.
- The slicer does not report the model as outside the bed.
- The first layer completes across the full plate.
- Corners do not lift during the print.
- The finished plate measures close to 180 x 180 mm.

**Pass condition:** The plate prints fully, remains attached, and has no major first-layer gaps.

## Test 2 — Small detail at 0.4 mm

**Print:** A 40 x 40 mm detail coupon containing 0.8, 1.0, 1.2, and 1.6 mm positive features; 1.0, 1.5, and 2.0 mm holes; and small text.

**Purpose:** Establish the practical detail limit for the K1 with a 0.4 mm nozzle.

**What to look for:**

- Positive features above 1.2 mm are recognizable.
- 2.0 mm holes are open and usable.
- 1.0 mm holes may close or need drilling; record the result.
- Text is legible if its stroke width is at least about 0.4-0.5 mm.
- No severe stringing or blobs interfere with the features.

**Pass condition:** The coupon completes and you can record the smallest reliable positive feature, hole, and text size.

## Test 3 — Nozzle change to 0.6 mm

**Print:** The same detail coupon from Test 2, using a 0.6 mm nozzle and an appropriate 0.6 mm slicer profile.

**Purpose:** Verify that ZEIM’s nozzle picker and exported settings survive a real nozzle change.

**What to look for:**

- The slicer receives or uses the intended 0.6 mm nozzle profile.
- Layer height and line width match the 0.6 mm profile.
- Larger features print faster but small holes and fine text lose detail.
- There is no under-extrusion, grinding, or inconsistent extrusion after the nozzle change.
- Record whether ZEIM correctly marks 0.6 mm as available and recommends suitable settings.

**Pass condition:** The 0.6 mm print completes with appropriate settings and the UI/export does not retain stale 0.4 mm values.

## Test 4 — PLA versus PETG

**Print:** Two identical 60 x 60 x 20 mm functional boxes with a snap-fit lid or press-fit peg, once in PLA and once in PETG.

**Purpose:** Confirm that material selection changes the exported settings and produces usable functional parts.

**What to look for:**

- PLA and PETG receive different slicer profiles or settings.
- PETG shows acceptable bed adhesion and does not warp excessively.
- The box walls are solid enough for the intended use.
- The lid, peg, or mating feature fits without excessive force.
- Record dimensional difference between the two materials, especially around holes and pegs.

**Pass condition:** Both prints complete and the functional fit is usable; note any material-specific adjustment needed.

## Test 5 — Will It Print? warning

**Print:** A deliberately risky 80 x 80 x 60 mm model with a 70-degree overhang, a thin isolated wall, and a small blind hole.

**Purpose:** Verify that ZEIM warns before printing rather than after a failed print.

**What to look for:**

- ZEIM identifies the steep overhang and recommends orientation or supports.
- ZEIM identifies the thin wall or small feature as risky.
- The exported file still opens normally in the slicer.
- Print the model once as-is and once with the recommended fix.
- Compare failure mode, support usage, surface quality, and print time.

**Pass condition:** The warning appears before slicing, and the recommended change measurably improves the physical result or avoids a failure.

## Test 6 — Flat lithophane

**Print:** A 100 x 75 mm PLA lithophane from a high-contrast photo, printed vertically with a 0.4 mm nozzle and approximately 0.12 mm layers.

**Purpose:** Validate ZEIM’s lithophane thickness mapping and vertical-print export.

**What to look for:**

- The lithophane prints vertically without detaching.
- Thin areas transmit light; thick areas block light.
- Facial or main-subject detail is visible with a cool-white LED backlight.
- There are no major layer shifts, gaps, or failed sections.
- The lithophane is not so thick that the image appears muddy.

**Pass condition:** The image is recognizable under backlight, with acceptable contrast and no structural failure.

## Test 7 — Night-light stand with LED puck

**Print:** A lithophane frame or stand designed for a measured LED puck, using the actual puck’s diameter and thickness.

**Purpose:** Validate that ZEIM’s light-source dimensions produce a usable physical assembly.

**What to look for:**

- The LED puck inserts without forcing.
- The puck does not fall through or rattle excessively.
- The lithophane seats securely in the frame.
- The light source illuminates the image evenly.
- The assembly has ventilation and the LED wiring/battery access remains usable.

**Pass condition:** The puck fits, the lithophane is held securely, and the completed night light works.

## Test 8 — Split part with magnets

**Print:** A small two-piece Split test part using the merged magnet-pocket specification: for example, 8 x 3 mm magnets with a 8.25-8.30 mm pocket diameter and 3.15 mm pocket depth.

**Purpose:** Validate magnet-pocket sizing, polarity workflow, and the Split connection.

**What to look for:**

- Magnets insert into the pockets without splitting the walls.
- Magnets seat fully after adhesive is applied.
- Opposite poles attract and align the two halves.
- The halves do not repel or sit unevenly.
- The magnet does not protrude above the surface or sit so deep that it loses holding force.

**Pass condition:** Both halves join repeatably with magnetic alignment and the magnets remain securely captured.

## Test 9 — Split dovetail and alignment pins

**Print:** A two-piece Split coupon with a 60-degree dovetail and a two-pin alignment pattern: one round hole and one elongated slot.

**Purpose:** Validate the Split mechanical-connection specifications on the K1.

**What to look for:**

- The dovetail joins by hand or with light pressure, without binding.
- The alignment pins locate the halves without forcing.
- The slot absorbs small alignment error.
- The assembled coupon does not wobble excessively.
- The parts can be separated without breaking.

**Pass condition:** The coupon assembles and separates repeatedly without damage, with acceptable alignment.

## Test 10 — Bird call

**Print:** A ZEIM bird call in PLA, using the intended internal air channel, cap, and mouthpiece geometry.

**Purpose:** Validate that ZEIM can produce a functional print, not only a visual model.

**What to look for:**

- The air channel is open and free of obstruction.
- The cap or mating part seals sufficiently without excessive force.
- The call produces a clear sound when blown correctly.
- There are no leaks that prevent sound production.
- If it fails, record whether the issue is dimensional fit, layer leakage, cap fit, or mouthpiece geometry.

**Pass condition:** The bird call produces a repeatable sound; if not, the failure is documented with enough detail to revise the model.

## Result log

| # | Test | Material | Nozzle | Result | Notes |
|---|---|---|---|---|---|
| 1 | Bed fit and export | PLA | 0.4 mm |  |  |
| 2 | Small detail | PLA | 0.4 mm |  |  |
| 3 | Nozzle change | PLA | 0.6 mm |  |  |
| 4 | PLA vs PETG | PLA / PETG | 0.4 mm |  |  |
| 5 | Will It Print? warning | PLA | 0.4 mm |  |  |
| 6 | Flat lithophane | PLA | 0.4 mm |  |  |
| 7 | Night-light stand | PLA | 0.4 mm |  |  |
| 8 | Split magnets | PLA | 0.4 mm |  |  |
| 9 | Split dovetail / pins | PLA | 0.4 mm |  |  |
| 10 | Bird call | PLA | 0.4 mm |  |  |
