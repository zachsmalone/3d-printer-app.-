# ZEIM design, accessibility & kid/teacher-friendliness audit

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


**Author:** Sakura (Design & UX lead) · **Date:** Sun 2026-10-04 (CT) · **Scope:** read-only audit of `/workspace/photo3d` (README, ROADMAP, `static/*`, relevant `app/*` copy) and the running app at `localhost:8765`.
**Status:** first-pass audit. Read the **Hansei** section to see what was and was not actually verified. Effort sizes (S/M/L) are guesses by a designer, not engineering estimates.

---

## Top 8 changes for Engineering (tickets)

Each is written so it can be picked up as-is. IDs refer to the detailed list below.

**T1 — Make the top bar work on phones and tablets (D1, P0).**
*Problem:* at a 390 px viewport the page is 809 px wide; "Spark Lab", the Beginner/Expert switch, Sign up and Settings are off-screen (measured with a headless browser). `.topbar` (style.css:4) has no wrap and there is no mobile media query for it.
*Do:* allow the header to wrap or collapse (logo + menu button; nav as a bottom tab bar or a menu sheet); move Beginner/Expert and Settings/Account into that menu on narrow screens; add a `@media (max-width: 640px)` pass. *Done when:* no horizontal scroll at 320–768 px on Studio, Edit, Showcase, Learn; every nav item reachable; targets ≥ 44 px.

**T2 — Keyboard and screen-reader access to uploads and cards (D2 + D3, P0).**
*Problem:* the photo drop zones use `<input hidden>` inside a `<label>` (index.html:34–38 Studio, 136–139 Edit), so keyboard users cannot reach "choose a file" (probe: `#drop` tabIndex = −1). Showcase cards, lesson cards, history thumbnails and edit-step chips are `div`/`img`/`li` with click handlers (community.js:76, ~155; app.js:119; edit.js:86): not focusable, no role.
*Do:* keep the file input in the DOM but visually hidden (not `hidden`), show a visible focus ring on the label via `:focus-within`, and add a real "Choose a photo" button; render cards as `<a>`/`<button>` (or add `role="button" tabindex="0"` + Enter/Space handlers); give thumbnails meaningful `alt` (the project title). *Done when:* the whole Studio → build → print path and Showcase/Learn browsing can be done with Tab/Enter/Space only.

**T3 — Replace `prompt()` / `confirm()` in safety and classroom flows with proper dialogs (D4 + D6, P0).**
*Problem:* "Report" asks the user to type a raw code (`minor_safety, not_family_friendly, copyright, …`) in a `prompt()` (community.js:105). Teacher feedback, "Submit a build" (type a number), Remove student (no confirmation at all, community.js:211) and Mute all rely on `prompt`/`confirm` or nothing. The API has a report endpoint for teacher feedback (`/classrooms/{code}/projects/{pid}/feedback/{fid}/report`) but no UI uses it.
*Do:* a small report dialog with plain-language radio choices ("It's not kid-friendly", "It shows a person without permission", "It's unkind", "It's copied from someone", "Something else") + optional note + a line "If someone is in danger, tell a grown-up now"; a build picker (thumbnails) for submit-to-class; a feedback textarea dialog with the 500-char counter; confirm dialogs for Remove student and Delete class that say what will be erased; add a Report button to class feedback. *Done when:* no native `prompt()`/`confirm()` remains in `community.js`; every dialog is keyboard-operable and returns focus to its trigger.

**T4 — Remove developer language from the user interface (D5, P0).**
*Problem:* Settings shows "OAuth connections (scaffold — sharing not implemented)", environment variable names and "restart the server" (app.js:240, index.html:224), "stored in `data/settings.json`", "tested against mock servers" (index.html:218); an item dialog says "Follow is scaffolding…" (community.js:97); "EXAMPLE seed data". A teacher or child reads these as "this is broken".
*Do:* hide unconfigured providers entirely (or one line "Coming later"), move env-var instructions to README/admin docs, reword to plain text ("Example project — not made by a real person"; "Following is coming soon"), put printer API-key storage notes behind an Expert-only "Details" disclosure. Also rename the Showcase tab **Free** (everything is free, so the tab implies otherwise) to e.g. **Newest** (branding.py `SHOWCASE_TABS`). *Done when:* a grep of user-visible strings finds none of: scaffold, OAuth client, env var names, mock, seed, stub.

**T5 — Form labels, dialog/tab semantics, announcements (D7 + D12 + D13, P1).**
*Problem:* most `<label>` elements are siblings of their input with no `for`/`id` (index.html:57, 68–91, 190–193, 297–299; edit.js:16–17), so fields are unnamed to assistive tech; the level switch is `role=tablist` but its buttons are not `role=tab` (index.html:21); Settings tabs, X close buttons (✕), 🗑 delete, and the visibility `<select>` (title only, index.html:115) have no accessible names; toasts (index.html:304) are not announced and errors vanish after 8 s.
*Do:* associate every label (wrap input in label or add `for`), `aria-label` on icon-only buttons, `aria-labelledby` on dialogs, proper tab pattern or switch to a radio/toggle group for Beginner/Expert (`aria-pressed`), `aria-current="page"` on nav, `role="status"` (info) / `role="alert"` (errors) on the toast region, keep errors until dismissed. *Done when:* an automated axe/Lighthouse run shows no "form elements must have labels" or "buttons must have discernible text".

