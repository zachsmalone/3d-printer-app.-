# ZEIM remediation register

Baseline: `zeim` @ `ce508b2c3aeac74129fbf83c6db0c602b51228c2` (origin/HEAD is `zeim`; local and origin match after fetch). The live zeimapp.com commit is not recorded in the repo or deploy docs, so it is not assumed to match this SHA.

Unmerged work checked before editing: no remote branch named Perplexity (merged history only: PRs 30–34). Open PRs 36, 37, 45, and draft 49 do not touch these save/export paths. PR 49 has no file changes.

Batch 1 only. Status values follow the owner brief.

Verification log (this branch, Python 3.12 venv, Playwright not installed):

- `node --test tests/js/worksave.test.mjs` — 7 passed, 0 failed.
- `python -m pytest -q tests/test_batch1_outputs.py tests/test_worksave_js.py tests/test_b1_edit_text.py tests/test_cad_b8_b9_b12.py tests/test_export_d.py tests/test_plate_editor.py` — 58 passed, 0 failed.
- `python -m pytest -q` on the CI file list plus `tests/test_cad_workspace.py`, `tests/test_cad_beginner.py`, `tests/test_cad_text.py`, `tests/test_cad_n3.py`, `tests/test_cad_qa_kobi.py`, `tests/test_universal_export.py`, `tests/test_3mf_download.py`, `tests/test_3mf_import.py`, `tests/test_sculpt.py`, `tests/test_parts.py` — 271 passed, 2 skipped, 2 failed. Both failures are `ModuleNotFoundError: playwright` inside `tests/ui_cad_beginner.py` and `tests/ui_cad_text.py`. They were not run as browser tests.
- Body-index repro: one-off script, described on row B1-6. Not a committed test.

No browser, visual, external-viewer, or printer run.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1-1 | Functional / false save | Verified fixed for the storage decision. No browser paint of the indicator. | `ls()` swallowed `setItem` failures and `saveSection` still cleared dirty and returned success. | A full or dropped browser store looked like “Saved”, and the unsaved flag was cleared, so a later reminder or exit would not retry. | `71f4bc5`: `writeRaw` requires the read-back to match. Failure keeps the section dirty and the label is “Not saved”. | `node --test tests/js/worksave.test.mjs`: 7 passed, 0 failed. Includes a thrown `setItem` and a write that does not read back. | No browser pass of the on-screen indicator. |
| B1-2 | Functional / draft isolation | Verified fixed for key separation. No two-account browser session. | Draft keys were `zeim.work.<section>` with no account or project. | Account B could restore account A’s workspace draft. Two slicer projects shared one form draft. | `71f4bc5`: keys are `zeim.work.v2.<account>.<project>.<section>`. Nothing is written until `/api/me` identifies the account. Slicer drafts follow the open project (`static/edit.js`). Lithophane, TorchC0, and the CAD last-design slot are one per account (one form or one reopen prompt, not a second project document). Old unscoped keys are not copied. | Same node file: account `u:aaaaaaaaaaaa` / `u:bbbbbbbbbbbb` and projects `aaaaaaaaaaaa` / `bbbbbbbbbbbb` kept separate JSON. 7 passed. | No real signed-in browser session. Legacy drafts from before this change are not migrated. |
| B1-3 | Functional / save indicator | Verified fixed for the label string. No browser paint. | The visible label was “Saved” plus a time for a local draft, while the title talked about account storage. | A signed-in maker could read a browser draft write as a server confirmation. | `71f4bc5`: label is “Draft saved” plus the time, or “Not saved”. The title says the time is the browser draft. Guest/account sentences are unchanged. Studio “Save work” says “Draft saved in this browser” or that the draft did not store. | Node: successful save label matches `^Draft saved ` and does not start with `Saved `. `tests/test_export_d.py::test_ui_wiring` passed (source still contains “only in this browser” and “on your account”). | `tests/ui_export_d.py` was not run (needs a browser). |
| B1-4 | Functional / stale export | Verified fixed by trimesh on the written STL. No second mesh application. | `ensure_exports` treated `exports_head == head` plus the files existing as fresh. `set_dims` does not move `head`. Undo then a different edit can return to the same head without an export in between. | A dimension change, or undo followed by a different edit at the same index, could download the previous STL/OBJ/3MF. | `71f4bc5`: `geometry_revision()` hashes the applied steps, named dimensions, plate layout at that head, and text steps replay will skip. Exports store `exports_rev`. | `tests/test_batch1_outputs.py`: undo then ×3 at head 1 exports extent 30 (not the earlier ×2). `PUT` dims `$s` 2 → 3 keeps `head` and the download extent is 30. Both passed. | No check in a mesh tool other than trimesh. |
| B1-5 | Functional / skipped text replay | Verified fixed for warm cache and export bytes. | `mesh_at` skipped a text step that no longer passes, but `add_op` had cached the mesh that included it, and a matching step index could keep the old file. The omission was silent. | After a word-list change, the open project could still show and export text that a restarted process would drop, with no explanation. | `71f4bc5`: cache entries store the geometry revision. The project warning starts with “Left out of the model:” and is written with the export. | `test_text_that_no_longer_passes_is_left_out_of_the_warm_cache_and_the_export` and `test_a_changed_text_rule_drops_the_warm_mesh` passed. Poisoned “sh1t” and a patched reject both matched the untextured face count; the export bytes changed and the warning was stored. | Text is still omitted rather than blocking project open. That is the existing safety behaviour, now the same in memory and in the file, and it is named on the project. |
| B1-6 | Functional / body references | Confirmed, including a runtime replay on this branch. Not fixed. | Bodies are sorted by centre (`app/core/cadops.py`). A step stores an index and resolves it again on replay. | An upstream edit that changes body order applies a later transform to a different body, including in the export after replay. | Not changed. | One-off script (not a committed test, so the bug is not locked in): 10 mm box, sphere diameter 10 at x=40, then `body_transform` scale 2 on body 1. Extents were box 10 and sphere ~20. Editing the sphere to x=-40 and replaying left the sphere at ~10 and scaled the box to 20. Volume went from about 5177 mm³ to about 8522 mm³. | Stable identity needs a history migration (an id that survives replay, plus an explicit broken-reference error). A nearest-centre guess is not used. This does not block the save/export rows above. |
| B1-7 | Functional / save-as | Not applicable—with evidence | `editproj.clone()` already copies the original, the steps up to head, dimensions, and plate layouts. | None from a missing save-as. | Not rebuilt. | `tests/test_cad_b8_b9_b12.py` passed in the Batch 1 pytest run (58 passed, including `test_b12_redo_tail_is_not_copied` and `test_b12_cad_design_version_keeps_its_cad_steps`). | None. |
| B1-8 | Functional / safe exit | Fixed—awaiting verification of the on-screen dialog. The leave decision is covered without a browser. | CAD Back (`#cwBack`) navigated immediately. It was labelled “Back” while Home is fit-view. A failed draft write could still look successful (B1-1). | Leaving the CAD workspace could drop a dirty browser draft, or leave after a save that had not been stored. | `71f4bc5`: the control is labelled “Exit workspace” and calls `zeimSave.leave`. Leave writes the draft first. If the write fails, or the account is not known yet, it does not navigate. With a document it shows Stay / Exit anyway. The in-app Back chip uses the same helper. | Node: failed storage does not call the navigate callback and stays dirty (2 tests). A successful dirty draft navigates and the key contains the design id. `test_cad_exit_is_save_aware_in_source` passed (label and `zeimSave.leave` in the CAD files). | No browser click of Exit, Stay, or Exit anyway. The dialog itself was not shown. |

## Batch 2 — stable layout

Baseline: `zeim` @ `02bf8dac993b069673929dd52b9acd4f2496c511` (Batch 1 merged). Branch `cursor/stable-layout-batch2-8a58`. Layout code is `b40f331`. Save-aware Exit (`#cwBack`, `zeimSave.leave`) was not edited. B1-6 body identity was not edited.

Verification log (this branch):

