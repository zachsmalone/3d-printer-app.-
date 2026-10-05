# "Nozzle it" spec: one positive-only button that replaces every like, heart and upvote

**Author:** Accessibility & Usability Reviewer (design owner) · **Date:** 2026-10-04 · **Mock:** `mock-nozzle.html`
**Checked:** axe-core 4.13.0 on the mock: light + dark, 320/390/1280 px, 5 states (grid, pressed, signed-out dialog, class-off, item dialog): 30 runs, 0 violations. Keyboard run in headless Chrome (Space and Enter toggle, name and `aria-pressed` update, focus stays, failure rolls back, 44 px sizes). Contrast numbers below are computed. **Not tested:** real screen readers (spoken text comes from the markup pattern, not heard), real iPhone, real server. Comments and video surfaces do not exist in the app yet; their markup is specified here and shown in the mock as "future surface".

## 1. What it is
- Name shown to people: **Nozzle it** (the action) and **nozzles** (the count). Never "likes", "hearts", "upvotes".
- Positive only: **no downvote, no "dislike"**. Pressing again takes your nozzle back.
- One button style everywhere: Showcase card, project page/dialog, comments, videos.
- Data stays compatible: the server keeps `likes` / `liked` / `can_like` and the route `POST /api/showcase/<id>/like`. This is a rename + new icon + better states. The server already accepts an explicit `{"liked": true|false}` (community.py:234), so the page always sends the state it wants, not a blind toggle. That stops a double-tap flipping it back.

## 2. The icon (inline SVG, 24×24, `currentColor`)
A printer hot-end from the side: heater block, cone, tip. Pressing "extrudes" a filament drop. **Off:** outline only, no drop. **On:** filled, with the drop. The two states differ by shape, not only by colour.
```html
<svg class="nz-ico" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
  <g class="nz-body"><rect x="6" y="2.5" width="12" height="5.5" rx="1.5"/><path d="M8.2 8h7.6l-2 5.5h-3.6z"/><path d="M10.2 13.5h3.6V16h-3.6z"/></g>
  <path class="nz-drop" d="M12 17.6c-1.5 1.9-2 2.7-2 3.5a2 2 0 0 0 4 0c0-.8-.5-1.6-2-3.5z"/>
</svg>
```
Always `aria-hidden="true"` (the button has its own name). One inline copy per button, not `<use>`: the press animation targets `.nz-body` and `.nz-drop` inside each button. Icon is original artwork drawn for this spec (no third-party icon set).

## 3. Anatomy and states
```html
<button type="button" class="nz" data-nz="ITEM_ID" aria-pressed="false" aria-label="Nozzle it, 12 nozzles">
  <svg class="nz-ico">…</svg><span class="nz-count">12</span>
</button>
```
Large version (project page): `class="nz nz-lg"` plus `<span class="nz-text">Nozzle it</span>` before the count.

| State | Looks like | Accessible name | `aria-pressed` | Notes |
|---|---|---|---|---|
| Not nozzled | outline icon, 2 px neutral border, count in text colour | `Nozzle it, 12 nozzles` | `false` | |
| Nozzled | filled icon + drop, 2 px warm border, warm tint background | same pattern, new count | `true` | The name does **not** change to "Nozzled": state is carried by `aria-pressed` only (two changing signals get read twice) |
| 0 nozzles | icon only, no number | `Nozzle it, no nozzles yet` | | Never show "0" to a child |
| 1 nozzle | | `Nozzle it, 1 nozzle` | | singular |
| Big numbers | `1.2k` visible, full number in the name | `Nozzle it, 1243 nozzles` | | |
| Count hidden | no number | `Nozzle it` | | Server sends `likes: null` (young makers; flag `HIDE_COUNTS_FOR_MINORS`). Button still works if `can_like` |
| **EXAMPLE item** | **no button, no number** | n/a | n/a | Test `i.example`. Today `likes: null` hides the whole button (`i.likes != null`); once the button shows for null counts, `!i.example` must be tested too |
| Your own project | not a button: icon + text "3 nozzles" | text | n/a | Server: `can_like` is false for the owner |
| Signed out | normal button | `Nozzle it, 12 nozzles` | `false` | Press opens a small dialog "Make a free account to nozzle" (heading, one sentence, **Make an account** / **Not now**), not a vanishing toast. After sign-up: announce "Account made. You can nozzle projects now." and keep the person where they were |
| Teacher turned nozzles off (class) | dashed grey border, grey icon | `Nozzle it, 12 nozzles`, `aria-describedby` → "Your teacher turned nozzles off for your class." | `false` | `aria-disabled="true"`, **not** `disabled`, so it stays focusable and the reason can be read. Pressing speaks the reason; nothing is sent. The reason is also visible text under the button |
| Saving | optimistic result | unchanged | new value | Ignore presses on that button while the request is in flight (`data-busy`) |
| Failed | rolls back | old name | old value | `role="alert"`: "Couldn't save your nozzle. Check your connection and try again." + visible toast |