**T6 — CSS token pass: contrast, focus, text size, touch targets (D8–D10, P1).**
*Do:* (a) `--acc` for white-on-purple text: current #7c5cff gives 4.35:1 and the primary-button gradient ends at #5b8cff (3.16:1); use e.g. #6a4bf0 (5.4:1) and a darker gradient end. (b) Raise control borders: `--line` #2a3344 is 1.36:1 against the panel, so input/button edges are nearly invisible; use ≈#6b7a96 (≈4:1) for input and button outlines (keep the faint one for decoration). (c) Add a global `:focus-visible { outline: 3px solid var(--acc2); outline-offset: 2px }` for buttons, links, cards, summary. (d) Base font 16 px, `.help`/pills/tags ≥ 13–14 px (54 style declarations are ≤ 12 px). (e) Min target 44×44 px on touch (measured 29 px "Try a sample photo", 32 px Thin/Standard/Thick, 16 px slider). (f) `@media (prefers-reduced-motion: reduce)` disables transitions/hover-lift/spinner spin/smooth scroll. *Done when:* Lighthouse a11y ≥ 95 and the contrast table in the appendix has no failing text pairs.

**T7 — Make Beginner mode truly beginner in Studio results and the Print dialog (D14, P1).**
*Problem:* Beginner results show "282,108 triangles · 1 body · ✔ watertight" (app.js:97–99) and three file formats; the Print dialog in Beginner mode shows layer height, infill %, brim, supports, "PrusaSlicer CLI detected", G-code, and a long "deep links need the slicer on the SAME computer…" paragraph (index.html:181–204, printing.py:60).
*Do:* Beginner result: a plain size line ("10.6 × 8.1 cm, 0.3 cm thick"), a green "Ready to print ✔" (with a tooltip "no holes in the model" for watertight), one primary **Download for printing (3MF)** button and "Other formats" menu. Beginner Print dialog: three big choices — "Open in my slicer app", "Send to my printer", "Download file to give to a grown-up/teacher" — with slice options under "More options". Keep everything as-is in Expert. *Done when:* a first-time 10-year-old can reach "I have a file I can print" without seeing the words triangle, body, G-code, infill, or brim.

**T8 — Teacher "Class setup & safety" panel and recoverable class access (D6b, P1).**
*Problem:* class creation, join info, assignments, students, projects and deletion live in one long modal (community.js:187–215). A teacher cannot see what protections are active, cannot view/reset the join password after creating it, cannot regenerate the code, and sees no moderation status (blocked-language events, reports, muted students) beyond a Mute button.
*Do:* split into tabs **Setup | Students | Projects | Safety**; Safety lists in plain words what is on (nickname-only, class-private projects, no chat — canned messages only, language filter, no public sharing from a class), shows muted students and any reports/filter blocks, and offers "Reset class password" and "New class code (old one stops working)"; a printable one-page "Join instructions" (code + QR; password written by teacher). *Done when:* a teacher can set up a class, hand out access, and answer "is this safe for my students?" on one screen without reading docs.

---

## Summary

ZEIM has a good foundation for families and schools: a calm dark UI with clear numbered steps in Studio, plain-language style cards (e.g. "Glows when backlit"), a Beginner/Expert split in Studio and Edit, "Auto-chosen settings" that explain *why*, private-by-default sharing, nickname-only classrooms, canned student messages, and lesson text that is easy to read (my rough Flesch-Kincaid estimate puts the lesson step text around grade 2–5, one 8-year-old-level step reaches ~11). The biggest gaps are not visual taste but access and clarity:

1. **The app is not usable on phones/tablets** (top bar overflows, nav items cut off) and **not fully usable by keyboard** (uploads and clickable cards).
2. **Safety-critical interactions use browser `prompt()`/`confirm()`**, including reporting, which asks people to type internal code words.
3. **Developer language leaks into user screens** (OAuth scaffolds, env vars, "scaffolding", "seed data").
4. **Beginner mode is beginner only in the Studio form**; the result bar and Print dialog speak slicer.
5. **Teachers lack a safety/moderation overview** and recovery options for class access.
6. **Contrast and size** are decent for body text (muted text is 5.4–6.4:1) but fall short for the purple button/active-state text, control borders (1.4:1), tiny text (≤12 px) and touch targets.

No claim here is a comparison with other products; where other tools are mentioned in the research section it is only to learn from public user feedback.

### Screen × mode matrix (what I checked and how)

| Screen | Beginner | Expert | Evidence type |
|---|---|---|---|
| Studio (form, result, history) | Clear 3-step flow; jargon in result pills; auto table good | Dense but well grouped; unlabeled fields (no `for`); σ/gamma without help | markup + CSS + screenshots |
| Edit | Four big buttons are friendly; "flipped faces" and "drain hole" need plain words | 8 collapsible tools, many numeric inputs, no help text; fine for experts, no labels bound | markup + JS + screenshots |
| Showcase | Same in both modes (toggle has no effect here) | same | markup + JS + screenshot |
| Learn / Spark Lab | Lessons friendly; safety steps not visually distinct; re-render on every checkbox | same | markup + JS + screenshot |
| Classrooms (student join) | Join dialog is plain; good nickname warning | n/a | markup + one live probe (wrong code → "Wrong class code or password") |
| Classrooms (teacher) | One long modal; `prompt`/`confirm` | n/a | markup/JS only — **not exercised live** (needs adult account) |
| Settings / Accounts | Developer text in Beginner | printer form OK for Expert | markup + screenshot |
| Print dialog | Expert content shown to Beginner | fine | markup + screenshot |
| Account / privacy | Understandable; DOB-first order awkward for under-13s | same | markup/JS only |

