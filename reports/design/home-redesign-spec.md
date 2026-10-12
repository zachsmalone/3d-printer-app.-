# Home screen redesign (Studio), palette, and the Send menu

**Author:** Accessibility & Usability Reviewer (design owner) · **Date:** 2026-10-04 · **Mock:** `mock-home.html` (grey MOCK bar: pretend to be an adult on iPhone, an adult on a computer, a visitor, a teen, a class student; light/dark theme; the Mode select works as in `mock-mode.html`).
**Checked:** axe-core 4.13.0 on the mock: light + dark × 320/390/1280 px × 8 states (empty, built, Experienced, Teacher, Teacher explainer, Send as adult/desktop/student). No horizontal scroll at any width. Every visible control ≥44×44 (measured at 390). Keyboard: focus goes into the Send sheet on open and back to the Send button on Esc. Contrast numbers are computed. **Not tested:** real VoiceOver/TalkBack/NVDA, a real iPhone share sheet, a real camera, other browsers, children or teachers. The 3D "viewer" in the mock is a flat placeholder, so the turn buttons only show the pattern.

## 1. What the page is for
A first-time child, parent or teacher should know in five seconds what ZEIM does and what to press. One job: **photo → preview → print-ready.**
- **One h1 and one big action.** "Turn a photo into something you can print." then **Take a photo** (primary), **Choose a photo**, and a plain link **Try a sample photo**. Copy is confident and every claim is true ("Free for everyone" is true today; no comparisons).
- **A three-step path** (an `<ol>` with `aria-current="step"`): Photo → Preview → Print-ready. Done steps get a tick **and** a green border (not colour alone). Changes are announced in a polite status line ("Photo chosen." "Making your 3D model. Step 2 of 3." "Model ready. Step 3 of 3…").
- **Same page, same landmarks:** `header` (banner) → `nav aria-label="Main"` → `main` (h1, path nav, panels, "Pick up where you left off", "Keep exploring") → `footer` (contentinfo: Community Guidelines · Privacy · Terms · Credits; the pages must exist before the links go live. Kenji flagged that no privacy/terms link exists anywhere today).
- **Plain words:** "Lithophane: a picture that glows with a light behind it", "Make my 3D model", "Pick up where you left off". No "build", "Auto-chosen", "heightmap".

## 2. Mode-aware (see `mode-dropdown-spec.md`)
| | Beginner | Experienced | Teacher |
|---|---|---|---|
| Hero | full: h1, sentence, three buttons | collapses to a small "Studio" heading (no sentence, no big buttons; the photo picker sits in the panel) | as Beginner + "Teaching with ZEIM? Start with the Glow Card lesson · Class tools" |
| Path | shown | shown (compact) | shown |
| Settings | Style, Width, Thin/Standard/Thick; photo auto-builds | + Image & detail etc.; press "Make my 3D model" | as Beginner |
| Classroom bar | – | – | shown under the top bar |
| "Keep exploring" tiles | shown | hidden | Learn first |

