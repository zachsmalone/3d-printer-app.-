# ZEIM — Accessibility & Usability Audit (WCAG 2.2 AA)

**Date:** 2026-10-04 · **Scope:** `/workspace/photo3d` (served at http://localhost:8765) — Studio, Edit, Showcase, Spark Lab (Learn), all dialogs, and the server-rendered pages `/p/<id>`, `/u/<id>`, `/static/COMMUNITY_GUIDELINES.html`.
**Method:** static review of `static/index.html`, `style.css`, `app.js`, `community.js`, `edit.js`, `viewer.js`, `app/api/learn.py` (server-rendered pages); live run of **axe-core 4.x** (WCAG 2.0/2.1/2.2 A+AA + best-practice tags) in headless Chrome against every view/dialog; scripted measurements (tab order, target sizes, 320 px reflow); contrast ratios computed from the CSS custom properties (WCAG relative-luminance formula). No screen reader or real-device testing was done, so SR announcement claims come from code/ARIA inspection.
**No app files were modified.** (Test helper scripts live in `/workspace/a11y-tools/`. My headless test sessions did create about a dozen throw-away build/edit folders under `/workspace/photo3d/outputs/` — see the note at the end.)

> **Build Plates (groups):** the feature is not built yet (README/ROADMAP; `branding.py` only holds the names), so there is no UI to audit. Forward-looking requirements are in "Notes for Build Plates" at the end.

## Summary

| Severity | Count |
|---|---|
| Blocker | 3 |
| High | 9 |
| Medium | 12 |
| Low | 6 |
| **Total** | **30** |

axe-core totals across all views: **critical** – unlabeled inputs/selects (≈35 controls), `aria-required-children` on `#levelSwitch` (every page); **serious** – colour contrast (up to 10 nodes/view), target size (`/u/<id>`), missing `lang`/`<title>` on guidelines page; **moderate** – no `<h1>` (Studio/Edit), heading order, content outside landmarks. axe "needs review" items for contrast (step-number badges, close "✕" buttons, EXAMPLE pill, primary buttons on gradient) are covered by the manual calculations below.

What already works well (keep): `<html lang="en">` on the app and server pages; viewport meta allows zoom; native `<dialog>.showModal()` (focus trap, Esc, inert background); native `<button>`s for nearly all actions; default browser focus ring is intact (no `outline:none` anywhere); Beginner/Expert split and "Auto-chosen settings (what/why)" table; "Try a sample photo" button; privacy defaults; kid-aware "no account needed, use a nickname" copy; logo `alt`; `QR` image has descriptive `alt`.

---

## BLOCKERS

### 1. Photo upload cannot be done with the keyboard (Studio and Edit)
- **Severity:** Blocker · **WCAG:** 2.1.1 Keyboard, 2.4.7 Focus Visible, 4.1.2 Name/Role/Value
- **Where:** `static/index.html:34-38` (`#drop` > `<input type="file" id="file" hidden>`), same pattern `index.html:136-139` (`#editFile`); `style.css:12` (`.drop`).
- **Evidence:** the `hidden` attribute makes the input `display:none`; live check `file.focus()` → not focused. The `<label class="drop">` is not focusable and has no role. Tabbing goes straight from "Try a sample photo" past the drop zone. A keyboard-only or switch user can only use the sample photo — they cannot start the app's core flow with their own photo.
- **Why it matters:** the whole product starts with "upload a photo"; this is the first step of the flow.
- **Fix:** don't use `hidden`; use a visually-hidden-but-focusable input and show focus on the label:
  ```css
  .drop input[type=file]{position:absolute;opacity:0;width:1px;height:1px}
  .drop:focus-within{outline:3px solid var(--acc2);outline-offset:2px}
  ```
  (give `.drop{position:relative}`), or replace the label with `<button type="button" id="pick">Choose a photo</button>` that calls `file.click()`. Add `aria-describedby` pointing to the "JPG / PNG · up to 25 MB" text. Keep drag-and-drop as an extra, not the only way. Repeat for `#editFile`.

### 2. Clickable `<div>`/`<li>` cards are unreachable by keyboard (Showcase, Spark Lab lessons, Edit step history)
- **Severity:** Blocker · **WCAG:** 2.1.1, 4.1.2, 1.3.1
- **Where:** `static/community.js:76` (`<div class="pcard" data-item>` → opens project), `community.js:156` (`<div class="pcard" data-lesson>` → opens lesson), `edit.js:86` (`<li data-goto>` step jump), click delegation at `community.js:81, 158`, `edit.js:91`; `style.css:88` (`cursor:pointer`).
- **Evidence:** no `tabindex`, no role, no key handler. Tab order in the live Showcase never enters the cards. Whole Showcase and all lessons (the school/classroom content) are mouse/touch-only. Same for the Undo-history "chips" in Edit.
- **Fix:** make the card's title a real link/button: `<a class="pcard" href="#p/ex07">…</a>` (or `<button class="pcard">`), or at minimum `role="button" tabindex="0"` + Enter/Space handler. For lessons use real links (`href="#learn/<id>"`; the router already supports it, `community.js:34`). For the step chips use `<button>` inside the `<li>` with `aria-current="step"` on the current one. Add `:focus-visible` style next to `:hover` at `style.css:89`.

### 3. Dozens of form controls have no programmatic label
- **Severity:** Blocker (blocks sign-up, joining a class, print options and all Expert/Edit tools for screen-reader users) · **WCAG:** 1.3.1, 3.3.2, 4.1.2
- **Where / evidence (axe "label"/"select-name", critical):**
  - Studio width slider `#widthRange` (`index.html:54`); all Expert inputs `resolution, smooth, gamma, min_thickness, max_thickness, border_mm, base_mm, relief_mm, levels, layer_mm, halftone_cell, palette`, `style` select (`index.html:68-91`).
  - Print dialog `#s_layer #s_fill #s_brim` (`index.html:190-192`), `#printerSel` (`:199`, plus `#resVis`/`#editVis` selects `:115, :170` and `#pub_vis`, `#pub_title`, `#pub_desc`, `#pub_tags` `:268-271`).
  - Sign-up `#su_name`, `#su_dob` (`community.js:43-44`), Join a class `#j_code #j_pw #j_nick` (`index.html:297-299`), Settings `#set_slicer #set_base` (`:213-214`) and every printer field (`app.js:200-206`, `<label>` with no `for`), teacher form `#cr_name #cr_pw` (placeholder only, `community.js:191`), Showcase search `#shSearch` (placeholder only, `index.html:245`).
  - Edit workspace: `#editUnits #editPhotoMode #editFromBuild` (`index.html:141-142, 147`) and every tool field generated by `lenInput`/`numInput` (`edit.js:16-17`: 10+ nodes on Expert), cut/boolean/text selects (`edit.js:~150-165`).
- **Root cause:** pattern `<div class="field"><label>Text</label><input …></div>` — a `<label>` only labels a control if it wraps it or has `for="id"`.
- **Fix:** one-line change in each template: add `for`/`id` (or wrap the input in the label). In the JS generators (`lenInput`, `numInput`, `renderPrinters`, `renderLinkInputs`) generate unique ids: `const id="f_"+name; <label for="${id}">…<input id="${id}" name="${name}">`. For search and the teacher form add visible labels or `aria-label`. Make the `<em>` unit text part of the label (it is) and add `aria-describedby` for hint text.

---

## HIGH

### 4. 3D viewer: no keyboard control, no name/role, no text alternative; drag-only gestures
- **Severity:** High · **WCAG:** 1.1.1, 2.1.1, 2.5.7 Dragging Movements, 4.1.2
- **Where:** `static/viewer.js:2-3, 8-11` (`new OrbitControls(camera, canvas)` but `listenToKeyEvents()` never called, so arrow-key orbit/pan in `vendor/OrbitControls.js:136` is off), canvas created with no attributes (live: `tabindex/role/aria-label` all null); Edit measure tool is pointer-only `edit.js:25-27, 277-292`; instruction "Drag to rotate · scroll to zoom · right-drag to pan" `index.html:102, 154`.
- **Why it matters:** the "preview" step of upload → preview → print is invisible to AT users and un-operable by keyboard; rotating needs a drag with no single-pointer/keyboard alternative.
- **Fix:**
  1. After creating controls: `canvas.tabIndex=0; canvas.setAttribute("role","img"); canvas.setAttribute("aria-label", "3D preview …"); controls.listenToKeyEvents(canvas);` and add `:focus-visible` outline on `.viewer canvas`.
  2. Update the `aria-label`/a visible caption on every `load()`: e.g. "Lithophane, 106 × 81 × 3.2 mm, 1 piece, ready to print" (the data already exists in `stats`).
  3. Add real buttons next to Reset/Wireframe: Rotate ◀ ▶ ▲ ▼, Zoom + −, Pan (with `aria-label`s), ≥ 44 px.
  4. Edit measure: allow typing/choosing two points via keyboard, or show bounding-box dimensions as text (already in "Measure & info" table `edit.js:~207`) and say so.
  5. Make the instruction text real keyboard help ("Click the model, then use arrow keys…") and link it via `aria-describedby`.
  6. If WebGL fails (`app.js:25`, `edit.js:22` only `console.warn`), show a visible message ("Your browser can't show the 3D preview, but you can still download your file") instead of leaving the placeholder.

### 5. Progress, results and errors are never announced; focus is lost after Build
- **Severity:** High · **WCAG:** 4.1.3 Status Messages, 2.2.1 Timing Adjustable, 2.4.3 Focus Order
- **Where:** live count of `[aria-live],[role=status],[role=alert],[aria-busy]` in the whole app = **0**. `index.html:103` (`#busy` "Building…" overlay), `index.html:304` + `app.js:11-14` (`toast()`: plain divs auto-removed after 4.5 s / 8 s), `app.js:97-103` (result stats rendered silently), `app.js:79,87` (Build button is disabled while it has focus → focus falls to `<body>`), `app.js:179-182, 186-188` (slice/send status text), `edit.js:15` (`#editBusy`), `edit.js:83` (`#editMsg`), `community.js:175` (`#qzOut` "Correct!/Not quite"), `index.html:97` (`#buildHint`).
- **Why it matters:** a blind user presses "Build 3D model", hears nothing, and focus is on nothing. Error toasts vanish in 8 s; slow readers/SR users can miss them (2.2.1).
- **Fix:**
  - `#toasts` → `role="region" aria-label="Notifications"` with `aria-live="polite"`; error toasts `role="alert"`; stop auto-dismiss for errors (or ≥ 20 s + a close button + pause on hover/focus).
  - `#busy` → `role="status"`; set `aria-busy="true"` on the stage while building; put text like "Building your model… this usually takes a few seconds" and make `hidden` toggling not suppress the announcement (keep an always-present polite live region and write messages into it: "Build finished: Lithophane 106 × 81 × 3.2 mm, watertight").
  - After success move focus to the result heading (`tabindex="-1"` + `.focus()`), or at least keep focus on the Build button (use `aria-disabled="true"` instead of `disabled`).
  - Wrap `#buildHint, #sliceOut, #sendOut, #editMsg, #shNotice, #qzOut` in `aria-live="polite"`.

### 6. Layout does not reflow: horizontal scroll at 320–390 px (the top bar never wraps)
- **Severity:** High · **WCAG:** 1.4.10 Reflow (also 1.4.4/1.4.12 comfort)
- **Where:** `style.css:4` (`.topbar{display:flex;…}` with no `flex-wrap`), `index.html:13-28`.
- **Evidence (live, headless Chrome):** at 320 px width `document.documentElement.scrollWidth = 809` (client 320); at 390 px (typical phone) also 809. Overflow comes from `#mainNav`, `#levelSwitch`, `#btnAccount`, `#btnSettings` in the single non-wrapping row. Page body below the header does stack correctly at < 960 px (`style.css:7`), so only the header is broken. The sticky 100 px-tall header also eats screen at 320 px.
- **Fix:** `.topbar{flex-wrap:wrap;gap:8px 12px}` `.nav{flex-wrap:wrap}`; below 640 px collapse Account/Settings into icon+label buttons or a menu; move the Beginner/Expert switch under the nav; make the topbar `position:static` on small screens. Re-test at 320 px and 400 % zoom.

### 7. Text colour contrast failures
- **Severity:** High · **WCAG:** 1.4.3 Contrast (Minimum)
- **Computed from CSS (`style.css:1` variables), body text is OK (`--txt` on panels 13:1; `--mut` #8b97ad on panels 5.4–6.4:1), but:**

| Where | Colours | Ratio | Needs |
|---|---|---|---|
| Selected toggle/preset/mode text: `.seg button.on` (Beginner/Expert, Thin/Standard/Thick, unit toggle, Showcase tabs) `style.css:34` | #fff on #7c5cff | **4.35:1** (14 px) | 4.5 |
| Primary buttons `.btn.primary` (Build, Print, Publish, Join…) `style.css:37` | #fff on gradient #7c5cff → #5b8cff | **4.35 → 3.16:1** | 4.5 |
| Unit/hint text in labels `.field label em` (`opacity:.65`) `style.css:21` — "mm", "px wide", "hex, dark→light" … | ≈#626c7d on #161b24 | **3.26:1** (3.07 on panel2) | 4.5 |
| "Empty slot" `.hslot` `style.css:63` | #4b566d on #161b24 | **2.34:1** | 4.5 |
| Disabled/future items (`opacity:.45/.4`) – exempt if truly disabled, but `.oplist li.future` is clickable `style.css:120` | ~#3f4655 | < 3 | 4.5 |
| Links in dialogs `a` default blue on dark (axe: `a[href$=ex-ada]` in item dialog, `<a>` in `.sharepage` uses #22d3ee OK) and `--acc` (#7c5cff) used as text/border on #161b24 | | **3.97:1** | 4.5 (text) / 3 (border OK) |
| Tag/pill text 11–12 px in `--mut` | 5.3–5.9:1 | passes but very small (see #20) |

- **Fix:** darken the selected-state background (e.g. `--acc:#5b3df0` → white 6.4:1) or use dark text on the lighter accent; make the primary gradient end at ≥ 4.5:1 (e.g. `#6b4cff → #4f6fe8`); drop `opacity:.65` on `em` and use `--mut`; raise `.hslot` text to `--mut`; give `.oplist li.future` a non-opacity cue (dashed border + italic) at full contrast. Re-check the close "✕" (#8b97ad on panel, fine at 5.9 but 18 px glyph is OK) and the EXAMPLE pill (semi-transparent black over gradient—ensure ≥ 4.5 with solid `#000c`).

### 8. Controls and boundaries below 3:1 (non-text contrast)
- **Severity:** High · **WCAG:** 1.4.11 Non-text Contrast
- **Where:** `--line:#2a3344` is used for input/select borders (`style.css:24`), buttons (`:35`), cards (`:17`), the dashed drop-zone border (`:12`), segmented-control boundaries (`:31`). Computed: **1.49:1 vs page bg #0e1117; 1.36:1 vs panel #161b24**. Text inputs are `--bg` on `--panel` (≈1.1:1 fill difference) so fields are nearly invisible for low-vision users. Unselected `.card`/`.seg` state is also shown only by this faint border.
- **Fix:** introduce `--ctl:#6b7a99` (≥ 3:1 on both bg and panel) for borders of inputs, selects, buttons, cards, the drop zone and toggle groups; keep `--line` for decorative dividers only. Selected state: add a non-colour cue (✓ icon or bold + 2 px border) in addition to colour.

### 9. ARIA misuse and missing state on custom controls
- **Severity:** High · **WCAG:** 4.1.2, 1.3.1, 1.3.2
- **Where / evidence:**
  - `index.html:21` `<div class="seg" id="levelSwitch" role="tablist">` whose children are plain `<button>`s with no `role="tab"` → axe **critical** `aria-required-children` on every page; and it doesn't behave like tabs (no arrow keys, no `aria-selected`, no tabpanel).
  - Selected state is only a CSS class (`.on`) for: level switch (`app.js:32`), style cards `#modeCards` (`:37`), thickness `#presetSeg` (`:43`), main nav `#mainNav` (`community.js:23`), Showcase tabs `#shTabs`, Settings `.tabs` (`app.js:244`), unit toggle `#unitSeg`, Edit big tools `.bigtool.on`, hollow wall presets. Screen readers can't tell which option is chosen.
  - `.tabs` (Settings) and `#shTabs` look like tabs but have no tab roles.
  - `<label class="inl" title="Who can open this build's files"><select …>` – `title` is the only name for the visibility select.
- **Fix:** remove `role=tablist` from the level switch and use toggle buttons with `aria-pressed="true|false"` (or radio-group: `role="radiogroup"` + `role="radio" aria-checked`). Style cards/presets: `aria-pressed` or real radios styled as cards (best — gives arrow-key behavior). Main nav: `<nav aria-label="Main">` with `aria-current="page"` on the active item (ideally real `<a href="#showcase">` links since they change the hash). For genuine tabs (Settings, Showcase) implement the full tabs pattern (roles, `aria-selected`, `aria-controls`, roving tabindex, arrow keys). Replace `title` with a real label.

### 10. Error and validation messaging is raw, easy to miss, and sometimes unreadable
- **Severity:** High · **WCAG:** 3.3.1 Error Identification, 3.3.3 Error Suggestion, 3.3.2 Labels or Instructions, 4.1.3
- **Where / evidence:**
  - All errors are toasts (`app.js:86, 108, 109`; `community.js` many) that disappear; nothing is shown next to the field, no `aria-invalid`, no `required`.
  - Server validation errors are shown verbatim: uploading a text file returns `cannot read image: cannot identify image file <_io.BytesIO object at 0x7fa9…>`; `width_mm=abc` returns a FastAPI 422 **array** which `api()` (`app.js:18`: `new Error(j?.detail …)`) turns into the toast text **"Build failed: [object Object]"**; `width_mm=99999` → `width_mm must be 5..1000` (technical, no field highlight).
  - Required fields (display name, date of birth, class code/password/nickname, publish title + guidelines checkbox) aren't marked required or described before submit; `maxlength` silently truncates.
  - Client side: no validation of file type/size before upload (`app.js:48-53`), `min/max` on number inputs aren't surfaced.
- **Fix:** map server errors to friendly sentences ("That file isn't a photo we can open. Try a JPG or PNG under 25 MB."); in `api()` flatten 422 `detail[]` into `loc + msg`; show inline messages under the field (`<p id="err_x" role="alert">`) with `aria-invalid="true"` and `aria-describedby`; mark required fields (`required` + visible "(required)"); validate file type/size client-side before enabling Build; show errors in a persistent `role="alert"` box near the Build button instead of (or in addition to) toasts.

### 11. Report / feedback / "which build?" flows use browser `prompt()` and require typing machine codes
- **Severity:** High (usability, kid/school safety flow) · **WCAG:** 3.3.2, 3.3.5-spirit, 2.4.3; cognitive accessibility
- **Where:** `static/community.js:103` — `prompt("Report reason: minor_safety, not_family_friendly, copyright, harassment, personal_info, other", "not_family_friendly")` followed by a second `prompt("Details (optional)")` (`:105`); `community.js:210` teacher feedback `prompt()`; `community.js:219` "Which build? Type a number:" `prompt()`; `app.js:134`, `community.js:212` `confirm()` for deletes.
- **Why it matters:** a child (or anyone) who wants to report something unsafe must type an internal identifier exactly; typos return an error; native prompts can't be styled/translated/labeled, break on some embedded/kiosk school browsers, and the default silently pre-selects "not_family_friendly". The safety-critical path should be the *easiest* one.
- **Fix:** replace with a `<dialog>` containing a `<fieldset><legend>What's wrong?</legend>` of radio buttons with plain labels ("It's not safe for kids", "Someone's real photo or personal info", "Bullying or mean", "It copies someone else's work", "Something else") + optional textarea + clear "Send report" button and a confirmation message. Same for build picker (radio list with thumbnails) and delete confirmations (dialog that names the item).

### 12. The "upload → preview → print-ready" flow is not clearly signposted, and "Print" is a technical wall
- **Severity:** High (usability) · **WCAG:** 3.3.2, 2.4.6; cognitive accessibility
- **Where / evidence:** `index.html:96-127`, `app.js:91-106`, `app.js:158-183`, `index.html:181-204`.
  - Steps 1-3 are numbered, but after "Build 3D model" there is no "Step 4 / what now?" The result appears *below* the viewer (below the fold at ≤ 960 px, far from the Build button in the stacked mobile layout). No "Ready to print ✔" summary; only chips like "282,108 triangles · 1 body · ✔ watertight".
  - **"Print…" is always enabled**, even when the model is "✖ not watertight" (`app.js:99`) — nothing explains whether it's safe to print.
  - The Print dialog leads with "Open in your slicer" (needs desktop software installed), then Layer height / Infill % / Brim mm / Supports / "Stand upright" with no explanations, then "Send to a network printer" (needs Settings). A student or family with no printer setup has no obvious path: the plain "download 3MF" link is a ghost button at the end of the slicer list (`app.js:166`).
  - No size-fit check against a printer bed or common bed sizes; no time/filament estimate until after slicing; only 5 builds are kept (`app.js:138-146`) and hitting the cap interrupts the flow with a dialog (see #24).
- **Fix:**
  - Add a short, always-visible 4-step progress list: *1 Photo → 2 Style → 3 Size → 4 Build & print*, and after a build show a "Your model is ready" panel: big thumbnail/preview, plain-language checks ("Closed shape ✔ — printers can read it", "Fits on a 220 mm printer ✔", "Thin parts: none"), and the **one** recommended next action ("Download for printing (3MF)").
  - Make "Print…" a stepper with three plain choices: **Download file**, **Open in my slicer app**, **Send to my printer** (hidden or "set up first" when no printer), each with one sentence on what it does. Move the technical options into an "Advanced" `<details>`.
  - Disable/annotate Print when not watertight with a "Fix automatically" button (the Edit tool already has Fix).
  - On mobile, scroll/focus to the result after Build (see #5).

---

## MEDIUM

### 13. Single-page navigation doesn't change title, focus or announce; no skip link; weak landmark/heading structure
- **WCAG:** 2.4.1 Bypass Blocks, 2.4.2 Page Titled, 2.4.6, 1.3.1, 4.1.3
- **Where:** `community.js:22-35` (`show()` just toggles `hidden`); `document.title` is "ZEIM" everywhere (`community.js:9`); `index.html:13-28` header/nav; four sibling `<main>` elements (`index.html:30, 132, 243, 251`; only one visible at a time — OK, but the active one never gets focus).
- Evidence: ~9 tab stops (logo, 4 nav, 2 level, 2 account) precede content; the first `<h1>` exists only in Showcase/Learn (`axe: page-has-heading-one` on Studio and Edit; Studio headings are h2 steps then h3 "Recent builds"); lesson view jumps h2 → h4 (`community.js:165`, axe `heading-order`); `<nav class="nav">` has no `aria-label`; the toast container sits outside any landmark (axe `region`).
- **Fix:** add `<a class="skip" href="#content">Skip to main content</a>`; give each view an `<h1>` (visually hidden in Studio/Edit: "Studio — make a 3D print from a photo"); on view change set `document.title = "Showcase · ZEIM"`, move focus to the view's `<h1>` (`tabindex="-1"`) and announce via the live region; label `<nav aria-label="Main">`; fix heading order (h2 → h3 in quiz); put `#toasts` in a labelled region. Give the logo link a text name ("ZEIM home") rather than relying on `title`.

### 14. Touch / pointer target sizes
- **WCAG:** 2.5.8 Target Size (Minimum, 24 px) — AA in 2.2; 2.5.5 (44 px) as good practice
- **Measured (1280 px viewport):** `#widthRange` 252×**16** px; history-card buttons/links "Open", "STL", "OBJ", "3MF", 🗑 `style.css:61` ≈ 34–43 × **22** px with 4 px gaps (below 24 px, spacing exemption not met for the smallest ones); `.x` close buttons (no padding, `style.css:69`); `.btn.small` (≈ 26–28 px) and `.seg button` (≈ 28 px); checkbox/radio inputs have default 13 px boxes (labels are clickable, OK); `/u/<id>` project links 3 × < 24 px (axe `target-size`, serious). **30 interactive elements are < 44 px** on the Studio page alone. `.hcard img` (thumbnail) is also a click target but has no keyboard equivalent besides the Open button (acceptable).
- **Fix:** `.hcard .row2 a,.hcard .row2 button{min-height:32px;padding:6px 10px}` (≥ 44 px on coarse pointers via `@media (pointer:coarse)`); `.x{min-width:44px;min-height:44px}`; `input[type=range]{height:24px}` (or larger thumb); `.sharepage li a{display:inline-block;padding:6px 0}`.

### 15. Dialogs: unnamed, "✕" close buttons unlabeled, focus handling after re-render
- **WCAG:** 4.1.2, 2.4.3, 1.3.1
- **Where:** all nine `<dialog>`s `index.html:181-302` have no `aria-labelledby` (live check: all `none`); close buttons are `<button class="x" data-close>✕</button>` with no accessible name (`index.html:182, 208, 234, 260, 265, 278, 283, 289, 294`); `community.js:187-215` `openTeacher()` rebuilds `#teacherBody.innerHTML` after every action (mute, remove, mark read, create class), so focus drops to `<body>` inside an open modal; `community.js:84-111` `openItem()` is re-called after Like/Follow (same focus loss — Like button disappears and is recreated); `#fullList` (`app.js:144`) re-renders after delete.
- Good: native `showModal()` provides the focus trap, Esc to close, inert background and focus return to the opener.
- **Fix:** `<dialog aria-labelledby="dlgPrintTitle">` with the `<h3>` given that id; `<button class="x" aria-label="Close dialog">✕</button>` (add `aria-hidden` to the glyph); after re-render restore focus to the same control (`const id=document.activeElement?.id` … `$("#"+id)?.focus()`) or update only the changed nodes; `aria-pressed` on Like/Follow so a state change doesn't need a re-render.

### 16. Copy is jargon-heavy for kids and school users
- **WCAG:** 3.1.5 Reading Level (AAA, but explicit project goal); 3.3.2
- **Examples:** *Lithophane, Relief, Pop-art, Posterize, Halftone, σ (smoothing), Gamma, Infill %, Brim, Supports, Watertight, Triangles, Bodies, Slicer, G-code, STL/OBJ/3MF, Boolean, Hollow/Drain hole, Mesh*; "Auto-chosen settings" table (`app.js:103`) with "~0.35 mm per pixel"; "OAuth connections (scaffold — sharing not implemented)" and "API keys are stored in `data/settings.json`" in user-facing Settings (`index.html:218, 224`); status text "Follow is scaffolding — a feed of followed creators isn't built yet" (`community.js:99`) and "EXAMPLE seed data" (`community.js:85`); error "Chat doesn't allow that language." wording is fine but unexplained.
- Positive: Beginner mode, "Glows when backlit", "Layers pop off the page", "No account needed. Use a nickname — not your real full name".
- **Fix:** add one-line "What's this?" help (`<details>` or `aria-describedby`) for each technical term; rename "watertight" → "Closed shape — ready to print"; "triangles" → hide behind "Details"; "Slice" → "Prepare for printer (make G-code)"; hide developer notes (scaffold/stub/API-key paths) from the student UI or put them behind "For grown-ups / Developers"; aim for ~grade 5–6 wording in Beginner and Spark Lab; keep a glossary link.

### 17. Community Guidelines page (and any static page) lacks `lang`, `<title>`, and landmarks
- **WCAG:** 3.1.1 Language of Page, 2.4.2, 1.3.1, 2.4.1 · **Where:** `static/COMMUNITY_GUIDELINES.html:1-14` (axe: `html-has-lang`, `document-title`, `landmark-one-main`, `region` ×6). This page is required reading — the Publish dialog's checkbox links to it (`index.html:272`) and it is the family-safety policy.
- **Fix:** add `<!doctype html><html lang="en"><title>Community Guidelines · ZEIM</title>`, wrap content in `<main>`, give the body a `<header>`/home link, use an `<ol>` for the numbered rules (currently "1. … 2. …" typed into a `<p>`), and mark the link `target=_blank` as "(opens in a new tab)".

### 18. Focus may be hidden behind the sticky header
- **WCAG:** 2.4.11 Focus Not Obscured (Minimum) — new in 2.2
- **Where:** `style.css:4` (`.topbar{position:sticky;top:0;z-index:5}`) and no `scroll-padding-top`; fixed toasts bottom-right (`style.css:77`, z-index 50) can cover focused controls near the bottom edge.
- **Fix:** `html{scroll-padding-top:80px}` (header height; less once #6 is fixed); keep toasts out of the way when the focused element is under them (or make them dismissible/focusable); make the header non-sticky on small screens.

### 19. No `prefers-reduced-motion` support
- **WCAG:** 2.3.3 Animation from Interactions (AAA; recommended), 2.2.2 Pause/Stop/Hide for auto-playing motion
- **Where:** `style.css` has zero `prefers-reduced-motion` rules. Motion: infinite spinner `style.css:46`, `transition:.15s` on many controls, `.pcard:hover{transform:translateY(-2px)}` `:89`, `scrollIntoView({behavior:"smooth"})` `community.js:168`, OrbitControls `enableDamping=true` `viewer.js:10`.
- **Fix:** 
  ```css
  @media (prefers-reduced-motion: reduce){*{animation-duration:.01ms!important;animation-iteration-count:1!important;transition:none!important;scroll-behavior:auto!important}.spin{animation:none;border-top-color:var(--acc2)}}
  ```
  and in JS: `controls.enableDamping = !matchMedia("(prefers-reduced-motion: reduce)").matches;` plus `behavior: reduce ? "auto" : "smooth"`. Keep the "Building…" text so the spinner isn't the only cue.

### 20. Very small text
- **WCAG:** 1.4.4 Resize Text, 1.4.12 Text Spacing (comfort) · **Where:** base 14 px (`style.css:3`), `.help` 12 px, `.card small` 11 px, `.hcard .row2` 11 px, `.pill/.tag` 11–12 px, `.pcard .ex` **10 px** (`style.css:92`), `.help` used for important instructions (privacy explanations, safety rules). Fixed-height rows could clip when users apply text-spacing overrides (`.hcard .meta b{white-space:nowrap;overflow:hidden}` `style.css:59`, `.viewer` fixed height).
- **Fix:** base 16 px with `rem` units; minimum 12–13 px for any text; move important rules out of `.help` (muted, small) into normal-size body text; allow wrapping on card titles (use `line-clamp` with `title`/tooltip fallback).

### 21. Image alternatives have gaps
- **WCAG:** 1.1.1 · **Where:** `index.html:36` `<img id="dropPreview" alt="">` – the user's chosen photo is presented with an empty alt and nothing else announces it (only `#buildHint` text changes silently, `app.js:52`); `community.js:87` item-dialog image `<img src=… style=…>` **has no `alt` attribute**; `app.js:141` `.fl img` no `alt`; Showcase/history thumbnails use `alt=""` (`community.js:76`, `app.js:119`) — acceptable only because the title is adjacent, but the card is not a link (see #2); lesson/project emoji (🖼️ 🎨) are announced by name in headings/titles (`community.js:162`).
- **Fix:** set `dropPreview.alt = "Your photo: " + file.name` on selection; give thumbnails `alt="Preview of <title>"` where the image is the only link content; add `alt=""` explicitly where decorative; wrap decorative emoji in `<span aria-hidden="true">` (see #26).

### 22. Upload feedback and validation are minimal
- **WCAG:** 3.3.1, 3.3.4, 4.1.3 (usability)
- **Where:** `app.js:48-53, 56-58, 62-88`; `index.html:37` ("JPG / PNG · up to 25 MB").
- **Evidence:** the file picker accepts `image/*` but the copy says JPG/PNG (phone HEIC/WebP photos will be selectable and then fail with the raw server message, see #10 — not verified with a real HEIC); dropping any file type enables Build (`setFile()` just creates an object URL); size limit (25 MB, `app/config.py:10`) is only checked server-side; there is no upload/processing progress, estimated time, or Cancel (the whole `/api/generate` is a single `fetch`); the "Try a sample photo" fallback is good.
- **Fix:** check `type` and `size` on selection and say what to do; show the file name + size + a "Remove/Choose another photo" button; show "Uploading… / Making your model… (about N seconds)" in the status region; add `AbortController` + Cancel; either list the formats you really support or convert unsupported ones.

### 23. 3D viewer performance & resilience on school hardware
- **WCAG:** 2.2.2 (related), usability · **Where:** `viewer.js:23-24` — `requestAnimationFrame` render loop runs forever, even when idle, hidden (Studio view hidden behind Edit/Showcase), or the tab is in the background; Edit creates a *second* `Viewer`/WebGL context (`edit.js:22`); `renderer.setPixelRatio(min(dpr,2))`.
- **Evidence:** in headless Chrome with software GL, page navigations with both viewers alive repeatedly timed out until viewers were avoided (anecdotal; not reproducible on real GPUs). Chromebook/older-laptop users and anyone using forced-colors/zoom may see lag.
- **Fix:** render on demand (`controls.addEventListener("change", render)`; only animate while damping), stop the loop when the view is `hidden`/`document.hidden`, share one renderer between Studio and Edit, expose a "Low-power preview" toggle, and honour `prefers-reduced-motion` (#19).

### 24. Destructive "Auto-delete oldest & build" and the 5-build cap
- **WCAG:** 3.3.4 Error Prevention (data), 3.3.2 · **Where:** `index.html:233-240`, `app.js:138-148`.
- **Issue:** the dialog title "Build history is full" doesn't name which build will be deleted; "Auto-delete oldest & build" is a one-click irreversible delete of user work; "Delete" buttons per item have no confirmation and no accessible name beyond "Delete" (which build?); list re-render drops focus. History slots also use a bare 🗑 emoji button with no accessible name (`app.js:123`).
- **Fix:** name the item ("Delete 'Sunset lithophane' (made 2 days ago)?"), `aria-label="Delete {title}"`, offer "Download its files first" link, and restore focus to the next delete button. Consider raising the limit or archiving instead.

---

## LOW

### 25. Emoji used as icons inside accessible names
`index.html:22-23, 26-27, 45-47, 96, 115-118`; `app.js:123` — buttons read as "seedling Beginner", "gear Settings", "sparkles Build 3D model", "globe Share to Showcase", "wastebasket" (🗑 button has *no* text name at all). **Fix:** wrap in `<span aria-hidden="true">` and add visible text or `aria-label` (🗑 → "Delete {title}").

### 26. Data tables lack headers/captions
`index.html:121`/`app.js:103` ("Auto-chosen settings" `<table>` rows are label/value/why with no `<th>`/`<caption>`); Edit "Measure & info" `edit.js:~207`. **Fix:** `<th scope="row">` for the first cell, `<caption>` or `aria-labelledby` the `<summary>`.

### 27. `autocomplete` and password-field handling
`index.html:298` class password has `autocomplete="off"` (acceptable for shared class passwords but 3.3.8 Accessible Authentication requires not blocking paste/password managers — it doesn't block paste, so pass); sign-up fields lack `autocomplete` (`name`/`bday` purpose per 1.3.5) `community.js:43-44`; axe console warning "Password field is not contained in a form". **Fix:** wrap dialog inputs in `<form method="dialog">` so Enter submits (currently Enter in "Nickname" does nothing — `index.html:293-302` uses a click handler on a button); add `autocomplete="off"` deliberately with a comment, `bday` only if desired.

### 28. New-window links and `rel` hygiene
`index.html:272`, `community.js:53, 86, 194` use `target="_blank"` with no "(opens in new tab)" text and no `rel="noopener"` (modern browsers imply it, but add for older school browsers). **Fix:** add text/icon with `aria-label`/visually-hidden text.

### 29. Keyboard shortcut and hover-only hints
`edit.js:107-111` Ctrl+Z / Ctrl+Y only work when focus is outside inputs (fine, 2.1.4 not triggered because modifiers are used) but are only documented in `title` tooltips (`index.html:158-159`), which keyboard/touch/SR users don't reliably get. **Fix:** visible hint "Shortcut: Ctrl+Z" / `aria-keyshortcuts="Control+Z"`.

### 30. Minor markup consistency
Duplicate `.brand` rule and unused `.logo` styles (`style.css:5, 82`); `<label class="inl" title=…>` wrapping a `<select>` with no label text (`index.html:115, 170`) — covered by #3; `target=_blank` link colour `a` in dialogs uses UA blue on dark (axe contrast in item dialog) — style `a{color:var(--acc2)}` globally with underline (don't rely on colour alone, 1.4.1). **Fix:** add `a{color:var(--acc2);text-decoration:underline}` in `style.css` outside `.sharepage`.

---

## Notes for Build Plates (groups) — when built
Not testable today; requirements to build in from day one: group list/cards as real links with the group name as the link text; join/leave as buttons with `aria-pressed`/state text; any member lists as `<ul>`; every chat/post field labelled; the language-filter rejection message ("Chat doesn't allow that language. Please use appropriate language.") shown inline next to the message box with `role="alert"` and `aria-invalid`, plus a kid-friendly "why" and a retry path (no loss of typed text); report/block flows as accessible dialogs (see #11); new-message arrival announced politely (not per-message for fast chats) with a "pause live updates" control; no auto-scrolling that steals focus; avatars with text alternatives; moderation/safety help linked from every Build Plate page; ensure the 13+ and teen defaults are explained in plain language.

## Quick wins (≈ a day of work, high impact)
1. **Un-hide the file input** (visually-hidden + `:focus-within` ring) — fixes the #1 blocker (`index.html:35,137`).
2. **Add `for`/`id` to every `<label>`** in templates and the two JS generators (`lenInput`/`numInput`, printer/link renderers) — clears ~35 axe criticals.
3. **Turn cards into links/buttons** (`community.js:76,156`, `edit.js:86`).
4. **Add `aria-live="polite"` to `#toasts`, `#busy` (role=status), `#buildHint/#sliceOut/#sendOut/#editMsg`**; keep focus on Build (use `aria-disabled`); make error toasts persistent.
5. **Remove `role="tablist"` from `#levelSwitch`; add `aria-pressed`** to level/mode/preset/unit buttons and `aria-current="page"` to the nav.
6. **`aria-label="Close dialog"` on all ✕ buttons** and `aria-labelledby` on all `<dialog>`s.
7. **Darken `--acc` (≈ #5b3df0) and the primary gradient, remove `opacity:.65` on `label em`, add `--ctl` border colour** for form controls.
8. **`.topbar{flex-wrap:wrap}`** to stop the 809 px horizontal overflow on phones.
9. **Add `<html lang>`, `<title>`, `<main>` to `COMMUNITY_GUIDELINES.html`**, plus a skip link and an `<h1>` on Studio/Edit.
10. **Add the `prefers-reduced-motion` block** and `scroll-padding-top`.
11. **Canvas `tabindex=0`, `role="img"`, `aria-label` with model dimensions, `controls.listenToKeyEvents(canvas)`.**
12. **Fix the `[object Object]` error** in `api()` (`app.js:18`) and replace raw server messages with friendly ones; swap `prompt()` Report flow for a radio-button dialog.

## Test artifacts / housekeeping
- Helper scripts and raw results: `/workspace/a11y-tools/` (`run2.py`, `run3.py`, `axe.json`, screenshots; `node_modules/axe-core`). Nothing under `/workspace/photo3d/static` or `/workspace/photo3d/app` was edited (the repo already had uncommitted changes from other work in `app/`; I did not touch them).
- My headless sessions (anonymous cookie sessions) used the app's normal API: sample-photo builds, one Edit "sample model" project, and 3 deliberately invalid `curl` uploads (rejected). This left roughly a dozen extra folders in `/workspace/photo3d/outputs/` (build/edit outputs) — safe to delete (they were not in the original 8). I did not remove them.