Why not `disabled`: iOS and Android readers skip disabled buttons, so a child using VoiceOver would never learn why it doesn't work.

## 4. Announcements
- One page-level polite region `#nzStatus` (`role="status"`, `aria-live="polite"`, `aria-atomic="true"`), cleared then filled ~60 ms later so repeats are spoken. Texts: "Nozzled. 13 nozzles." · "Nozzle removed. 12 nozzles." · (count hidden) "Nozzled." / "Nozzle removed."
- One alert region `#nzAlert` (`role="alert"`) for failures. Both regions exist in the DOM from page load.
- Real-device test item: some screen readers speak the new `aria-pressed` state *and* the live text. If a reader double-speaks, drop the live text for success and keep the alert; the changed name already carries the count.
- Update buttons **in place** (attribute + count text). Today `itLike` calls `openItem(id)` and `loadShowcase()`, which rebuild the dialog and grid and drop focus. That must go.

## 5. Press animation
- Press: nozzle dips 2 px and squashes to 92% (0.22 s); the drop appears and falls into place with a small overshoot (0.45 s). Taking it back: only the dip (0.16 s). CSS is in the mock (`@keyframes nzpress`, `nzdrop`).
- `@media (prefers-reduced-motion: reduce)` removes **all** animation; the state change is instant (filled + drop). The JS also checks `matchMedia("(prefers-reduced-motion: reduce)")` and skips adding `.pop`.
- Nothing flashes; no sound; no confetti. The animation is decoration, never the only signal.

## 6. Colour and contrast (computed, WCAG 2.x)
Border and icon ≥3:1 against what they sit on (1.4.11); text ≥4.5:1 (1.4.3).

| Pair | Light "Warm" | Dark |
|---|---|---|
| Not-nozzled border (`--ctl`) on card panel | 4.85 | 4.86 |
| Not-nozzled icon/count (`--txt`) on card panel | 15.75 | 14.32 |
| Same border on hover background (`--panel2`) | 4.35 | 4.44 |
| Nozzled icon + border (`--warm`) on its tint (`--warmtint`) | 4.62 | 7.75 |
| Nozzled border (`--warm`) against the card (`--panel`) | 5.67 | 9.73 |
| Count text (`--txt`) on the nozzled tint | 12.83 | 11.41 |
| Class-off text/icon (`--mut`) on panel | 7.87 | 8.27 |
| Focus ring (`--focus`) on card / page | 6.70 / 6.35 | 8.58 / 10.65 |

Disabled text is kept above 4.5:1 on purpose: WCAG exempts disabled controls, but the reason must be readable by low-vision kids.
Pressed vs not pressed = filled vs outline icon, the drop, a warm border and tint, and `aria-pressed`. Never colour alone.

## 7. Size, layout, touch
- Every nozzle control is **≥44×44 CSS px** (measured in the mock: 52–91 × 44; card title links are also ≥44 px tall). Compact card version: `padding:4px 12px; min-height:44px`.
- On a card the title is the link; the card uses the **stretched-link** pattern (`h3 a::after{position:absolute;inset:0}`) so the whole card still opens, while the Nozzle button sits above it (`position:relative; z-index:2`). This also fixes the audit blocker "cards are clickable divs" (today `<div class="pcard" data-item>` with a delegated click, community.js:83, 91). A button inside a clickable `div` would be a nested-interactive error.
- Comments: small button on the comment's action row. Videos: in the action row next to the title, never inside the player controls.
- At 320 px the grid is one column; nothing scrolls sideways (checked).

