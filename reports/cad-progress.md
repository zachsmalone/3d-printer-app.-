# CAD launch progress log

| Time (CDT) | % | Just finished | Left |
|---|---|---|---|
| 2026-10-18 17:34 | ~84 | Red-team CADRT-1..7 fixed with regression tests (pattern/fillet preflight caps; per-op param allowlist + plane validation; contact filter + no-markup on every param string; History/Items render user strings via textContent; 3MF zip-bomb ratio cap; upload gate on /api/edit/new + /multi; plain-text titles/step names; /api/cad/new 422 on contact title). CAD UI scripts pass desktop+iPad. | Full suite under flock, Light Loop video items, screenshots |
| 2026-10-18 18:25 | ~84 (held) | Kobi QA B1-B7, B10, B11 (size floor + honest skip label), B12 (title), B14, B15 fixed with tests; runtime memory ceiling (core/guard.py) on remesh/pattern/fillet/booleans/simplify/repair + willprint/printcheck; 540k sphere /api/slice now peaks ~650 MB (was 8.8 GB OOM); post-extrude Union/Subtract/New body pop-up; origin snap. QA bugs added work, so % held. | Full suite under flock, UI screenshots, later list (B8 units picker, B9, B13, B16, B17, Light Loop bigger items) |