## 3. Layout and responsive rules (mobile first)
- One column from 320 px. Two columns (400 px controls | preview) from 900 px. `main{max-width:1100px}`.
- **Top bar (fixes the old non-wrapping bar; the T1 media query already stops sideways scroll, this makes it shorter and keeps the Mode select):** row 1 brand + Account + Settings (icon-only ≤480 px; the words stay as `sr-only` text so the names don't change); row 2 Mode; row 3 the four tabs, each ≥44 px. Heights measured in the mock: **165 px at 320/390, 65 px at 1280** (the live app is 187 px at 320). From 900 px it is one row: brand · nav · Mode · … · Account · Settings.
- Focus order on phones follows the DOM (brand, tabs, Mode, Account, Settings) while the picture shows Account/Settings first. That mismatch is small and already exists in the live bar; the alternative was a second DOM copy of the buttons.
- Preview and result sit **right after** the controls on phones, and finishing a build scrolls the result into view (`scrollIntoView({block:"nearest"})`), which Edit still needs (Haruto's polish pass).
- Touch: every button/link/select ≥44×44, inputs 16 px (no iOS zoom), safe-area padding on the sides/top/bottom, Send sheet is a bottom sheet ≤600 px.
- Viewer: besides drag/pinch, add **Turn left / Turn right / Reset view** buttons and a text alternative (`role="img"` + `aria-label` describing the model, plus the stats list as real text). That closes the audit's "3D viewer has no keyboard or text alternative" (H-1). Keep the "swipe on the thin edge strips to scroll" hint already shipped.
- Motion: only a spinner and the 0.5 s model turn. `prefers-reduced-motion` removes both (spinner becomes static text "Making your 3D model…", which is already on screen).

## 4. Send menu (a sheet, not an ARIA menu)
The existing `#dlgSendSheet` (send.js) is the right shape: each row has a label **and** a description and there is a status line, which `role="menu"` cannot hold. Keep it, tidy it:
- **Opener:** button "⬆ Send or save" with `aria-haspopup="dialog"` (was "⬆ Send"). Opens `<dialog aria-labelledby>`; bottom sheet ≤600 px; centred above.
- **Order of rows (top = most useful, only rows the server allows are drawn):** 1) **Save to this device** (primary, always; "Download my model" for teens/students) 2) **Send to my teacher** (class students) 3) group "Send to another app": **Share…** (share sheet: Files, Mail, Shapr3D, Creality…), **Email it to myself** (opens the Mail app via the share sheet; ZEIM doesn't send mail), **Share as STL for Shapr3D…** 4) group "Print": **Send to my printer** (local mode only, labelled "Tested with a pretend printer only") 5) "More places" (Creality Cloud ↗, opens their site).
- **Each row:** a `<button>` (or `<a download>` for Save), bold label + one-line description, ≥56 px tall, full width, 2 px `--ctl` border. Emoji are decorative. Rows that can't work on this device are **not drawn** (no dead buttons); a short sentence says how to get the same result ("Save it first, then open the Files app, press and hold the file, and tap Share").
- **Status:** `#sendStatus` (`role="status"`, polite) says what happened ("Saved! Look in your Files or Downloads."); `#sendAlert` (`role="alert"`) says what failed and what to do instead ("That didn't work on this device. Save it instead."). Both are inside the dialog from the start. Messages also appear as the visible text under the rows (not a vanishing toast).
- **Focus:** opens on "Save to this device"; Esc/Close returns focus to "Send or save"; after a failed share, focus goes to Save.
- **Safari rule:** `navigator.share` must run **directly inside the tap**. Keep the current "fetch the file when the sheet opens, enable Share when ready" approach (send.js `prepare()`); the Share/Email/Shapr3D rows stay `disabled` until the file is ready and say "Getting your file ready…".
- **Privacy defaults (Kenji's rules, unchanged):** off-ZEIM sending is adults only; class students and teens get Download (+ Send to teacher); the sheet always shows "A lithophane or relief is your photo turned into a shape. Anyone who gets the file can see it."
- **Not promised yet:** Share, Email, Shapr3D and Creality rows are **untested on real iPhone/iPad** until Zach tries them; printer send is tested only against a mock server. The sheet text must not say otherwise.

## 5. Palette (computed)
Warm light is the default; Dark is the existing dark look with fixed contrast. Tokens are CSS variables on `:root` / `[data-theme=dark]` (full block at the top of `mock-home.html`'s `<style>`). **Decision (Oct 12, 2026): Warm is ALWAYS the default. Dark applies only when the person picks it; the app does NOT follow `prefers-color-scheme` / the OS setting.** The choice is stored in `localStorage.theme` (Settings option "Look: Warm / Dark").

| Token | Light "Warm" | Dark | Used for |
|---|---|---|---|
| `--bg` | #FFF8EE | #0E1117 | page |
| `--panel` | #FFFFFF | #161B24 | cards, panels, dialogs |
| `--panel2` | #FFF1DC | #1C2330 | tinted areas, hover |
| `--line` | #E6D5BD | #2A3344 | decorative dividers only (never a control edge) |
| `--ctl` | #7F6F5D | #7B88A6 | **control borders** (≥3:1 everywhere) |
| `--txt` / `--mut` | #2B2118 / #5E4F40 | #E6EAF2 / #A9B4C9 | text / help text |
| `--acc` / `--on-acc` | #5B3FD6 / #FFFFFF | #5B3FD6 / #FFFFFF | primary button fill / its text |
| `--accink` | #4F34C7 | #B8A9FF | links, selected borders, accent text |
| `--tint` | #EDE7FF | #2A2457 | selected state background |
| `--warm` / `--warmtint` | #B4410C / #FFE3CC | #FFB26B / #3A2A1A | nozzle, classroom bar, warm accents |
| `--focus` | #1D4ED8 | #8DB8FF | 3 px focus ring, 2 px offset |
| `--ok` / `--okbg`; `--bad` / `--badbg`; `--warn` | #166534 / #E3F5E8; #B91C1C / #FDE8E8; #8A5300 | #4ADE80 / #12301F; #FF9A9A / #3A1A1E; #FBBF24 | success, error, warning (always with words/icons) |

Computed contrast (WCAG 2.x relative luminance; "Need" is the WCAG minimum for that use):

| Use | Pair | Light | Dark | Need |
|---|---|---|---|---|
| Body text | `txt` on `bg` | 14.93 ✓ | 15.67 ✓ | 4.5:1 |
| Body text on card | `txt` on `panel` | 15.75 ✓ | 14.32 ✓ | 4.5:1 |
| Body text on tinted panel | `txt` on `panel2` | 14.15 ✓ | 13.07 ✓ | 4.5:1 |
| Muted/help text | `mut` on `bg` | 7.46 ✓ | 9.05 ✓ | 4.5:1 |
| Muted text on card | `mut` on `panel` | 7.87 ✓ | 8.27 ✓ | 4.5:1 |
| Muted text on tinted panel | `mut` on `panel2` | 7.07 ✓ | 7.55 ✓ | 4.5:1 |
| Text on selected tint | `txt` on `tint` | 13.11 ✓ | 11.70 ✓ | 4.5:1 |
| Muted on selected tint | `mut` on `tint` | 6.55 ✓ | 6.76 ✓ | 4.5:1 |
| Links and accent text | `accink` on `bg` | 7.52 ✓ | 9.14 ✓ | 4.5:1 |
| Accent text on card | `accink` on `panel` | 7.93 ✓ | 8.35 ✓ | 4.5:1 |
| Accent text on selected tint | `accink` on `tint` | 6.60 ✓ | 6.82 ✓ | 4.5:1 |
| Primary button text | `#FFFFFF` on `acc` | 6.72 ✓ | 6.72 ✓ | 4.5:1 |
| Warm accent text/icon | `warm` on `bg` | 5.38 ✓ | 10.65 ✓ | 4.5:1 |
| Warm accent on its tint | `warm` on `warmtint` | 4.62 ✓ | 7.75 ✓ | 3:1 |
| Text on warm tint (classroom bar) | `txt` on `warmtint` | 12.83 ✓ | 11.41 ✓ | 4.5:1 |
| Control border on page | `ctl` on `bg` | 4.59 ✓ | 5.32 ✓ | 3:1 |
| Control border on card | `ctl` on `panel` | 4.85 ✓ | 4.86 ✓ | 3:1 |
| Control border on tinted panel | `ctl` on `panel2` | 4.35 ✓ | 4.44 ✓ | 3:1 |
| Control border on selected tint | `ctl` on `tint` | 4.03 ✓ | 3.97 ✓ | 3:1 |
| Selected border (accent ink) | `accink` on `bg` | 7.52 ✓ | 9.14 ✓ | 3:1 |
| Focus ring on page | `focus` on `bg` | 6.35 ✓ | 9.39 ✓ | 3:1 |
| Focus ring on card | `focus` on `panel` | 6.70 ✓ | 8.58 ✓ | 3:1 |
| Focus ring on selected tint | `focus` on `tint` | 5.58 ✓ | 7.01 ✓ | 3:1 |
| Success text on success bg | `ok` on `okbg` | 6.28 ✓ | 8.21 ✓ | 4.5:1 |
| Error text on card | `bad` on `panel` | 6.47 ✓ | 8.50 ✓ | 4.5:1 |
| Error text on error bg | `bad` on `badbg` | 5.51 ✓ | 7.68 ✓ | 4.5:1 |
| Warning text on tinted panel | `warn` on `panel2` | 5.69 ✓ | 9.44 ✓ | 4.5:1 |

Rules that come out of the numbers:
1. White text is allowed only on `--acc` (6.72:1) and `--warm` light (5.67:1). The old brand violet `#7C5CFF` with white text was 3.16–4.35:1, so it goes.
2. **Never use `--acc` as an edge or text on dark backgrounds** (2.35–2.81:1). In dark theme the primary button gets a 2 px `--accink` border; the white label (6.72:1) is what identifies it.
3. Control borders use `--ctl`, never `--line` (1.36–1.49:1, which is the audit's M-contrast finding).
4. Selected state = tint + `--accink` 2 px border + inset ring, plus `aria-checked`/`:checked`. Not colour alone.
5. Success/done steps use a tick shape in addition to colour.
6. All pairs above also hold in forced-colors mode because states use borders and shape (the mock sets system colours for borders).

## 6. Exact changes (current tree, 2026-10-04)
**index.html**
- `:13-28` header: replace with the mock's header (brand, `nav aria-label="Main"` with `aria-current="page"` instead of `.on`, Mode select from the mode spec, Account/Settings buttons with `class="lbl"` text). `:21-24` `#levelSwitch` is removed by the Mode spec.
- `:30-39` Studio start: insert the hero `<section class="hero" aria-labelledby="h1">` with `<h1 id="h1">`, the sentence, and **move `<div id="studioPhoto"></div>` (`:34`) into the hero** (`photoBlock("s")` from photo.js:`49` already renders Take / Choose / Use a sample; restyle: Take = primary, Choose = secondary, sample = `.linkbtn`). Keep `#drop`/`#dropPreview` as "Your photo" below, with the new empty text.
- Add the path `<nav aria-label="Your progress"><ol class="path" id="path">` + `#pathSay` (`role="status"`) before `<main class="layout">` content; add `<h1>` handling: only one `<h1>` per view (Showcase and Learn already have one; Studio and Edit don't).
- `:43-47` Style cards become a `<fieldset><legend>` with radio inputs (the audit's "buttons don't expose selected" fix) and the plainer captions; `:57-59` Thickness the same (radio group). `app.js:37-42` stop toggling `.on` and read `input:checked` instead.
- `:95-96` Build button text → "✨ Make my 3D model"; keep the live hint `#buildHint`.
- `:100-109` viewer: add `role="img"` + `aria-label` on the canvas wrapper, the `#vtools` buttons "Turn left", "Turn right", "Reset view" (also visible when no pointer), and keep the touch hint.
- `:110-123` result: `<h2>Your model is ready</h2>`; stats as `<ul class="stats">`; **"⬆ Send or save"** with `aria-haspopup="dialog"`.
- `:125-128` history: `<ul class="hist">` of `<li class="hcard">` with real buttons; heading "Pick up where you left off".
- After `:129` add "Keep exploring" tiles (`<ul class="tiles"><li><a class="tile">…`), hidden in Experienced.
- Before `</body>` add `<footer class="site">` with the four links (pages must exist first) and the `#modeStatus` region (Mode spec).
- Dialog headers: **change `<header>` inside every `<dialog>` to `<div class="dh">`** (and `<footer>` to `<div class="df">`): axe reports duplicate banner/contentinfo landmarks when a dialog's header sits next to the page header (found in this mock; it will happen in the real app at `:183, :216, :222, :248, :276, :281, :294, :299, :305, :310`). Update the matching `.dlg header` selectors in style.css `:67-68`.
**style.css**
- Replace the `:root` token line `:1` with the two-theme block from the mock; replace hard-coded colours (`#1f2740`, `#232a49`, `#131923`, `#1a2236`, `#24305a`, `#2a2230`, `#16281f`, `#f6f8fb`, and every `var(--mut)`/`var(--line)` used for a control edge) with tokens. Use `--ctl` for input/select/button/card edges (`:12,17,24,31,35,57`).
- `.seg button.on`, `.card.on`, `.nav button.on`, `.tabs button.on`: keep the class names but restyle to `--tint` + `--accink` border; text colour `--txt` (the `#fff`-on-violet pairs at `:11,34,37,226` go).
- `.btn.primary` (`:37`): solid `--acc`, no gradient, `color:var(--on-acc)`.
- Add `.hero`, `.path`, `.tiles`, `.tile`, `.hist`, `footer.site`, `.row-btn` (Send rows), `.dh`, `.df`, `.cardfoot`, `.stats` from the mock; keep the existing `@media` blocks at `:133-148`, `:171-176`, `:189-217` (they already do 44 px, 16 px inputs, safe areas) but change the topbar rule to the 3-row order above.
- `.empty{...}` at `:129` overrides `:43` (the viewer's empty state is left-aligned and padded); give the viewer's empty block its own class so it stays centred.
- Add `@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}` and the `forced-colors` block.
**app.js**
- `:27-41` Mode logic per `mode-dropdown-spec.md`. `:49` unchanged (`photoBlock("s")`), but mount it inside the hero.
- `:66-72` `setFile()` → also call `setPath(1,…)`; `build()` → `setPath(2, "Making your 3D model. Step 2 of 3.")` at start and `setPath(3, "Model ready. Step 3 of 3: save or print it.")` on success; add `setPath()` (mock) and `#pathSay` writes.
- After a build, move focus to the result heading (`#resultH` `tabindex="-1"`) instead of dropping to `<body>` (audit H-3).
- Toast → status: errors also go to a `role="alert"` region; the "Build failed: [object Object]" case uses `e.message` text only (audit).
**community.js:** `:19-20` set `S.canTeach` (Mode spec); `:84,:113` nozzle (Nozzle spec); `:83` cards become `<li>`/stretched link.
**send.js** (button text/ARIA only; behaviour untouched)
- `render()` rows: split into the two groups with `<h3 class="group">` and `<ul class="rows">`; keep ids `ssSave/ssTeacher/ssShare/ssEmail/ssShapr/ssPrinter` so tests keep working; add `aria-haspopup="dialog"` on `#btnSendSheet` (index.html `:114`) and on `#editSend` (`:170`).
- `#ssStatus` and `#ssAlert` stay; make sure they exist before the first message (they do).
- Title `ssTitle` → "Send or save your model" for adults, "Save your model" for teens/students.
**photo.js:** no behaviour change; add `aria-describedby` from the Take/Choose buttons to `.pp-note` (one sentence: "Photos stay private to you unless you choose to share") so the privacy line is read with the buttons.
**Server:** none for this page.

## 7. Acceptance tests
**Accessibility**
- H1 axe: 0 violations on Studio: empty, photo chosen, built, Experienced, Teacher; Send sheet open as adult / teen / student; light and dark; 320/390/1280 px.
- H2 No horizontal scroll at 320, 360, 390, 768, 1280 px, and at 200% zoom. Top bar ≤170 px tall at 320 px (before the Teacher classroom bar).
- H3 Landmarks: exactly one banner, one main, one contentinfo, one `nav` "Main" plus the "Your progress" nav; one `<h1>`; no skipped heading levels; no duplicate landmarks when a dialog is open.
- H4 Keyboard only, in this order: skip link → brand → tabs → Mode → Account → Settings → Take / Choose / sample → style radios (arrow keys) → Width → thickness radios → Make my 3D model → viewer buttons → Send or save → … → footer links. Visible 3 px focus ring everywhere; no trap; Esc closes dialogs and returns focus to the opener.
- H5 Screen reader (VoiceOver iPhone + one desktop reader): the step status is read after each stage ("Photo chosen", "Making your 3D model", "Model ready"); style and thickness are read as "radio, 1 of 3, selected/not selected"; the viewer is read as an image with a description; Send rows read label + description.
- H6 Contrast: every row of §5 measured on the built page (axe + manual check of gradients and the disabled/hover states) in both themes; hero text over its gradient ≥4.5:1 at both ends of the gradient.
- H7 Targets ≥44×44 (including footer links and the "Try a sample photo" link). Inputs 16 px. No target overlaps another.
- H8 Reduced motion: no spinner rotation or transitions. Forced-colors / Windows high contrast: borders, selected state and focus ring still visible.
- H9 200% text-only zoom: nothing clipped; the three-step path stays readable (captions may hide at ≤420 px).
**Behaviour**
- P1 Fresh visitor: the only primary button above the fold at 390×844 is "Take a photo" (or "Choose a photo" on a desktop without camera, as photo.js decides).
- P2 Choose a photo → in Beginner it builds by itself, step 2 shows "Making…", then step 3 and the result is scrolled into view and focused; in Experienced it waits for the button.
- P3 Errors (non-image, too big, build failed, offline) show plain words next to the step and in the alert region, never `[object Object]` or Python text, and keep the photo.
- P4 Send sheet: rows exactly as the server allows (adult / adult desktop local / teen / class student); Share-type rows disabled until the file is ready; Save works without JavaScript beyond the dialog; status and alert announced; Esc returns focus; no row links to anything outside ZEIM except the labelled Creality site link.
- P5 Teacher mode shows the classroom bar and the lesson link; a student/teen never sees them.
- P6 Warm is shown on first visit even when the OS is in dark mode; Dark only after the person picks it; the choice survives reload. (Changed Oct 12, 2026: the app no longer follows the OS.)
- P7 Safari iPhone/iPad (real device, over HTTPS): Take a photo opens the camera; Share opens the share sheet from a single tap; recorded as pass/fail by Ren Ishikawa. **Until then the page may not claim it works.**

## 8. Decisions needed
1. **Yami/Zach:** OK to retire the violet-gradient look for the warm light theme as the default (dark stays as a choice)? It is the biggest visual change; the old violet fails contrast.
2. **Zach:** hero wording. Proposed: "Turn a photo into something you can print." / "Take or choose a photo. ZEIM makes a 3D model you can turn around, then gets it ready to print. Free for everyone." Every word is true today (for the "Free for everyone" line, confirm with Kenji's claims list).
3. **Yami:** the footer needs real Privacy and Terms pages (Kenji/Aiko) before the links go live; Credits is Kenji's spec.
4. **Zach:** "Email it to myself" stays "your Mail app sends it" (via the share sheet) until a ZEIM-owned sender exists; the sheet says so.
