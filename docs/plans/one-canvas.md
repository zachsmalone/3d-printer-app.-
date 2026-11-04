# One Canvas — plan (doc only, no code)

Direction from Zach: the model is the product. One persistent Three.js scene and one model store live for the whole session. Lithophane, CAD, FDM, TorchC0 and Fix are toolsets that swap in and out around it. Showcase and Me become overlays. Base: `zeim` @ 1e469bd.

## (a) Current state (from the code)

| Area | How it gets its viewport | Where friction happens |
|---|---|---|
| Nav | `static/index.html:30-38` has 9 `data-view` sections: Showcase, FDM Slicer, TorchC0, CAD, 2D→3D, Lithophane, Smart Fix, Learn, Account | Each section is its own panel, which gives the user "mental tabs" |
| Lithophane / FDM (`app.js`) | `app.js:78` `new Viewer($("#viewer"))` | `showBuild`/`showPhotoBuild` (`app.js:376,413`) replace the group's contents |
| Edit workspace (`edit.js`) | A **second** `Viewer` at `edit.js:38` on `#editViewer` | "Open in CAD" leaves the page (`edit.js:206`, `index.html:531`) |
| TorchC0 (`torchc0.js`) | One `Viewer` per element, cached in a `views` Map (`torchc0.js:13`) | Separate scene, and selection is not shared |
| 2D→3D (`ai3d.js`) | Its own `Viewer` at `ai3d.js:136` | — |
| G-code preview (`gcodeview.js`) | Its own renderer and scene (`gcodeview.js:79-83`) | — |
| CAD (`static/cad.html` + `cad.js`) | A **separate page** with its own renderer and scene (`cad.js:125-130`) | Full page load. The mesh comes back from the server through `?bid=` (`handoff.js:138`, `project-flow.js:250,268`, `studio-library.js:136`, `community.js:205`). Camera and selection are lost both ways |
| Parts builder (`builder.html`/`builder.js:108`) | Another separate page with its own `Viewer` | Sends the user to `/#slicer`, gives a download link, or opens `cad.html?bid=` (`builder.js:146,198`) |
| Repair (`repair.html`/`repair.js`) | A separate page | `location.href = "/?edit=…#slicer"` (`repair.js:89-120`) means a full reload |
| Publish | `handoff.js:116` `location.href="/?publish="` | Full reload |
| Account | `community.js:361,467,493`, `zeim-account.js:26` | `location.reload()` drops whatever is in the canvas |

`viewer.js` (`Viewer` class, 184 lines) is the one shared building block, and it already disposes geometry (`viewer.js:155-179`). Today there are **at least 6 WebGL contexts across 4 HTML pages**. Every hand-off to another page goes through a server build id, so the user effectively exports and re-imports. Persistence today: `worksave.js` handles autosave for index and CAD, and the service worker (`sw.template.js`) caches each version.

## (b) Target architecture

- **`static/core/store.js`**: a small evented store with no framework. Shape:
  `{ meshes:[{id, geometry(BufferGeometry ref), bid?, name}], selection:[ids], origin:'photo'|'cad'|'upload'|'ai'|'builder', manifold:{ok, checkedAt, issues}, process:'fdm'|'resin'|'both', mode, history:{past[], future[]} (geometry diffs or snapshots, capped by bytes), dims, estimate }`.
  Subscriptions work per key. `bid` is a cache key for server calls. It is not how the mesh moves between modes.
- **`static/core/stage.js`**: owns the single renderer, scene, camera, controls and selection outline (1px `#00D1FF`). It extends `Viewer`. Modes add overlay groups such as plate, supports or a sketch plane, and remove them when they exit. They never own a renderer. The G-code preview becomes a layer on the stage.
- **`static/core/modes.js` registry**: `registerMode({id, ribbon:[tools], panel(el, store), enter(stage, store), exit(), relevant(store)})`. Switching modes calls the old mode's `exit()`, then the new mode's `enter()`, and swaps the ribbon and panel. The camera and store are left alone. The registry feeds the compact switcher and Cmd+K.
- **Routing (`core/route.js`)**, a pure function of the store, so it can be unit-tested:
  - photo → Lithophane. After Generate, the primary button is Slice (Resin if `process==='resin'`, otherwise FDM). Edit, Fix and Share are secondary.
  - mesh upload → run the manifold check automatically. If it fails, Fix is primary. If it passes, Slice for the preferred process.
  - Any geometry change that breaks manifold puts the Fix badge back and makes Repair primary.
  - Resin tools show only in TorchC0 or when resin is the process. Filament slots show only in FDM. Irrelevant tools are hidden, not greyed out.
