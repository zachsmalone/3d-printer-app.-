# Mode dropdown spec (Beginner · Experienced · Teacher)

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


**Author:** Accessibility & Usability Reviewer (design owner) · **Date:** 2026-10-04 · **Status:** ready for Yami to hand to the builders
**Mock:** `mock-mode.html` (open it in a browser; the grey "MOCK" bar lets you pretend to be a visitor, adult, teen or class student, and flip the light/dark theme).
**Checked:** axe-core 4.13.0 on the mock, light and dark, at 320, 390 and 1280 px, in five states (Beginner, Experienced, Teacher as adult, the guest explainer, the teen explainer): 30 runs, 0 violations. Keyboard run in headless Chrome (arrow keys on the closed select, explainer, sign-up path). Contrast is computed (see `home-redesign-spec.md`, Palette). **Not tested:** real VoiceOver/TalkBack/NVDA, real iPhone picker, other browsers. Announcement wording is from the code pattern, not heard.

## 1. Decision in one paragraph
Replace the two-button `#levelSwitch` (a `role="tablist"` whose buttons are not tabs; audit H-6) with **one native `<select>` labelled "Mode"** with three options: **Beginner, Experienced, Teacher**. A native select is correct by default (name, value, expanded state, arrow keys, type-ahead, iOS wheel picker, high-contrast mode) and needs no ARIA. A custom button + listbox would add ~80 lines of keyboard code to get the same result, so we don't build one. The mode is **a view preference only**: it never grants a permission. The server keeps deciding who may do what (as it does today for Send, classes, and Showcase).

## 2. What each mode shows
Internal values stay `beginner | expert | teacher`. `expert` is kept so stored data and the `beginner` flag sent to the server (`fd.append("beginner", …)`) do not change. Only the **label** changes to "Experienced" (friendlier, and "Expert" made new makers feel locked out).

| Area | Beginner (default) | Experienced | Teacher |
|---|---|---|---|
| Studio settings | Style cards, Width, Thin/Standard/Thick, Build starts by itself after a photo is chosen (today's behaviour) | Everything in `#expertOpts` (resolution, smoothing, thickness, base, pop-art layers…). Photo does **not** auto-build; Build button is fixed at the bottom on phones (today's behaviour) | Same as Beginner, so a demo matches what students see |
| After a build | "Auto-chosen settings" table open | Table hidden (you set them) | Same as Beginner |
| Edit workspace | Big job buttons (`[data-lvl=beginner]`) | Full toolset (`[data-lvl=expert]`) | Same as Beginner |
| Send sheet | File type folded under "Different file type?" | File-type chooser open | Same as Beginner |
| Classroom bar | hidden | hidden | **Shown** under the top bar: class name, join code (large), "Students sending files out of ZEIM: Off/On", **Teacher tools** button |
| Learn lessons | "Teacher notes" closed | closed | "Teacher notes" **open** |
| Print dialog | unchanged in v1 (optional later: fold "Slice here" under "More print options") | unchanged | unchanged |
| Server/permissions | no change | no change | **no change**: same adult-only endpoints as before |

If a Teacher wants the full controls for their own work they switch to Experienced; the classroom bar then hides. Two things to say out loud in the UI help text: Teacher mode *looks* like Beginner, and it needs an adult account.

## 3. Defaults and persistence
- First visit: **Beginner**.
- Stored in `localStorage.level` (existing key). Valid values `beginner|expert|teacher`; anything else → `beginner` (today any junk value would leave the page half hidden).
- `teacher` is only restored if the account is an adult account (see §4). Otherwise start in Beginner, silently (no scary message on load).
- Signing out, or switching to a teen/student session, while in Teacher mode → back to Beginner and announce "Back to Beginner mode." (Prevents a shared school computer from showing a teacher's class code to the next student.)
- Changing mode never reloads the page and never loses a photo, a build or typed text.
- No server-side storage in v1.

## 4. Teacher mode without an adult account (friendly, never a dead end)
Eligibility = the same test `openTeacher()` already uses: `ME.signed_up && ME.age_group === "adult"` (community.js:216).

**The Teacher option is always selectable** (a disabled `<option>` is skipped by some screen readers and explains nothing). When someone picks it and is not eligible:
1. The select **snaps back** to their previous mode (so the screen always tells the truth).
2. A **non-modal explainer** appears directly under the top bar (`<section class="note">`, heading + text + buttons). It is not a modal dialog, because on desktop Chrome/Edge/Firefox an arrow key on a closed select fires `change` immediately, and a modal would hijack someone who is just arrowing through the list.
3. A polite live message says what happened and where to look: "Teacher mode needs a grown-up account. Details are just below the top bar. You are still in Beginner mode." **Focus stays on the select.**

| Who | Heading | Text | Buttons |
|---|---|---|---|
| Visitor, no account | Teacher mode is for grown-ups with an account | It adds class tools: make a class, share a join code and see what students send. Setting up takes about a minute. Students never need an account. ZEIM can't check who is a teacher, so please only make a class for students you teach. (wording from Kenji's edit of HQ-1) | **Make a grown-up account** (starts the HQ-1 flow; on success switch to Teacher and announce it) · Not now |
| Signed-in teen | Teacher mode is for adults | Teacher mode needs an adult (18 or older) account. You can still join a class with a code from your teacher. | **Join a class** (opens `#dlgJoin`) · Okay, keep Beginner mode |
| Class student (no account) | Teacher mode is for adults | You don't need it. Your teacher gives you a class code, and you join from the Learn page. | Join a class · Okay |

