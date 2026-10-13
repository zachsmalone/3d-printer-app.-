# Lithophane upgrade specification

## Goal

Upgrade the existing photo-to-lithophane flow with curved/cylindrical output, hanging holes, stand presets, lamp kits, text/QR overlays, multi-photo bundles, AMS/MMU colour mapping, improved pop-art, and mesh decimation.

## Scope

- Build on the existing photo upload and lithophane/relief generation flow.
- Keep the current flat lithophane mode as the default.
- Add new output modes and accessories without breaking existing builds.
- Keep all generated geometry exportable as STL/OBJ/3MF and sliceable through the existing slicer flow.

## Phase 1: Curved and cylindrical lithophanes

### Flat mode

- Keep current behavior.
- Flat plate with configurable width, height, thickness, and relief depth.

### Curved mode

- Add a cylindrical arc parameter.
- User selects arc angle in degrees (default 90, range 30-270).
- User selects radius in mm (default 80, range 40-300).
- The lithophane wraps around the outside of the cylinder.
- Thickness is measured radially, not vertically.
- The image is mapped around the arc without stretching beyond the selected arc length.

### Cylindrical mode

- Full 360-degree wrap.
- User selects diameter in mm (default 80, range 40-300).
- User selects height in mm (default 100, range 40-300).
- Image repeats or tiles around the cylinder.
- Optional seam alignment at the back.
- Optional top and bottom rims for structural stability.

## Phase 2: Hanging holes and stands

### Hanging holes

- Add optional hanging holes at the top of flat and curved lithophanes.
- Hole diameter default 4 mm, range 2-8 mm.
- Hole spacing default 40 mm, range 20-120 mm.
- Hole inset from top edge default 6 mm, range 3-15 mm.
- Add reinforcement rings around holes to reduce cracking.

### Stand presets

- Add 3-5 stand presets: simple A-frame, curved cradle, cylindrical base, wall-mount bracket, and desk easel.
- Stands are generated as separate STL/OBJ/3MF files or as a combined multi-part export.
- Stand geometry must match the selected lithophane width, curvature, and weight.

## Phase 3: Lamp kits

### Lamp shade

- Cylindrical lithophane shade with optional top/bottom rims.
- Default diameter 100 mm, height 120 mm, wall thickness 1.2 mm.
- Optional light-hole pattern at the top for ventilation and cable routing.
- Optional bottom opening for a bulb or LED module.

### Lamp base

- Simple cylindrical or conical base.
- Optional cavity for LED strip, tea light, or small bulb.
- Optional cable pass-through.
- Base must be printable without supports where possible.

## Phase 4: Text and QR overlays

### Text

- Add optional text on the front or back of the lithophane.
- User selects font, size, position, and depth.
- Text can be embossed or debossed.
- Text must not interfere with the image relief.

### QR code

- Add optional QR code overlay.
- User provides URL or text.
- QR code is generated as a binary pattern and embossed/debossed.
- QR code size and position are configurable.
- QR code must remain scannable after printing.

## Phase 5: Multi-photo bundles

- Allow 2-6 photos in one lithophane layout.
- Layout options: horizontal strip, vertical strip, grid, or custom placement.
- Each photo can have its own crop, brightness, and contrast.
- Output is a single lithophane mesh.

## Phase 6: AMS/MMU colour mapping

- Map photo colours to filament slots.
- User selects number of colours (2-8).
- User assigns each colour to an AMS/MMU slot.
- Generate colour-separated regions in the 3MF export.
- Keep monochrome mode as default.

## Phase 7: Pop-art and decimation

### Pop-art improvements

- Add outline layers.
- Add drop-shadow offsets.
- Improve edge detection and colour separation.

### Mesh decimation

- Add automatic decimation for large lithophanes.
- Target triangle count configurable (default 100k, range 20k-500k).
- Preserve image detail where possible.
- Warn user if decimation may reduce quality.

## Print settings

- Default layer height 0.1 mm for detail.
- Default wall thickness 1.2 mm.
- Default infill 100% for lithophane body.
- Default material PLA or PETG.
- Orientation: flat lithophanes print flat; curved/cylindrical print vertically with supports as needed.

## Acceptance criteria

- Flat lithophane still works as before.
- Curved and cylindrical modes generate valid, watertight meshes.
- Hanging holes and stands are structurally reasonable and printable.
- Lamp kits generate a shade and base that fit together.
- Text and QR overlays are visible and functional.
- Multi-photo bundles combine images without overlap errors.
- AMS/MMU colour mapping produces valid multi-colour 3MF.
- Pop-art and decimation improve output without breaking existing features.

## Sources

- Roadmap item 7 lists curved/cylindrical lithophanes, hanging holes/stands, lamp kits, text/QR, multi-photo bundles, AMS/MMU colour mapping, better pop-art, and mesh decimation as planned Studio features.
- Existing repo already supports photo-to-lithophane/relief base generation, STL/OBJ/3MF export, and PrusaSlicer slicing.
