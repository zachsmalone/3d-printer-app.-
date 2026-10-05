# Lithophane+ plan: more shapes, and Experimental colour

Author: Haruto Tanaka (Engineering) · 2026-10-04 · Docs only: **no app code was changed.** Build starts AFTER the safety batch.
Asked for by Zach (via Yami): push the lithophane maker hard. Everything below that has not been printed is **untested until Zach prints**.

**Label key.** `[code]` = read in the live tree (`/workspace/photo3d`, read-only). `[box]` = I ran it on this box in a scratch folder (`/workspace/make-scratch/litho/`, not part of the app). `[web]` = public page I read (URL in section 12). `[Zach]` = needs Zach's printer, filament or eyes. Timings are from a shared, busy box: rough.

---

## 0. Summary (read this first)

| | Verdict |
|---|---|
| New flat shapes (heart, ornament, keychain, car-mirror hanger) | **High** feasibility. One generic "outline" path; heart prototype is watertight and builds in 0.2 s `[box]`. |
| Curved panel / cylinder lamp | **High** for geometry (prototype watertight `[box]`); **medium** for a good print (seam, base ring, light fit) `[Zach]`. |
| Globe: two hemispheres + LED / tea-light opening | **Medium.** Geometry works `[box]`; print orientation has a steep cap (13.7 % of the surface is past 45 °, 10.6 % with the opening) and the halves must join. Needs a test print before we say more. |
| Night-light frames | **Medium-high.** Frame/stand are easy; fitting "any" night light is not (we should not design around mains plugs, see 4.7). |
| Colour (a1): swap-by-layer tinted lithophane (few colour changes, K1 can do it with pauses) | **Medium.** Geometry/export are easy and partly verified `[box]`; colour *prediction* needs Zach's calibration. **Experimental.** |
| Colour (a2): full-colour stacked CMYK-style lithophane | **Low** for now. Needs a multi-material system (K1 + CFS), 4 suitable translucent filaments and calibration. Research spike only. |
| Colour (b): multi-colour raised images (colour per layer height) | **High** for single-extruder swap-by-layer; **medium** for multi-material. Also fixes a real bug found today (section 1.4). **Experimental.** |
| Paper colour-guide sheet | **Medium**, small, **not promised** (section 6). |
| Mode dropdown | **Open dependency** on Sakura's message (section 7). Not asked. |

Total estimate: **about 39.5 working days** for the whole ordered list (**33** without the optional paper sheet LITHO-13 and the A2 spike LITHO-16); the geometry slice LITHO-1..6 is about **13.5 days**, and with the UI (LITHO-14) and budgets (LITHO-15) about **17.5**. Section 9 is the source of truth. Colour is **Experimental** throughout.

Top three engineering truths found while reading code (details in section 1):
1. Today's lithophane is **one flat rectangle with an optional border**. No shapes, no hang hole, no stand.
2. The **Print dialog's lithophane defaults are not the ones lithophane guides recommend** (0.2 mm layers, 15 % infill; and 100 % infill is refused by PrusaSlicer unless the pattern is rectilinear) `[code][box]`.
3. The pop-art "multi-colour" 3MF we export **does not slice as a stack** in PrusaSlicer 2.9.2: it reads as 4 separate plates (max height 1.0 mm instead of 4.0 mm) `[box]`. Colour work has to start by fixing the export.

---

## 1. What exists today (honest)

### 1.1 Code `[code]`
- `app/core/geometry.py :: lithophane(im, width_mm=100, min_thickness=0.8, max_thickness=3.0, border_mm=3, resolution=200, smooth=0.8, gamma=1, auto_contrast=True, invert=False)`.
  - Picture → grey (`0.299R+0.587G+0.114B`) → optional smoothing / 1–99 percentile contrast stretch / gamma → `thick = tmax − (tmax−tmin)·g` (**linear**: bright = thin).
  - Border = extra cells at full thickness around the picture; `width_mm` is the OUTSIDE width (fixed by a test, `test_b2_mesh.py`).
  - `heightfield_solid()` builds a closed mesh from a node grid: flat back at Z=0, relief on +Z. Watertight by construction.
  - Limits: `MAX_RES=600`, `MAX_CELLS=360 000`, `MAX_ASPECT=20` (refused), `WARN_ASPECT=6`.
- Beginner mode (`autotune.py`): presets thin 0.6–2.4 mm, standard 0.8–3.2, thick 1.0–4.0; resolution ≈ width / 0.35 mm, clipped 100–500; smoothing 0.7 (1.2 if noisy); border 3 mm (2 mm under 60 mm).
- Expert mode (`static/index.html`, "Lithophane" section): Min thickness 0.8, Max 3.0, Border 3.
- Preview thumbnail (`thumbnail.lithophane_backlit`) simulates light with `exp(−0.9·thickness)`. **The 0.9 per mm is an assumed constant, not measured on any filament.**
- Exports: STL (binary), OBJ, 3MF (`exporters.py`). The 3MF writer supports per-body colours via `<basematerials>` only; no slicer-specific metadata.
- Print dialog / slicing: for lithophane builds the UI ticks **"Stand upright"** (`static/app.js:204`); slicing defaults are layer 0.2 mm and infill 15 %; brim 0.
- Edit tab: a photo can become a "Lithophane base" and be edited like any mesh (`edit.py`, `photo_mode`).
- A lesson exists (`education.py`, "lithophanes"): thickness vs light, "test it with an LED light".
- Showcase/catalog already tags lithophanes ("nightlight", "lamp"), so shape names can reuse tags.

