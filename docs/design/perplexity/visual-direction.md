# ZEIM: the maker’s workbench

Visual direction, imported-file editing strategy and lithophane quality plan. Prepared October 18, 2026.

This is a proposed direction, not an approved brand system or a claim that the production app already has these features. The companion interactive preview is a separate prototype; no production ZEIM source or deployed service was changed.

## The product promise

“Your starting point doesn’t have to be your final design.”

Make ZEIM the place where someone can bring an existing model, understand what it is, adapt it to a real need, and leave with a usable print file. Photo-to-lithophane should be a focused, unusually reliable workflow inside that workbench, not a generic “photo-to-3D” claim.

- **Import first:** an existing file receives the same visual prominence as a new sketch.
- **Understand before editing:** identify geometry, units, mesh health and available operations.
- **Explain the next path:** replace mystery disabled buttons with “repair this opening,” “recover this face,” or “use a sketch cutter.”
- **Keep the original:** preserve source bytes and create a reversible derivative with explicit transformations and operation parameters.
- **Finish outside the cloud:** retain the existing “Open in your slicer” export direction; do not add printer-account linking.

## Visual direction

### Design lineage

Carry forward the persistent tool shell from the earlier source-assisted [ArtCraft review](https://github.com/storytold/artcraft), the structured model-detail pattern from [Printables](https://www.printables.com/model/1863827-heavy-duty-keyboard-holder-no-supports), the profile-oriented file presentation seen on [MakerWorld](https://makerworld.com/en/models/2490856-nuclear-launch-switch-keycap), and the copy/remix emphasis visible in [Tinkercad’s gallery](https://www.tinkercad.com/things). These inform ZEIM’s proposed layout; they are not claims that the prior pass verified those products’ complete editing workflows.

### Workshop, not dashboard

Use a quiet, lightly warm workbench with a large model viewport, compact navigation and one context-sensitive inspector. Avoid dashboard metrics, advertisements, a rainbow of status chips and a permanently visible wall of expert settings.

- **Persistent shell:** Remix studio, Lithophane lab, Appearance & mods; later add discovery and project-library views without replacing the editing shell.
- **Primary canvas:** faint grid, actual dimensions, orbit guidance, unambiguous selected geometry and a repeatable reset-camera action.
- **Inspector:** what is selected, what it is made of, what can change now and what preparation is needed.
- **Operation history:** proposed reversible stack with source identity, parameter values, recompute state, undo/redo and before/after comparison; not a fake recreation of an imported author’s original CAD history.
- **Community continuity:** model detail → editable copy → derivative → export; retain attribution, source license and remix eligibility. The previous competitor pass informs these patterns but did not verify every logged-in workflow.
- **Beginner and Expert:** same underlying file and model state, with progressive disclosure of tolerances and diagnostics. Do not tie light mode to beginners or dark mode to experts; theme is a personal preference.

### Default palette and tokens

| Role | Workshop value | Intended use |
|---|---|---|
| Background | `#F3F3EE` | Quiet workspace surround |
| Surface | `#FCFCF8` | Inspector, toolbar, inputs |
| Text | `#242D27` | Main labels and content |
| Accent | `#315F48` | Primary action, focus and active states |
| Material preview | `#9DB6A3` | Sample object only, not an actual filament prediction |
| Error | `#A42C2C` in light mode | Error semantics, not recolored by accent choice |

These are original proposed ZEIM values, not colors copied from a competitor. Use semantic variables, perceptually uniform palette generation in production, contrast-tested foregrounds and fixed semantic meanings for errors, warnings and selection.

- **Type:** Satoshi, using weight for hierarchy; 12 px minimum metadata, 14 px controls, 16 px body and a 24–32 px page title.
- **Spacing:** 4 px system; 24–32 px main gutters; compact but legible inspector.
- **Shape:** 4–8 px control radii, restrained borders, no inflated pill-shaped panels.
- **Motion:** functional state transitions; honor reduced motion. No auto-rotating models or distracting ambient effects.
- **Touch:** 44 px interaction targets and labeled controls. On phones, canvas and inspector stack; do not squeeze a desktop CAD layout into 375 px.

## Palette changer: which reference is best?

No universal winner is established by this review. My recommendation is to use tweakcn as the strongest detailed-settings reference, Realtime Colors for context and Coolors for rapid exploration.

| Reference | Verified feature | What ZEIM should adapt |
|---|---|---|
| tweakcn | Live colors, typography, radius, spacing and shadow controls, preset themes, contrast checking and Tailwind exports. ([tweakcn](https://tweakcn.com/)) | Advanced token controls, safe named presets and live component previews. |
| Realtime Colors | In-context website color preview, locking, contrast checks, undo/redo, light/dark switching and several color export formats. ([Realtime Colors documentation](https://www.realtimecolors.com/docs/how-it-works)) | Preview the actual workbench while changing roles; add theme undo/redo in production. |
| Coolors | Spacebar generation, locked colors, drag reordering, export/save and a color-blindness view. ([Coolors help](https://coolors-help.zendesk.com/hc/en-us/articles/360010581980-Generate-a-palette)) | Lock favorite roles and remix the rest; later add accessible palette suggestions and color-vision simulations. |

The tweakcn editor and Realtime Colors landing-page visualizer were also opened and visually inspected during this work. Coolors was documentation-reviewed, not interactively tested; the review does not establish comparative speed, reliability or a market-wide ranking.

### Three color systems, deliberately separate

- **Interface theme:** background, surfaces, foreground, accent, focus and semantic states.
- **Model appearance:** material or per-part viewport color. STL has no dependable standardized color/material export in this prototype; exporting STL does not bake in a UI or viewport color.
- **Physical print palette:** actual spools, layer swaps, transmission characteristics and printer-supported material assignments. A hex code is not a prediction of a printed or backlit result.

### Presets and mods

Proposed theme starts: Workshop, Kiln, Blueprint, Graphite, Tidepool and Orchid. Keep the product identifiable through typography, structure and interaction, even when users change its colors.

| Customization | In the companion preview | Production direction |
|---|---|---|
| Six theme starts | Working | Pair each with contrast-tested light/dark variants |
| Four editable color roles | Working with foreground safeguards | OKLCH-based generation, gamut handling and visible adjusted-color values |
| Lock and remix | Working | True palette history, harmony controls and accessible alternatives |
| Light/dark | Working | System, project and user settings with account persistence |
| Focus grid | Working | Grid size, units and scene-specific overlays |
| Left-hand inspector | Working on desktop | Full keyboard/touch interaction and configurable toolbars |
| Spacious controls | Working | Density, type sizing and scalable icons |
| Theme export/import | Working, validated JSON v1 | Versioned migrations, account sync and permission-aware sharing |
| Custom shortcuts, reusable tool presets | Not implemented | Conflicts shown before activation; easy reset |
| Plugins and code mods | Not implemented | Separate signed/permissioned extension architecture, not arbitrary scripts in a theme |

Do not let a theme hide an error, a destructive action or selected geometry. Provide reset and export before experimentation; an accessible fallback can override a bad foreground/background pairing even when a palette role is locked.

## Imported files: make real modifications possible

### Correct the competitive premise

Shapr3D does not require all editable content to originate inside its app: its documentation describes editing imported supported CAD parts, while noting that another system’s feature history does not carry across. ([Shapr3D CAD ecosystem](https://support.shapr3d.com/hc/en-us/articles/13807534145436-Shapr3D-in-a-CAD-ecosystem))

The narrower issue is imported mesh geometry: Shapr3D documents transformations and booleans on meshes, requires closed mesh bodies for booleans and says the result remains a mesh. ([Shapr3D mesh files](https://support.shapr3d.com/hc/en-us/articles/7874501863708-Mesh-files))

Position ZEIM around easier, clearer editing of imported meshes and mixed geometry, not “Shapr3D cannot edit imports.” Avoid “every STL becomes fully parametric” as well.

### Proposed capability routing

The following is an engineering target, not functionality delivered by the visual prototype.

| Incoming content | Initial interpretation | First editing path | Advanced editing path |
|---|---|---|---|
| STL / OBJ mesh | Triangle mesh; units may require confirmation | Transform, split, plane cut, hole cutters, booleans, mesh offset and text emboss/deboss | Fit planar/cylindrical regions, reconstruct selected CAD features where confidence allows |
| 3MF | Container with geometry, units and potentially parts/materials or slicer metadata | Parse documented supported fields; retain original metadata and show what will be lost | Component-aware operations and part-preserving 3MF export after compatibility tests |
| STEP / CAD solids | Boundary representation after validation | Direct face offsets, sketch-based additions/cuts, fillet/chamfer where topology allows | New ZEIM parametric history over imported base geometry |
| Scan or organic mesh | Dense/freeform geometry | Region tools, repair, controlled remeshing and limited edits | Approximate surface reconstruction with explicit error bounds; never promise exact feature recovery |
| Photo | Pixels, not a complete 3D object | Lithophane or clearly labeled relief | Color/backing workflows with material calibration |

Fusion is a useful technical benchmark: its documentation distinguishes faceted conversion from prismatic feature inference and organic conversion, and recommends repair and meaningful face groups before conversion. ([Autodesk mesh conversion](https://help.autodesk.com/cloudhelp/ENU/Fusion-Mesh/files/MESH-CONVERT-TO-SOLID.htm))

That is why ZEIM should not merely convert every triangle into an independent CAD face and claim the editability problem is solved. Proposed face recognition should fit geometry, report residual error and preserve the untouched source as a comparison reference.

### The import inspector

Proposed pipeline: identify → normalize units/transforms → diagnose → choose route → preview → apply → validate → export.

- **Identity:** filename, format, immutable source hash, local/remote provenance and importer version.
- **Health:** boundary edges, connected shells, manifoldness, normals, self-intersections, degeneracy and minimum feature scale. Do not show “watertight” until it has actually been checked.
- **Selected region:** display whether it is a triangle set, inferred plane, inferred cylinder or native CAD face.
- **Available actions:** show operations valid for this region and explain prerequisites for the others.
- **Precision:** show input/output deviation and unit-dependent tolerances; preserve fit dimensions such as hole diameters.
- **Recovery:** no silent decimation; keep measurements of maximum deviation and protect selected features.
- **Fail safely:** a failed boolean leaves the prior body intact; source, cutters and parameters remain available for retry.

Boolean failure handling matters: Blender’s manual distinguishes its solvers and their handling of overlap and non-manifold geometry; its Manifold solver does not work on non-manifold meshes. ([Blender Boolean modifier](https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/booleans.html))

### Editing acceptance suite

Use your own or appropriately licensed fixtures: a bracket STL, dimensioned enclosure STEP, open scanned mesh, dense curved STL, multi-part 3MF and a deliberately malformed file. Test:

- **Useful edits:** enlarge a mounting hole, add a cable opening, move a planar wall, add raised text, split with alignment pins and fillet an eligible recovered CAD edge.
- **Geometry checks:** bounds and units, volume where meaningful, manifoldness, self-intersections and signed source/result deviation.
- **Round trips:** reimport each exported format and compare dimensions, component identity and supported metadata.
- **UX failures:** ambiguous faces, failed reconstruction, oversized files and rejected operations must explain what happened without losing work.
- **Honest limits:** a mechanical STL and an organic scan should not receive the same precision or CAD-editability guarantee.

## Lithophanes: quality is the whole pipeline

### Current reference capabilities

- **ItsLitho:** image adjustments, multiple shapes, material and backlight previews, STL export and a color-backing JPG workflow already exist; a color backing is not the same as a multi-filament 3D print. ([ItsLitho features](https://itslitho.com/itslitho-lithophane-features/))
- **Lithophane Maker:** its color generator exposes lithophane resolution, colored resolution, layer heights and thickness bounds; it says correct filament choices and matching print settings matter. ([Color Lithophane Maker](https://lithophanemaker.com/Color%20Lithophane.html))
- **HueForge:** its documentation describes measured filament transmission-distance values, batch variation, user calibration and layer-swap instructions for predicted layered-color results; independent accuracy data was not supplied by this page. ([About HueForge](https://shop.thehueforge.com/pages/about-hueforge))

Therefore the opportunity is not “a color picker plus a pretty backlit preview.” The target is a more dependable route from a specific photograph, filament and light source to a good physical object.

### The proposed quality pipeline

- **Image preparation:** honor orientation and embedded color profiles; use managed working color; crop and frame non-destructively; offer manual brightness, contrast, gamma and restrained local adjustments. Keep faces and fine textures natural, not artificially sharpened.
- **Material calibration:** print a thickness coupon, record filament brand/color/batch, light source and measured transmission; allow manual measurements without requiring specialist hardware. Show “uncalibrated” until there is a valid profile.
- **Tone mapping:** dark areas map to more thickness for monochrome backlit panels; fit a monotonic measured transmission curve rather than treating a screen’s RGB value as a universal thickness rule.
- **Realistic simulation:** show ambient/unlit and backlit states with configurable light. Label model uncertainty; avoid calling an arbitrary exponential attenuation preview physically accurate.
- **Printer-aware detail:** derive mesh sampling from image information and feasible nozzle/layer capabilities. Separate preview resolution from export resolution and show the effective mm per sample.
- **Geometry:** manifold, closed output with consistent normals; borders, bases and frames designed not to destroy image detail. Curves and lamps come after the flat-panel baseline.
- **Print preparation:** profiles should account for nozzle, line width, layer height, speed, orientation, support/brim needs and truly solid image regions. Verify the sliced toolpaths instead of assuming a particular infill percentage guarantees solid coverage.
- **Delivery:** STL for simple single-material panels; validated part-aware 3MF for multi-part output when implemented; source/license, orientation, units and calibration instructions included in the project/export package.

ItsLitho recommends calibration for minimum/maximum thickness and gives print-setting guidance that varies with material, shape and machine; treat those as starting points, not universal settings to hard-code. ([ItsLitho slicer guidance](https://itslitho.com/itslitho-blog/slicer-settings-for-lithophanes-tweaking-to-perfection/))

### Keep color workflows distinct

- **Monochrome transmission:** one material, tone from thickness; the first quality gate.
- **Printed backing:** a registered 2D color sheet behind the panel; account for physical size, bleed, alignment and mirrored/back-side placement.
- **Multi-filament/CMYK:** real spool order, transmission behavior, available tool changes, layer height and printer capability. A material profile and slicer validation are mandatory before any color-match claim.
- **Filament painting:** reflectance/layered-blending artwork has different viewing conditions from a backlit lithophane. Do not combine their tone-mapping rules under one generic color slider.

### Benchmark before saying “best”

Proposed test plan: compare ZEIM against ItsLitho and Lithophane Maker on a consented, licensed image set covering portraits/skin tones, pets/fur, text, low-light scenes, high-dynamic-range scenes and smooth gradients. Add a separate color benchmark against an appropriate layered-color reference when that workflow is actually implemented.

- **Fair controls:** same physical dimensions, material batch, printer, nozzle, light source, camera exposure and a matched configuration for each method. Let each tool use documented recommended settings rather than intentionally bad defaults.
- **Repeatability:** repeat prints and include more than one filament and printer configuration before generalizing.
- **Measures:** blind human preference, face/detail preservation, banding, dimensional error, print success, material use and real sliced print time.
- **Image metrics:** align and normalize photographed backlit panels; report tonal and structural differences with controlled lighting. Do not substitute metrics for human inspection.
- **Color metrics:** evaluate under a defined illuminant after registration and calibration; report color error and gamut limits, not vague “photo-real” claims.
- **Release gate:** no leaks/non-manifold output in the fixture suite, no material loss in export, and physical-print evidence for every promised supported profile. Publish failures and support boundaries along with successes.

The target is measurable improvement. Superiority remains unverified until those tests are completed.

## Implementation sequence

### First: make imports trustworthy

Establish the source/derived-body data model, import diagnostics, units confirmation and an operation stack. Ship a tested subset of transforms, plane cuts, sketch cutters and booleans before attempting automatic CAD reconstruction.

### Next: ship a calibrated flat lithophane

Finish monochrome tone mapping, coupon workflow, mesh validation, resolution choice and printer/slicer fixtures. Validate actual prints before extending to decorative shapes.

### Then: deepen precision and expression

Add selected-region prismatic recovery, eligible fillets/chamfers, richer material-aware color workflows and safe shared workspace themes. Expand only after fixtures prove that geometry and metadata survive.

## What the companion preview actually does

- **Working:** local STL/OBJ import, Three.js orbit/wireframe viewer, uniform scaling, viewport color and binary STL export.
- **Working:** six presets, four role pickers, locks/remix, automatic text foreground protection, light/dark, grid, left-hand inspector, spacing and validated theme JSON import/export.
- **Working:** local PNG/JPEG/WebP input; flat-panel luminance-to-thickness generation; gamma and thickness controls; source/thickness/uncalibrated backlit views; a closed heightfield STL and thickness-coupon STL export.
- **Not implemented:** true face selection/editing, booleans, mesh repair, CAD reconstruction, STEP/3MF parsing, accounts, persistent preferences, measured-material calibration, color printing, full-resolution adaptive meshing or slicer integration.
- **Physical validation:** not performed. A topologically closed mesh is not proof of a successful or high-quality print.

The default sample is a generated landscape illustration for tonal demonstration, not a photograph or a competitor print result. Upload your own photo to exercise that path; processing in this prototype stays inside the current browser tab.

## Verification of this prototype

Playwright checks exercised the main controls, STL and OBJ imports, modified export/reimport, theme JSON round trips, all four mods, malformed inputs, contrast safeguards and the image-to-STL path. Desktop and 375 px mobile layouts were inspected, including dark and left-hand variants.

The exported black/white test panel measured 150 × 112.5 × 3.2 mm, with 3.2 mm thickness in the dark region and 0.8 mm in the light region. Its 77,920 triangles passed the independent edge-incidence, winding and degeneracy checks, as did the thickness coupon; these are topology checks, not a physical print test.

A computed small-text contrast check found no sub-4.5:1 text pairs across all three views in the six light presets and the tested dark theme. This is a bounded contrast audit, not a complete accessibility certification, and does not prove every possible user-entered palette is perfect.
