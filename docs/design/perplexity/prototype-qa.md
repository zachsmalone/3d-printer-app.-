# ZEIM design direction: QA inventory

This is a design prototype separate from the production ZEIM repository.

## Acceptance checks

- Studio, lithophane and appearance views: navigation, keyboard 1/2/3, one clear primary action, desktop 1440 and mobile 375.
- Studio: rendered WebGL geometry; orbit, reset, solid/wireframe full cycle; scale readout and exported bounds; material color; STL and OBJ imports; source unmodified; restore sample.
- Import boundaries: invalid STL, unsupported extension, long filenames and bad geometry show a failure rather than a false successful load.
- Theme: all six presets; each role; locked roles preserved during remix; all-locked feedback; live contrast ratios; automatic foreground safeguards.
- Mods: dark, focus grid, left-hand inspector and spacing; each on/off; desktop→mobile→desktop; reset defaults.
- Theme JSON: export, import round trip, malformed JSON rejected, invalid colors rejected. No executable plugin payloads or browser storage.
- Lithophane: sample and uploaded image; source/backlit/thickness modes; dimensions, thickness and gamma updates; light-temperature preview; invalid minimum/maximum blocks generation.
- Lithophane STL: dark thicker than light, bounds match dimensions, finite coordinates, consistent winding, undirected edges shared exactly twice; coupon export dimensions/range.
- Export boundaries: closed mesh is not the same as physically print-validated; simulated light is visibly marked uncalibrated; no claim of a production CAD engine, CMYK generator or slicer integration.
- Outbound reference links: actual user activation opens expected domain.
- Visual pass: studio, appearance, lithophane at desktop and mobile; dark and left-hand layouts; no horizontal overflow, illegible labels or page exceptions.
- Exploratory scenarios: white-on-white user palette; all locked then remix; reversed thickness bounds; imported filename with punctuation and long unbroken words.

## Intended scope limits

No account, production-repository change, CAD face reconstruction, mesh boolean engine, STEP/3MF parser, physical printer test, photo benchmark or automatic measured-filament calibration is included.

## Results

Executed through Playwright in Chromium with real button, input, file-input and keyboard interactions.

- Passed all six theme presets, role locks, all-locked feedback, white-on-white protection, opposed black/white surfaces and a bright-yellow accent.
- Computed small-text contrast audit: all three views across all six light presets plus dark mode; no text elements below 4.5:1 were found in that matrix. This is not a full WCAG conformance certification.
- Passed all four mods on/off, desktop→mobile→desktop layout changes and theme JSON export/import. Malformed/invalid theme files were rejected.
- Passed actual STL reimport with scale-preserving dimensions, tetrahedron OBJ import, material control, orbit/reset, wireframe/solid toggle, export and restoration. Invalid STL and unsupported STEP imports were rejected.
- Passed local image input, preview-mode changes, panel sizing, gamma and lighting, reversed-thickness validation and STL/coupon downloads.
- Independent mesh verification: test panel 150 × 112.5 × 3.2 mm; 77,920 triangles; no degenerate triangles, no edge-incidence or winding errors. Black-region thickness 3.2 mm, white-region thickness 0.8 mm.
- Coupon verification: 80 × 20 × 4.15 mm; no degenerate triangles, edge-incidence or winding errors.
- Verified reference-link popups for Realtime Colors, tweakcn and Coolors.
- Inspected desktop, 375 px mobile, dark and left-hand layouts; checked a short desktop window. No horizontal overflow or uncaught page exceptions in the exercised flows.
- Explored malformed files, long filenames, invalid thicknesses, locked palettes and extreme colors. No physical-print or calibrated optical-accuracy claim is made.

Artifacts: `qa/mesh-results.json`, `qa/contrast-results.json`, viewport screenshots and exported test STL files. A screenshot taken before a CSS transition or WebGL resize had settled was not treated as final evidence; captures were repeated after transitions and render frames settled.