- `node --test tests/js/layout-batch2.test.mjs` — 9 passed, 0 failed. jsdom covers free rectangles, route identity, breakpoint defaults, keyboard, orientation, and destroy. Two cases drive headless Chrome (`/usr/local/bin/google-chrome`, CDP) against local fixtures and read geometry JSON. That is not a screenshot review and not the real Studio, Lithophane, Slicer, TorchC0, or CAD pages.
- Python source assertions for the locked layout strings in `static/wslayout.js` and `studioRoute` / `phone` in `static/ws-main.js` — passed. `pytest` is not installed here, so `tests/test_batch2_layout.py`, `tests/test_workspace_source.py`, and `tests/test_litho_up1.py` were not collected.
- Playwright is not installed. `tests/ui_workspaces.py` and `tests/ui_litho_up1.py` were not run. The Studio key in `tests/ui_workspaces.py` now follows the hash, matching the route identity.
- CI (`.github/workflows/ci.yml`) does not run these layout tests.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B2-1 | Layout / shrink-to-fit | Verified in the headless Chrome geometry fixture and jsdom. No screenshot of the app. | `place()` tried widths and heights at 1, 0.75, 0.55, and 0.4 and kept the smaller size. | An open panel could shrink on the next layout without a resize. | `b40f331`: place at the real size, slide along the preferred edge, the other edges, then a free rectangle. A clamp into the largest usable rect is not written back. A second pass shares the box only when a panel is tight or blocked. | Node file: 9 passed. Chrome 800×600 fixture: settings stayed a tall column (height > 500) and did not overlap result or undo. | No Playwright pass of the real Studio page. |
| B2-2 | Layout / auto-min and auto-off | Verified by the source contract and the Chrome fixture. | Opening a chip marked other panels `auto-min`. The crowded fallback added `auto-off` (`display:none`). | A tool could minimise or disappear because another panel opened. | `b40f331`: `chipPri` only decides which panel is placed first. `auto-min` and `auto-off` are cleared and never added. | Same node file forbids those class adds. Chrome: an explicit minimise plus opening that chip leaves the other panels open. | A layout saved before this change can still have `min: true` from the old auto-min. That is the same flag as a deliberate minimise, so it stays until Reset layout. |
| B2-3 | Layout / overlap | Verified in the Chrome fixture, including a 360×640 root. | When no smaller size fit, the panel was marked crowded and left on top of another. | Finish, export, undo, or save could sit under another panel. | `b40f331`: no crowded flag. Each placed panel is an obstacle for the next. If no usable rect remains, the panel stays visible and `dataset.blocked` is set. | Chrome: settings, result, and undo do not overlap, including after an obstacle is shown and on the narrow root (three panels, result height ≥ 120). | A workspace with no usable free rectangle can still overlap. It is marked blocked instead of hidden. |
| B2-4 | Layout / user size | Verified in the Chrome fixture. | The user-sized path returned before the obstacle check. | A resized panel could cover the busy overlay or another panel, and the next layout kept that. | `b40f331`: a user size is measured, then the same obstacle search runs. Sliding it does not clear `userSize` or rewrite the saved width and height. | Chrome: after a user resize, `userSize` and the saved size remain, and the panel is off the obstacle. | No pointer-drag of a panel on a real app page. |
| B2-5 | Layout / listener cleanup | Verified in jsdom. | Creating a workspace again stacked resize listeners and observers. A layout queued after the document closed threw. | A closed workspace could throw, and a later resize could still move it. | `b40f331`: `destroy()` disconnects observers, removes listeners, clears timers, and unmounts. A queued layout checks the epoch and that the root is still connected. Creating the same id destroys the previous instance. | jsdom: after `destroy()`, a resize does not remount `.zws`. | Not checked against every live route change in the app. |
| B2-6 | Layout / reset | Verified in jsdom and the Chrome fixture. | Reset could leave the other orientation key, in-memory priority, or an in-flight drag that saved over the reset. | Reset layout did not reliably return the defaults, or a rotate brought the old dock back. | `b40f331`: reset bumps the gesture token, clears inline styles and priority, deletes the visibility key and both orientation keys, and applies the defaults for the breakpoint on screen. If `removeItem` fails, it writes those defaults. | jsdom: a landscape dock survives a portrait load, and reset clears both keys. Chrome: reset restores undo on top, settings on the left, result on the right, and clears that workspace’s `zeim.ws.*` keys. | The Customise dialog’s Reset button was not clicked in the real app. |
| B2-7 | Layout / Studio vs Lithophane | Verified in jsdom and headless Chrome. | The saved key flipped when `#litLightBox` was shown or hidden. Both routes share `#viewCreate`. | My Studio and Lithophane overwrote each other’s docks. | `b40f331`: the key is `litho` only for `#lithophane`. `#studio` and `#create` stay `studio`. The light box is still watched so the toolbar can reflow; it is not the identity. | jsdom: hiding or showing the light box does not retarget the key. Chrome 1280×800 `#lithophane`: stored keys are `*.litho` while the light box is hidden. `#studio` does not read that key. | `tests/ui_workspaces.py` was not run. Its key check now uses the hash. |
| B2-8 | Layout / breakpoints | Verified in jsdom and Chrome at 390×844. | Phone defaults were read once when the script loaded. A keyboard resize could look like leaving the phone breakpoint. | A later resize kept the first paint’s docks, or the keyboard closed or opened panels. | `b40f331`: defaults are functions. A breakpoint reloads them only when nothing is saved. A keyboard (`visualViewport` shorter by more than 120px, or `offsetTop` above 80) only reflows. Orientation still loads the other orientation key. CAD phone defaults use the same live query. | jsdom: empty storage follows the phone query; a saved grip edge survives; keyboard plus a spurious phone change does not change open, min, or edge. Chrome 390×844 `#studio`: settings starts minimised, result is on the bottom, recent builds is hidden. | No physical phone, on-screen keyboard, or hardware rotation. |

## My Studio library

`#studio` and the Account “Open Studio” link used to alias the Lithophane photo workspace. The library now stays on Account. B1-6 is still open and was not edited.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MS-1 | Navigation / My Studio | Fixed—awaiting verification. No browser click-through in this pass. | `ALIAS.studio` was `lithophane`, and Account’s button was `href="#studio"`. The hash showed `#viewCreate`. | Choosing My Studio opened the Lithophane maker instead of the saved-project list. | This change. `#account/studio` is the library. `#studio` is rewritten to that hash. Open and Edit are the only row actions that enter a workspace. | `node --test tests/js/studio-library.test.mjs`: 6 passed. `pytest tests/test_me_studio.py tests/test_studio_library.py tests/test_workspace_source.py`: 5 passed. | Playwright is not installed here, so `tests/test_studio_pickup.py` was not run. Older browser harnesses that open `/#studio` as the photo form now land on the library. The photo form is `/#create`. Lithophane stays `/#lithophane`. Those harnesses were not rewritten. |
| MS-2 | Navigation / return | Fixed—awaiting verification for the path this bug needs. | There was no return marker from the library because the library was the photo page. | Leaving a project opened from My Studio had nowhere to go back to the list. | Open and Edit store `zeim.back` (`from: "mystudio"`, url `/#account/studio`). The existing Back chip uses it. CAD Exit uses it only after the existing save-or-confirm leave, and only for that marker. Arriving on the library clears that marker and no project key. | Same node file: open writes only `zeim.back`; exit returns the library url and leaves project keys; a foreign back marker is left alone. | Exit, Done, and New build are still missing outside CAD. This change does not add them. New build still does not ask before clearing a working area. |
| MS-3 | Navigation / Showcase | Not changed. Out of scope. | Not a routing defect found while fixing the library. | Send to Showcase stays the explicit Send-to menu action in `handoff.js`. | None. Library Open, Edit, the file Send… sheet, the Back chip, and CAD Exit do not call `sendToShowcase`. | Read of `static/handoff.js` and the library click handler. No publish call was added. | Not audited across every workspace. |
| B1-6 | Account / body identity | Not fixed. Left as recorded in Batch 1. | `body_index` is still the body id. | A later body can point at another person’s saved measurements. | None in this change. | Not retested. | Still open. |

## Exit, Done, and New build outside CAD