- **Server**: unchanged. Slicing and repair stay server-side. The client uploads the current geometry **once** and gets a `bid` back. After that it reuses the `bid` until the geometry changes (a content hash decides).

## (c) Migration: small PRs, each one ships working

Order follows Zach's priority. Size is relative only.

1. **PR1 – Store + stage shell (M).** Add `core/store.js` and `core/stage.js`. The `app.js` viewer starts writing into the store. Nothing visible changes. Add unit tests for the store and history.
2. **PR2 – In-page modes fold onto the stage (L).** Lithophane, FDM, TorchC0, Edit and 2D→3D all use the one stage. Remove the extra `new Viewer` calls in `edit.js`, `torchc0.js` and `ai3d.js`. "Send to…" becomes a store mode switch with no fetch.
3. **PR3 – Repair and builder in-canvas (M).** `repair.html` and `builder.html` logic become the Fix and CAD-primitives modes. The old URLs redirect to `/?mode=…`.
4. **PR4 – CAD into the canvas (L, likely split in two).** Refactor `cad.js` (2.4k lines, plus `cad-*.js`) so it runs on the shared stage as a mode. Keep `cad.html` as a thin wrapper until everything matches, then redirect it.
5. **PR5 – Context ribbon + side panel + status bar (M).** Built from the registry, with the 40–48px ribbon and a 280–320px collapsible panel.
6. **PR6 – Global undo/redo (M).** Geometry-changing tools push to `store.history`.
7. **PR7 – Data-aware CTAs (S–M).** `route.js` plus the preferred process setting (in Me and first-run, persisted).
8. **PR8 – Kill nav sections → switcher + Cmd+K (S–M).** Old hashes such as `#slicer` and `#cad` map to modes.
9. **PR9 – Design tokens (M).** CSS variables and fonts (Inter/Geist for UI, JetBrains Mono for numbers), applied everywhere. Remove the per-section themes.
10. **PR10 – Showcase + Me as overlays (M).** Replace `location.reload()` in account flows with store-preserving refreshes. "Open from Showcase" loads into the canvas and picks the mode.

PR1–2 are the core change. The later PRs depend on them.

## (d) Risks

- **Memory with 50–200MB meshes**: one scene helps, because today there are duplicate contexts. Undo snapshots could still blow up memory. Mitigations: cap history by bytes, store diffs or transforms instead of copies, keep the full mesh in one place, move history to IndexedDB, and dispose every overlay when a mode exits.
- **Server slicing stays server-side**: the hash-gated upload has to avoid re-sending big meshes, and stale `bid` values must not slice old geometry.
- **Mobile collapse**: the ribbon turns into a scroller and the panel into a bottom sheet. Reuse the existing phone code (`cad-phone.js`, `wslayout.js`, the recent lithophane bottom sheet #148). The phone path uses low-power WebGL, as `cad.js:125` already does.
- **Existing tests**: 255 Python test files plus `tests/js/*.test.mjs`, including `fdm-chrome`, `build-chrome`, `layout-batch2` and `cad-*`. Many of them assert section DOM, URLs or `cad.html`. Each PR updates its own tests. Don't do one big rewrite.
- **Big-bang risk in the CAD merge (PR4)**: keep the `cad.html` fallback behind the existing flags system until the mode matches it.
- **WebGL context loss**: with one context, losing it would lose everything. The stage needs a restore handler that rebuilds from the store.

## (e) Must preserve

- NSFW / mature blur and the confirm step (`community.js:561,721,737`, `.nsfw` styles).
- Feature flags default **off** (`app/config.py`: `ZEIM_2D3D_ENABLED`, `PLANS_ENABLED`, `COMING_SOON`, etc.). Hidden-when-off behavior has to work in the new switcher too (`community.js:45`).
- How the FDM quick buttons behave: the quick Print dialog defaults (`app.js:759`, 99% infill rule) and the printer checklist (`printer.js:541`).
- Autosave and version history (`worksave.js`, including the iOS 7-day notice and backup zip) must cover the store.
- Offline cache: the service worker version busting (`sw.template.js`, `sw-register.js`) must precache the new `core/*.js`.
- Old deep links (`/static/cad.html?bid=`, `/builder.html?bid=`, `/?edit=`, `/?publish=`, `#slicer`) keep working through redirects.
