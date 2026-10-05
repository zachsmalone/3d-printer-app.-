# ZEIM build log (lead engineer)

Branch `haruto/work` (worktree `/workspace/photo3d-wt`). Labels: **tested** = an automated test passes on a scratch/temp-data server (Chrome/WebKit are emulation at 390 px, not a real iPhone). **Untested** = nothing has run it on a real device, printer or with real users. Nothing here claims legal compliance.

## Batch A

### 1. Safety fixes (Kenji's queue + filter follow-ups) - DONE (tested)
Already on the branch from Haruto: `9c91224` (inline refusals that keep typed text; file name never becomes the title or pre-fills Share; one under-13 refusal no longer blocks the address; the correct class password gets in during slow mode; chunked JSON body cap; data files 600 / dirs 700; local-mode Origin check for settings = S-01; Rules/Privacy/Terms pages and footer links), `b3fbd19` (Report is a dialog, no prompt()), `97a63d6` (filter: one normalisation, licence file no longer a word list, stems no longer cross words, obfuscated e-mail / spelled-out phones / handles / addresses).
Added now:
- `f81e352` - filter gaps closed: "my number is 5551234", "snap me" / "dm me" / "add me on <app>", spaced-out e-mail (`n a m e @ g m a i l . c o m`), Cyrillic "u" look-alike; allowed: butt joint, hard, Peter, Anita, nipple fitting, blue tit and similar (see `wordlists/allow_*.txt`); multipart upload cap (413 above 56 MB, 411 with no length); Report dialog links to Rules/Privacy/Terms. Tests `tests/test_b3_filter2.py`.
- `614e8ad` - the `test_b1_ui` camera "timeout" was a stale test, not an app bug: CR-5 (permission box) correctly refuses a camera photo until the box is ticked, so no build appeared. The UI script now asserts the refusal and then ticks the box.
- The stale Edit-text "would float free" test no longer fails (it passed in both baseline runs).
- `ddfe9d3` - the last two native `prompt()` boxes (class "Send a build", teacher feedback) are dialogs with inline errors that keep typed text; Chrome + WebKit test.
Not verified: real iPhone Safari, real school networks, real teachers. The filter is a word list plus patterns: it does not detect grooming phrases, many languages are unlisted, and bare 10-digit numbers pass. `confirm()` is still used for "Delete this class".

### 2. QA-1 / Hollow / Simplify / size cap - DONE (tested, on the branch before this session)
`0c6a454` (QA-1..QA-6: Print/Send open the right model per tab, etc.), `1a19401` (Hollow drops sealed micro-voids and measures the real wall; Simplify stays manifold and says when the target was not met; Cut closes or warns; extreme aspect ratio refused / cell cap; base 0 clamped with a warning). Tests `tests/test_b2_mesh.py`. Ren Ishikawa has not re-tested these on a fresh build.

### 3. Build cleanup and retention - DONE (tested)
`edb6e0e`: 20 builds per person with a Favorite star (oldest un-starred rolls off; all starred = a message, never a silent delete), 7 days for unsaved output, 30 days for saved (Showcase / class) non-favorites, starred never removed by age, cap or low disk; deleting a build or "Delete everything I made" removes its files; cleanup runs at start and hourly, only inside the per-build folder (refuses library, static, code); logs carry counts only. Tests `tests/test_b2_retention.py`. Not verified: behaviour on a full disk in production, backups (retention does not touch backups).

### 4. Unique usernames - DONE (tested)
`8ba3397`: username separate from display name; under-18 always start from a generated nickname; one change per 90 days (`PHOTO3D_USERNAME_CHANGE_DAYS`), capital-letter-only changes free; the name you leave stays reserved (`username_history`); credit is looked up from the account id every time so a rename updates old credits, and community projects show `@username`, not the display name; names pass the same chat filter and rules (3-20 chars, no e-mail/phone-like text, reserved words); email appears in no public response (test). UI: optional username at sign-up, "Change username" and "Suggest names" in Account, locked with a date after a change (Chrome + WebKit). Tests `tests/test_b2_usernames.py`, `tests/ui_username.py`.
Not verified / open: the public profile page still shows the adult's display name; ZEIM has no email field yet (verification waits on a ZEIM sender domain); moderators still see display names in the queue.

### 5. Creality-first export - DONE (tested at 390 px; no real device)
`59b205d` (Print dialog: Creality Cloud app first on phones via an authenticated 3MF download and the phone's share sheet; desktop slicers under "On a computer"), `7a3cc17` (default slicer "Automatic"; unbuilt printer types say Coming soon). Not verified: whether the Creality Cloud app actually receives the file on Zach's iPhone, anything on a real K1.

### Merge
See the end of this file for the merge result and final test counts.