Lithophane, the FDM Slicer, TorchC0, and 2D→3D now have Exit, Done, New build, and Return to My Studio. Exit and Return save through `zeimSave.leave`, then go to Account → My Studio when the project was opened from that library. Otherwise Exit opens the Showcase list (`#showcase`) and does not publish. Done saves and stays, unless the project came from My Studio, in which case it returns to the library. New build saves a dirty draft first and asks before clearing a photo, TorchC0 file, or prepared resin result that is not a saved project. Send to Showcase is still only the existing publish button and the Send to… menu. CAD’s Exit control was not rebuilt. B1-6 was not edited. A Send to… hand-off keeps the My Studio return nested on `zeim.back`, so Exit can still find the library.

## PR #53 — Exit, Done, and New build outside CAD

Merged and deployed to zeimapp.com at `f33cd1b3f36aaf553c5aeab90d887b9a3e8e63e9`. Healthz and home returned 200. Live browser check 2026-10-27: Lithophane Exit went to `#showcase` and did not publish. New build on an empty Lithophane stayed on `#lithophane`. Temporary work `yami-temp-exit-check` was cleaned from My Studio. This closes the “still missing outside CAD” note on MS-2. B1-6 is still open. This row records that deploy check; it was not re-run for the 500 MB import change.

## Model import limit — 500 MB

The mesh byte ceiling was 50 MiB (`MAX_UPLOAD_EDIT`), Caddy `max_size 55MB` (decimal), and `MAX_MULTIPART_BODY` 56 MiB. A legitimate mesh above that was refused before parse. Photos stay at 25 MB.

| Gate | Was | Now |
| --- | --- | --- |
| `editproj.MAX_UPLOAD_EDIT` (edit, repair, TorchC0, `max_upload_mb`) | 50 MiB | 500 MiB |
| Caddy `request_body` (`reports/deploy/Caddyfile`, `local-https/Caddyfile.local`) | `55MB` | `550MiB` |
| `MAX_MULTIPART_BODY` | 56 MiB | 560 MiB |
| Editor client (one file / several files together) | 50 MB / 55 MB | 500 MB / 550 MB |
| Drop copy, repair page, CAD / repair / TorchC0 pre-check | 50 MB, or none | 500 MB |

`550MiB` is the old 50 → 55 gap in binary units. Caddy’s `MB` is decimal, so `550MB` (550,000,000 bytes) would sit under a 550 MiB multi-file sum. The app body cap stays one step above Caddy (560 MiB), same as 55 → 56. A small STL still imports. A payload just over 50 MiB is no longer a size 413. Photos over 25 MB are still 413.

Tests (Python 3.12 venv, pytest):

- `python -m pytest -q tests/test_upload_limit.py tests/test_b3_filter2.py tests/test_uploadsafe.py tests/test_uploadgate.py tests/test_b1_upload.py` — 114 passed.
- `python -m pytest -q tests/test_3mf_import.py tests/test_slice_api.py tests/test_cad_workspace.py::test_cadrt4_5_zip_bomb_3mf_refused_and_gate_used` — 50 passed, 1 skipped.

Not deployed. No browser pass of a real 500 MB file.

Still in force, and not raised here:

- Triangle cap `MAX_FACES` 3,000,000 (a binary STL of that size is about 143 MiB). Larger triangle counts are still refused.
- 3MF expansion: upload gate 64 MiB per member, 128 MiB uncompressed, 32 MiB model XML; `meshedit.sniff` still refuses uncompressed totals over 128 MiB or non-model members over 16 MiB.
- `POST /api/slice` with a file stays at 50 MB (`MAX_UPLOAD_BYTES`). Slicing an imported project uses the saved mesh, not this direct-upload cap.
- Photo uploads stay at 25 MB. Share-sheet hide in `static/send.js` stays at 50 MB (separate from import).
- iPhone-test Caddy template stays at `30MB`.
- B1-6 body identity is still open and was not edited.

## Batch 3 — one project through design, repair, prepare, and slice