### 1.2 Tests `[code]`
- `tests/test_app.py::test_modes_exports_watertight` (lithophane res 120, border 2: STL/OBJ/3MF load, watertight, >100 faces) and `test_beginner_autotune` (thick preset → max 4.0).
- `tests/test_b2_mesh.py::test_lithophane_requested_width_is_the_outside_width_with_border` (100.00 mm width for borders 0/3/6).
- `tests/test_b1_hq.py` builds a lithophane for slicing (upright layer count follows height).
- Nothing tests: image orientation (does it read correctly from the viewing side), light-curve, thickness extremes on the printed side, any non-rectangular shape, or any colour export.

### 1.3 Numbers `[box]` (sample.png 480×360, 100 mm, res 200)
- Build 0.15 s model time (the API builds a preview as well, so about 2 s end-to-end under load, see `engineering-polish.md`); **137,372 triangles**; 100.0 × 76.3 × 3.0 mm; volume 18.2 cm³; watertight.
- PrusaSlicer (generic profile, upright, 0.2 mm, 15 %): 382 layers, **2 h 02 m, 22 g**; extrusion mix 50 % perimeter, 24 % external perimeter, 10 % solid infill, **15 % sparse infill**. At 0.12 mm layers and 95 % infill: 635 layers, **3 h 13 m**.
- **Print-dialog gap:** infill 100 % → PrusaSlicer error *"The selected fill pattern is not supposed to work at 100% density"*, and the UI allows 100 (already in `slicer-and-infill-plan.md`). 15 % sparse infill inside a 3 mm backlit wall shows as texture; lithophane guides recommend full infill or many perimeters and 0.1–0.12 mm layers `[web: 3dprinterstuff, Nozzle Down, Bake3D, Vextrude]`.

