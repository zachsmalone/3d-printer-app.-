# ZEIM — Accessibility & Usability Audit, Round 2 (WCAG 2.2 AA + design-spec acceptance tests)

Date: Mon 12 Oct 2026, ~2:15–3:00 PM CT · Auditor: Grok Bot (executor)

## Commit tested
- **`22f091bb078e69d0aa63fd7eb06c443f87b0b4e0`** (`22f091b`, "CI: run on the zeim branch and allow manual runs", 2026-10-12 14:13 CT), branch **`zeim`** of github.com/zachsmalone/3d-printer-app.- , fresh clone via authenticated `gh` into `/workspace/scratch/a11y-zeim` (no fallback to local main was needed; `/workspace/photo3d` was not touched except for writing this file).
- No app code was edited. Line numbers below refer to this commit.

## Method
- Scratch server: `uvicorn app.main:app` on **127.0.0.1:8792**, `PHOTO3D_MODE=local`, `PHOTO3D_DATA=/tmp/a11y-data-*` (temp data dir). Fixtures made through the public API: adult teacher "Ms Rivera" with class "Room 12" and 3 students (Ava/Ben/Cy, Ben then Cy with a raised hand), a second adult, a 13-year-old teen account, and one real **public** Showcase item ("Our dog Max") alongside the EXAMPLE seeds.
- Engines: Playwright 1.63 (venv `/workspace/a11y-tools/pwv`) driving **Chromium** (Google Chrome) and **WebKit 26.6**.
- **axe-core 4.14** (tags wcag2a/aa, 21a/aa, 22aa). The axe copy in `/workspace/a11y-tools` was missing `node_modules`, so I unpacked axe-core 4.14 to `/workspace/scratch/axe` (I didn't modify the shared tools dir). The site CSP blocks inline scripts, so test contexts use `bypass_csp`.
- Matrix: Studio home in Beginner / Experienced / Teacher, Warm and Dark (`localStorage.theme=dark`), at **320 / 390 / 1280 px**, in both engines (36 axe runs + reflow + top-bar height + target-size scan). **200 % zoom** was emulated as a 640 CSS-px viewport at DPR 2, and **text-only 200 %** as a 200 % root font-size at 390 px.
- Scripted keyboard walk-throughs: home tab order and focus-ring styles, Mode select (arrows, ineligible Teacher), Nozzle signed-out and signed-in (Enter/Space, focus, live text, grid↔dialog sync), Teacher tools → Live view (table semantics, hand cue, polite region, sort/reorder during a 12 s poll with the pointer over a row, "Helped"), Delete class dialog (initial focus, Tab cycle, Shift+Tab, Esc, Enter on initial, focus return), and Sign out dialog.
- Computed contrast: WCAG relative-luminance math on computed colours (script `/workspace/scratch/cr.py`) plus axe color-contrast.
- Scripts and output are in `/workspace/scratch/` (`a_matrix.py`, `a_dark.py`, `c_interact.py`, `d_teacher.py`, `e_views.py`, `matrix.json`, `shots/`).

## What wasn't tested
- **No real screen reader** (VoiceOver, NVDA, JAWS, TalkBack) and **no real phones or tablets**. Everything here is browser automation, the accessibility tree, and code review. Spec items that ask for recorded speech (A4, N4, H5) or a real iPhone (P7) are marked *Not tested*.
- Playwright WebKit is not Safari. In particular, whether **Safari/VoiceOver keeps table semantics** for the Live-view table when it is restyled as cards at narrow widths (`display:block` on `table/tr`) can't be confirmed from here.
- Not covered: Windows High Contrast / forced-colors (I only checked that the CSS rules exist), real OS zoom, the Send sheet (H1/P4 rows), the full sign-up flow from the Teacher explainer (B4), the class-off nozzle state at runtime (N8), network-failure rollback (B3), and widths 360 and 768 px.

## TOP 10 fixes (ranked)

| # | Severity | WCAG | Where (file:line / selector) | Repro | Fix |
|---|---|---|---|---|---|
| 1 | **Blocker** | 1.3.1, 3.3.2, 4.1.2 | Sign-up `#su_name`, `#su_dob` (`static/community.js:61,64`); also Edit `#editUnits #editPhotoMode #editFromBuild` (`index.html:173,174,178`) and Settings `#set_slicer` (`index.html:258`) | axe `label` / `select-name` (critical) when the Account and Settings dialogs and the Edit view are open, at 390 px in Chromium. Screen readers hear "edit text" and "date" with no name, on the sign-up form a parent or teacher must fill in | Add `for=`/`id` (or wrap the input in its label), as was already done for `#expertOpts` in `app.js:458-461`. Earlier finding #3, still open in these places. |
| 2 | **Blocker** | 2.1.1, 4.1.2 | Lesson cards `<div class="pcard" data-lesson>` (`community.js:317`, click delegation at `:321`); Edit history `<li data-goto>` (`edit.js:106`, `:111`) | Learn view: lesson cards report `tabIndex=-1` and contain no link or button, so a keyboard user can't open any lesson. That is the core classroom content | Use the Showcase pattern that already works: `<h3><a href="#learn/<id>">title</a></h3>` with a stretched link. For history steps, put a `<button>` inside each `<li>` and mark the current one with `aria-current="step"`. Earlier blocker #2 is fixed for Showcase only. |
| 3 | High | 2.4.3, 4.1.3 | Live view "Helped" button, `community.js:361` (re-render) and `:384-386` (handler) | Teacher → Live view → Tab to "Helped Ben" → Enter. The button is removed, so **focus drops to `<body>`** (both engines), and the announcement is just "Marked as helped." with no name | Before `livePoll()`, save the row id. Afterwards, move focus to that row's `<th>` (`tabindex=-1`) or to the next "Helped" button. Announce `"${nickname} marked as helped."` and clear `#liveSay` before writing (`textContent=""`, then set it about 60 ms later) so repeated text is spoken again. |
| 4 | High | 3.2.5-spirit, 2.4.3, spec "rows don't reorder under cursor" | `#liveSort` on → `community.js:349`, `:365` (`insertBefore` on every poll) | Tick "Show students who need help first", rest the pointer on the last row, then raise a hand. On the next 12 s poll, rows jump (Ava/Cy swapped under the pointer, both engines). Default join order is stable, which passes | When sorting is on, re-sort only when the teacher asks ("Re-sort now" button), or freeze order while the pointer or focus is inside `#liveRows` (`:hover`/`:focus-within`) and show "1 new hand. Re-sort?". |
| 5 | High | 3.3.1, 3.3.3 | `api()` in `static/app.js:24-28` | The server's 422 replies have `detail` as an **array** (checked: `width_mm=abc` → `[{type:"float_parsing",…}]`). `new Error(j.detail)` produces "**[object Object]**" (or raw pydantic text). Earlier High #10 is still open in code (spec P3) | If `Array.isArray(j.detail)`, map each entry to a friendly field message (`loc.at(-1)` → label) and fall back to "Something in the form isn't right. Check the highlighted field." Never show raw `msg`. |
| 6 | Medium | 2.4.7, 1.4.11; spec H4 "3 px ring everywhere" | `style.css:29` `input:focus,select:focus{outline:2px solid var(--acc);outline-offset:-1px}` and `:266` | Focus on the Mode select, Width, the Experienced inputs or the date field: the ring is **2 px `#5B3FD6`**. In Dark theme that is **2.57:1** on `#161B24` and 2.81:1 on `#0E1117`, below 3:1, and the spec itself says never use `--acc` as an edge on dark. It also overrides the global 3 px `--focus` ring at `:4` | Delete both rules (let `:focus-visible{outline:3px solid var(--focus)}` win), or use `outline:3px solid var(--focus)`. |
| 7 | Medium | 2.4.1; spec H4 | `index.html:13-14` (no skip link before `.topbar`) | The first Tab stop is the brand, then 4 tabs, Mode, Account and Settings, so 8 stops before any content (the top bar is 161–165 px and sticky) | Add `<a class="skip" href="#viewCreate">Skip to main content</a>` as the first child of `<body>`, visible on focus, and make `main` `tabindex=-1`. |
| 8 | Medium | 2.4.3, 2.1.2 (dialog modality) | Stacked modals: `#dlgSignout` opened from `#dlgAccount` (`community.js:126-148`); `#dlgDelClass` (`index.html:394`) | WebKit: Tab inside Sign out reaches **`dialog#dlgAccount`** (the dialog *underneath*) and then `dialog#dlgSignout` itself, and Shift+Tab in Delete class lands on the `<dialog>` element. Chromium cycles correctly (dialog buttons ↔ browser UI). Needs confirming in real Safari | Close or `inert` the parent dialog while the child is open (`$("#dlgAccount").inert = true`, restored on close), or reuse one dialog. Don't let the `<dialog>` element take focus (no `tabindex`, initial focus on a control). |
| 9 | Medium | 2.5.8 (AA fail), spec A6/H7 (44 px) | Teacher "Assign" checkboxes (`community.js:429`, 13×13, **axe target-size, 3 nodes** at 1280 px Chromium); Teacher explainer buttons 38 px (`app.js:61-63`, `#tnActions`); Delete class / Keep buttons 38 px and the desktop tabs 34 px (`style.css:39,43,88`; the 44 px rules apply only ≤ the mobile breakpoint, `:145,:195`); `.btn.small` 12 px text | Measured at 1280 px in Chromium. At 320/390 px most controls are already ≥44 | Make `min-height:44px` global for `.btn`, `.nav button` and `.tnote button`. Give the checkboxes 24 px and wrap each in a padded label (`.inl{min-height:44px;display:inline-flex;align-items:center}`). Raise `.btn.small` to ≥14 px. |
| 10 | Medium | 3.3.2, 4.1.2, 2.4.3 | Sign out dialog `community.js:127-148`, `index.html:391-393` | Initial focus is the ✕. "Sign out" is natively `disabled` with nothing saying why, so Tab skips it. For adults the checkbox is also disabled until "Show my recovery code" is pressed. A screen-reader user Tabs ✕ → Show code → Cancel and never learns there is a Sign out button or a prerequisite. Esc returns focus to "Sign out…" correctly | Use `aria-disabled="true"` (still focusable) plus `aria-describedby` → visible text "Tick the box above to sign out". Put initial focus on the first body control (`soCodeBtn` or the checkbox) with `autofocus`. |

Other findings (lower priority)
- **Live view**: when the hand is down, the Hand cell is **empty** (read as a blank cell). Show "–" or "No" (sr text "hand down"). The raised state is good: "✋ Needs help" text plus the row tint (`#8A5300` on `#FFE3CC` = 5.16:1) plus a "Helped <name>" button, so it doesn't rely on colour alone. Esc from Live view returns focus to the top-bar "Teacher tools" button but **does not reopen Teacher tools**, which loses the teacher's place (`community.js:378`). Narrow widths turn `table/tr` into `display:block` cards: add explicit `role="table|row|columnheader|rowheader|cell"` so Safari keeps table semantics (couldn't verify, see "What wasn't tested").
- **Delete class**: wording is fine ("Delete this class?", names the class, "can't be undone"). Initial focus is on **Keep**, Esc keeps the class and returns focus to the opener, and Enter on the initial focus keeps it, all pass. The danger button is `#B91C1C` on `#FFF1DC` (5.81:1), with a `--ctl` border at 4.35:1. Suggest naming the class on the button ("Delete Room 12") and giving the danger button a distinct shape (filled or bold border), so it isn't just red text on the same button style as Keep.
- **Nozzle**: after un-nozzling to zero, the live text says "**Nozzle removed. 0 nozzles.**" (`community.js:224`), while the spec says never "0" to a child. Use "Nozzle removed. No nozzles yet."
- **Teacher explainer**: the button reads "Close", where the spec says "Not now"/"Okay". Teens get only "Close", not "Join a class" (spec §4). The visitor heading "Teacher mode needs a grown-up account" differs from the spec ("…is for grown-ups with an account"). These are copy issues, and the behaviour is right.
- **Theme**: Dark does **not** follow the OS (`boot.js:5`, `style.css:1` say Warm is the default by design), so spec P6 fails. Either update the spec or add `prefers-color-scheme`.
- **Settings dialog**: `<nav class="tabs">` (`index.html:255`) is an unnamed nav that looks like tabs without tab semantics (earlier #9, still open there). `#shTabs` has the same problem.
- **Viewer** `aria-label` is static ("3D preview of your model…"). Spec H5 and earlier #4 want the model described (type, mm, pieces). Turn left/right/Reset buttons now exist, so earlier #4 is mostly fixed.
- `confirm()` is still used for deleting a build (`app.js:240`), which is earlier #11, partly open.

## Spec acceptance-test results

Legend: **P** pass · **F** fail · **Pt** partly tested or partly passing · **NT** not tested.

### mode-dropdown-spec.md §8
| Test | Result | Evidence |
|---|---|---|
| A1 axe 0 violations, all modes/themes/widths | **P** | 36 runs (2 engines × 3 widths × 3 modes × 2 themes), 0 violations |
| A2 name "Mode", no tablist | **P** | `<label for=modeSel>Mode</label>`; no `role="tablist"` in index.html |
| A3 keyboard, status updates, focus stays | **P** | ArrowDown → expert + "Experienced mode on…"; ArrowUp back; focus on `#modeSel` (both engines). Esc on an open list wasn't testable headless |
| A4 one polite announcement (real SR) | **NT** | `#modeStatus` clears and then sets after 60 ms (`app.js:44`), but no recording |
| A5 ineligible Teacher flow | **P** | Reverts to beginner, explainer shown, "…You are still in Beginner mode.", focus stays on select, buttons reachable by Tab, dismiss → focus back on select (labels "Close" not "Not now") |
| A6 ≥44 px, 16 px select, no h-scroll at 320 | **F** | Select 44/48 px and 16 px, no h-scroll; **explainer buttons 38 px** and Teacher tools 38 px at 1280 |
| A7 contrast | **P** | axe clean in both themes; select border 4.85 (warm) / 4.86 (dark). See TOP-10 #6 for the focus ring |
| A8 reduced motion, 200 % zoom, text zoom | **P** | Spinner `animation:none` under reduce; 640 px @ DPR 2 and text-200 %: no h-scroll, no clipped controls detected |
| B1 default/persist/junk | **P** | Fresh → beginner; reload keeps expert; junk → beginner |
| B2 auto-build vs button | **Pt** | Beginner auto-builds (sample → "Model ready…"); the Experienced side wasn't run |
| B3 keep photo/model/width across modes | **NT** | |
| B4 visitor → sign-up → Teacher | **NT** | |
| B5 teen never Teacher | **P** | Teen with `localStorage.level=teacher` → beginner, no class bar |
| B6 sign-out in Teacher → Beginner | **NT** | |
| B7 Teacher builds `beginner=true`, "Experienced" labels | **NT** | |
| B8 no server request on mode change | **P** | 0 `/api/` requests during the change |

**Mode: 9 P · 1 F · 1 Pt · 5 NT**

### nozzle-it-spec.md §10
| Test | Result | Evidence |
|---|---|---|
| N1 axe grid / item dialog / signed-out dialog | **P** | 0 violations (390 px, warm, both engines). Dark and 320/1280 weren't run on Showcase |
| N2 role, name, aria-pressed | **P** | `button`, "Nozzle it, no nozzles yet" → "Nozzle it, 1 nozzle", `aria-pressed` toggles |
| N3 keyboard order, Enter & Space, focus kept | **P** | Shift+Tab from the button = card title link; Enter and Space both toggle; focus stays |
| N4 spoken once (real SR) | **NT** | Live text is "Nozzle removed. **0 nozzles.**" (see other findings) |
| N5 reduced motion | **P** | `community.js:208` checks the media query, `style.css:345` |
| N6 ≥44×44, whole card opens from title | **P** | 58×44; `<li>` card with a title link |
| N7 contrast both themes + forced-colors | **Pt** | Warm passes (axe); dark Showcase and forced-colors not measured |
| N8 class-off/signed-out understandable without colour | **NT** | Code has a visible `.nz-note` and `aria-describedby` (`community.js:196-197`), not run |
| B1 toggle / count | **P** | |
| B2 grid ↔ dialog in sync | **P** | Both copies are `false/no nozzles yet` after toggling |
| B3 failure rollback + alert | **NT** | Code rolls back (`:226`) |
| B4 EXAMPLE no button; 0 shows no number | **P** | 10 cards, 1 button (the real item); count span empty at 0 |
| B5 signed-out → dialog, Not now returns focus | **P** | Dialog opens on "Not now"; Esc and Not now both return focus to the button |
| B6 own project static, no dislike | **P** | API `can_like_reason:"own"` → `nz-static` (`:193`); no dislike strings |
| B7 no "♥/like/heart" user-facing | **P** | grep of static/*: no user-facing hits |
| B8 `{}` still toggles | **P** | `liked:None` → toggle (`catalog.py:284-293`) |

**Nozzle: 12 P · 0 F · 1 Pt · 3 NT**
**Known gap now fixed:** the server **rejects a nozzle from a signed-out visitor**. `POST /api/showcase/<id>/like` with `{"liked":true}` and with `{}` both return **401** "Make a free account to nozzle projects." (`app/api/community.py:306-307`), and the count stayed at 0.

### home-redesign-spec.md §7
| Test | Result | Evidence |
|---|---|---|
| H1 axe Studio states/sheet | **Pt** | Empty, Experienced, Teacher and built: 0 violations (both themes, all widths). The Send sheet wasn't run |
| H2 no h-scroll; top bar ≤170 px at 320 | **P** | scrollWidth = viewport at 320/390/1280 and 200 %; top bar 161 px (Chromium) / 165 px (WebKit) |
| H3 landmarks / one h1 | **P** | 1 banner, 1 main, 1 contentinfo, navs "Main" + "Your progress", 1 visible h1 (an unnamed nav exists only inside Settings) |
| H4 keyboard order + skip link + 3 px ring | **F** | **No skip link**; select and inputs get a 2 px `--acc` ring (TOP-10 #6, #7). The rest of the order matches |
| H5 screen reader | **NT** | |
| H6 contrast | **P** | axe clean in both themes; spot checks: focus `#1D4ED8` on bg 6.35, white on `--acc` 6.72 |
| H7 targets ≥44 | **F** | Desktop tabs 34 px, Account/Settings 38, teacher lesson link 19 px tall, checkboxes 13 px |
| H8 reduced motion / forced colors | **Pt** | Reduced motion passes; forced-colors not run |
| H9 text-only 200 % | **P** | No clipping detected programmatically (both engines) |
| P1 one primary above the fold | **P** | "Take a photo" (WebKit) / "Choose a photo" (desktop Chromium) |
| P2 Beginner auto-build, result focused | **P** | "Model ready. Step 3 of 3…"; focus on `#resultH` |
| P3 friendly errors, no `[object Object]` | **F** | `api()` stringifies the 422 `detail` array (TOP-10 #5) |
| P4 Send sheet rows/focus | **NT** | |
| P5 classroom bar for Teacher only | **P** | Teacher sees the class bar and lesson line; teen doesn't |
| P6 dark follows OS | **F** | By design Warm is the default; it ignores `prefers-color-scheme` |
| P7 real iPhone/iPad | **NT** | |

**Home: 7 P · 4 F · 2 Pt · 3 NT**

**All three specs: 28 pass · 5 fail · 4 partly · 11 not tested (48 tests).**

### Screens not covered by a spec
| Screen | Result |
|---|---|
| Teacher Live view | **Mostly passes.** A real `<table>` with a caption, 5 `th[scope=col]` and a row header per student. Raised hand = ✋ text + "Needs help" + a "Helped <name>" button + a tint. `#liveSay` is polite and announces new hands ("Ben needs help."). Rows are stable in the default order. **Fails:** focus is lost after "Helped" (#3); rows reorder under the pointer when the sort is on (#4); the hand-down cell is empty |
| Sign out | Native dialog, labelled, Esc returns focus. **Issues:** disabled Sign out with no explanation, initial focus on ✕ (#10), WebKit focus leaks into the parent dialog (#8) |
| Delete class | **Passes**: initial focus on Keep, Esc and Enter keep the class, focus returns to the opener, clear "can't be undone" wording, `aria-describedby` on the body, axe clean, cycle stays inside in Chromium. Minor: generic "Delete class" label, weak danger styling, 38 px buttons on desktop, WebKit Shift+Tab lands on the `<dialog>` |

## Earlier Blocker/High issues (accessibility.md) — status at 22f091b
| # | Issue | Status | Evidence |
|---|---|---|---|
| 1 | Photo upload not keyboard-operable | **Fixed** | Real buttons `#sTake/#sChoose/#sSample` in the tab order; Edit has `#editChooseModel` with an `sr-only` input |
| 2 | Clickable div/li cards | **Partly fixed** | Showcase cards now have a title link plus a stretched card. **Lesson cards (`community.js:317`) and Edit history `<li>` (`edit.js:106`) are still mouse-only** |
| 3 | Unlabelled form controls | **Partly fixed** | Studio/Experienced are now labelled (axe clean). **Still open:** `#su_name #su_dob`, `#editUnits #editPhotoMode #editFromBuild`, `#set_slicer` |
| 4 | 3D viewer keyboard/text alternative | **Mostly fixed** | `role=img` + label, Turn left/right/Reset buttons. The label doesn't describe the model yet |
| 5 | No announcements; focus lost after build | **Fixed** | Polite `#pathSay`, `#makingLine`, `#buildHint`, `#modeStatus`, `#nzStatus`/`#nzAlert`; focus → `#resultH` after the build |
| 6 | No reflow at 320–390 | **Fixed** | No h-scroll at 320/390/640@2x; the bar wraps (161–165 px) |
| 7 | Text contrast | **Fixed** | New warm/dark palette; axe color-contrast clean in 36 runs |
| 8 | Non-text contrast | **Mostly fixed** | `--ctl` borders 4.35–4.86:1. **Exception:** the 2 px `--acc` focus outline on inputs/selects is 2.57:1 in Dark (#6) |
| 9 | ARIA misuse / missing state | **Mostly fixed** | Level tablist replaced by a native select; main nav `aria-current="page"`; style/thickness are real radios. **Still open:** Settings `.tabs` and `#shTabs` use `.on` only |
| 10 | Raw error messages | **Partly fixed** | Inline messages exist; the `api()` 422 array still gives "[object Object]" (#5) |
| 11 | `prompt()`/`confirm()` flows | **Mostly fixed** | Delete class and others are in-app dialogs; `confirm()` remains for deleting a build (`app.js:240`) |
| 12 | Flow not signposted | **Fixed** | "Your progress" 3-step path with a live status ("Model ready. Step 3 of 3…") |

Blocker/High summary: **5 fixed, 4 mostly fixed, 3 partly fixed, 0 untouched.** Both earlier Blockers that are still partly open (#2, #3) are TOP-10 #1–#2.
