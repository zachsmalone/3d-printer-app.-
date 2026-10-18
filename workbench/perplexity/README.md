# ZEIM Perplexity workbench

An opt-in integration of the design work from the REA/ArtCraft-assisted review.
This does **not** replace ZEIM's existing editor, lithophane engine, homepage,
community, authentication, printer or slicing APIs.

## Open

Run ZEIM normally, then visit **`/workbench/`**. The existing `/` homepage is unchanged.
The header links back to the original ZEIM app.

The compiled files are committed under `static/perplexity-workbench/`, so Python-only
deploys and the current Docker image do not require Node or an extra build step.

## Edit and rebuild

```sh
cd workbench/perplexity
npm ci
npm test
npm run build
```

Commit both source and regenerated static assets. Production Python dependencies and
the app's CSP do not need to change. Manrope is self-hosted under its OFL license;
Three.js and Lucide notices ship with the bundle.

## Working prototype features

- Local STL/OBJ import, orbit/wireframe, uniform scale and STL export.
- Six themes, editable/lockable roles, remix, contrast safeguards and four layout mods.
- Validated theme JSON import/export; preferences are session-only.
- Flat lithophane image input, thickness/gamma/light controls, heightfield STL and coupon export.

Files are processed locally in the browser, not posted to ZEIM's APIs.
The preview does not inherit an existing build or login state.

## Deliberate boundaries

Mesh booleans, true CAD face/edge editing, STEP/3MF import, calibrated optical
simulation, printer/slicer wiring and color lithophanes are **not implemented here**.
The original ZEIM app already has additional edit and lithophane functionality;
this isolated preview is not its capability inventory or a replacement engine.

Read [`docs/design/perplexity/`](../../docs/design/perplexity/) for the design brief,
competitor review, verification and REA/ArtCraft provenance. Raw third-party DOM,
screenshots and environment captures are not redistributed in this public branch.