---

## Prioritized fix list

Format: **ID · Title** — *Screen · Mode* — Evidence → Fix (effort).

### P0 — blocks access, safety clarity, or trust

**D1 · Top bar overflows on small screens** — *All screens · both modes* — Evidence: style.css:4 (`.topbar` flex, no wrap, no media query); live probe at 390×800: `scrollWidth` 809 vs 390 on Studio/Showcase/Learn/Edit; the "Spark Lab" tab, Beginner/Expert switch, Sign up and Settings extend to x≈710 (off-screen); top bar is ~100 px tall when partly wrapped. → Fix: see T1. (M)

**D2 · Photo drop zones not keyboard-reachable** — *Studio, Edit · both* — Evidence: index.html:35, 137 (`<input type="file" hidden>` inside `<label class="drop">`); probe `#drop.tabIndex = -1`. → Fix: see T2. Also add a visible button "Choose a photo" and mention keyboard in the hint. (S)

**D3 · Clickable non-interactive elements** — *Showcase, Learn, Studio history, Edit steps · both* — Evidence: community.js:76 (`div.pcard` data-item click), lesson cards (~l.155), app.js:119 (`img data-open`), edit.js:86 (`li data-goto`), `.pcard{cursor:pointer}` style.css:88. → Fix: native `<a>/<button>`; keep hover styles; `alt` text for thumbnails (title) instead of `alt=""` where the image is the only link content. (S–M)

**D4 · Reporting and class actions use `prompt()`** — *Showcase item dialog, Learn/class · both* — Evidence: community.js:105 (type a reason code), 210 (feedback), 219 (type a number to pick a build); no UI for reporting class feedback although API exists (learn.py `report_feedback`). Native prompts are not styled, not translated, not reliably accessible, and a child cannot know the code words. → Fix: see T3. (M)

**D5 · Developer/scaffold language visible to users** — *Settings, Showcase item, Showcase notice, Print · Beginner especially* — Evidence: index.html:218, 224; app.js:240–241; community.js:97; app/api showcase `example_notice` ("placeholder seed data"). Screenshot `ui_settings_accounts.png` shows "OAuth connections (scaffold…)", `PHOTO3D_TIKTOK_CLIENT_ID`. → Fix: see T4. (S)