## 8. Needs-account, minors, classes (follows decisions.md)
- Likes need an account once auth exists: signed-out state above.
- "Counts hidden for minors": today the server hides **numbers on under-18 creators' items**. The button stays. **Question for Yami:** should a minor *viewer* also see no numbers on adult projects? The mock follows the server as it is. If yes, send `likes: null` to minor viewers (server) and the page needs no change.
- EXAMPLE items: no button, no number.
- A class student sees the button only if the teacher's Showcase switch is on; the second switch off gives the greyed state. When the Teacher-tools UI for that switch is built, label it "Let students nozzle projects".

## 9. Exact change list
**community.js**
- `:83` `<div class="pcard" data-item=…>` → `<li class="pcard">` (grid becomes `<ul>`, see `home-redesign-spec.md`) with `<h3><a href="…" data-open="ID">title</a></h3>`; no click-on-div.
- `:84` replace `${i.likes != null ? ` · ♥ ${i.likes}` : ""}` and `${i.liked_by_others ? " · ♥ liked" : ""}` with `${nzHTML(i)}` in a `.cardfoot` row; downloads beside it as "⬇ 40" + `<span class="sr-only"> downloads</span>`. Owner's own item: static "N nozzles".
- `:91` and `:95` grid click wiring: open from the title link (`e.target.closest("[data-open]")`, `preventDefault()`); add the nozzle handler.
- `:113` replace the `#itLike` button with `${nzHTML(i,{large:true})}`; `:118` delete the `#itLike` handler.
- `:117` copy: "Likes and downloads are counted…" → "Nozzles and downloads are counted once per person and only for public projects."
- Add (≈40 lines, as in the mock): `SVG` constant, `nameFor()`, `short()`, `nzHTML()`, `refreshAll(id)` (updates every button with that `data-nz`), one delegated click handler (signed-out dialog, class-off message, optimistic update, `POST …/like {"liked": want}`, rollback, announcements).
- Items with `i.example` → no nozzle markup.
**index.html** add `#nzStatus` and `#nzAlert` near `#toasts` (`:320`); add the signed-out dialog (mock `#dlgAcct`).
**style.css** add the `.nz*` block (mock `<style>`), `.cardfoot`, stretched link; update `.pcard` (`:88-93`). Use the tokens from the Palette in `home-redesign-spec.md`.
**app/api/learn.py:329** teacher project list text `· ♥ N` → `· N nozzles` (nothing when `likes is None`).
**Server (small, optional):** return `can_like_reason` (`own` · `signed_out` · `class_off`). Without it the page infers: `owned` → static; guest → signed-out; role `student` + `can_like` false → class-off.
**Search the tree** for `♥`, `❤`, `like`, `Like`, `heart` in `static/*`, `COMMUNITY_GUIDELINES.*`, Learn copy and replace the words.
**Videos/comments (when built):** same `nzHTML()`; ids `comment:ID` / `video:ID`; same request shape.

## 10. Acceptance tests
**Accessibility**
- N1 axe: 0 violations on Showcase grid, item dialog, signed-out dialog, light and dark, 320/390/1280.
- N2 Each nozzle button has role button, a name like `Nozzle it, N nozzles`, and `aria-pressed`. No title-only labels. Visible text ("12", "Nozzle it") is contained in the name (WCAG 2.5.3).
- N3 Keyboard: Tab reaches the button after the card's title link; Space and Enter both toggle; focus stays on the button; no focus loss after the request.
- N4 Live text is spoken once per action (record with VoiceOver on iPhone and one desktop reader). Failure uses the alert.
- N5 OS reduced motion: no animation; pressed look still right.
- N6 Touch: every button ≥44×44; no overlapping targets; the whole card still opens from the title link.
- N7 Contrast: the §6 rows re-measured on the real page, both themes; pressed is distinguishable in forced-colors mode.
- N8 Class-off and signed-out states are understandable without colour (visible reason text, dashed border).
**Behaviour**
- B1 Press → count +1 and `aria-pressed=true`; press again → back. Rapid double-tap leaves one request in flight and a consistent end state.
- B2 The grid card and the dialog button for the same project stay in sync.
- B3 Failure: rolls back, alert announced, nothing saved.
- B4 EXAMPLE items: no button, no number. Real items with `likes:null`: button, no number. Count 0: no number.
- B5 Signed-out press opens the account dialog; Not now closes it and returns focus to the button.
- B6 Own project shows static text, not a button. No downvote or "dislike" anywhere (search DOM and strings).
- B7 Searching the app for "♥", "like", "heart" finds nothing user-facing (except words users wrote themselves).
- B8 Request shape unchanged except `{"liked": bool}`; an old client sending `{}` still toggles.