"Not now"/"Okay" dismiss the explainer and return focus to the select. The explainer also closes by itself if the person picks another mode.
Trade-off to know about: the explainer comes after Account and Settings in tab order (it sits after `</header>`). That is the least bad option because making it a child of the top bar would break the wrapping layout; the live message says where it is.

## 5. Keyboard and screen reader behaviour
- Native `<select id="modeSel">` with a real `<label for>` ("Mode"), `aria-describedby="modeHelp"` pointing at a short hidden description of the three modes.
- Keys (all native): Tab to reach; Up/Down change the value (closed); Alt+Down/Space/Enter open the list; first letter jumps; Esc closes.
- **Change announcement:** a single page-level `<div id="modeStatus" class="sr-only" role="status" aria-live="polite" aria-atomic="true">`. On change, clear then set text after ~60 ms (so identical text is re-announced): "Experienced mode on. All settings are showing." / "Beginner mode on. ZEIM picks the settings for you." / "Teacher mode on. Your classroom tools are showing above the page."
- A visible one-line description of the current mode sits at the top of the Studio panel (`#modeLine`), so sighted people also learn what the mode does. It updates with the same text family.
- The emoji (🌱 🛠 🍎) is shown **beside** the select in a `<span aria-hidden="true">`, not inside `<option>` text, so screen readers don't read "seedling".
- Hidden content must be `hidden`/`display:none` (not just faded) so screen readers and Tab skip it.
- Focus never moves because of a mode change. (After a successful sign-up from the explainer, focus returns to the select.)