**D6 · Destructive teacher actions without confirmation; teacher UI is one long modal** — *Teacher tools · n/a* — Evidence: community.js:211 (Remove student: immediate), 209 (Mute: immediate, no explanation of what mute does), 212 (Delete class uses `confirm()`; text doesn't say it erases all projects); layout in 187–200 is a single scroll. → Fix: confirmation dialog naming the student/class and the effect; explain Mute in one line ("They can still learn but can't send quick messages"); undo toast for Mute. (S) — structural rework is D6b/T8.

### P1 — important friction for kids, teachers, and keyboard/screen-reader users

**D6b · No class safety overview, password recovery, or moderation visibility for teachers** — *Teacher tools* — Evidence: community.js:187–215 shows code/QR/link and a one-time password field (`cr_pw`, plain text); no later view or reset of the password; no regenerate-code; no view of reports or language-filter blocks (safety.py blocks silently from the teacher's point of view); no co-teacher. Roadmap acknowledges roster/LMS as future. → Fix: see T8. (M)

**D7 · Unlabeled form controls** — *All forms · both* — Evidence: index.html:57, 68–91 (label then input as siblings without `for`), 190–193, 297–299; edit.js:16–17 generates the same pattern; search box and class-name/password inputs rely on placeholder (index.html:245, community.js:191). → Fix: bind labels; keep visible labels (placeholders vanish while typing; harder for kids). (S–M)

**D8 · Contrast shortfalls (computed from CSS)** — *All* — Evidence (see appendix): white on `--acc` 4.35:1 (active segmented button, step numbers at 11 px), primary-button gradient end 3.16:1 with 14–15 px text, `.hslot` text 2.34:1, `.field label em` (opacity .65) ≈ 3.5:1, input/card borders 1.36:1 (WCAG 1.4.11 asks for 3:1 on component boundaries), note box text 4.33:1. Body (15.7:1) and muted (5.4–6.4:1) text pass. → Fix: see T6. (S)

**D9 · Focus visibility relies on browser defaults** — *All* — Evidence: only `input:focus,select:focus` is styled (style.css:25); probe of the first 10 Tab stops showed UA default `outline: auto 1px` on nav/toggle buttons (3 px on some) — on a dark UI with purple/dark-grey controls this is easy to miss; `.nav button.on` uses only an inset shadow for state. `input:focus` uses `outline-offset:-1px` inside a 1.36:1 border. → Fix: global `:focus-visible` ring (T6c). (S)

**D10 · Small text and touch targets** — *All, worst in History cards, Teacher table, Settings* — Evidence: base 14 px (style.css:3); 54 declarations at ≤12 px (`.help` 12, `.pill` 12, `.tag` 11, `.hcard .row2` buttons 11 px with 2 px padding, `.x` close 18 px glyph with no padding); probe at 390 px: Try-a-sample 130×29, slider 230×16, width input 36 px, preset buttons 32 px high. → Fix: T6(d,e). Offer a text-size option in Settings (S/M/L). (S)

**D11 · No fallback when WebGL is unavailable** — *Studio, Edit* — Evidence: app.js:25 and edit.js:22 only `console.warn`; the user gets an empty viewer and no explanation (school Chromebooks/VMs sometimes block WebGL). → Fix: show a message "Your browser can't show 3D previews, but you can still download the file" and still show downloads/results. (S)

**D12 · Toasts are invisible to assistive tech and disappear** — *All* — Evidence: index.html:304, app.js:11–14 (4.5 s ok / 8 s error, no live region, no close). Raw server errors are shown (`e.message`, e.g. "unknown build"). → Fix: T5, plus map common errors to friendly text with a next step ("That file is too big (max 25 MB). Try a smaller photo."). (S)

**D13 · Dialog and tab semantics** — *All dialogs · both* — Evidence: `<dialog>` is used (good: native focus trap/Esc; probe confirmed it opens with focus on the close button and `open` true), but no `aria-labelledby`; "✕" buttons unnamed; `role=tablist` without `role=tab` (index.html:21); Settings `.tabs` plain buttons; no `aria-current` on nav. After closing a dialog, focus return was not verified. → Fix: T5. (S)

**D14 · Beginner mode jargon outside the form** — *Studio result, Print dialog, Showcase tags, Edit, Settings · Beginner* — Evidence: app.js:97–99 ("triangles", "bodies", "watertight"), 100 (STL/OBJ/3MF), index.html:181–204 and app.js:159–165 (Print dialog), printing.py:60 hint; Edit big-button copy "Repair holes & flipped faces"; hollow drawer "drain hole (needed for resin…)"; Showcase "Halftone", "Relief". → Fix: T7; glossary tooltips ("What's this?") for Lithophane/Relief/Pop-art/Halftone; replace "flipped faces" with "fix broken parts of the model". (M)

**D15 · Lesson page re-renders and jumps on every checkbox** — *Learn · both* — Evidence: community.js:171 (`openLesson(id)` after each step toggle) → rebuilds `innerHTML` and calls `scrollIntoView({behavior:"smooth"})` (168); keyboard focus is lost and the page scrolls; quiz re-renders after 700 ms on success (175). Hard for keyboard/screen-reader users and annoying for kids. → Fix: update only the progress bar and the one `li`; announce "Step 2 done" via live region; do not scroll on re-render. (S)

**D16 · Safety steps in lessons are not visually distinct** — *Learn · both* — Evidence: education.py steps ("Safety first", the hot-bulb warning in step 5 of Lithophane) render as ordinary `p.help`. → Fix: a "⚠ Safety" callout style with icon + text (not colour alone) and a "Teacher: printer-safety card" link (see research R10). (S)

**D17 · Empty/error states are thin** — *Showcase, Learn, Teacher, History* — Evidence: community.js:78 "Nothing here yet."; empty For You, empty search results, no "couldn't load" state (`loadShowcase` only toasts); History "Empty slot" is fine and clear; "Teacher tools need an adult account" appears as a toast then immediately opens the account dialog (probe confirmed), which is confusing. → Fix: purposeful empty states ("No projects match 'dragon'. Try fewer words, or browse Newest."), an inline error with Retry, and an explanatory dialog for Teacher tools ("Teacher tools are for adults. Sign up with an adult date of birth, or ask your teacher for a class code"). (S)

**D18 · Account flow order for under-13s** — *Account dialog · both* — Evidence: community.js:42–45 asks Display name + Date of birth first; under-13s learn about "13+" only after submitting the form (identity.py:65–66 error). The header button says "Sign up" for everyone. → Fix: first question "Joining with a class? → Join a class" and "I'm 13+ → Create account"; do not collect DOB from someone before telling them the age rule. Add a kid-readable one-line "why we ask". (S)

**D19 · Result bar is crowded and its primary action unclear** — *Studio/Edit result · both* — Evidence: index.html:111–120 (3 downloads + visibility select + Edit + Share + Print in one row); the visibility `<select>` has only a `title`. → Fix: Print as the single primary; "Share to Showcase" and "Edit this" as secondary; downloads grouped in a menu; visible label "Who can see this: 🔒 Only me". (S)

**D20 · Joining a class: help students avoid real names** — *Join dialog · student* — Evidence: index.html:293–302 has a good warning; no suggested nicknames; no show-password toggle; `j_code` lacks `autocapitalize`/`inputmode`; password field `autocomplete=off`. → Fix: "Suggest a nickname" button (e.g. Color + Animal) and show/hide password (kids mistype). (S)

### P2 — polish and later

**D21 · Reduced motion not honoured** — Evidence: no `prefers-reduced-motion` rule; spinner (style.css:46), hover lift `.pcard:hover{transform}` (89), transitions, smooth scroll (community.js:168), OrbitControls damping (viewer.js:15). → Fix: media query + disable damping/auto-scroll. (S)

**D22 · Beginner/Expert toggle appears on screens where it does nothing and isn't explained** — Evidence: index.html:21 is global; Showcase and Learn ignore it. Name "Expert" may tempt kids. → Fix: show only on Studio/Edit; tooltip "Beginner: fewer choices. Expert: every setting."; optional teacher lock to Beginner per class. (S/M)

**D23 · Naming inconsistency** — Evidence: nav label from config is "Spark Lab" (branding.py) but static fallback text, h1 and several strings say "Learn"; README describes both. → Fix: pick one visible name (suggest "Spark Lab" with the sub-label "Learn"), update fallback HTML so there is no flash of "Learn" before config loads. (S)

**D24 · "My data" / "For You" labels** — Evidence: index.html:245 "🔒 My data", community.js openData. → Fix: "Privacy & my data"; "For You" explained as "Picks based on what you searched on this device". (S)

**D25 · Learn page copy accuracy** — Evidence: index.html:252 says "no chat, no user uploads, no external links", but classrooms allow students to submit builds (class-private) and teachers to write feedback. → Fix: reword honestly: "No public chat. Student projects stay inside the class." (S)

**D26 · Lesson-to-Studio hand-off** — Evidence: community.js:177 loads the sample photo silently and leaves Learn. Students lose the lesson text. → Fix: keep a floating "Back to lesson" chip showing the current step; optionally a split view on wide screens. (M)

**D27 · Build progress** — Evidence: index.html:103 spinner "Building…" without time hint; a 282k-triangle build can take a while. → Fix: "Usually under a minute" and a cancel button; Beginner default resolution low enough to be quick. (S–M)

**D28 · Expert density in Edit** — Evidence: edit.js:126–160: eight `<details>`, many 3-column numeric grids; no inline help for Cut, Boolean, Base. Works for experts but is unforgiving to a curious beginner who toggles it. → Fix: one-line help per tool; "Reset to default" per form; remember open/closed tools; a small "Why is this disabled?" text for the disabled big buttons (`cap.hollow` false). (M)

**D29 · Expert-mode Studio help** — Evidence: index.html:68–91: `σ`, "Gamma", "Posterize", "Halftone" without tooltips; units appear in `<em>` with opacity .65 (low contrast). → Fix: `?` popovers with one sentence and an example; PrusaSlicer-style "safe to change / careful" hints (research R9). (M)

**D30 · Policy question for Trust & Safety, not a design call** — "Promote your accounts" includes Patreon link-outs (index.html:210) on a family product. Design view: keep it out of any class or teen surface (already hidden for teens) and label as "optional, adults only"; whether Patreon belongs at all given "no paid content" positioning is for Kenji/Yami to decide. (S)

**D31 · Build Plates (groups) — design guardrails for when they are built** (not built yet; no UI exists to audit). Recommendations: show one plain-language "Who can see this Build Plate" line at the top; school/class Build Plates use the same class-private rules as classrooms; moderator list visible to members; "Report" always one click away using the T3 dialog; join by invite for under-18s; no free-text DMs; any "Build Plate" naming gets a short explainer ("a group of makers who share a print bed idea") since a child may not know the pun. (M, later)

---

## Beginner vs Expert — consolidated recommendations

- **Beginner:** fewer words, plain units (cm/mm only where needed), "Ready to print ✔", one primary action per screen, hide stats pills except size/time, hide all server/integration detail, keep "Auto-chosen settings" (it is a strength — add a "Change this" link that switches to Expert for that field).
- **Expert:** keep density but add help popovers, per-field reset, tooltips on abbreviations, and keyboard shortcuts list (Ctrl+Z/Y exist, edit.js:107–111, but are undocumented outside `title`).
- **Teacher control:** optional "lock students to Beginner" and "disable Showcase publishing for this class" switches (the latter is already how class projects behave, so this is mostly explanation).

---

## Global research (public web sources, design/UX angle)

Method and limits: I used web search results and their page excerpts (not full reads of every page). Reddit and forum threads are anecdotal, skew toward complaints, and may be outdated. Sources are listed so Engineering/Yami can check them. Nothing below claims ZEIM is better than anyone; the aim is to learn what makers, teachers and parents say they need.

### What people said, and what to do

| # | Observation (source) | Recommendation | Why |
|---|---|---|---|
| R1 | Makers complain about AI-generated or untested uploads flooding search and about points-farming on MakerWorld; MakerWorld now requires a real-print photo (since 2026-02-05). ([r/makerworld](https://www.reddit.com/r/makerworld/comments/1r8us2c/when_will_makerworld_take_action_against_ai_abuse/), [r/BambuLab](https://www.reddit.com/r/BambuLab/comments/1vyk4wp/makerworld_profile_point_farming/), [3druck.com](https://3druck.com/en/programs/bambu-lab-takes-stronger-action-against-ai-slop-on-3d-model-platform-makerworld-57153725/)) | **Adapt**: auto-attach a "Made with ZEIM from a photo / uploaded file" label and encourage an optional "I printed this" photo on a project page; no mandatory photo for kids. | Trust in what you download is a real need; ZEIM's builds come from the user's own photo, so provenance can be shown cheaply. A mandatory real-print photo would exclude students who can't print. |
| R2 | Reward/point systems create farming and disputes (same threads; a creator reports points wiped after review: [Bambu forum](https://forum.bambulab.com/t/makerworld-retroactively-blocked-2024-models-wiped-1-600-in-points-21k-pts/259059)). Printables has "Prusameters" rewards ([3dprintingideas](https://3dprintingideas.com/thingiverse-alternatives/)). | **Reject** points/cash-like rewards. **Adapt** learning badges only (already in Spark Lab). | Rewards invite gaming and disputes; a free, family product with kids should not have a points economy. |
| R3 | Some users want a way to filter AI-made models; a commenter says Printables asks creators to declare AI and offers a "hide AI" filter ([r/makerworld thread](https://www.reddit.com/r/makerworld/comments/1vboodv/is_anyone_else_sick_of_all_the_ai_slop_and/) — a user's claim; I did not verify it on Printables). | **Adapt**: a "How it was made" tag (photo-to-3D, edited file, uploaded design) plus a Showcase filter when volume justifies it. | Cheap, honest, helps teachers choose class-appropriate examples. |
| R4 | Thingiverse: slow, hard-to-use search, ads between results, spam ([Fabbaloo](https://www.fabbaloo.com/news/modernizing-thingiverse-key-challenges-await-myminifactory-after-acquisition), [r/3Dprinting](https://www.reddit.com/r/3Dprinting/comments/1q2nwng/what_happened_to_thingiverse/), [Trustpilot](https://au.trustpilot.com/review/www.thingiverse.com)). Printables is praised for filters (material, print time, license) ([3dprintingideas](https://3dprintingideas.com/thingiverse-alternatives/), [3DSearch](https://3dsearch.app/blog/printables-vs-thingiverse) — a comparison blog, treat as opinion). | **Adapt** filters (mode, size, print time, "classroom-ready"); **reject** ads in results (ZEIM is free and ad-free by design). | Findability matters once Showcase grows; it is an easy guardrail to design now. |
| R5 | Creators dislike silent delisting/shadow-bans and templated replies ([r/3Dprinting](https://www.reddit.com/r/3Dprinting/comments/1q2nwng/what_happened_to_thingiverse/), [Bambu forum](https://forum.bambulab.com/t/makerworld-retroactively-blocked-2024-models-wiped-1-600-in-points-21k-pts/259059)). | **Adopt**: when something is hidden or blocked, tell the owner what and why in plain words, with an appeal route (except where safety rules require discretion). Teachers should see the same for class content. | Transparency builds trust with parents and teachers; fits T8. |
| R6 | Tinkercad Classrooms: class link (recommended) or code, class "seats" with teacher-set nicknames, no student email, Safe Mode on by default (designs private, no public sharing or comments, limited gallery), per-student/per-class toggle, class gallery, co-teachers, ability to regenerate class code, optional Google sign-in ([Tinkercad help](https://www.tinkercad.com/help/classrooms/share-class-link-code), [Tinkercad guide PDF](https://images.tinkercad.com/jl5ii4oqrdmc/5v197WuuaqspGT81cG5tT6/81154785a527f1b42a32325487a30e44/tinkercad-guides_classrooms-Printable.pdf), [TSI support](https://help.mytsi.org/v2/knowledge-base/how-to-use-tinkercad-classrooms/), [Autodesk children's privacy](https://www.autodesk.com/company/legal-notices-trademarks/privacy-statement/childrens-privacy-statement)). | **Adopt** the *idea* of an explicit "safe mode" summary (T8); **adapt** class link as primary join method (ZEIM has `/#join/CODE` + QR — make it the default share action), generated nicknames (D20), code regeneration, class gallery view for the teacher; **defer** co-teachers and Google sign-in (ROADMAP + legal review). | These are patterns teachers already know; reuse of mental models lowers training cost. ZEIM's own class-private model stays. |
| R7 | Teachers batch several student models per print bed and review before printing; students' models often don't print well; printing capacity is limited ([PrintLab blog](https://weareprintlab.com/blog/managing-3d-printing-in-the-classroom-with-tinkercad-collaboration-tools/), [VistaThink](https://www.vistathink.com/tinkercad-for-kids-grades-3-5/), [r/3Dprinting teaching thread](https://www.reddit.com/r/3Dprinting/comments/1ums31w/teaching_3d_printing/)). | **Adopt**: "Ready for teacher" status + a printability checklist in Beginner (flat base, no floating parts, minimum thickness, size limit), using ZEIM's existing watertight/size analysis; **adapt** ROADMAP's "print queue per class" into a teacher-approval step. | Directly addresses a teacher bottleneck and reduces failed prints. |
| R8 | Not every project needs to be printed; digital portfolios/screenshots; district security can block STL uploads ([VistaThink](https://www.vistathink.com/tinkercad-for-kids-grades-3-5/)). | **Adopt**: lessons that can be completed without a printer (screenshot/"save preview image") and a download option that is a ZIP/3MF + preview PNG for IT-restricted environments. | Many classrooms have no printer or a locked-down network. |
| R9 | PrusaSlicer's Simple/Advanced/Expert tiers with colour-coded settings (green safe for beginners, yellow advanced, red expert) ([Prusa KB](https://help.prusa3d.com/article/simple-advanced-expert-modes_1765)); OrcaSlicer users report the "Advanced" toggle is missed and duplicated ([OrcaSlicer #1236](https://github.com/SoftFever/OrcaSlicer/issues/1236), [#12070](https://github.com/OrcaSlicer/OrcaSlicer/issues/12070)). | **Adapt**: keep ZEIM's two levels but add "safe to change / careful" hints in Expert; make the mode switch obvious and single (D22). **Reject** three duplicate toggles. | Shows the value of tiers and the cost of an undiscoverable toggle. |
| R10 | Lab-safety guidance: signage next to printers, supervised use, PPE for post-processing, PLA recommended for schools ([SelfCAD blog](https://www.selfcad.com/blog/manage-a-3d-printing-lab-safety-workflow-and-student-rotations), [OCTE SOP PDF](https://octe.ca/download_file/becad7e8-cdb7-4b46-86a8-449668295abc/1019)). | **Adopt**: a printable one-page "Printer safety card" in Spark Lab for teachers; a visible safety callout style (D16). | ZEIM's first lesson already says "grown-up nearby"; a printable card helps teachers who must post rules. |
| R11 | Parents/educators look for COPPA-style privacy, private-by-default sharing and moderated community; some makers asked for family-friendly filters ([Autodesk children's privacy](https://www.autodesk.com/company/legal-notices-trademarks/privacy-statement/childrens-privacy-statement), [Makers Empire safety](https://www.makersempire.com/safety-privacy/), [MakerBot children privacy](https://www.makerbot.com/legal/children-privacy-policy/), [Bambu forum request](https://forum.bambulab.com/t/family-friendly-filters/90848)). | **Adopt**: a short "For parents & teachers" page (what data exists — nickname only; who can see what; how to delete; who to contact). The legal text still needs counsel; this is a plain-language layer. | There is currently no parent-facing explanation in the UI. |
| R12 | Shapr3D: tools appear contextually after selecting geometry; touch gestures for navigation, stylus for precision ([Shapr3D help](https://support.shapr3d.com/hc/en-us/articles/13079101770268-Get-started-A-Shapr3D-Overview), [AEC Magazine review](https://aecmag.com/cad/review-shapr3d/)). Free education licence needs school email ([Shapr3D education](https://www.shapr3d.com/education)). | **Adapt** the contextual-tools idea for Edit Beginner (tool drawers already similar) and make the 3D viewer usable with touch; **reject** requiring school email (ZEIM keeps nickname-only classes). | Schools use tablets and Chromebooks; email gating conflicts with ZEIM's data-minimal approach. |
| R13 | Cults3D and Printables' planned paid tiers show monetisation and payout disputes ([Cults FAQ](https://cults3d.com/en/questions), [Prusa blog](https://blog.prusa3d.com/support-the-designers-you-love-coming-soon-to-printables-com_78461/), [r/3Dprinting](https://www.reddit.com/r/3Dprinting/comments/zddebd/cults3d_withholding_payments/)). | **Reject** for ZEIM (no paid content by policy). Nothing to design. | Keeps the product simple and consistent with the "free" promise. |

### Gaps in this research
Parent voices came from vendor privacy pages and one forum request rather than parent forums; teacher voices from blogs and one Reddit thread, not teacher-only communities (e.g. ISTE/educator Facebook groups were not reachable via search); Shapr3D and Cults3D coverage is thin; Thingiverse/MyMiniFactory news in 2026 may be moving. Treat the table as a starting list for a real interview round (see Hansei).

---

## Hansei (reflection)

**What went partial or wrong**
- **Specialist bot not created.** The kickoff asked me to create my own accessibility/usability reviewer bot. I have no tool to create agents in this run, so I did not. Proposed charter if the parent can create it: "A11y & Usability Reviewer — runs axe-core/Lighthouse and a keyboard-only + 390 px + 200 % zoom pass against each release; reports to Sakura; read-only."
- **Screenshots were interpreted via text descriptions**, not pixel measurements. The descriptions were occasionally inconsistent (e.g. the Expert icon described as a gear in one image and a wrench in another; one phone-width screenshot listed only three nav items — which actually matched my measured overflow). I therefore trusted **CSS-computed contrast** and **live DOM measurements** over screenshot impressions. I briefly considered flagging the "EXAMPLE" badge for contrast and then saw it has its own dark `#000a` background, so I dropped it.
- **Live checks were limited.** I ran one small headless-Chrome probe (390×800 viewport; first 10 Tab stops; opening the account dialog; teacher-tools-without-account; one deliberately wrong class join). **Not tested:** real screen readers (NVDA/VoiceOver/TalkBack), real touch devices, Safari/Firefox, 200–400 % zoom reflow, Windows high-contrast/forced-colors, axe-core or Lighthouse (not run), focus return after closing dialogs, Escape behaviour in every dialog, drag-and-drop with a keyboard.
- **Teacher and student-in-class flows were read from code, not exercised.** I did not create an adult account or a class to avoid changing the app's data; findings in D4, D6, D6b, D20 come from markup/JS and the README, so a real run may reveal more (or show that something already works better than the code suggests). The one wrong-code join produced the plain message "Wrong class code or password" (good), and counted one wrong guess against code `ZZZZZZ`. The probe also created an anonymous browser session on the server; no builds or accounts were created.
- **Edit tools and printing:** reviewed markup/JS and screenshots only; I did not run operations, slice, or send to a printer.
- **Reading level:** I used a rough Flesch-Kincaid formula on lesson text and two UI strings. It is not validated for children and says nothing about comprehension or vocabulary (e.g. "heightmap", "G-code"). It needs a short test with real 8–12-year-olds and a few teachers.
- **Back-end and docs depth.** I skimmed API files for copy and behaviour (learn/classrooms/identity/safety) but did not audit server-side logic or tests. I did not review `README.md`'s full middle section line by line after the output was truncated; I re-read the missing parts afterward.
- **Priorities and efforts are my judgement**, not user-tested. D6 vs D6b and the choice of Top-8 could reasonably differ if Engineering sees hidden cost.
- **Research quality:** mostly search-result excerpts; some blog comparisons are opinionated; Reddit is negative-skewed. I did not hold interviews or surveys. A "Printables AI filter" detail is a commenter's claim and unverified. I deliberately avoided adult-content threads and do not recommend anything from them.
- **Copy suggestions are drafts** and have not gone through Kenji (Trust, Safety & Legal) or Aiko (Education & Community); reporting-flow wording and the parent page in particular need their review.

**What I would change next time**
1. Start with an automated pass (axe-core + Lighthouse + keyboard walk script) and keep its output in `reports/` as evidence.
2. Get an adult test account and a throwaway class (in a temp data dir) to walk the teacher and student flows end to end.
3. Test at 320/390/768/1024 px and at 200 % zoom as a standard checklist item.
4. Run a 20-minute round with 2–3 kids and 2 teachers before ranking Beginner-mode copy.
5. Record exact screenshots of each finding (before/after) instead of relying on descriptions.
6. Ask Kenji and Aiko to co-review reporting/safety copy before it goes to Engineering.

---

## Appendix A — Contrast ratios (computed from `static/style.css` colours, WCAG relative luminance)

| Pair | Ratio | Verdict |
|---|---|---|
| `--txt` #e6eaf2 on `--bg` #0e1117 | 15.67 | pass |
| `--mut` #8b97ad on `--bg` | 6.41 | pass |
| `--mut` on `--panel` #161b24 | 5.86 | pass |
| `--mut` on `--panel2` #1c2330 | 5.35 | pass |
| `--mut` on #131923 (details/printer cards) | 5.98 | pass |
| `--mut` on #1a2236 (`.sticky`, `.banner`) | 5.38 | pass |
| `--mut` on #232a49 (selected card) | 4.76 | pass (small text borderline) |
| `--mut` on #24305a (`.note`) | 4.33 | **fail** for < 18 px text |
| white on `--acc` #7c5cff (active segmented button, step number) | 4.35 | **fail** for small text (needs 4.5) |
| white on #5b8cff (end of primary-button gradient) | 3.16 | **fail** for 14–15 px text |
| `.field label em` (opacity .65 on `--mut`) ≈ #5f6a7d on `--bg` | ≈3.46 | **fail** |
| `.hslot` text #4b566d on `--panel` | 2.34 | **fail** |
| `--line` #2a3344 border on `--panel` / `--bg` | 1.36 / 1.49 | **fail** as component boundary (needs 3:1) |
| `--acc` #7c5cff as a border on `--panel` | 3.97 | pass (non-text) |
| `--acc2` #22d3ee on `--panel` | 9.55 | pass |
| `--ok` #34d399 on `--panel2` | 8.20 | pass |
| `--bad` #f87171 on `--panel2` | 5.70 | pass |
| `--warn` #fbbf24 on `--bg` | 11.32 | pass |
| Suggested: white on #6a4bf0 | 5.42 | pass |
| Suggested border #6b7a96 on `--panel` / `--bg` | 3.99 / 4.36 | pass |

Note: status pills (`ok`/`bad`) rely on colour plus a ✔/✖ glyph — good; keep the glyph/text when restyling.

## Appendix B — Live probe results (headless Chrome, 2026-10-04 ~4:30 PM CT)

- 390×800: `documentElement.scrollWidth` 809 vs `clientWidth` 390 on Studio, Showcase, Learn, Edit; elements past the right edge: `#mainNav` (to 435), `#levelSwitch` (to 620), `#btnAccount` (to 710).
- Targets under 44 px at 390 px: `#btnSample` 130×29, `#widthRange` 230×16, `#width_mm` 80×36, Thin/Standard/Thick 104×32.
- First 10 Tab stops at 1440×900: logo link, Studio, Showcase, Edit, Spark Lab, Beginner, Expert, Sign up, Settings, Try a sample photo — each shows the browser default outline (`auto`, 1–3 px). The file drop zone is not in the Tab order (`tabIndex −1`, input `hidden`).
- Account dialog opens with focus on its first button (the close ✕).
- "Teacher tools" while not signed in: toast "Teacher tools need an adult account — sign up first." and the account dialog opens.
- Wrong class join: toast "Wrong class code or password".
- Lesson readability (rough FK grade): first-print 4.4, intro-modeling 3.4, lithophanes 3.4; UI sentence "All other settings are chosen automatically…" ≈ 11.

## Appendix C — Strengths worth keeping
Numbered Studio steps; plain style-card subtitles; "Auto-chosen settings" with reasons; private-by-default and clear visibility labels (🔒/👥/🌐); history-full dialog with clear choices; undo/redo and "original kept" in Edit; EXAMPLE labelling; no dislikes; nickname-only class join with a "not your real name" warning; canned messages only; class-private projects; native `<dialog>` use (focus trap and Esc come free); `lang="en"` and viewport meta present; honest "Known limits" tone.
