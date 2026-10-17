# Lithophane market gap: 10 features ranked by user value vs effort

Research date: October 17, 2026. Sources are vendor pages, tool guides, and user threads —
dates in parentheses. Repo status is against `app/core/litho_shapes.py`, `litho_light.py`,
`geometry.py`, `app/api/builds.py` on branch `perplexity/litho-features`.

## What the top makers do

- **ItsLitho** — described by reviewers as "the most complete lithophane maker online": shapes
  (plane, arc, cylinder, sphere, vase, bell, pumpkin, lamp), a built-in image editor (contrast,
  crop, flip, grayscale method), backlit preview, frames/borders, attributes (night-light
  fitters, LED puck holders, candle holders), multi-image uploads merged into one model,
  polygon/hexagon shapes, and color lithophanes (paper print behind the white print).
  Exports STL only ([skipthecad review, 2026-10-15](https://skipthecad.com/generators/itslitho/),
  [itslitho.com feature page, accessed 2026-10-17](https://itslitho.com/itslitho-lithophane-features/),
  [tool.itslitho.com, accessed 2026-10-17](https://tool.itslitho.com/)).
- **MakerWorld MakerLab "Make My Lithophane"** (Bambu) — mono and CMYK color modes, frames,
  3MF export tied to Bambu Studio, plus sibling tools (Lightbox Maker, folding fan)
  ([skipthecad category, accessed 2026-10-17](https://skipthecad.com/category/lithophanes/),
  [Gates Library patron guide, 2026-06-05](https://gateslibrary.org/wp-content/uploads/2026/04/3D-Printed-Lithophanes-Patron-Guide.pdf)).
- **LithophaneMaker.com** — one tool per object: lamp, night light, light box, globe with base,
  ceiling-fan cover, Christmas tree, and a dedicated **hangable** lithophane ("surrounds the
  lithophane with a frame and some holes for hanging... twine and suction cups")
  ([lithophanemaker.com, accessed 2026-10-17](https://lithophanemaker.com/index.html)).
- **3dp.rocks** — minimal, client-side, private: flat, curved, cylinder, dome, pillow, heart
  ([Nested Cube review, 2026-10-05](https://www.nestedcube.com/products/lithophane/)).
- **Cura/PrusaSlicer workflows** — Cura imports images directly (drag-and-drop with basic
  height settings), while PrusaSlicer does not generate lithophanes from images at all: its
  users go through an external converter and import the STL
  ([JLC3DP guide, 2026-10-17](https://jlc3dp.com/blog/lithophane-3d-print),
  [zipdo comparison, 2026-10-08](https://zipdo.co/best/lithophane-software/),
  [Xometry guide, 2026-10-15](https://www.xometry.com/resources/3d-printing/image-to-stl-file/),
  [Prusa blog, 2026-10-08](https://blog.prusa3d.com/lets-play-with-filament-transparency-how-to-make-amazing-lifelike-color-photos-with-just-a-simple-color-change_104338/)).
  ZEIM's photo → slice → print chain removes that hop for both slicers.

## What users struggle with (r/3Dprinting)

Vertical orientation, brim, and wobble dominate first-print threads ([first lithophane tips, accessed 2026-10-17](https://www.reddit.com/r/3Dprinting/comments/zat1cq/first_complete_lithophane_tips/));
polarity confusion (tool defaulted to negative) ([lithophane question, accessed 2026-10-17](https://www.reddit.com/r/3Dprinting/comments/neyv0t/lithophane_question/));
prints too dark (max thickness too high) and thickness silently scaling when the STL is resized
in the slicer ([JLC3DP problems section, 2026-10-17](https://jlc3dp.com/blog/lithophane-3d-print));
long print times ([first print thread, accessed 2026-10-17](https://www.reddit.com/r/3Dprinting/comments/rve8rd/super_happy_with_my_first_lithophane/)).

## The ranking (value ÷ effort)

A judgment call from the research above, not a measurement.

| # | Feature | User value | Effort | Status in repo |
|---|---|---|---|---|
| 1 | Hanging holes (hang on a window/hook) | High — window lithophanes are a common gift/display use; LithophaneMaker ships a whole tool for it | Low | **Was missing — built on this branch** (`app/core/litho_hang.py`, spec Phase 2) |
| 2 | Display stand / base | High — vertical prints need a base; guides and threads call it out every time | Low | **Was missing — built on this branch** (`app/core/litho_stand.py`, spec Phase 2) |
| 3 | Multi-image collage | Med-high — ItsLitho merges multiple uploads into one model | Med | Missing (single image per build) |
| 4 | Lamp kit: shade + fitter rings/holders | Med-high — a prominent ItsLitho attribute family | Med | Partial — nightlight sleeve with clearance exists; no shade/fitters |
| 5 | Color lithophane (CMYK/AMS) | High | High | Missing — `color_mode` hook exists, mono only |
| 6 | Polygon shapes (hexagon/triangle/pentagon) | Med | Low-med | Missing — flat shapes are heart/circle/star/square |
| 7 | Standard photo-frame sizes (4x6, 5x7...) | Med | Low | Partial — border exists, no frame presets |
| 8 | Light box (hollow box with plate face) | Med | High | Missing |
| 9 | 3MF export with print settings | Med — ItsLitho's top con is "STL only, no 3MF with print settings" | Med | Partial — 3MF export exists, no slicer settings embedded |
| 10 | Image editor (crop/straighten/paint-out) | Med | Med | Partial — placement (move/zoom/rotate) + tone controls; no crop/paint |

Curved/cylindrical output — the classic gap — is **already done** in this repo (globe, nightlight
sleeve, cup in `litho_shapes.py`), so the top two *missing* items are #1 and #2, both backend-only.

## Notes on the two built features

- Holes are cut through the rim (max-thickness material) with a manifold boolean, so the mesh
  stays watertight and the holes are structurally strong; the border auto-widens to
  `inset + hole_d/2 + wall` when needed and the real full-thickness rim is guaranteed to
  reach that width (the rect-path pad grows until `(pad - 1) * final pitch` covers it — the
  last padded row is a transition cell). The picture area shrinks slightly — the same
  tradeoff ItsLitho's frame makes.
- The stand is a one-piece U-channel sized to the panel's width and max thickness (groove
  exactly `groove_depth` deep, measured on the mesh), exported as a second body in the same
  download, parked beside the plate so the two parts never overlap in a combined print.
- Both are refused with clear client errors for curved shapes. Flat shapes are placement-
  dependent: the containment check refuses a hole that would leave the plate (with typical
  centered settings that means `heart` — top notch — and `star` — pointed top — are rejected
  with guidance; a wide enough rim and suitable settings can still work on other shapes).
- Not done: reinforcement rings around holes (spec Phase 2), stands for curved shapes, UI
  wiring in `static/edit.js` (Copilot's file — the API params are ready for it).
