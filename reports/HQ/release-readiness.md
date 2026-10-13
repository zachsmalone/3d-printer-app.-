# ZEIM release readiness (audit of origin/zeim @ 95cb54a, 2026-10-12)

Read-only audit in a fresh worktree; own server on :8799 (`PHOTO3D_MODE=shared`), temp data dirs. No app code changed.
Supersedes the outside review based on 22f091b.

**Bottom line:** the core (photo → watertight mesh → export → PrusaSlicer G-code that fits a K1 bed) works and is well tested
(655 tests pass). It is **not launch-ready** for a public teen audience: no real authentication, word-list-only moderation with no
human process, nothing tested on a real printer, phone or screen reader, and no hosting/legal decisions yet.

## How it was checked
| Check | Command | Result |
|---|---|---|
| Full test suite | `pytest -q tests` (pwenv) | **655 passed, 0 failed** (12m35s). One earlier `-x` run failed `test_b1_ui.py::test_ios2_touch_targets…` on a page-load timeout under load; it passed on re-run (flaky under load). |
| Malformed-input fuzz | `/tmp/aud/fuzz.py`: all 68 OpenAPI paths × methods, ids `x` / `../../etc/passwd` / 30 digits, bodies: none, broken JSON, nested objects, arrays, null/wrong types, NUL bytes, junk multipart | **692 requests, 0 × 5xx, 0 × "[object Object]"** (200:85, 400:116, 401:52, 403:34, 404:232, 415:1, 422:171, 429:1). Server log: 0 tracebacks. |
| axe + Playwright | `tests/ui_home.py`, `ui_a11y2.py`, `ui_mobile.py`, `ui_touch.py` with axe-core 4.10 (`AXE_JS=…`) at 390/320 px | ui_home 81 pass / **6 fail (axe)**; ui_a11y2 37/37 pass without axe; mobile/touch OK. |
| Mesh + slicing | `/tmp/aud/mesh.py`: 3 modes × 100/250 mm, STL/OBJ/3MF reload in trimesh, slice with `app/profiles/creality_k1.ini` on 220×220 bed | see below |
| School leftovers | `rg -i "school|classroom|teacher|student|grade" app static README.md ROADMAP.md` | code clean; docs have leftovers (below) |

## Flagged items from the outside review
| Item | Status | Evidence |
|---|---|---|
| Lesson cards not keyboard-openable | **Fixed** | Title is a real link `static/community.js:333`, handler `:336`; `ui_a11y2.py` "keyboard lesson cards" PASS |
| Unlabeled fields | **Partly fixed – still broken for Mode select** | axe `select-name` (critical) + `label-title-only` on `#modeSel` in every Studio state at 390/320 px; cause: `static/style.css:472` hides the `<label for=modeSel>` with `display:none` in the top bar |
| Focus loss | **Fixed (automated)** | `ui_a11y2.py` skip-link, stacked-dialog focus trap checks PASS |
| "[object Object]" errors | **Fixed** | `static/app.js:24-40` maps 422 lists; ui_a11y2 PASS; fuzz found none. Minor: `static/moderation.js:8` still does `j.detail || statusText` (admin page only) |
| No strong authentication | **Still open** | README "Known limits": identity = 1-year anonymous cookie (`app/community/identity.py:59`), recovery codes only; age is self-declared |
| No real-printer verification | **Still open** | OctoPrint/Moonraker only against mocks (`tests/test_b2_k1.py`, README "Print") |
| No real-device / screen-reader testing | **Still open** | `tests/ui_a11y2.py:3` "No screen reader or real phone here" |
| Safety / moderation / deployment / legal gaps | **Still open** | see Teen safety + Deployment below; ROADMAP.md:41 (COPPA/privacy policy "still to do"); trademark not cleared (README) |

## By area
**Security / auth – partly verified.** Good: CSP, X-Frame-Options DENY, nosniff, no-referrer, HttpOnly SameSite=Lax cookie, API docs off in prod (`app/main.py:47`), Origin check (`app/api/guards.py:56`), constant-time token compares, signed 10-min file links, privacy 404s; fuzz 0×500. Broken/untested: no passwords/strong auth; anyone with the cookie is the user; self-declared adults can send to an admin's printer; age-gate IP lock can block a whole shared network (README Known limits); JSON-file storage (no concurrency/backup story); no external pen test.

**Teen safety / moderation – partly verified.** Good: language + contact-detail filter with tests (`test_b1_filter.py`, `test_b3_filter2.py`), teen defaults Private, teens get no slicer links/send/sharing (`test_b1_teen_posture.py`), `minor_safety` reports auto-hide. Gaps: grooming phrases not detected (README), **no image moderation for uploaded photos/thumbnails**, moderation queue is an API behind one admin token with no staffing/SLA/escalation (`app/community/moderation.py:4`), teen can still set an item Public (open decision), no parental-consent/age-verification beyond typed DOB.

**Accessibility – mostly verified, one critical axe failure.** Above. Untested: VoiceOver/TalkBack, real iPhone, Dark-mode contrast beyond automated checks. Note: axe is silently skipped when `/workspace/a11y-tools/.../axe.min.js` is missing (`tests/ui_a11y2.py:7`), so CI does not catch the #modeSel failure.

**Error handling – verified.** 0 × 5xx / "[object Object]" across all endpoints. Weak spot: an oversize model gives the raw message **"slicer failed"** + log tail "All objects are outside of the print volume" (`app/services/slicer.py:88`) instead of a plain "too big for your K1 bed (220×220 mm)" check before slicing.

