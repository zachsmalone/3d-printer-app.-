# CAD launch version: what's left (2026-10-18, 18:25 CDT)

**Current honest estimate: about 86%.** Branch `cad-workspace` @ f9ee187. Everything is committed and the tree is clean.
**Time to 90%: about 2.5–3 h** (items marked ★). **Time to 100% of the launch scope: about 9–11 h** (all must-haves). "Later" items are not counted.

Done since the last report (all with tests): CADRT-1..7 (Lindsi re-test PASS); CADRT-8 (guard clamps to the inherited RLIMIT_AS, never raises it, refuses kindly when there's no headroom); CADRT-9 (all CAD/sculpt ops now go through guard, max 2 guarded children per process, otherwise a "busy, try again" message); Kobi B1–B7, B10, B11, B12 (title only), B14, B15; the runtime memory ceiling; the post-extrude Union/Subtract/New body pop-up; snapping to the origin.

Last full suite (flock, run before CADRT-8/9): 1778 passed, 39 failed. Rerunning those 39 on the base worktree: 38 also fail there (browser/env tests, printer_ssrf, dmca, litho_shapes, so not CAD). The one caused by this branch, `test_print_core::test_badge_geometry_checks`, is fixed and passes. The CAD tests pass (26/26), and all 3 CAD Playwright scripts passed on desktop and iPad.

| # | Item | Launch? | Est. | To 90% |
|---|---|---|---|---|
| 1 | Full suite under flock on f9ee187 (includes CADRT-8/9 and the willprint change); confirm only the 38 known base failures remain | Must | 0.5 h (wall time 15 min) | ★ |
| 2 | Re-run the 3 CAD Playwright scripts and refresh the desktop/iPad screenshots (incl. edit-imported.png, post-extrude pop-up, the "can't open, Undo" banner) | Must | 0.5 h | ★ |
| 3 | B8: units picker (mm/cm/in/m) in CAD Open ▾ → Import (the API already supports units) | Must | 0.5 h | ★ |
| 4 | B9: the size warning is wrong after a unit conversion (re-run the warning after scaling) | Must | 0.3 h | ★ |
| 5 | B13: Measure: tapping an edge shows its length (pick the edge before the body hit) | Must | 0.3 h | ★ |
| 6 | Lindsi/Kobi re-test of B1–B7, B10, B11 and CADRT-8/9 on the new commit; fix whatever comes back | Must | 1–2 h | half ★ |
| 7 | Imports over 200k triangles can't open in CAD (413). Offer "Open simplified copy" (decimate to 200k as a new version) | Must | 1 h | |
| 8 | B12 rest: Save as version keeps flattening history, and shows a colour warning even on single-colour files (show it only when there's more than one colour) | Must (warning) / Later (keeping history) | 0.3 h / 3 h+ | |
| 9 | Fillet on plate+hole only works through the fallback; check fillet/chamfer on 5–10 real imported parts and look at the refusal rate | Must | 1 h | |
| 10 | Edge push in = fillet / out = chamfer, with a floating number pill to type the exact value (Light Loop) | Must | 1 h | |
| 11 | Items tree: rename bodies (eye toggles already exist) | Must | 0.5 h | |
| 12 | Snap to face centre in sketches, plus a visible centre-rectangle toggle (Alt mode already exists) | Must | 0.5 h | |
| 13 | Split Body in two clicks (body, then plane or sketch line) using the existing manifold split | Must | 1 h | |
| 14 | Client sculpt preview for X symmetry should use the model's centre (the server already does) | Must | 0.2 h | |
| 15 | iPhone check (real device or the WebKit/iPhone viewport): rail, panels, pop-up, sculpt gestures | Must | 1 h | |
| 16 | Docs: update spec/licensing/ROADMAP for guard, caps and the new pop-ups | Must | 0.3 h | |
| 17 | Construct menu: offset plane, and midplane between two faces | Later (about 2 h) | 2 h | |
| 18 | Draggable pivot dot for circular pattern | Later (about 1.5 h) | 1.5 h | |
| 19 | Tool search box: already covered by the command palette (Search). Only check that it lists every tool | Must (verify) | 0.2 h | |
| 20 | B16: Fix mesh leaves overlapping shells, so volume is double-counted (self-intersection check, or union the shells) | Later | 2 h | |
| 21 | B17: sculpt stroke uses the first normal for every dab, so long strokes can fold faces (per-dab normals + fold check) | Later | 1.5 h | |
| 22 | Replace Face (Light Loop) | Later (after launch, per Zach) | 3 h+ | |
| 23 | WebKit/real Safari XSS check of History (host libs missing on the box) | Later / needs a device | 0.5 h | |
| 24 | Cgroup MemoryMax for production workers (ops/deploy, not app code) | Later (deploy) | n/a | |

Items 1–5 plus half of 6 take us to about 90%. Must-haves left in total: 1–16 and 19, about 9–11 h including the re-test loop.