## 6. Size, colour, layout
- Select: `min-height:44px`, `min-width:150px`, `font-size:16px` (stops iOS zooming into the field), at **all** widths (today's 44px rule is only inside the ≤768px query).
- Border `--ctl` ≥ 3:1 on every surface; text `--txt` ≥ 4.5:1 (numbers in the Palette table). Focus ring 3 px `--focus`, 2 px offset. No information by colour alone.
- In the top bar the select + its label stay on one line; at 320 px they sit on row 2 beside the brand. Nothing scrolls sideways (checked at 320/390/1280).
- Classroom bar uses the warm tint with a 2 px warm bottom border and wraps; the join code is `font:700 18px monospace`, letter-spaced, with an `aria-label` that spells it ("K 7 Q M 2 X").

## 7. Exact changes (file:line from the current tree, 2026-10-04)
**index.html**
- `:21-24` replace the whole `<div class="seg" id="levelSwitch" …>…</div>` with:
```html
<div class="modepick">
  <label for="modeSel">Mode</label>
  <span class="ico" id="modeIco" aria-hidden="true">🌱</span>
  <select id="modeSel" aria-describedby="modeHelp">
    <option value="beginner">Beginner</option>
    <option value="expert">Experienced</option>
    <option value="teacher">Teacher</option>
  </select>
  <p class="sr-only" id="modeHelp">Beginner: ZEIM picks the settings. Experienced: every setting is yours. Teacher: Beginner settings plus class tools, for adults with an account.</p>
</div>
```
- After `</header>` (`:28`) add `<section class="note" id="teacherNote" hidden aria-labelledby="tnTitle"><h2 id="tnTitle"></h2><p id="tnBody"></p><div class="row" id="tnActions"></div></section>` and the Classroom bar `<div class="classbar" id="classBar" hidden role="region" aria-label="Classroom">…</div>` (markup in the mock).
- Add `<div id="modeStatus" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div>` once, near `#toasts` (`:320`).
- `:33` (top of the Studio controls panel) add `<p class="modeline" id="modeLine"></p>`.
- `:122` `(Beginner mode)` → leave; it is rendered for Beginner and Teacher.

**style.css**
- Delete `#levelSwitch` rules: `:137` (`#levelSwitch{order:2}`), `:141-142`, `:151`. Replace with `.modepick{order:2}` at ≤768px.
- `:108` `body[data-level=beginner] [data-lvl=expert],body[data-level=expert] [data-lvl=beginner]{display:none !important}` → add `,body[data-level=teacher] [data-lvl=expert]{display:none !important}`.
- `:174-175` unchanged (they target `data-level=expert`, which is still correct).
- Add `.modepick`, `.modeline`, `.classbar`, `.code`, `.note` (copy from the mock's `<style>`; tokens per the Palette).
- Add the 44 px rule for `.modepick select` outside the media query.

**app.js**
- `:4` `level: localStorage.level || "beginner"` → `level: ["beginner","expert","teacher"].includes(localStorage.level) ? localStorage.level : "beginner"`.
- Add near `:27`: `const isExpert = () => S.level === "expert";` (everything else asks `!isExpert()`: Teacher behaves like Beginner).
- `:28-34` `applyLevel()`: drop the `#levelSwitch` button loop (`:32`); `#beginnerOpts.hidden = isExpert()`; `#expertOpts.hidden = !isExpert()`; set `#modeSel.value`, `#modeIco` text, `#modeLine` text, `#classBar.hidden = S.level !== "teacher"`; announce when called from a user change.
- `:41` replace the `#levelSwitch` click wiring with the `change` handler from the mock (revert + explainer when `S.level==="teacher"` is chosen and `!S.canTeach`).
- `:70` `S.level === "beginner"` → `!isExpert()`; `:88` `fd.append("beginner", !isExpert())`; `:91` `S.level === "expert"` → `isExpert()`.
- `:154` and `:195` label text `b.beginner ? "Beginner" : "Expert"` → `"Experienced"`.
- `:316` `applyLevel()` stays; call it again when `zeim:me` fires (below).

**community.js**
- `:19-20` in `refreshMe()` add `S.canTeach = !!(ME.signed_up && ME.age_group === "adult"); document.dispatchEvent(new CustomEvent("zeim:me"));`. If `S.level==="teacher" && !S.canTeach` then `S.level="beginner"; applyLevel(); say("Back to Beginner mode.")`.
- `:216` `openTeacher()` stays the single source of "who is eligible"; the explainer's "Make a grown-up account" button calls the HQ-1 setup flow and, on success, sets `S.level="teacher"`.
- `:187` `<details><summary>Teacher notes</summary>` → `<details ${S.level === "teacher" ? "open" : ""}>…`.
- Teacher tools button in the Classroom bar → `openTeacher()`.

**edit.js** `:53`, `:71` `S.level === "beginner"` → `!isExpert()` (import it); `:133` text "switch to Expert" → "switch to Experienced mode"; `:177` `S.level === "beginner"` → `!isExpert()`; `:82` event name unchanged.
**send.js** `:26` "Expert" → "Experienced"; `:43` `S.level === "beginner"` → `!isExpert()`.
**Server:** none. `beginner:true` is sent for Teacher builds.

## 8. Acceptance tests
**Accessibility (axe + manual)**
- A1 axe: 0 violations on Studio in each mode, light and dark, at 320/390/1280.
- A2 The select has the accessible name "Mode" and its value is announced as Beginner/Experienced/Teacher. No `role="tablist"` remains anywhere in the top bar.
- A3 Keyboard only: Tab to Mode, Down/Up changes it, the status text updates, focus stays on the select, no keyboard trap, Esc closes an open list.
- A4 Each change produces exactly one polite announcement (check with VoiceOver on iPhone and one desktop reader; record the spoken text).
- A5 Picking Teacher while ineligible: select reverts, explainer appears, announcement mentions "still in Beginner/Experienced mode", focus stays on select, explainer buttons reachable by Tab, "Not now" returns focus to the select.
- A6 Select, explainer buttons, Classroom bar button are ≥44×44 CSS px; select text is 16 px; no horizontal scroll at 320 px.
- A7 Contrast: select text/border, status line, explainer, classroom bar meet 4.5:1 / 3:1 in both themes (numbers in the Palette table).
- A8 Reduced motion: nothing animates on mode change. Zoom 200% and text-only zoom 200%: nothing clipped.

**Behaviour**
- B1 Fresh browser → Beginner. Reload keeps the choice. Junk `localStorage.level` → Beginner.
- B2 Beginner: choosing a photo auto-builds; Experienced: it does not, and Build is reachable on a phone.
- B3 Beginner→Experienced→Beginner keeps the photo, the built model, and values typed in Width.
- B4 Visitor picks Teacher → explainer → "Make a grown-up account" → after sign-up the mode is Teacher and the Classroom bar shows.
- B5 Teen and class student never get Teacher mode, even with `localStorage.level="teacher"` set by hand (page reverts; server shows nothing different anyway).
- B6 Signing out while in Teacher mode → Beginner, Classroom bar gone.
- B7 Teacher mode builds send `beginner=true` and look like Beginner builds in history; history/Send labels read "Experienced" not "Expert".
- B8 No request to the server is made by a mode change.

## 9. Decisions needed
1. **Yami/Zach:** OK that Teacher mode = Beginner view + classroom bar + notes open, with no extra permissions? (If a teacher should also be able to *lock* a class to Beginner, that is a server feature; parked.)
2. **Zach:** label "Experienced" instead of "Expert". Recommended; one word.