**3D mesh correctness – verified for generated models.**
| Mode | solid watertight / consistent winding | STL | OBJ | 3MF |
|---|---|---|---|---|
| lithophane 100 & 250 mm | yes / yes | watertight, ΔV<1e-7 | watertight | watertight |
| relief 100 & 250 mm | yes / yes | watertight | watertight | watertight |
| pop-art 100 & 250 mm | yes / yes | watertight (merged mesh) | **not watertight when re-loaded as one mesh** (ΔV 8e-4; separate colour bodies by design, README) | watertight |
Plus `test_b2_mesh.py`, `test_c3_qa_mesh.py`, `test_3mf_import.py`. Untested: large corpus of real-world STL/OBJ/3MF in Edit; 3MF opened in Bambu/Orca/Creality Print.

**Slicing / G-code for K1 – verified in software only.** PrusaSlicer 2.9.2 + `creality_k1.ini` (bed 220×220, height 250): all 100 mm models sliced; extrusion X 53.8–166.2, Y within 66–154, Z ≤ 76.8 (upright lithophane), temps set (M104/M109). 250 mm models are refused by the slicer (correct, but unfriendly message). Slice and send use the same bed/profile (`test_b2_k1.py::test_slice_and_send_use_the_same_bed_and_profile`). Untested: printing on a real K1, K1 firmware accepting the start G-code, Moonraker upload on a real K1.

**Mobile layout 390 px – verified in emulation.** `ui_home.py` (81 checks), `ui_mobile.py`, `ui_touch.py` pass (Chrome + WebKit emulation, 44 px targets, 16 px inputs). Untested: real iPhone Safari (keyboard, safe-area, file picker/camera, 3D viewer memory).

**Performance – partly measured.** 4000×3000 photo at max 600 px resolution, 150 mm: lithophane 6.8 s, relief 5.6 s, pop-art 10.9 s, STL ~55-59 MB, peak RAM ~1.1 GB in one process. Not done: concurrent-user load test, phone-side three.js on a 1.4 M-triangle preview, memory limit per request on a small host.

**School leftovers.** App code: none functional (only removal comments, `usernames.py:20` reserves "teacher" – fine). Docs still describe school features: `README.md:3` "classroom-friendly education center"; `README.md:39` "class students … send to my teacher … a teacher can switch on sharing"; `README.md:60` "shared school address"; `ROADMAP.md:58` "teacher mute". Learn/Spark Lab lessons remain as intended.

## Top 15 launch blockers (ranked)
| # | Blocker | Severity | Effort | Lane |
|---|---|---|---|---|
| 1 | No strong authentication: account = anonymous 1-year cookie + recovery code; age self-declared | Critical | L | engineering |
| 2 | No human moderation process (queue is an admin-token API; no staffing, SLA, escalation, law-enforcement/NCMEC path) | Critical | M | safety |
| 3 | No image moderation of uploaded photos / published thumbnails | Critical | M | safety |
| 4 | Legal: privacy policy, terms, COPPA/GDPR-K/UK AADC review, data-retention policy not done (ROADMAP.md:41) | Critical | M | safety (legal) |
| 5 | Hosting not decided: JSON-file storage, single process, no backups, TLS/secure-cookie and secrets setup undocumented for prod | Critical | L | devops |
| 6 | Never printed on a real K1 (G-code + Moonraker send only verified in software/mocks) | High | S | engineering (Zach) |
| 7 | Never tested on a real iPhone / Android | High | S | design (Zach) |
| 8 | No screen-reader pass (VoiceOver/TalkBack) | High | M | design |
| 9 | `#modeSel` has no accessible name at phone width (axe critical; `style.css:472`) | High | S | design |
| 10 | Grooming-style messages not detected; filter is word-list only | High | M | safety |
| 11 | Teens can still make an item Public (open decision) | High | S | safety |
| 12 | Self-declared adult can send jobs to a shared printer; age-gate IP lock can block a whole shared network | Medium | M | engineering |
| 13 | No load/memory test: one 600 px pop-art build ≈11 s and ~1.1 GB RAM | Medium | M | devops |
| 14 | Oversize model gives raw "slicer failed / outside print volume" instead of a bed-fit check | Medium | S | engineering |
| 15 | axe silently skipped when not installed, so CI misses a11y regressions; README/ROADMAP still describe class/teacher features; trademark not cleared | Low | S | engineering / design |

## Needs Zach
- Real **K1 print test**: slice a lithophane, relief and pop-art at 100 mm, send via Moonraker, print, photo of results.
- Real **iPhone (Safari) test** at 390 px: upload from camera roll, build, 3D preview, download, Learn lessons; plus a VoiceOver pass if possible.
- **Hosting** choice (where, DB instead of JSON files, backups, domain/TLS, who holds `PHOTO3D_ADMIN_TOKEN`).
- **Legal**: privacy policy + terms, children's-privacy review (13+ only; teen defaults), trademark clearance for "ZEIM", DMCA/report contact.
- **Policy decisions**: may teens publish Public items? who moderates and how fast? real accounts (email/passkey) before launch?

## Counts
Tests 655 pass / 0 fail (1 load-flake seen) · fuzz 692 requests, 0 server errors, 0 "[object Object]" · axe: 1 critical + 1 serious rule on 1 element (6 page states) · outside-review items: 4 fixed, 1 partly fixed, 4 still open · areas: 2 verified, 5 partly verified, 0 fully broken · blockers: 5 critical, 6 high, 3 medium, 1 low · doc school leftovers: 4 lines.