Merged and deployed to zeimapp.com at `01e495566e88701cec198d06f30015f6b0fd6d8b` (PR #55). The deploy record for this task: healthz and the root page returned 200. Projects is in the top bar and opens Account → My Studio. The stage bar (Design → Check & Repair → Prepare → Slice & Export) is live. This Batch 4 pass did not request zeimapp.com again.

Still open from the PR #55 notes, and not closed here:

- No signed-in click-through of generate → repair → slice.
- A photo design’s slicer copy is remembered for the tab; that reuse was not re-checked in a browser.
- The standalone repair page still opens the repaired file as a new FDM Slicer project (a copy), which is another upload of that file.
- UI tests for that flow were not run.

B1-6 is still open. `bodies()` in `app/core/cadops.py` still sorts shells by centre. This batch does not guess a nearest body.

## Batch 4 — dependable existing tools

Branch `cursor/dependable-tools-batch4-ed74`, off `zeim` @ `01e4955`. No merge and no deploy.

Update: Batch 4 is on `zeim` at `e9c2c03d2b8be6cfff65ebcfd921fb706b992a9b` (PR #56). The table below is the record from before that merge. B1-6 is handled in the section at the end of this file.

Verification log (this branch, Python 3.12, packages under `/tmp/pydeps`, Playwright not installed):

- `node --test tests/js/pickgeom.test.mjs tests/js/worksave.test.mjs` — 11 passed, 0 failed.
- `python3 -m pytest -q tests/test_sculpt.py tests/test_cad_workspace.py::test_sculpt_strokes_and_remesh tests/test_real_print_send.py tests/test_print_core.py::test_anonymous_choice_is_browser_only_and_signed_up_choice_is_saved_on_the_profile tests/test_print_core.py::test_signup_can_carry_the_optional_printer tests/test_doctor.py` — 48 passed, 1 failed. The failure is `test_doctor_in_a_real_browser`: `ModuleNotFoundError: playwright`.
- `python3 -m pytest -q tests/test_batch4_tools.py tests/test_cad_qa_kobi.py tests/test_print_send10.py tests/test_doctor.py -k "not test_doctor_in_a_real_browser"` — 38 passed, 1 deselected.
- `python3 -m pytest -q tests/test_cad_workspace.py tests/test_torchc0_resin.py tests/test_b4_ui.py::test_send_sheet_labels_untested_rows_and_never_claims_they_work tests/test_real_print_send.py::test_ui_honesty_strings` — 56 passed, 2 failed. Both failures are Playwright imports in `test_torchc0_in_a_real_browser` and `test_torchc0_islands_cups_cost_in_chromium`.
- `node --check` on `static/cad.js`, `static/edit.js`, `static/app.js`, `static/doctor.js`, `static/printer.js`, and `static/pickgeom.js` — syntax ok.

No browser, visual, printer-hardware, or live-site pass.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B4-1 | Selection / picking | Verified in `tests/js/pickgeom.test.mjs`. Not clicked in the CAD page. | `pickEdge` projected every edge, including edges behind the camera (a negative clip `w` flips onto the screen) and edges on the cut-away side of section view. Fillet used that pick with no depth test, so an edge behind the surface could win. | A tap could select an edge the user could not see, or an edge the section plane had cut away. | This change. `static/pickgeom.js` clips to the kept half-space and to `w > 0`, and rejects an edge farther from the camera than the face under the pointer. Face hits with `w <= 0` are skipped. The picked edge stored for fillet is still the full edge. | Node file: 4 passed (clip, behind-camera, occlusion, lost edge/face). | No pointer test on the CAD canvas. |
| B4-2 | Selection / disabled and lost | Verified by source and the reconcile helper. Not clicked. | Constraint buttons stayed pressable with nothing selected. Face extrude and on-model text Apply did not look disabled. Undo/reload kept edge and face coordinates that no longer sat on the mesh. Hiding a body left its selection up. | A tool looked ready when it could not run, or a highlight floated off the model after the shape changed. | This change. Constraint buttons disable until the right number of curves is selected, and enable again when it is. Apply stays disabled, with a reason, until a face or text spot exists. After a rebuild, a missing edge, face, or hidden body is cleared and the status says to tap again. | `reconcileSelection` cases in the node file passed. | The disabled paint was not checked in a browser. |
| B4-3 | Failure / cancel | Verified by reading the import paths. Not cancelled against a running server. | CAD and FDM Slicer imports had no cancel. A failed stroke save could be followed by another stroke’s preview. The page could report success only after `run` returned, but a cancelled wait had no honest sentence. | A long import could not be stopped from the page. A failed sculpt save could leave the next stroke looking saved. | This change. Import uses `AbortController` and a Cancel control on the existing busy overlay. Cancel says the page stopped waiting and the file may still appear in Projects if the server already accepted it. Sculpt strokes save in order. A failed save drops the rest of that burst, reloads the last good mesh, and says so. Undo stays disabled while a stroke is saving. | No automated cancel of a live upload. Sculpt refusal paths are covered by B4-4. | The server has no cancel hook, so an aborted upload can still finish. |
| B4-4 | Sculpt / thin wall and naming | Verified on subdivided plates and the existing sphere strokes. | Live Sculpt (`sculpt_stroke`) moved every vertex inside the brush sphere, including the back of a thin wall. The button said Remesh. That op only splits edges to a maximum length. A folded result was still returned. | A brush on a thin wall pushed the far side. History called uniform subdivision a remesh. A folded stroke could be stored. | This change. Only vertices facing the stroke normal move. A move that would pinch a nearby back face under 0.4 mm is held. Vertices outside the brush (plus a small margin) must not move, or the stroke is refused and the model is unchanged. Folded touched faces are refused. History and the button say uniform subdivision / Subdivide evenly. | `tests/test_batch4_tools.py` plate carve, clamp, and label passed. `test_sculpt_strokes_and_remesh` and `tests/test_sculpt.py` passed. The older `sculpt` op is unchanged. | The older `sculpt` op still moves both sides of a thin wall. `test_thin_wall_selection_policy_is_spatial_and_disclosed` pins that. CAD Live Sculpt does not call it. No brush drag in a browser. |
| B4-5 | Cleanup / CAD scene | Verified by source (`disposeObj` / `clearGroup` in `static/cad.js`). Not measured in a GPU capture. | `world.clear()`, `selG.clear()`, `sketchG.clear()`, and grid replacement dropped objects without `dispose()`. Each selection redraw replaced body materials and left the old ones. The indexed geometry from `toNonIndexed()` was never disposed. | A long CAD session kept growing GPU buffers for meshes, edges, the grid, and sketch lines. | This change. Rebuilds, selection redraws, sketch redraws, and grid changes dispose the previous geometry and materials. The indexed buffer is disposed after the non-indexed mesh is built. | Source assertion in `test_existing_tool_copy_is_honest_in_source` passed. | No heap snapshot. |
| B4-6 | Labels / what the tools are | Verified by source and history labels. | CAD copy said “exact sizes” next to fillet and face tools that move a mesh. STL for Shapr3D was “use this one” without saying the mesh is not an editable solid. TorchC0 showed a layer count that could be read as a machine file. The failure doctor showed the default Creality K1 as if it had been saved, and a signed-in user with no saved printer still received that default from `/api/me/printer`. | A maker could think ZEIM fillets and face offsets were precise solids, that an STL was a Shapr3D solid, that TorchC0 had sliced a resin layer file, or that troubleshooting was for a printer they had not saved. | This change. Fillet/chamfer history says approximate mesh (the “Fillet N mm (N edges)” prefix stays). Face offset says it is a mesh push. CAD page copy says the same. The STL hint says Shapr3D opens a reference mesh. TorchC0 says the layer count is an estimate and the printer’s slicer writes the layer file. `/api/me/printer` adds `saved`. The doctor uses a saved printer only, and says when fixes are general and that it does not read the photo. | `test_remesh_is_labelled_uniform_subdivision`, `test_doctor_without_a_saved_printer_stays_general`, the printer-pref equality tests, `test_send_sheet_labels_untested_rows_and_never_claims_they_work`, and `test_ui_honesty_strings` passed. | No browser read of the CAD page, the doctor, or TorchC0. |
| B4-7 | Success states / send and draft | Verified on the mocked Moonraker and OctoPrint clients. The draft label was already “Draft saved”. | A Live API upload with `print=true` and HTTP 2xx said the print had started. A 2xx only means the file was accepted. The draft indicator’s tooltip led with the account/server sentence. | A maker could think the printer was printing when it had only taken the file, or read the draft clock as a server receipt. | This change. `start` is `not_requested`, `requested`, or `confirmed`. Confirmed means a follow-up status says `printing` and, when a job name is present, that it matches the file. The send line names that state. Bambu stays Simulated and does not say a real print started. Pause/resume/cancel say the printer accepted the request and ZEIM has not confirmed the new state. The draft tooltip leads with “this browser” and “not a server confirmation”. The visible label is still “Draft saved” or “Not saved”. | `test_print_confirmed_only_when_the_printer_says_printing`, `test_octoprint_upload_with_start_is_a_request_until_status_confirms`, and `tests/test_real_print_send.py` passed. `tests/js/worksave.test.mjs` passed (7 cases). | No hardware printer. An empty job name plus state `printing` counts as confirmed. No browser paint of the draft indicator. |
| B1-6 | Body identity | Not fixed. Not retested. The sort in `bodies()` was not edited. | Bodies are still ordered by centre. A step stores an index. | An upstream edit that changes body order can apply a later step to a different body. | None. | Not run. | Still open. Stable identity needs a history migration. A nearest-centre guess is not used. |

## Batch 3 — streamlined workflow

Baseline: `zeim` @ `e09170ac1056dc0c8d4dd7cdf56cb8067bec11a4` (My Studio on Account, Exit/Done/New build, 500 MB import). Investigated after that. The photo page was still titled Studio in Experienced mode, the mesh workspace was still titled Edit, saved projects were only reached through Account, and moving a model on meant a new import or a separate repair page with no way back into the project. B1-6 was not edited.

Verification (this branch):

- `node --test tests/js/project-flow.test.mjs tests/js/studio-library.test.mjs tests/js/workspace-controls.test.mjs` — 21 passed.
- `python3 -m pytest -q tests/test_batch3_workflow.py tests/test_me_studio.py tests/test_studio_library.py tests/test_handoff_e.py tests/test_workspace_controls.py tests/test_workspace_source.py tests/test_b1_ui.py` — 20 passed, 18 skipped. The skips are `tests/test_b1_ui.py` (needs Chrome and Playwright; Playwright is not installed).
- Headless Chrome loaded a fixture that imports `static/project-flow.js`, painted Design → Check & Repair → Prepare → Slice & Export with Design current, and a Check & Repair click planned `repair:send:copy` for a photo with no slicer copy yet. That is not the full ZEIM page. The app server was not started (FastAPI is not installed here). No screenshot pass of zeimapp.com.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B3-1 | Workflow / Projects home | Fixed in source and the route tests. No signed-in browser pass of Account. | Saved projects lived on Account → My Studio, and the top bar had no Projects control. | A maker looking for their work had to know to open Account. | This change. Projects in the top bar is `#projects`, rewritten to `#account/studio`. The list is still `#meStudio` on Account. | Node: `#projects`, `#studio`, and `#account/studio` are the library, nav `projects`, not Lithophane. `tests/test_me_studio.py` and `tests/test_batch3_workflow.py` passed. | No click-through on the live site. |
| B3-2 | Workflow / names | Fixed in the labels. No Experienced-mode screenshot. | Experienced mode titled the photo page Studio. The slicer page title and links said Edit. Send-to named the photo page Studio, so Back said Back to Studio. | Studio, My Studio, and Edit meant three different things. | This change. Photo page title is Photo (Lithophane when that style is selected). Slicer title is FDM Slicer. Back chip says Photo. My Studio stays the list name. Section names in `app/branding.py` match. | `tests/test_batch3_workflow.py::test_photo_and_slicer_are_not_named_studio_or_edit` passed. `tests/ui_home.py` and `tests/ui_handoff_e.py` expect Photo; they were not run (Playwright). | Older harnesses that open `/#studio` still land on the library, as after #52. |
| B3-3 | Workflow / one project | Fixed for the stage decision and the remembered copy. No full generate → repair → slice click-through. | Design, repair, prepare, and slice were separate destinations. Sending a photo to the slicer created a new edit project every time, and the nav did not carry the open model. | The next stage asked for the file again, or made another copy with no sentence saying so. | This change. A stage bar on Lithophane, the FDM Slicer, TorchC0, CAD, and Smart Fix. The same edit id is reused. A photo design makes one slicer copy per id for this tab (`zeim.flow`), and the note says the photo design stays in Projects. Resin Slice & Export says the layer file is made in the printer's slicer. | Node file: 8 passed, including reuse, same-id hops, and the resin note. Chrome fixture: Check & Repair on a photo with no copy plans a derived send. | A rebuilt photo with the same id keeps the earlier slicer copy for this tab. A new build id gets a new copy. The bar was not exercised inside the running app. |
| B3-4 | Workflow / duplicate actions | Fixed in the markup. The hidden controls remain for older tests. | The photo result had Edit this beside Send to Slicer. The slicer start had Edit a Studio build, a second list of the same projects. | Two controls opened the slicer, and one of them ignored the resin printer type. | This change. Edit this is hidden and uses Send to Slicer. The second project picker is hidden. The visible line points at Projects. | `tests/test_batch3_workflow.py` passed. `tests/ui_trace2d.py` now clicks Send to Slicer; it was not run. | Send to Slicer, Send to CAD, and Send to Showcase stay. They are the explicit hand-off, not a second project list. |
| B3-5 | Workflow / repair dead end | The browser re-upload is removed. See the repair hand-off section below. | `/static/repair.html` ended at a download. The slicer link sent a broken file there with no return into a project. | After a repair, the maker had to download and import the file themselves. | First change posted the repaired file to `/api/edit/new`. That round trip is gone. `POST /api/repair/{id}/slicer` copies the repaired bytes on the server into one FDM Slicer project. | See the repair hand-off section. | The one-hour repair file can expire. The slicer project stays. A deleted project is a new id the next time. |
| B1-6 | Functional / body references | Not fixed. Left as recorded in Batch 1. | Bodies are still sorted by centre. A step still stores an index. | An upstream edit can renumber a later body. | None in this change. `tests/test_batch3_workflow.py::test_body_identity_is_unchanged` passed (the sort is still there). | Not retested as a geometry replay. | Still open. That pin was replaced when B1-6 was fixed; see the section below. |

## Batch 4 — shipped

`zeim` @ `e9c2c03d2b8be6cfff65ebcfd921fb706b992a9b` (PR #56, “Keep existing tools honest about picks, failures, and limits”). Merged before this B1-6 work. This change does not deploy.

## B1-6 — stable body identity

The on-screen body list is still sorted by centre. That order is no longer the identity a step stores. Each body carries an id on its faces (`b1`, `b2`, …). A new step stores that id. Replay looks the id up. If the id is not on the mesh, the step fails and does not move a different body. A saved project that still has a list index is rewritten by replaying the saved steps in order and recording the id at that list position. If two bodies share a centre (rounded to 0.001 mm), the index is ambiguous and the step fails. A nearest body is not chosen.

The box/sphere repro is `tests/test_b1_6_body_identity.py`. 10 mm box, sphere diameter 10 at x=40, scale ×2 on body 1. Before the upstream edit the sphere is about 20 mm and the box is 10 mm. Moving the sphere to x=−40 and replaying leaves the sphere at about 20 mm on x=−40 and the box at 10 mm. Volume stays about 5177 mm³. The old failure scaled the box and left the sphere near 10 mm, about 8522 mm³. The same edit is covered after the stored `body: 1` index is put back, which is the migration path, and after the in-memory mesh is dropped so replay reads the saved file. A stored `b999` raises `Body reference b999 does not match any body` and does not save the edit. Two boxes with the same centre refuse index 0 as ambiguous and do not scale either box.

Verification (this branch, Python 3.12, packages under the user site, Playwright not installed):

- `python3 -m pytest -q tests/test_b1_6_body_identity.py` — 5 passed.
- `python3 -m pytest -q tests/test_cad_workspace.py tests/test_b1_6_body_identity.py tests/test_qa_n1_mirror.py tests/test_cad_deferred.py -k "not real_browser"` — 57 passed, 1 deselected.
- `python3 -m pytest -q tests/test_cad_beginner.py tests/test_parts.py tests/test_batch3_workflow.py tests/test_batch4_tools.py tests/test_cad_qa_kobi.py tests/test_sculpt.py tests/test_batch1_outputs.py tests/test_cad_b8_b9_b12.py -k "not real_browser"` — 93 passed, 1 deselected.

Not run: Playwright browser scripts (`tests/ui_cad_beginner.py`, `tests/ui_cad_text.py`, `tests/ui_cad_deferred.py`) because Playwright is not installed. No browser pass. No printer. Not deployed.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1-6 | Functional / body references | Fixed for separate bodies whose faces keep an id, including the box/sphere replay and a saved index. Not a browser pass. | `bodies()` sorted by centre and a step stored that index, then resolved it again on replay. | An upstream edit that changed body order applied a later transform to a different body, including the export after replay. | This change. Ids live on faces. Steps store the id. Legacy indices are rewritten in saved order. A missing or ambiguous reference raises. | `tests/test_b1_6_body_identity.py`: 5 passed. The moved sphere stays ~20 mm and the box stays 10 mm; volume ~5177 mm³. CAD workspace, mirror, beginner, parts, sculpt, batch 1 and batch 4 tests listed above passed. | See the risks below. |

Remaining risks, stated as they are:

- Migration replays the saved steps and records the id at the old index. That is the body the index named before any upstream edit. It cannot recover a project whose earlier step was already edited and re-saved under the old index behaviour; that file already points at the wrong body, and this change will keep pointing at that body.
- Two bodies whose centres round to the same 0.001 mm cannot be told apart by an old index. The step fails. The project is unchanged. Opening or editing past that step raises.
- A boolean, repair, simplify, or hollow that rebuilds faces and does not leave exactly one body in and one body out drops the old ids. Later steps that name those ids fail instead of moving another body. An unedited history still migrates each index once against that rebuilt mesh, so reopen of an unedited project can still replay.
- If one id has been copied onto two separate shells, the earliest faces keep it and the other shell gets a new id. That follows face order, not which centre is closer.
- Appearance colours and the body list numbers are still the centre-sorted index. A colour can follow the list slot after a move. Those keys were not migrated.
- Smart merge still matches Smart Split pieces to a recorded point. That matcher was not part of this bug and was not changed.
- Whole-mesh moves keep ids when the face list is unchanged. A body step on a mesh large enough to run in the forked memory guard was not measured. The guard returns the mesh through pickle; ids are applied again in the parent when the faces still line up, or when one body stays one body.
- The CAD page was not clicked. The history field for a body id is text. A maker can still pick a body for a new step; the server stores the id.

## Build chrome polish — Exit stays clear, process sheet

Branch `cursor/build-chrome-polish-4f8f`, off `zeim` @ `44367d9`. No merge and no deploy. My Studio stays on Account. Exit, Done, New build, Return to My Studio, and Send to Showcase keep their existing jobs. B1-6 was not edited.

Before: a floating panel could be dragged over Exit. On the main workspaces the drag layer sat above the workspace bar. On CAD, a drag could paint out of the view and over the header. Slicer settings lived in the right-hand result card, so opening them covered the model.

After: the workspace bar is a top strip that layout will not use, and it paints above a drag. Docked tool rails slide along an edge and cannot be left floating over that strip. View controls (Fit, turn, wire) dock mid-right. Move / Rotate / Scale sit in a bottom row on the FDM plate, with Plate and Process tabs under them. Process opens a half-height sheet (Quality, Support, Infill, Adhesion) using the patterns and support modes ZEIM already slices. Close hides the sheet and does not leave the workspace. Slice in the top-right runs the same Slice button.

Verification (this branch, Python 3.12, Playwright not installed):

- `node --check` on `static/wslayout.js`, `static/ws-main.js`, `static/cad-phone.js`, `static/printer.js` — syntax ok.
- `python3 -m pytest -q tests/test_build_chrome.py tests/test_workspace_source.py tests/test_workspace_controls.py tests/test_c8_slicer_presets.py tests/test_print_core.py::test_panel_ui_has_beginner_and_advanced tests/test_litho_up1.py::test_layout_watches_obstacles_so_panels_come_back tests/test_litho_up1.py::test_core_panel_is_not_minimised_to_make_room` — 17 passed.
- `python3 -m pytest -q tests/test_c12_lithophane_preset.py::test_panel_ui_defaults_to_lithophane_preset_when_hinted tests/test_c8_slicer_presets.py` — 7 passed.
- `node --test tests/js/layout-batch2.test.mjs tests/js/build-chrome.test.mjs` — 10 passed. The new Chrome check (1280×800 and 390×844) drags a docked tool and a free panel at Exit and reads `elementFromPoint`. Exit stays the hit. The process sheet stays about half the view, and Close and Move stay hittable.
- Live `cad.html` on `127.0.0.1:8765` (headless Chrome): Exit stayed the hit target while the tool grip was dragged at it, at 1280px and on the phone layout (44px Exit).

Not run: Playwright UI scripts (`tests/ui_*.py`). No signed-in browser pass of Lithophane, TorchC0, or a sliced plate. No printer.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UI-1 | Layout / Exit covered | Verified in the headless Chrome fixture and on live CAD. Not a full app click-through. | Free-drag used a higher layer than the workspace bar, and the layout box included that bar. CAD drags could paint over the header. | Exit, Done, or New build could sit under a tool panel. | `f017a25`. The bar is reserved and paints above a drag. Docked rails cannot be dropped over it. CAD header stacks above the view, and the view clips overflow. | Chrome fixture and live CAD, above. | A saved free panel can still sit in the open area under the bar. It cannot take the Exit hit. |
| UI-2 | Layout / docked tools | Verified for the dock flag and the plate row markup. Not dragged on a real plate. | View and undo bars defaulted to the top edge, in the same band as Exit. | Tools felt dropped on the model instead of part of the workspace. | `f017a25`. View docks mid-right. Plate Move / Rotate / Scale dock at the bottom and focus the fields ZEIM already has. | Source test and the fixture’s Move hit. | There is no new on-model gizmo. Move still uses the plate fields or the existing forms. |
| UI-3 | Slicer / process sheet | Verified by source and by the sheet’s box in the Chrome fixture. The live slicer was not given a model. | Settings were inside the floating result card. | Choosing quality or supports covered the model. | `f017a25`. Process is a bottom sheet, about half the view, with Quality, Support, Infill, and Adhesion. Icons only for patterns ZEIM already slices. | `test_build_chrome.py` and the fixture height check. Preset tests passed. | Beginner still sends the preset’s walls and temperatures. Pattern and brim are sent from the visible choices. A 100% fill with a pattern other than solid lines can still be refused, and the sheet says so. |

## Build chrome / gizmos — beads on the model

Branch `cursor/on-model-gizmos-da19`, off `zeim` @ `f227df9`. No deploy. The bottom Move / Rotate / Scale row stays. Exit, Done, New build, and Send to Showcase are unchanged. A bead drag stores the same step the fields already store: plate `transform`, a single model’s `translate` / `rotate` / `scale`, or CAD `body_transform`. Saved projects and history are the same list of steps.

On the FDM plate, Move shows X and Y beads (the part stays on the bed). Rotate shows one Z bead. Scale shows a bead per axis and one for all sides. A single model, with no plate, gets X, Y, and Z. In CAD, Move / Rotate has Slide and Turn, and Scale has the same beads. Arrow keys nudge the focused bead. Holding Alt skips the 1 mm / 5° snap. A bead that would sit on Exit, the bottom row, the process sheet, or the view controls is not a hit target. Hover and press ease over 180 ms; reduced motion turns that off.

Verification (this branch, Python 3.12, Playwright not installed):

- `node --check` on `static/gizmo-math.js`, `static/gizmo-view.js`, `static/plate.js`, `static/edit.js`, `static/cad.js`, `static/ws-main.js` — syntax ok.
- `node --test tests/js/gizmo-math.test.mjs tests/js/gizmo-view.test.mjs` — 11 passed. The Chrome fixture drags the X bead and reads a plate `transform` of `dx: 10`. A bead covered by the Exit bar is not a hit target.
- `node --test tests/js/build-chrome.test.mjs tests/js/layout-batch2.test.mjs` — 10 passed. Exit stays the hit while a docked tool is dragged at it. jsdom for the layout file was installed under `/tmp/jsdom-batch2` for this run; it is not a project dependency.
- `python3 -m pytest -q tests/test_gizmo.py tests/test_build_chrome.py tests/test_plate_editor.py tests/test_cad_workspace.py -k "not real_browser"` — 29 passed.

Not run: Playwright UI scripts (`tests/ui_*.py`). No signed-in pass of a loaded plate or a CAD body. No printer. Not deployed.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UI-4 | Build chrome / on-model gizmos | Verified by the bead math, the source contract, and a headless drag that commits a plate transform. Not clicked on a loaded plate or in CAD. | Move / Rotate / Scale only focused the number fields. The plate could already be dragged, but there was no handle for turn or size. | Makers could not grab a bead on the model. | `8728a71`. Beads call the existing step. The bottom row still focuses the fields. | 11 node tests and the pytest list above. Plate editor and CAD workspace tests passed. | A live model was not opened. Plate turn and size preview do not repeat the server’s drop onto the bed until the step returns, so the part can settle on release. A bead under Exit, the dock, the process sheet, or the view rail is hidden until the view moves. |

## CAD interaction polish — selection, gates, 180 ms

Branch `cursor/cad-interaction-polish-b7a7`, off `zeim` @ `ba8f636`. No deploy. Saved projects, history, and body ids are unchanged. Exit still leaves the workspace and does not send the model to Showcase. Send to Showcase stays its own control.

Hover, press, and the committed face, edge, or body are separate. Hover uses the same edge test as the tap, including the Batch 4 clip and occlusion rules. A fillet tap that misses an edge does not store the face under it. Sketch curves use the same three states. Face and edge marks are screen-sized strokes. The push/pull handle uses the bead hover and press (180 ms ease; reduced motion turns that off). Tool rows use that same ease on colour and shadow.

Fillet/chamfer, face extrude, extrude, revolve, sketch constraints, and Measure say why they cannot run. Apply stays off for a size or distance of 0, a missing face, or a sketch that is not closed. Constraint buttons stay pressable when blocked so the hint can say why. A context bar is shifted off Exit, the view cube, and the mid-right grid/snap dock. A push/pull handle on that chrome is not a hit target.

Verification (this branch, Python 3.12, Playwright not installed):

- `node --check` on `static/cad.js` and `static/cad-feel.js` — syntax ok.
- `node --test tests/js/cad-feel.test.mjs tests/js/pickgeom.test.mjs tests/js/gizmo-math.test.mjs` — 19 passed.
- `python3 -m pytest -q tests/test_cad_feel.py tests/test_gizmo.py` — 5 passed.
- Headless Chrome on `cad.html` (1280×800): Exit stayed the hit. The mark layer does not take clicks (`pointer-events: none`); the middle of the view is the canvas. The view cube and the Grid chip stayed the hits on the mid-right dock. Download… was still the format picker. Measure, with no solid, stayed available to click and said “Make a solid first.” Parallel, with no curves, said “Select curves first.” Face extrude said “Tap a flat face first.”, then “Type a distance other than 0.”, and Apply came back at 2 mm. Fillet at size 0 said “Type a size greater than 0.” Tool rows reported a 0.18 s ease.

Not run: Playwright UI scripts (`tests/ui_*.py`). No signed-in CAD body and no printer. Not deployed.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UI-5 | CAD selection and tool gates | Verified by the pick/gate math and a headless CAD page. Not dragged on a saved body. | Hover was absent, a fillet miss could store the face, and several tools looked ready when the size was 0 or the pick was missing. Context actions could sit on the view dock. | A pick felt vague, and Apply could be pressed when the step could not run. | This change. Hover uses the tap’s edge test. Gates name the reason. The bar stays off Exit and the mid-right dock. Motion is the bead’s 180 ms ease. | 19 node tests, the pytest pair above, and the Chrome checks. | A loaded body was not filleted in the browser. The push/pull handle hides while it sits on a dock. |

## Repair hand-off — FDM Slicer without a second upload

Branch `cursor/repair-slicer-handoff-8aa0`, off `zeim` @ `e016994`. No deploy. Saved projects are not rewritten to hold an unrelated repair. Exit, Done, New build, and Send to Showcase are unchanged. Exit still does not publish.

Before: Smart Fix / repair on `/static/repair.html` ended at a download. Open in the FDM Slicer fetched that file in the browser and posted it to `/api/edit/new`, so a large repair was uploaded twice and each click could start another project.

After: `POST /api/repair/{id}/slicer` reads the repaired bytes already on the server and opens one FDM Slicer project. A second open returns that same id. The id is remembered for this tab in `zeim.flow` (`repairs`, beside the photo copies). A different saved project, including a project made from another repair, is left as it is. The page says when the project is new, and says when a deleted project means a new one. The stage bar on the repair page is Design → Check & Repair → Prepare → Slice & Export. The file name is not the project title.

Verification (this branch, Python 3.12, Playwright not installed, system Chrome present):

- `node --test tests/js/project-flow.test.mjs` — 10 passed. The repair page stays on Check & Repair. With a kept id, Slice, Prepare, and Design use that id. Photo copies and repair hand-offs do not erase each other.
- `node --test tests/js/repair-handoff.test.mjs` — 1 passed. Headless Chrome at 1280×800 repaired a 20 mm box, read the new-project sentence, and Open in the FDM Slicer landed on `/?edit=<12 hex>#slicer` with the slicer panel open. The log had one `POST /api/repair/<id>/slicer` and no `POST /api/edit/new` and no GET of the repair download. Exit’s title still says it does not send the model to Showcase. The publish dialog was closed.
- `python3 -m pytest -q tests/test_repair_slicer.py tests/test_batch3_workflow.py tests/test_stl_repair.py` — 23 passed. The repaired STL bytes match the project original. Volume is about 8000 mm³ and the mesh is watertight. The second open does not add a history slot and does not change Beginner. A project titled Desk clip stays Desk clip. A project made from a different repair is not reused. `MiaJohnson_clip.stl` does not become the title. Another session gets 404. An anonymous session can open a project. A missing repair id does not create one.

Not run: Playwright `tests/ui_*.py`. The stage-bar Prepare and Design hops were not clicked in Chrome. A full history (every build starred) was not filled, so the 409 path was not seen. A repair near 500 MB was not timed. No printer. Not deployed. GitHub CI is the `test` job; this note does not mark that job passed.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B3-5 | Workflow / repair hand-off | Verified by the API tests and one headless Chrome repair → slicer open. Prepare and Design on the repair bar were not clicked. | The repaired file was downloaded and posted to `/api/edit/new`. | A large repair was uploaded twice, and the slicer project was not a stable id. | This change. The server copies the repaired file into one edit project. The same id is reused. A different project is not replaced. | The node, Chrome, and pytest runs above. | The one-hour repair file can expire after the project exists. If that project is deleted, the next open starts a new id and the page says so. The 409 “builds are full” path was not executed. |

## Remix switch and re-upload protection

Branch `cursor/remix-theft-protection-3b35`, off `zeim` @ `60aeddc` (repair hand-off #61). No deploy. Showcase, Projects, Exit, and saved projects are unchanged. Exit still does not publish.

Already on `zeim` before this change: the per-model Allow remixes Yes/No switch (default Yes, owner can change it, the API enforces it), the shape check on share (credited-remix offer, or a refusal when remixes are off, Private keep, visibility re-check), the hidden owner tag written into downloaded 3MF files, first-posted date, view-only downloads in the API and the Showcase dialog, and Report as stolen / Report a copy. A matching share is not held for a moderator. That hold was replaced by the offer or refusal. Reports still go to the queue, and nothing is deleted.

This change wires the rest of that path. A downloaded 3MF’s owner tag is read from the imported `original.3mf` when the model is shared. If the shape check misses, the tag still offers credit or refuses, using the same rules. A tag for a project this maker cannot see is ignored. The maker’s own tagged file passes with a warning. A private keep of a tagged file is checked again if it is made public. The public `/p/…` page shows the first-posted date and, for everyone except the owner, does not offer downloads when the project is view only. Report as stolen can include an optional original link. The moderator queue links that original when the report has one. Tip and challenge copy says ZEIM never takes a cut of tips or of sales a maker makes from their own link, and that Showcase downloads stay free.

Verification (this branch, Python 3.12, Playwright not installed):

- `node --check` on `static/community.js` and `static/moderation.js` — syntax ok.
- `python3 -m pytest -q` on the CI list, which now includes `tests/test_remix_switch.py`, `tests/test_theft_protection.py`, and `tests/test_reupload_protect.py` — 196 passed, 2 skipped. The skips are `tests/test_app.py` “no slicer” and `tests/test_slice_api.py` “PrusaSlicer not installed”. They were not run and are not counted as passed.
- `python3 -m pytest -q tests/test_show_rest.py::test_remix_challenge_prize_free_enter tests/test_show_rest.py::test_old_tip_rule_is_replaced_once tests/test_reupload_protect.py::test_owner_tag_blocks_reupload_when_the_shape_check_misses tests/test_theft_protection.py::test_share_page_hides_view_only_downloads_and_shows_first_posted` — 4 passed.

Not run: Playwright `tests/ui_remix_switch.py` and `tests/ui_reupload.py`. No signed-in click of the remix switch, the share dialog, or Report as stolen. No printer. Not deployed. GitHub CI on the PR is the check that still has to go green; this note does not mark that job passed.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RP-1 | Showcase / owner tag | Verified by the API tests. The import button was not clicked. | The tag was written on download and never read on the next share. | A re-upload of a downloaded 3MF could pass when the shape check missed. | This change. `original.3mf` is read at publish and again when a private project is made public. | The tag tests in `tests/test_reupload_protect.py` passed. | A slicer that saves a new 3MF drops the tag. A heavy edit can also miss the shape check. A repair that replaces the file with an STL drops the tag. |
| RP-2 | Showcase / view only page | Verified on `GET /p/{id}` through the test client. Not opened in a browser. | The share page always listed file links. The file route already returned 403. | A view-only project still showed download links that failed. | This change. Other people see “View only” and no file links. The owner still gets the files. The page shows the first-posted date. | `test_share_page_hides_view_only_downloads_and_shows_first_posted` passed. | The Showcase dialog was not clicked. |
| RP-3 | Copy / no cut | Verified by the challenge API test, including a one-time replacement of the old sentence. | Tip copy said ZEIM takes no cut of tips and did not mention sales from the maker’s own link. | The standing line was easy to miss, and an already-seeded challenge kept the old sentence. | This change. Publish, the model page, challenges, and the Remix challenge rule use the same sentence. Showcase downloads stay free. There is no ZEIM checkout in this change. | `test_old_tip_rule_is_replaced_once` and the prize-free enter test passed. | No browser read of the publish dialog. |

## Lithophane memory box

Branch `cursor/lithophane-memory-box-7937`, off `zeim` @ `66d46ae` (remix/theft #62). No deploy. Saved projects stay. Exit does not publish. My Studio stays on Account. A memory box opened from My Studio goes to Lithophane.

The box was already a four-side lithophane (frame, snap, or enclosed) plus a light base. The preview stopped before the result row, and opening the saved build set the page mode to `memorybox`, which had no thickness help and hid the Lithophane form. Reopen also showed the print layout, not the box together.

The picture is the assembled box (`assembled.3mf`, viewer only). Send to Slicer, Export, Print, and the STL zip use the existing build files: the separate parts, laid out to print. They fit each other. Sizes are starting points. Stand upright stays off for this file. Side 1 can use the photo already chosen above. That does not change a lithophane already made.

Verification (this branch, Python 3.12, Playwright not installed):

- `node --check` on `static/app.js`, `static/community.js`, and `static/studio-library.js` — syntax ok.
- `node --test tests/js/studio-library.test.mjs` — 7 passed. A memory box opens `#lithophane`.
- `python3 -m pytest -q tests/test_memorybox.py tests/test_membox_fit.py` — 21 passed. Reopen keeps the assembled height. Send to Slicer (`/api/edit/new` from the build) returns a project whose base mode is `memorybox`.
- `python3 -m pytest -q` on the CI file list — 196 passed, 2 skipped. The skips are `tests/test_app.py` “no slicer” and `tests/test_slice_api.py` “PrusaSlicer not installed”. They were not run and are not counted as passed.

Not run: Playwright `tests/ui_membox.py` and `tests/test_membox_ui.py`. No signed-in click of Preview, Send to Slicer, or Exit. No printer. Not deployed. GitHub CI on the PR is the check that still has to go green; this note does not mark that job passed. The CI job does not run the memory-box modules; those 21 were run locally.

## Testing mode switch

Branch `cursor/testing-mode-switch-3e3b`, off `zeim` @ `1f4e5d7` (memory box #63). No deploy.

One line in the server config, `ZEIM_TESTING_MODE=1`, lifts usage quotas and cooldowns (hourly uploads, the pause between local 2D→3D models, doctor checks, favorites, print photos, username tries, the rename wait, Showcase questions, collections, feedback notes, and tip / AI-label edits). Default is `0` in `.env.example`, `.env.production.example`, `.env.staging.example`, and the compose file. There is no public toggle. Account shows a short status line only when the flag is on, and the process log says the same.

Left on: password guesses, auth rate limits, admin-token guesses, signup-per-IP, reports, recovery codes, the age gate, the malware scan, and file-size / memory / disk caps. Stripe checkout stays closed. The local 2D→3D daily model cap stays unless `ZEIM_TESTING_ALLOW_PAID=1` as well. That second line does not charge a card. There is no paid third-party AI client in this tree.

Like routes still have no hourly cap in code (`LIKE_LIMIT_PER_HOUR` is unused). This change does not add one.

Verification (this branch, Python 3.12 venv, Playwright not installed, PrusaSlicer not installed):

- `python -m pytest -q tests/test_testing_mode.py` plus the CI file list and `tests/test_ai3d.py` / `tests/test_ai3d_off.py`, excluding `test_ui_tab_in_a_real_browser` — 232 passed, 2 skipped, 1 deselected. The skips are `tests/test_app.py` “no slicer” and `tests/test_slice_api.py` “PrusaSlicer not installed”. They were not run and are not counted as passed. The deselected test needs Playwright and was not run.
- `node --check` on `static/ai3d.js` and `static/community.js` — syntax ok.

Not run: a browser pass of the Account status line. No printer. Not deployed. GitHub CI on the PR is the check that still has to go green; this note does not mark that job passed. The CI job now includes `tests/test_testing_mode.py`.

## Hard-surface CAD — measure, fillet, joints, merge

Branch `cursor/cad-hard-surface-033f`, off `zeim` @ `da0d2f7` (testing mode #64). No deploy. Exit still leaves the workspace and does not send the model to Showcase. Body ids stay on the faces. Saved steps are the same history.

Already built: print-in-place hinge, snap hinge, ball, pin, and chain; Merge with a side snap; Smart merge along a recorded Smart Split; Measure (an edge, two points, the angle between faces); fillet and chamfer by a mesh opening.

Gaps this change closes:

- A fillet pick that missed the body, or sat 2 mm off the edge, was stored as a success and did not change the solid.
- A straight edge split into pieces was rounded only on the tapped piece.
- An inside corner was left sharp under a success message.
- A round hole rim could not be made into a clean solid. Following the whole curve now refuses, instead of saving a speck.
- Smart merge gave the joined solid a new id.
- The scene did not send the body id, so Merge remembered a list slot.
- Hinge copy said to Join each leaf. Pin copy said the arm needs no supports. A box overlap could be read as “these will fuse,” including a hinge whose solids do not touch.

Shipped: a pick follows the outside edge and stops at a corner. A miss or an inside corner is refused. Measure reads a split straight edge as one length, snaps a nearby corner, and adds the distance between parallel faces. Joint Add stays off for an even knuckle count or a clearance outside 0.15–1 mm. The parts are new, the fit is simulated, and Merge does not close the gap. Merge selects by id. Smart merge keeps one of the split ids when the pieces become one solid.

Not in this change: attaching a hinge to an edge that is already on the model, a precise solid fillet, or a cylinder diameter in Measure.

Verification (this branch, Python 3.12 venv, Playwright not installed, PrusaSlicer not installed, system Chrome present):

- `node --test tests/js/cad-feel.test.mjs tests/js/pickgeom.test.mjs` — 12 passed.
- `python3 -m pytest -q tests/test_cad_hard_surface.py tests/test_cad_workspace.py tests/test_cad_deferred.py tests/test_cad_feel.py tests/test_b1_6_body_identity.py tests/test_cad_qa_kobi.py::test_b3_fillet_boss_watertight_or_refused tests/test_batch4_tools.py::test_existing_tool_copy_is_honest_in_source -k "not real_browser"` — 45 passed, 1 deselected. The deselected test is the Playwright browser script. It was not run.
- The CI file list, which now includes `tests/test_cad_hard_surface.py` — 223 passed, 2 skipped. The skips are `tests/test_app.py` “no slicer” and `tests/test_slice_api.py` “PrusaSlicer not installed”. They were not run and are not counted as passed.
- Headless Chrome on live `cad.html` (`127.0.0.1:8765`): Exit’s title still says it does not send the model to Showcase, and Exit stayed the hit. A default hinge added two bodies with ids. Knuckles 4 kept Add off and named the reason. Merge said a clearance gap stays open. Fillet at 0 mm stayed off. Measure’s hint names the corner snap and the distance between parallel faces.

Not run: Playwright `tests/ui_*.py`. No drag of a fillet on a saved project. No printer. Not deployed. GitHub CI `test` on the PR passed (run 40707688283). The two slicer skips in that job are the same environment skips as above. They are not counted as passed.

| ID | Category | Evidence/status | Root cause | User impact | Fix/commit | Tests/results | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAD-1 | Fillet / chamfer | Verified by mesh tests. Not dragged on a saved body in the page. | A picked edge that missed the solid was still saved. A split straight edge was only partly rounded. A hole rim did not come back as a clean solid. | A maker could think an outside edge was rounded when the mesh had not changed, or when only a short piece had. | This change. The pick follows the outside edge and stops at a corner. A miss, an inside corner, or a curve that is not a clean solid is refused. | `tests/test_cad_hard_surface.py` and the fillet test in `tests/test_cad_workspace.py` passed. | A round hole rim stays sharp. The opening is still an approximate mesh. |
| CAD-2 | Measure | Verified by the length and face-distance math, and by the hint on the live page. Two points were not clicked on a box in the page. | A split edge reported one piece. A face tap did not snap to a corner. Parallel faces did not show the distance between the planes. | A 40 mm edge made of two pieces could read as 20 mm, and a thickness was only the slant between the taps. | This change. A straight run is one length. A tap within 10 px of a corner or an edge middle uses that point. Parallel faces add the plane distance. | Node tests for the chain and the face pair passed. The page hint was read in Chrome. | A cylinder diameter is not reported. The two-point line is still the tapped points. |
| CAD-3 | Joints / merge | Verified by the joint solids that already existed, the id tests, and the live hinge and Merge panel. | Copy named a Join step and said the pin needs no supports. Smart merge dropped the body id. Merge remembered a list index, and a box overlap was worded as a weld. | A hinge looked attached, and a later step could lose the body it named. | This change. Copy matches the solids. Add states why it is off. Merge uses the id. Smart merge keeps one split id. The note says a clearance gap stays open. | The deferred joint tests, the new id test, and the Chrome hinge/merge checks passed. | A hinge is still a new pair of parts. It is not built onto an edge you already have. Fit is simulated. |
