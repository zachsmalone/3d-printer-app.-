# ZEIM QA: Originals + regression, 2026-10-12

**Commit tested:** `22f091bb078e69d0aa63fd7eb06c443f87b0b4e0` (origin/zeim tip, "CI: run on the zeim branch and allow manual runs"), separate worktree /workspace/qa/zeim_src. Scratch server on 127.0.0.1:8771 with temp PHOTO3D_DATA/PHOTO3D_OUT and PHOTO3D_MODE=local.
**Note:** `library/originals/` is **not in git** at this commit (it's untracked in /workspace/photo3d), so the Originals were QA'd from /workspace/photo3d/library/originals (read-only).

## Regression (/workspace/qa/regress)
Harness fixes (harness only, no app changes; backups saved as *.bak): (1) run.sh now uses a QA venv (/workspace/qa/venv; it inherits the photo3d venv plus requests/playwright) because the photo3d .venv has no `requests` any more; (2) uploads now send `photo_ack=true`. Without it, CR-5 rejected every upload with HTTP 400, so section a ERRORed and section d gave **false PASSes**; (3) Studio level switch: `#levelSwitch` was replaced by the `#modeSel` select.

| Area | 2026-10-04 (old code) | 2026-10-12 (22f091bb078e69d0aa63fd7eb06c443f87b0b4e0, fixed harness) |
|---|---|---|
| a pop-art 3MF/OBJ/STL (10) | PASS | 10/10 PASS |
| b Hollow vase: shells | FAIL (333 shells) | PASS (2 shells, 0 slivers) |
| b Hollow vase: wall ≥2 mm | FAIL (0.2 mm) | **FAIL**: probe min 0.206 mm, p1 1.22–1.25 mm (need ≥1.33), with or without drain |
| b Hollow sphere | PASS | PASS |
| c Simplify 0.5 | FAIL (−2.4 %, 2 NM edges) | **FAIL**: 58,976→57,564 (97.6 %), wt=False, 2 non-manifold edges, app still says watertight=True with no warning (c1, c2, c3) |
| d 10x1000 / 1000x10 size cap | FAIL (4M tris) | PASS: rejected HTTP 400 "very long and thin… crop" |
| e QA-1 stale model in Print | PASS | PASS |
| f QA-6 text off face | FAIL (accepted silently) | PASS: off-face returns 422; overhang warns specifically |
| g no horizontal scroll 320/375/390/768 | PASS | PASS |
| **Total** | **30 PASS / 10 FAIL** | **37 PASS / 5 FAIL / 0 ERROR** |

First run before the harness fixes: 23 PASS / 5 FAIL / 14 ERROR (the d PASSes were bogus).

## Bugs
1. **Hollow leaves walls thinner than requested** (app/ Hollow edit op). Steps: Edit → load static/sample_model.stl (vase) → Hollow wall 2 mm, with or without a 3 mm drain. Expected: min wall ≥ 2 mm − voxel (0.67) = 1.33 mm. Actual: ray probe min 0.206 mm, p1 ≈1.23 mm. The sphere is fine (≥1.48), so this is geometry-dependent (thin vase regions).
2. **Simplify barely reduces the mesh and breaks manifoldness, and the app reports it as OK.** Steps: Edit → load a_gear_bracket_binary.stl → Simplify keep_ratio 0.5. Expected: 40–60 % of triangles, still watertight. Actual: 97.6 %, 2 non-manifold edges, not watertight; the app analysis shows watertight=True with no warnings.
3. **Originals not committed.** library/originals (45 STL + PNG + manifests) only exists as untracked files in /workspace/photo3d; a clean checkout of zeim has none.
4. **rain-guard-bird-feeder plate does not fit the K1.** The plate is 144×439 mm (bed is 220×220). validation_report.json passes it on largest_single_part_mm, but the STL as shipped won't slice: PrusaSlicer says "All objects are outside of the print volume". Expected: split the plate into separate STLs or arrange it within 220×220.
5. **Calls with sub-nozzle features** (crow, doe, goose, mallard, open-reed, deer): 1–4.5 % of the wall samples are 0.3 mm. That is below 0.4 mm, so these features drop out at 0.4 mm/2 perimeters. They may be intentional reed slots, but this is not verified (see below).

## Originals (45 STL found; 45 expected; validation_report.json count 45, passed 45)
Geometry (trimesh, merged vertices): **all 45** are watertight and winding-consistent, with 0 open edges, 0 non-manifold edges, 0 degenerate faces and volume > 0. All are in mm (no inch or metre scale). Triangle counts and body counts match validation_report.json for 45/45. All 45 have a flat base at z-min (base area column). K1 build volume **220×220×250 mm**, confirmed on Creality's official compare page: https://www.creality.com/compare/compare-k1-flagship-series (the nozzle is 0.4 mm per https://www.creality.com/support/creality-k1-3d-printer).
Slicing: PrusaSlicer 2.9.2 CLI with a generic profile (0.4 nozzle, 0.2 layer, 2 perimeters, 15 % infill, no supports, 220×220×250 bed, centered). 44/45 sliced; rain-guard failed. Filament grams were not computed (no density set), so mm is shown. Scratch G-code was deleted.
Wall = the 1st percentile of an inward ray thickness from 1,500 surface samples; "thin" = % of samples <0.8 / <0.4 mm. Overhang = % of surface area facing down >45° (excluding the base).

**K1: PASS 26 / WARN 12 / FAIL 7**

| model | tris | KB | geometry | shells | vol mm³ | bbox mm | wall p1 | thin% <.8/<.4 | base mm² | overhang % | est time | filament mm | slicer warnings | K1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| adjustable-drip-spike-bottle | 17110 | 835 | OK | 3 | 24973.1 | 92.0x36.0x96.0 | 1.7 | 0.2/0.1 | 353.8 | 8.0 | 2h 34m 40s | 6915.79 | Low bed adhesion | **PASS** |
| bobwhite-slide-whistle | 34766 | 1697 | OK | 4 | 20588.7 | 93.1x20.6x78.0 | 2.18 | 0.3/0.3 | 619.6 | 1.9 | 2h 12m 17s | 6458.27 | - | **PASS** |
| bubble-helmet-explorer-bust | 80000 | 3906 | OK | 1 | 158874.4 | 74.0x61.8x103.6 | 3.28 | 0.0/0.0 | 3422.7 | 5.4 | 3h 27m 41s | 16954.36 | - | **PASS** |
| cable-pebble-holder | 80000 | 3906 | OK | 1 | 67524.0 | 90.0x64.0x21.8 | 3.1 | 0.0/0.0 | 4430.6 | 0.2 | 1h 40m 45s | 7666.37 | - | **PASS** |
| cam-cleat-guyline-tensioner | 9392 | 458 | OK | 3 | 10279.1 | 97.9x22.0x24.0 | 2.4 | 0.0/0.0 | 1220.7 | 2.8 | 1h 9m 38s | 3347.35 | Low bed adhesion | **PASS** |
| chubby-penguin-scarf | 75000 | 3662 | OK | 1 | 66270.1 | 54.9x44.0x69.0 | 5.38 | 0.0/0.0 | 124.7 | 8.7 | 1h 26m 24s | 7216.75 | Collapsing overhang | **WARN** |
| crow-caw-call | 39324 | 1920 | OK | 5 | 20952.2 | 108.3x33.8x53.0 | 0.3 | 4.1/4.0 | 531.8 | 0.2 | 1h 56m 50s | 6016.11 | Low bed adhesion | **FAIL** |
| deer-grunt-tube | 18858 | 920 | OK | 5 | 46066.9 | 135.1x52.9x100.0 | 0.3 | 1.3/1.3 | 598.6 | 0.1 | 4h 8m 12s | 15271.61 | Low bed adhesion | **FAIL** |
| dino-phone-stand | 79998 | 3906 | OK | 1 | 137809.2 | 148.3x63.5x53.7 | 1.82 | 0.0/0.0 | 565.0 | 14.9 | 3h 54m 54s | 17275.59 | Loose extrusions | **WARN** |
| doe-bleat-can-call | 36444 | 1779 | OK | 5 | 20438.7 | 108.8x37.9x53.0 | 0.3 | 4.5/3.6 | 480.3 | 1.3 | 2h 0m 34s | 6249.08 | Low bed adhesion | **FAIL** |
| elk-bugle-tube-kit | 25236 | 1232 | OK | 4 | 96501.8 | 141.0x105.9x135.0 | 1.91 | 0.5/0.3 | 1805.0 | 0.5 | 7h 37m 45s | 32519.83 | - | **PASS** |
| ember-baby-dragon | 80000 | 3906 | OK | 1 | 107021.1 | 90.2x80.9x89.9 | 2.4 | 0.0/0.0 | 425.3 | 13.7 | 3h 12m 17s | 13066.40 | Loose extrusions | **WARN** |
| field-kit-box-spring-latch | 3336 | 162 | OK | 3 | 39208.7 | 81.6x141.0x22.7 | 1.6 | 0.2/0.1 | 8283.5 | 3.6 | 3h 35m 37s | 12062.48 | Low bed adhesion | **PASS** |
| fish-bottle-opener | 70000 | 3418 | OK | 1 | 23213.4 | 104.8x47.0x13.0 | 0.83 | 1.0/0.3 | 2318.4 | 0.6 | 1h 0m 8s | 3708.75 | - | **PASS** |
| flower-fidget-spinner | 98000 | 4785 | OK | 2 | 13234.6 | 58.0x58.0x13.9 | 1.88 | 0.2/0.0 | 2499.0 | 15.4 | 1h 5m 1s | 3246.73 | Loose extrusions | **WARN** |
| gear-ratio-lab-board | 16312 | 796 | OK | 7 | 55556.4 | 146.1x148.0x21.6 | 1.0 | 0.1/0.0 | 11576.4 | 0.7 | 3h 25m 39s | 10948.03 | Loose extrusions,Low bed adhesion | **PASS** |
| goose-flute-call | 37596 | 1835 | OK | 5 | 50796.7 | 146.7x79.7x53.0 | 0.3 | 1.9/1.9 | 884.9 | 0.3 | 2h 51m 39s | 10959.88 | Low bed adhesion | **FAIL** |
| hinged-strap-tail-clamp | 3370 | 164 | OK | 2 | 23850.6 | 57.6x89.0x11.5 | 1.2 | 0.1/0.0 | 4453.2 | 2.8 | 1h 48m 11s | 5332.76 | - | **PASS** |
| horn-dino-band-popper | 90000 | 4394 | OK | 1 | 116560.8 | 56.4x128.2x67.4 | 4.41 | 0.0/0.0 | 226.1 | 15.6 | 3h 32m 37s | 14263.43 | Low bed adhesion | **WARN** |
| launch-day-comic-panel | 89996 | 4394 | OK | 1 | 53478.6 | 120.0x86.1x8.0 | 1.11 | 0.3/0.1 | 9721.2 | 0.4 | 2h 52m 23s | 10007.91 | - | **PASS** |
| mallard-style-duck-call | 37596 | 1835 | OK | 5 | 30242.4 | 125.2x43.7x53.0 | 0.3 | 2.9/2.8 | 685.3 | 0.4 | 2h 22m 15s | 7821.14 | Low bed adhesion | **FAIL** |
| moon-phase-wheel-plaque | 156354 | 7634 | OK | 1 | 61107.9 | 120.1x120.1x8.6 | 1.8 | 0.0/0.0 | 10690.2 | 0.9 | 3h 6m 14s | 11105.70 | - | **PASS** |
| octo-buddy | 80000 | 3906 | OK | 1 | 121432.2 | 102.9x102.9x55.8 | 4.25 | 0.0/0.0 | 2246.0 | 9.1 | 2h 44m 27s | 13074.11 | - | **PASS** |
| open-reed-predator-call | 35868 | 1751 | OK | 5 | 36992.6 | 132.9x53.6x54.0 | 0.3 | 2.0/2.0 | 585.3 | 0.3 | 2h 43m 10s | 9623.20 | Low bed adhesion | **FAIL** |
| owl-hooter-whistle | 39806 | 1943 | OK | 4 | 76565.0 | 146.1x34.4x120.0 | 2.8 | 0.2/0.1 | 1931.5 | 1.7 | 4h 46m 12s | 16829.58 | - | **PASS** |
| pocket-sundial-compass-plate | 5546 | 270 | OK | 3 | 48657.8 | 117.8x96.0x24.2 | 0.5 | 1.7/0.2 | 6760.6 | 0.6 | 2h 11m 36s | 7749.95 | Loose extrusions,Low bed adhesion | **WARN** |
| pow-comic-burst-plaque | 89998 | 4394 | OK | 1 | 55299.3 | 128.8x125.9x9.5 | 1.17 | 0.3/0.0 | 8987.0 | 0.3 | 2h 59m 37s | 10235.66 | - | **PASS** |
| pumpkin-trinket-jar | 114940 | 5612 | OK | 2 | 52842.8 | 145.0x67.5x35.8 | 2.35 | 0.0/0.0 | 1613.5 | 13.9 | 2h 46m 45s | 10815.57 | Long bridging,Loose extrusions | **WARN** |
| rain-guard-bird-feeder | 11548 | 563 | OK | 4 | 185991.1 | 144.0x439.0x90.0 | 1.91 | 0.2/0.0 | 16480.3 | 3.4 | no G-code | - | - | **FAIL** |
| roly-poly-hedgehog | 162374 | 7928 | OK | 5 | 155651.3 | 96.1x139.8x58.6 | 1.04 | 0.7/0.1 | 5027.2 | 3.2 | 4h 34m 59s | 17548.87 | Low bed adhesion | **PASS** |
| seed-slide-single-dispenser | 5720 | 279 | OK | 3 | 21155.8 | 119.0x54.0x22.0 | 0.6 | 1.6/0.5 | 2800.2 | 1.8 | 1h 18m 1s | 4480.31 | - | **WARN** |
| sleepy-loaf-cat | 75000 | 3662 | OK | 1 | 93723.4 | 61.9x84.5x59.4 | 7.0 | 0.0/0.0 | 36.6 | 20.4 | 2h 11m 40s | 10278.20 | Collapsing overhang,Loose extrusions | **WARN** |
| spring-gate-bottle-neck-clip | 16932 | 826 | OK | 1 | 6993.8 | 53.4x36.0x8.0 | 1.18 | 0.6/0.1 | 758.1 | 3.4 | 23m 5s | 1432.84 | - | **PASS** |
| sunrise-waves-plaque | 109996 | 5370 | OK | 1 | 116358.3 | 124.1x88.1x17.0 | 3.4 | 0.0/0.0 | 10574.9 | 0.6 | 3h 57m 24s | 16228.28 | - | **PASS** |
| teal-peep-whistle | 28586 | 1395 | OK | 3 | 9452.5 | 62.2x18.6x46.0 | 1.97 | 0.2/0.1 | 391.3 | 1.5 | 49m 57s | 2858.81 | Low bed adhesion | **PASS** |
| telescoping-lantern-mast | 15570 | 760 | OK | 3 | 76337.8 | 97.0x30.0x142.0 | 2.0 | 0.2/0.0 | 727.7 | 1.5 | 4h 6m 57s | 18173.34 | Long bridging,Low bed adhesion | **PASS** |
| trail-tool-fob | 8684 | 424 | OK | 6 | 15262.3 | 146.0x102.0x15.6 | 1.8 | 0.3/0.1 | 5764.3 | 0.0 | 1h 33m 56s | 4413.46 | - | **PASS** |
| tree-stump-pen-cup | 80000 | 3906 | OK | 1 | 150475.0 | 92.9x86.8x103.1 | 3.22 | 0.1/0.0 | 5330.7 | 0.3 | 5h 51m 40s | 25835.91 | - | **PASS** |
| turkey-diaphragm-frame-set | 2132 | 104 | OK | 4 | 1752.4 | 128.0x55.4x2.4 | 1.4 | 0.1/0.0 | 841.9 | 0.0 | 13m 36s | 677.79 | - | **PASS** |
| turkey-friction-pot-call | 7822 | 382 | OK | 5 | 57720.2 | 141.2x141.0x112.0 | 2.0 | 0.1/0.1 | 7187.6 | 0.2 | 3h 49m 2s | 11926.20 | Low bed adhesion | **PASS** |
| turtle-trinket-jar | 80000 | 3906 | OK | 2 | 65720.1 | 146.0x97.2x31.7 | 2.37 | 0.3/0.0 | 3803.5 | 10.1 | 3h 20m 48s | 12815.59 | Long bridging,Loose extrusions | **WARN** |
| twist-vase-pen-pot | 80000 | 3906 | OK | 1 | 59861.4 | 65.7x70.0x110.0 | 1.99 | 0.0/0.0 | 2052.6 | 0.0 | 4h 48m 7s | 20066.79 | - | **PASS** |
| wave-book-stand | 102822 | 5020 | OK | 1 | 122629.2 | 134.6x97.3x77.0 | 3.85 | 0.1/0.1 | 11617.2 | 3.7 | 5h 50m 6s | 20531.46 | Collapsing overhang | **WARN** |
| whale-tail-wall-hook | 69998 | 3417 | OK | 1 | 27066.9 | 54.7x66.0x62.0 | 0.7 | 1.7/0.0 | 2770.5 | 4.4 | 1h 30m 41s | 4687.61 | - | **WARN** |
| wiggle-gator | 106062 | 5178 | OK | 8 | 22382.6 | 146.0x33.6x14.3 | 1.44 | 0.5/0.0 | 1229.4 | 7.7 | 1h 43m 3s | 5065.69 | Loose extrusions,Low bed adhesion | **PASS** |

### K1 fail/warn list
- **WARN** chubby-penguin-scarf: slicer: collapsing overhang; small base 124.7 mm² (adhesion/tipping)
- **FAIL** crow-caw-call: features <0.4 mm: p1 wall 0.3 mm, 4.0% of samples <0.4 mm
- **FAIL** deer-grunt-tube: features <0.4 mm: p1 wall 0.3 mm, 1.3% of samples <0.4 mm
- **WARN** dino-phone-stand: supports likely: 14.9% of area overhangs >45°
- **FAIL** doe-bleat-can-call: features <0.4 mm: p1 wall 0.3 mm, 3.6% of samples <0.4 mm
- **WARN** ember-baby-dragon: supports likely: 13.7% of area overhangs >45°
- **WARN** flower-fidget-spinner: supports likely: 15.4% of area overhangs >45°
- **FAIL** goose-flute-call: features <0.4 mm: p1 wall 0.3 mm, 1.9% of samples <0.4 mm
- **WARN** horn-dino-band-popper: supports likely: 15.6% of area overhangs >45°
- **FAIL** mallard-style-duck-call: features <0.4 mm: p1 wall 0.3 mm, 2.8% of samples <0.4 mm
- **FAIL** open-reed-predator-call: features <0.4 mm: p1 wall 0.3 mm, 2.0% of samples <0.4 mm
- **WARN** pocket-sundial-compass-plate: thin walls: p1 0.5 mm, 1.7% <0.8 mm
- **WARN** pumpkin-trinket-jar: supports likely: 13.9% of area overhangs >45°
- **FAIL** rain-guard-bird-feeder: plate 144.0x439.0 mm exceeds 220x220 bed (largest part 144.0 mm fits; must be split/arranged); PrusaSlicer: 'All objects are outside of the print volume'
- **WARN** seed-slide-single-dispenser: thin walls: p1 0.6 mm, 1.6% <0.8 mm
- **WARN** sleepy-loaf-cat: supports likely: 20.4% of area overhangs >45°; small base 36.6 mm² (adhesion/tipping)
- **WARN** turtle-trinket-jar: supports likely: 10.1% of area overhangs >45°
- **WARN** wave-book-stand: slicer: collapsing overhang
- **WARN** whale-tail-wall-hook: thin walls: p1 0.7 mm, 1.7% <0.8 mm

Slicer "Low bed adhesion" warnings (on 17 models, mostly multi-part call kits) are listed in the table but not graded.

## Unverified
- Whether the 0.3 mm features on the calls are intentional reeds or slots (not inspected visually).
- The ray-probe wall estimate is statistical and can't resolve features <0.4 mm narrower than the sample spacing.
- Times come from PrusaSlicer's estimate with a generic profile, not Creality Print or real hardware.