### 1.4 Colour today `[code][box]`
- Pop-art (`popart`) makes N levels with colours from a k-means palette (or a user palette), each level one `Body` with a hex colour; the STL/slicer mesh is a single merged heightfield (sloped risers).
- The Beginner note says the bodies are "ready for multi-colour printing / filament swaps".
- **Found today:** I sliced the app's own multi-body pop-art 3MF (4 levels, 1 mm layers, expected height 4.0 mm) in PrusaSlicer 2.9.2: `--info` reports **4 separate objects**, each re-centred on the bed at Z 0–1; the G-code tops out at **Z = 1.0 mm** and logs *"gcode path conflicts found between layer1 and layer0"*. So the colour 3MF is not a stacked multi-colour print in PrusaSlicer. Other slicers (Creality Print, Bambu Studio, Orca) were **not tested** here; they may differ.
- **Fix verified in PrusaSlicer 2.9.2 `[box]`:** one `<object>` with all triangles plus `Metadata/Slic3r_PE_model.config` that lists each colour as a `<volume firstid lastid>` with `extruder=N`: `--info` shows size_z **4.000**, 4 parts; slicing gives max Z 4.0 and **4 tool changes** with a 4-extruder setting (single-extruder setting also slices to 4.0).
- **Colour change at a height (single extruder) verified in PrusaSlicer 2.9.2 `[box]`:** a `Metadata/Prusa_Slicer_custom_gcode_per_print_z.xml` inside the 3MF (`<code print_z=".." type="0" extruder="1" color="#RRGGBB" gcode="M600"/>`) produced `M600` at the requested layer; with `--color-change-gcode PAUSE` it produced `PAUSE`. **Alignment catch:** with the default 0.35 mm first layer the change landed at Z 2.15 instead of 2.0. The change heights must be a multiple of the layer height and the first layer must equal the layer height (ZEIM's slicer wrapper sets the first layer to `max(layer, 0.2)`, which is wrong for 0.12 mm).

---

## 2. Design principles
1. **One pipeline, many shapes.** Keep `geometry.lithophane` as the "flat picture" engine; add `app/core/litho/` with `shapes.py` (outline, curved, sphere), `colour.py`, `profile.py`. A `shape` field (default `"flat"`) is added to `/api/generate` so old clients keep working.
2. **Guaranteed-closed meshes.** Three safe constructions, all verified `[box]`: (i) heightfield → ONE manifold3d boolean with an extruded outline; (ii) periodic grids (tube / dome) with welded seams; (iii) never union two near-coincident bodies (see 3.1 lesson).
3. **Check what the printer will see:** every shape runs the same "contract" test: watertight after an STL float32 round trip, extents inside the K1 bed (220×220×250), thickness min/max as asked, no zero-area triangles, triangle cap, and a PrusaSlicer smoke slice.
4. **Print profile is part of the feature.** A lithophane that prints with 15 % infill is a worse lithophane. Each shape ships a recommended profile (orientation, layer height, infill/perimeters, brim) shown in plain words and used by the Print dialog.
5. **Colour is Experimental, labelled in the UI, the file name and the docs**, and prediction colours are shown as "predicted, not guaranteed".
6. **Prior art is credited, nothing is copied.** We use public documentation for ideas only (section 8).

---

## 3. New shapes

Common to all: picture is cropped-to-fill the shape (crop box on phone, no stretching; image is not distorted unless the user asks), thickness mapping is `tmax − (tmax−tmin)·g` as today (a Beer–Lambert option comes in LITHO-8), `invert`, `smooth`, `gamma` unchanged. Thickness ranges below are starting points from public guides for **white PLA** (min ≈ 0.6–0.8 mm, max ≈ 2.8–3.2 mm) `[web]`; they depend on the filament and the light `[Zach]`.

### 3.1 Heart (and round / oval / rounded-square / star outlines)
- **Geometry.** Build the normal heightfield on the outline's bounding box; make the frame by raising the thickness field to `tmax` outside an inset outline (anti-aliased); then ONE manifold3d intersection with the extruded outer outline; optional hang hole by subtracting a cylinder. Prototype `[box]`: 70 mm heart, 88,768 triangles, **0.21 s**, 70.0 × 63.3 × 3.0 mm, watertight and one body **after an STL float32 round trip**.
  - *Lesson:* my first prototype built the picture and the frame as two bodies and united them: it had **32 non-manifold edges** after the STL round trip. The single-intersection construction fixes it. This is why section 2 rule (iii) exists.
- **Printability (FDM).** Two ways: (a) flat on the bed: no supports, 24 layers, **43 min, 5 g** (generic profile, 0.12 mm layers) `[box]` but 0.12 mm layers give only ~25 tonal steps across 3 mm; (b) standing up (better image, like other lithophanes): **standing on the pointed tip fails** in PrusaSlicer (*"object with no extrusions in the first layer"*) `[box]`. With the tip cut flat by 4 mm (59.3 mm tall) it slices: 493 layers, **1 h 28 m, 7 g** `[box]`. So the heart gets a small flat foot or a stand clip and a brim.
- **Size defaults.** 70 × 63 mm, frame 2.5 mm, thickness 0.8–3.0 mm, hang hole 3.6 mm (optional). Fits a K1 many times over.
- **Light.** A single LED puck, strip or phone torch behind it; or a lamp base in LITHO-6.
- **Tests.** contract (above); outline area within ±1 % of the analytic outline; frame width ≥ 2 mm everywhere; hang hole present and ≥ 1.5 mm of material around it; golden-image orientation test (the picture is not mirrored from the viewing side).
- **Effort 1 day** for heart/round/star specifics, hole and foot (LITHO-3), on top of the 2-day framework in LITHO-1. **Feasibility: high.**

### 3.2 Globe / sphere: two hemispheres with an LED or tea-light opening
- **Geometry.** Radial heightfield on a polar grid: image is sampled with an azimuthal-equidistant mapping (centre of the picture at the pole), inner radius fixed (smooth inside, easy to clean), outer radius = inner + thickness. Optional circular opening at the pole (default 38 mm, see below). Prototype `[box]`: Ø100 mm hemisphere, 171,360 triangles, **0.35 s**, 97.5 × 99.5 × 49 mm, watertight; **gotcha:** the rim face winding had to be flipped before the mesh was consistently wound (it was watertight but inconsistent at first).
- **Two halves.** Half A: picture + 38 mm opening for an LED tea light (wax tea lights are about 38 mm × 16 mm; LED ones are usually 38 mm wide but often taller `[web]`). Half B: second picture (or the same) closed, with a registration lip. Lip size and clearance (0.2–0.3 mm) are **untested until Zach prints**.
- **Safety:** LED tea lights ONLY; never a real candle (PLA melts); the opening must also not trap heat (no mains, no incandescent bulbs).
- **Printability.** Print dome-up, rim on the bed (the outer surface faces up). The inner surface is a ceiling: **13.7 % of the surface is past 45 °** for the closed hemisphere and **10.6 %** with the 38 mm opening `[box]`; dome-down is worse (17.6 % / 14.7 %). Generic-profile slices work (opening version, 0.12 mm: 374 layers, **4 h 12 m, 35 g**; closed pole at 0.2 mm: 245 layers, 2 h 59 m, 38 g) `[box]`, but **a slicer finishing is not a good dome**. Options to test: tree supports only under the cap, a slightly larger opening, or a pole disc. Needs a real print `[Zach]`.
- **Size defaults.** Ø100 mm halves (100 × 100 × 50 mm each; both on one K1 bed), thickness 0.8–3.0 mm (on a sphere the light enters at roughly 90 ° if the LED is at the centre, so the path equals the thickness).
- **Tests.** contract; opening diameter ±0.2 mm; both halves' lips mate (clearance measured by `trimesh` distance); the K1 plate holds two halves; overhang-area report logged (informational).
- **Effort 4 days. Feasibility: medium** (geometry high, printed result unknown).

### 3.3 Curved panel and cylinder lamp
- **Geometry.** Periodic grid tube (θ across, Z up), inner radius fixed, outer = inner + thickness; partial arcs (90–270 °) use the same code with open edges closed by walls; full 360 ° adds a base ring (LED or tea-light pocket, optional) and an optional top ring. Prototype `[box]`: Ø80 mm × 100 mm cylinder, 205,920 triangles, **0.11 s**, 86.0 × 86.0 × 100 mm (the picture adds up to 3 mm to the radius), watertight.
- **Printability.** Stand it on its ring: walls are vertical, **only 1.5 % of the surface faces down** (the bed contact) `[box]`; no supports. Generic slice, 0.12 mm layers: 833 layers, **8 h 12 m, 73 g**; this is the slow one (K1 may be faster; unverified). Print-time and filament are shown in the Print dialog.
- **Size defaults.** Ø80 mm, 100 mm tall, 360 columns (≈0.7 mm per pixel; the print is limited by the 0.4 mm nozzle anyway), thickness 0.8–3.0 mm, seam placed at the back.
- **Tests.** contract; diameter ±0.2 mm; seam is closed (no open edges); picture wraps once (columns 0 and N-1 differ by one pixel step); triangle cap < 400k.
- **Effort 3 days** (arc, tube, base ring, lamp fit). **Feasibility: high** (geometry), **medium** (a lamp that fits his lights `[Zach]`).

### 3.4 Car-mirror hanger ornament
- **Geometry.** Same engine as the heart: round / oval / rounded rectangle, 60 × 45 mm, 2.4 mm max, hang hole 4 mm with ≥ 3 mm ring, small loop or slot for a cord. **Flat-on-bed print, no supports.**
- **Light.** It is a *sun-catcher*, lit by daylight through the window: use the "thin" range (0.6–2.4 mm) as the default.
- **Cautions (these go in the UI text):** (1) PLA can soften in a hot parked car; use a heat-resistant filament, check the spool's datasheet `[Zach]`; (2) rules on hanging things from a mirror vary by place and a small item can still count as blocking the view `[web: Morning Call, Virginia code]`; so: "check your local rules; keep it small; don't let it hang in the driver's view". **Kenji to word and approve.** (3) Small part, strangulation/choking notes for young children.
- **Tests.** contract; hole centred in ring ≥ 3 mm; overall area ≤ 60 cm².
- **Effort 1 day** after LITHO-1/3 (it is mostly a preset; part of LITHO-4). **Feasibility: high.**

### 3.5 Ornaments
- Round, star, tree, bauble (flat), plus a **"two-sided" disc** (front and back picture, 3 mm total) as a stretch; hang hole top; same engine as 3.1.
- Printability: flat on the bed, 0.12 mm layers; ≈ 70 mm; 1.0–3.0 mm.
- Tests: contract + outline area + hole ring.
- **Effort 1.5 days** (LITHO-4 bundles ornament 1.5 + keychain 0.5 + hanger 1 = 3 d). **Feasibility: high.**

### 3.6 Keychains
- 40 × 40 mm, frame 2 mm, thickness 0.6–2.4 mm, ring hole 4–5 mm with ≥ 3 mm ring, rounded corners. Flat print, 20–30 min.
- Cautions: small part, a keyring is a strap/choking issue for the youngest children; fine for classes with a short note (Aiko/Kenji).
- **Effort 0.5 day** on top of 3.5. **Feasibility: high.**

### 3.7 Night-light frames
- **Geometry.** Flat lithophane (rectangle or heart) + frame + a **stand with a pocket for a battery LED puck or tea light** (default Ø38 × 17 mm) and a back cover with a vent slot; user can type the light's Ø × height. Prior art for "frames to fit a night light you can buy" exists (Lithophane Maker night-light maker, ItsLitho night-light attribute `[web]`); we adopt the *idea* of typed dimensions.
- **Safety stance:** battery/USB LED lights only; no plug-in mains night lights (heat, wiring, liability); no candles. **Kenji to review** the wording.
- **Printability.** Panel upright, stand flat, parts printed separately, clearance 0.3 mm (untested).
- **Tests.** contract per part; pocket ≥ Ø(light)+0.6 mm; parts fit the K1 bed; assembled bounding box check.
- **Effort 3 days. Feasibility: medium-high.**

---

## 4. Colour (Experimental, everything "untested until Zach prints")

### 4.1 What the Creality K1 can do (honest, cited)
1. **Stock K1: one filament at a time.** Public specs show a single direct-drive 0.4 mm nozzle (`creality-k1-research.md` §1.1) `[web]`. So no colour mixing inside a layer.
2. **Colour by hand: swap filament at a layer height.** HueForge's own FAQ says its layered colour prints need "only Swap-by-Layer" and no AMS/MMU, and that "many images have just 3–4 colour swaps and can easily be managed by hand" `[web: HueForge]`. On a stock K1 community write-ups say to use a **PAUSE** at the layer (Creality Print: Preview → right-click the layer slider → *Add Pause*) rather than M600, and warn that Creality Print's *Change filament* can insert a tool-change that does not suit a single extruder `[web: Creality forum threads, community, not official]`. I have not tried any of it on a K1 → **Experimental**.
3. **Multi-colour K1 = K1 + Creality CFS upgrade.** Creality sells a *K1 Series CFS Upgrade Accessory Kit* (new cutter extruder + run-out sensor + CFS) for K1 / K1C / K1 Max / K1 SE with an integrated (quick-swap) nozzle, **not** for the 2025 K1C/K1 Max versions; with CFS the K1's printable area becomes **220 × 215 × 250 mm** `[web: Creality store pages]`. The newer **CFS-C** lists K1, K1C, K1 Max, K1 SE and the 2025 K1C/K1 Max as compatible, 4 slots, one unit only, compatible filaments listed as **Hyper PLA, CR-PLA, CR-Silk** ("more via firmware update") `[web: creality.com CFS-C page]`. Earlier, Creality said the K1 series was *not* CFS-ready `[web: Creality forum FAQ, old]`. **`creality-k1-research.md` did not cover CFS; this section adds it.**
4. **Unknown for Zach:** which K1 (K1 / K1C / 2025), whether he has a CFS, which filaments (and whether any are translucent). → section 10.
5. **Slicer for K1 colour:** Creality Print is the natural slicer for CFS; our files are verified only in PrusaSlicer. A Creality-Print-flavoured 3MF is **not designed or tested**; for now the universal output is STL + a plain colour-change table (4.4).

### 4.2 (a) Colour lithophane by layers
**(a1) Swap-by-layer tinted lithophane (K1-friendly, Experimental).** The picture stays one-channel (brightness → thickness), but the *colour* of a pixel depends on how many colour layers its column contains. Printed **flat on the bed** (thickness = Z), as HueForge's devlog describes for backlit lithophanes `[web]`:
1. Pick a filament sequence from the bed up, e.g. base translucent white → yellow → red → deep blue/dark (user's own spools).
2. Every column contains the layers up to its top. Thin (bright) pixels only have the first filaments; thick (dark) pixels also have the later ones → a colour ramp from light to dark.
3. All swaps happen at the same heights for the whole print: **M−1 swaps** (3–4 for most images), by hand or with CFS.
4. Layer heights 0.08–0.12 mm are the common advice for smooth blends `[web: QIDI, FilaScope, Bake3D]`; use 0.12 as default on a K1 (print time!).
5. Honest limit: this gives **colourised monochrome** (a duotone-to-tritone look), not a full-colour photo. HueForge's own page says "NOT ALL IMAGES WILL WORK/LOOK GOOD" and full-spectrum images need special treatment `[web]`; we say the same.

*Prediction model (ours, simple).* Each filament f has per-channel absorption `k_f,c` (per mm); backlight L (colour/temperature); transmitted colour of a column `T_c(t) = L_c · Π_f exp(−k_f,c · d_f(t))` where `d_f(t)` is the thickness of f inside total thickness t. Calibration: print a step wedge for each filament (0.2 … 3.0 mm in 0.2 steps; public examples exist: `[web: Makeronline 4.8→0.2 mm test, HappyKatz transmissivity cards, American Filament calibration tower]`), photograph on the user's light, fit `−ln(T/T0) = k·d` per channel (a one-line least squares; we store k, not HueForge's "TD" number). The same wedge gives the **thickness-to-brightness curve** used in LITHO-8. Order effects and scattering are ignored (honest limitation); white filaments scatter, so predictions for stacked whites are rough.

**(a2) Stacked CMYK-style full-colour lithophane (Low, spike only).**
- Prior art: stacked translucent cyan / magenta / yellow over a white canvas (subtractive mixing); a *white* "key" instead of black because black blocks all light in backlit use; the same filaments need similar translucency; thin layers (0.08 mm) and a diffuse 5000 K+ backlight `[web: QIDI guide, FilaScope guide]`. Bambu Lab offers a PLA CMYK bundle plus its *Make My Lithophane* tool, whose wiki recommends a 0.2 mm nozzle, 0.15 mm first layer, 100 % rectilinear infill and matching AMS slot order `[web: Bambu wiki]`. Lithophane Maker has a "Color Lithophane Maker"; HueForge's devlog says it does *not* do the CMYK method `[web]`. We credit all of these.
- Sketch (ours): (1) pick filaments C, M, Y, W with calibrated `k`; (2) layer height h (0.08–0.12), total stack ≤ 3.0–3.2 mm → N ≈ 25–40 layers; (3) enumerate all integer layer-count combos `(nW,nC,nM,nY)` with sum ≤ N (about 31k combos for N = 27, 4 filaments), predict each colour with the model above, convert to Lab; (4) for each image pixel (gamut-mapped first: luminance squeezed into the reachable range) find the nearest combo in a k-d tree (scipy `cKDTree`; ~30k pixels = milliseconds); (5) place each filament as a per-pixel Z interval in a fixed order (white on the light side, then Y, M, C; the best order is a calibration question `[Zach]`); (6) export one object with four volumes (per-filament slabs between two height fields).
- Why Low: every layer has several filaments side by side → a tool change per filament per layer (hundreds) → needs a multi-material system with purge/waste; K1 would need CFS and RFID-listed filaments (translucent lithophane filaments are probably not on Creality's list: unverified); calibration per filament; unknown real colour accuracy. **Do not start until Zach has the hardware and the a1 result.**

**Output formats (ordered, all Experimental):**
1. STL (the stacked height field) + **colour-change table** in plain words: "Layer 17 (Z 2.04 mm): swap to red", layer numbers computed for the chosen layer height (works in any slicer; this is the HueForge-style text file `[web]`).
2. **PrusaSlicer 3MF** with `Prusa_Slicer_custom_gcode_per_print_z.xml` (single extruder: M600 or K1 `PAUSE`) and, for multi-material, `Slic3r_PE_model.config` volumes with extruders. Both slice in PrusaSlicer 2.9.2 `[box]`, **not tested in any other slicer or any printer.**
3. Orca / Bambu / Creality-Print flavours: **later**, after Zach says which slicer he uses. (Public sources suggest Orca stores pauses in `Metadata/custom_gcode_per_layer.xml` `[web: community extract of Orca source]`, unverified by me.)

### 4.3 (b) Multi-colour raised images (colour per layer height)
- **Exists:** pop-art levels with a palette; the STL (sloped risers) is the safe single-colour export.
- **Add (single extruder, K1-friendly):** pop-art-style raised image with N levels; the colour of level k is the colour of the layers between `base + (k−1)·step` and `base + k·step`; the user picks the colours (palette field already exists); export = STL + colour-change table + PrusaSlicer 3MF with custom G-code per print Z (`M600` or `PAUSE`). Layer step and base must be multiples of the layer height (the UI already offers 0.2 mm steps; enforce multiples of the layer height).
- **Add (multi-material):** the corrected PrusaSlicer 3MF (the fix verified in section 1.4) so each level becomes a volume with an extruder.
- **Prerequisite bug:** the current multi-body 3MF collapses into 4 plates in PrusaSlicer (1.4). It is a prerequisite.
- Raised images are **front-lit** (reflected light), so thickness doesn't matter for transparency and 0.2 mm layers are fine.
- **Effort 3 days** (incl. the export fix). **Feasibility: high** (single extruder) / **medium** (multi-material, per slicer).

### 4.4 Colour-change table (plain words)
Example the app will print on screen and in the file: *"Print with 0.12 mm layers, first layer 0.12 mm. At layer 18 (2.16 mm) pause and change to Red. At layer 25 (3.00 mm) pause and change to Dark blue. Heights are exact only if your slicer uses the same layer height."* Flagged **Experimental**.

---

## 5. Thickness-from-brightness mapping
- Today: **linear** (see 1.1). Real light follows `exp(−k·t)`: equal thickness steps do not give equal brightness steps; a linear map crowds the highlights.
- Plan (LITHO-8): option **"Light curve"**: choose `t(g)` so predicted brightness `exp(−k·t)` follows the picture brightness, bounded by `tmin..tmax`; default `k` from a filament profile (until measured: the generic value is **clearly labelled a guess**). Also **snap thickness to whole layers** (`t = n·layer_height`) to avoid slicer rounding surprises (and show how many tonal steps the user really gets: 3 mm at 0.12 mm = 25).
- Both options Experimental until Zach's step-wedge photo confirms they look better to him. No "better than" claim.

---

## 6. Printable colour guide / template sheet (paper): at most, not promised
- **Maybe** (LITHO-13, ≤ 1.5 days, last in the queue): one PDF/PNG made from the user's own colour-change table: a side-view stack diagram (heights, layer numbers, filament names and swatches), the swap steps for K1 (pause), and a blank "log your result" box. A second page could be a **step-wedge reference** with labelled steps to compare against the printed wedge.
- Not promised because: colours on paper depend on the user's printer/screen, so it can only be a *guide*; the useful thing is the table (4.4). The wedge STL itself (adapt public designs, see 12) is the real calibration tool.
- Related prior art: ItsLitho exports a matching colour image to print on **paper placed behind a white lithophane** so no multi-material printer is needed `[web: skipthecad review of ItsLitho]`. Not planned; mentioned as a K1-friendly idea for later.

---

## 7. Mode dropdown (open dependency)
Yami says to see Sakura's message about the Mode dropdown. Today Studio chooses the mode with three large cards (Lithophane / Relief / Pop-art, `static/index.html:43`) and the Edit tab is a separate tab. I did **not find her message on the board or in `reports/` as of 19:55 CT**, so the shape picker, the Experimental colour chip and the Beginner copy are **blocked behind it** (LITHO-14). Geometry/API tickets (LITHO-1..13) are independent. Nothing asked.

---

## 8. Public research: adopt / adapt / reject
| Source | What it showed | Decision |
|---|---|---|
| HueForge (Horn & Rhode) | Swap-by-layer colour, "Transmission Distance (TD)" per filament, Lithophane mode (backlit, taller = darker), exports a text file of swap heights, slicer-flavoured 3MF on their roadmap, honest "not all images work" | **Adapt the ideas** (swap table, calibration-driven prediction). **Reject** copying TD values or their filament library; we store our own per-filament measurements. Credit in docs. |
| Bambu Lab *Make My Lithophane* + PLA CMYK | CMYK-style stacked layers with a white key, 0.2 nozzle, 100 % rectilinear | **Adapt** the white-key lesson and settings advice for the spike. Credit. |
| QIDI guide, FilaScope guide | CMY over white, similar translucency, 0.08 mm layers, dry filament, diffuse 5000 K+ light | **Adopt** as guidance text (cited). |
| Lithophane Maker (lithophanemaker.com) | Heart, lamp, globe, curved, night-light, ceiling-fan, circular, colour makers | **Credit** as long-standing prior art; we implement our own geometry. |
| ItsLitho | Plane, arc, cylinder, sphere, vase, bell, pumpkin, lamp-shade, heart; frames, loops, night-light holders; paper-colour approach | **Credit**; ideas only. |
| Makeronline step test, HappyKatz transmissivity cards (Printables), American Filament tower | Public calibration wedges | **Adapt** into our own generated wedge STL; check each licence before bundling any file (we will generate ours, not copy). |
| Lithophane guides (3dprinterstuff, Nozzle Down, American Filament, Bake3D, Vextrude) | min 0.6–0.8 mm, max 2.8–3.2 mm, 0.1–0.12 mm layers, 100 % infill / many perimeters, upright | **Adopt as defaults to test** (white PLA), cited. |
| PrusaSlicer 3MF custom G-code / OrcaSlicer pause file | Where colour changes live | **Adopt** (PrusaSlicer verified `[box]`; Orca unverified). |
| Creality CFS pages | K1 multi-colour needs the CFS kit/CFS-C | **Adopt** as the factual basis for K1 claims. |

---

## 9. Ordered tickets (priority order; effort in working days; feasibility H/M/L)
Effort: S ≤ 0.5 d, M = 1–2 d, L = 3–5 d. All start after the safety batch.

| ID | Ticket | Eff. | Feas. | Acceptance tests |
|---|---|---|---|---|
| **LITHO-1** | Shape framework: `shape` param (default `flat`), crop-to-fill, outline engine (heightfield + one manifold intersection + frame via thickness field + optional hang hole), `Model.info` contract, shared "shape contract" test helper (watertight after STL float32 round trip, K1 bed fit, triangle cap, golden orientation) | 2 | H | Old `flat` build bit-identical to today (existing 3 lithophane tests pass unchanged); a deliberately broken two-body union fails the contract test; contract helper used by every later ticket |
| **LITHO-2** | Honest **Lithophane print profile**: allow 100 % infill for lithophane with `rectilinear`, 0.12 mm layer default, thin-wall setting, brim, per-shape orientation, first layer = layer height (also fixes colour heights), plain-words hint; K1 bed/profile used | 1.5 | H | Slice a lithophane at 100 %: no slicer error; layer count matches `height/layer`; first layer = layer height; hint text shown in Beginner without slicer words; existing slicing tests pass |
| **LITHO-3** | Heart + round / oval / rounded-square / star outlines; foot/stand so it does not stand on its tip | 1 | H | 70 mm heart: 70.0 ±0.2 mm wide, watertight, contract OK; `upright` slice does NOT fail with "no extrusions in first layer"; frame ≥ 2 mm; area within ±1 % |
| **LITHO-4** | Ornament, keychain and car-mirror hanger presets (hang holes, loops, size caps, cautions text) | 3 | H | hole ring ≥ 3 mm; area caps; text shown; presets build in < 1 s; hanger default thin range 0.6–2.4 |
| **LITHO-5** | Curved panel and cylinder lamp (arc 90–360 °, base ring, seam at back) | 3 | H geo / M print | Ø80 × 100: diameter ±0.2 mm; seam closed (0 boundary edges); triangle cap; slice smoke; image wraps once |
| **LITHO-6** | Night-light frame + stand (typed light Ø × height; LED/battery only wording) | 3 | M-H | pocket ≥ light + 0.6 mm; parts fit bed; assembled bbox; no mains wording in UI (Kenji review) |
| **LITHO-7** | Globe: hemispheres, 38 mm opening, mating lip, support advice | 4 | M | opening Ø ±0.2 mm; lip clearance ≥ 0.2 mm by distance test; two halves fit one K1 plate; overhang report in log |
| **LITHO-8** | Light curve + whole-layer snapping (Beer–Lambert option, `k` from profile or default-guess) | 1.5 | M-H | monotone `t(g)`; extremes respect tmin/tmax; snapped thickness is a multiple of layer height; golden thumbnails differ as expected; labelled Experimental |
| **LITHO-9** | "My filaments" profiles (name, hex, `k` from wedge photo or manual; stored per user, private) | 1.5 | H | CRUD tests; privacy: not in Showcase/exports; fit-from-photo gives `k` within 10 % on synthetic data |
| **LITHO-10** | Step-wedge generator (STL, 0.2 mm steps, labelled) + "how to photograph" text | 1 | H | all steps present at exact thickness ±0.01 mm; watertight; fits K1; prints in < 30 min `[Zach]` |
| **LITHO-11** | **Colour B first** (it fixes today's bug): PrusaSlicer-flavoured 3MF for pop-art (one object, volumes, extruders) + custom-G-code per Z + colour-change table; K1 `PAUSE` option; Experimental label | 3 | H | `prusa-slicer --info` size_z equals expected total; slice maxZ = expected; tool changes = levels−1 (multi-material) or `M600`/`PAUSE` count = levels−1 (single); change layer = exact multiple of layer height; file name contains "experimental" |
| **LITHO-12** | **Colour A1**: swap-by-layer tinted lithophane (flat print), thickness-path prediction preview, colour-change table, PrusaSlicer 3MF | 4 | M | swaps at exact layer numbers; predicted palette monotone in thickness; STL equals single-colour build; Experimental banner; round trip through PrusaSlicer slice |
| **LITHO-13** | Printable colour guide / step-wedge sheet (PDF/PNG) from the table | 1.5 | M | opens as A4/Letter; numbers equal the table; labelled guide, not colour-accurate. **Not promised; drop first if the schedule is tight.** |
| **LITHO-14** | UI: shape picker, size/light inputs, Experimental chips and copy (blocked on Mode dropdown, Sakura) | 3 | H | phone 390 px no overflow, 44 px targets, Beginner copy has no slicer words, Experimental text on every colour export |
| **LITHO-15** | Budgets: triangle caps per shape, disk per build (STL first, others lazily), memory; ties into the polish findings | 1 | H | cylinder/sphere builds < 250k tris on Beginner; build dir ≤ 30 MB for default shapes; polish tests pass |
| **LITHO-16** | Colour A2 spike (CMYW LUT solver, preview only, no promise) | 5 | L | prototype predicts a synthetic stack within ΔE ≤ 12 vs the same model (self-consistency only); decision memo; do not start without CFS + 4 suitable filaments `[Zach]` |
| **LITHO-17** | Claims & test log: update the claims table, record every Zach print (date, filament, light, result) | 0.5 | H | claims table matches `tested.json`-style data; nothing marked "printed" without a log line |

**Totals (sum of the table):** LITHO-1..7 = 17.5 d (geometry shapes; LITHO-1..6 = 13.5 d); LITHO-8..13 = 12.5 d; LITHO-14..17 = 9.5 d. **All = 39.5 d; without LITHO-13 and LITHO-16 = 33 d.** A sensible first release is LITHO-1, 2, 3, 4, 14, 15 (≈ 11.5 d) = flat shapes + honest print profile + UI; then 5, 11, 8, 12; the globe (7) and A2 (16) last.

---

## 10. Claims and tests
| Claim (what we may say) | Evidence | Status |
|---|---|---|
| "Shapes are printable solid models (no holes in the mesh)" | contract test: watertight after STL round trip, per shape | planned (LITHO-1); prototypes pass `[box]` |
| "Fits a Creality K1 bed (220 × 220 × 250 mm)" | bounding-box test vs `printers.bed_of` | planned; K1 size from Creality pages `[web]` |
| "Thickness 0.8–3.0 mm lets light through (white PLA)" | matches public guides, **not** measured on Zach's filament | **untested until Zach prints** |
| "Heart/ornament/keychain/hanger prints flat without supports" | slice smoke; heart flat sliced `[box]` | **untested until Zach prints** |
| "Cylinder lamp prints without supports" | 1.5 % downward-facing area (bed contact) `[box]` | **untested until Zach prints** |
| "Globe halves print without supports" | NOT claimed: 10–14 % of the surface is past 45 ° `[box]` | open; test print needed |
| "Light curve gives smoother tones" | not claimed until Zach compares wedge photos | **untested** |
| "Colour change at layer X" | PrusaSlicer 2.9.2 emits `M600`/`PAUSE` at the requested layer `[box]` | slicer-verified only; printer **untested** |
| "K1 can print this in colour" | only with a pause/hand swap (community) or CFS (Creality pages) | **Experimental; untested until Zach prints** |
| "Colour matches the preview" | never claimed; preview is a prediction | n/a |
| "Works with Creality Print / Orca / Bambu" | only PrusaSlicer was tested | **not claimed** |
| "Better than X" | never made | n/a |

## 11. Risks
1. **Dome overhang and joins** (globe): may need supports or a redesign; budget a second iteration.
2. **Wrong colours:** `exp(−k·d)` ignores scatter, order and light spectrum; mitigated by calibration + "predicted" wording; still may disappoint.
3. **Slicer variance:** only PrusaSlicer verified. Creality Print/Orca differ; Creality may change CFS support.
4. **K1 swap reliability:** `PAUSE` vs `M600` on stock K1 is community knowledge; a bad pause could crash a print; require a first test on a tiny model.
5. **Print time:** 0.12 mm layers make lamps 8 h+; show times before building (Print dialog already can).
6. **Memory and disk:** more triangles per build (200k+) on top of the polish findings (RSS and disk per build). Cap and lazy export (LITHO-15).
7. **Safety/legal:** car hanger wording, LED-only light sources, small-part notes (Kenji); filament heat in cars.
8. **Scope creep:** shapes expand forever; hold to the list; add by tickets.
9. **Mesh construction traps:** the two-body union (32 bad edges) and the sphere rim winding bug were found by tests; keep the contract test mandatory.
10. **Prior-art perception:** public tools exist for most of these shapes; we say "our own take" and credit them.

## 12. What needs Zach (smallest useful asks first)
1. **Printer facts:** K1 / K1C / K1 Max? Year (2025 model?)? Do you have a **CFS** (or the K1 Series CFS kit)? Slicer you use (Creality Print version)? Is the nozzle brass or hardened steel?
2. **Filament facts:** brands and colours you own; any **translucent / "lithophane" filaments**; is one a good **white** (and its datasheet temperature for the car hanger)?
3. **Light facts:** what will light the prints (LED tea light? USB LED? strip? phone)? colour temperature? Measure the tea light (Ø × height).
4. **Prints (each small first):** (i) the **step wedge** (LITHO-10): photograph it on your light; (ii) the **flat heart** (about 43 min); (iii) the **keychain/hanger**; (iv) the **cylinder lamp** (8 h, last); (v) one **globe half** to judge the dome; (vi) a **3-swap colour test** on a small raised image using Creality Print's *Add Pause* (and tell us what the K1 did); (vii) with CFS only: the multi-material version.
5. **Decisions:** keep the car hanger? (with caution text); OK to label all colour features Experimental in the UI and file names; which shape first (my proposal: heart, then ornament/keychain, then cylinder).

## 13. Sources (read this session)
- HueForge: https://shop.thehueforge.com/blogs/news/what-is-hueforge ; https://hueforge.wiki/index.php/FAQ ; https://devlog.thehueforge.com/p/what-is-hueforge-and-how-did-you ; https://devlog.thehueforge.com/p/what-exact-is-hueforge ; https://hueforge.wiki/index.php/HueForge_v8.1_UI_Break_Down
- Bambu Lab wiki, CMYK lithophane: https://wiki.bambulab.com/en/knowledge-sharing/CMYK-color-lithophane-printing-instructions (search extract; page itself did not render for me)
- QIDI colour lithophane guide: https://qidi3d.com/blogs/print-lab/multi-material-color-lithophane-printing-guide ; FilaScope: https://filascope.com/guides/backlit-lithophane-filament
- Calibration: https://www.makeronline.com/en/model/Lithophane%20test%20(4.8mm%20to%200.2mm%20with%200.2mm%20steps)/5255.html ; https://www.printables.com/model/1305294-light-transmissivity-test-cards ; https://americanfilament.us/blogs/3d-printing-guide/pages-beginners-guide-to-printing-lithophanes
- Lithophane settings: https://www.3dprinterstuff.com/workshop/lithophane-3d-printing-guide ; https://nozzledown.com/how-to-make-lithophane-tutorial/ ; https://bake3d.ai/guides/how-to-make-a-lithophane ; https://vextrude.com/blog-lithophane-guide
- Shapes prior art: https://lithophanemaker.com/ ; https://itslitho.com/ ; https://itslitho.com/itslitho-lithophane-features/ ; https://skipthecad.com/generators/itslitho/ ; https://itslitho.com/lithophane-guides/heart-lithophane-personalize-your-3d-printed-valentine-box/
- Creality CFS: https://www.creality.com/products/cfs-c-smart-filament-system ; https://www.creality3dofficial.eu/products/k1-series-cfs-upgrade-accessory-kit ; https://www.crealityofficial.co.uk/products/k1-series-cfs-upgrade-accessory-kit ; https://forum.creality.com/t/creality-k2-plus-cfs-frequently-asked-questions-you-should-know/21698
- K1 manual colour change (community): https://forum.creality.com/t/filament-change-color-change/5862 ; https://forum.creality.com/t/change-colour-mid-print-using-pause-in-cp-did-not-work/22160 ; https://forum.creality.com/t/how-to-pause-when-printing-k1/928 (search extracts)
- Slicer formats: PrusaSlicer `src/libslic3r/Format/3mf.cpp` / `CustomGCode.cpp` (search extract; I confirmed the behaviour by running PrusaSlicer 2.9.2 here); Orca `bbs_3mf.cpp` (extract only)
- Tea light size: https://en.wikipedia.org/wiki/Tealight ; hanging items in cars: https://www.mcall.com/2021/04/16/explainer-can-cops-stop-drivers-for-objects-hanging-from-rearview-mirror-pennsylvania-is-one-of-six-states-with-such-laws/ ; https://law.lis.virginia.gov/vacode/title46.2/chapter10/section46.2-1054/
- Local: `reports/creality-k1-research.md`, `reports/slicer-and-infill-plan.md`, `reports/make-tab-plan.md`, `reports/engineering-polish.md`.

## 14. Housekeeping
Prototype scripts and STLs lived in a scratch folder (`/workspace/make-scratch/litho/`, deleted after this pass); the four preview renders are in `reports/qa_screens/litho-plus/`. Nothing in `app/`, `static/` or `tests/` changed; the live server was not touched.

## 15. Hansei (what could be wrong here)
- All prototypes used the repo's synthetic `tests/sample.png` (noisy), not real photos; renders in `qa_screens/litho-plus/` look speckled for that reason (they show shape only). I never checked photo orientation or mirror on a real photo.
- Slice times/weights come from the generic PrusaSlicer profile with 15 % infill, not the K1 profile's real behaviour; K1 times will differ.
- Overhang percentages are surface-normal statistics, not a layer-by-layer simulation.
- Public pages were read through search extracts in several places (Bambu wiki, Creality forum, Orca/PrusaSlicer source); I verified only what I could run here. Web claims about K1 pauses are community reports.
- The effort numbers assume one engineer, no UI redesign, and the safety batch done. Use the section 9 table as the source of truth.
- I did not test Creality Print, Orca, Bambu Studio, a real K1, a CFS, or any light.
