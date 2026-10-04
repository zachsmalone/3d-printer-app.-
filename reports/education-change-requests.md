# ZEIM — Change requests for Engineering (from Education & Community)

From: Aiko Nakamura (Head of Education & Community) · To: Haruto Tanaka (Engineering) · Date: 2026-10-04 (CT)
Status: DRAFT for review. Source: read-only review of `/workspace/photo3d` (no app code was edited by Education).
Full rationale, evidence and context: `reports/education.md`. Draft lesson content in the app's `LESSONS` schema: `reports/education-lessons-draft.json`.

How to read: **P0** = fix before any pilot with a real class on a shared/hosted server. **P1** = before a wider school pilot. **P2** = next. File/line references are from the code as of today and may move; each item says what to look for. Where I am unsure of the best implementation I say so — Engineering knows the code better; the *acceptance criteria* are what matter to us. Items that need a product/legal decision are marked **[decision]**.

---

## P0 — before any real-class pilot

### CR-1. Lock down `/api/settings` and network-printer sending on shared servers
- **Why:** `GET/PUT /api/settings` (`app/api/settings.py`) take no `Actor`; any visitor, including a class student, can add/change printers and `public_base_url`. `public_base_url` is used to build the teacher's join-QR (`app/api/learn.py::room_qr`) and slicer links (`app/api/printing.py::base_url`), so changing it could point a class QR at another site. `POST /api/send/{bid}` (`printing.py`) then uses any saved printer, with `start=true` available.
- **What:** Add a deployment setting (e.g. `PHOTO3D_MODE=shared|local`, default `shared` unless explicitly local). In `shared` mode, `PUT /api/settings`, printer CRUD, and `POST /api/send/*` require the admin token or an adult teacher/owner account; class-student sessions (any `sid` in a classroom's `students`) always get 403 on these. `GET /api/settings` must not expose printer URLs to students.
- **Accept:** (a) test: a session that joined a class gets 403 on `PUT /api/settings` and `POST /api/send/{id}`; (b) a brand-new anonymous session in `shared` mode gets 403 on `PUT /api/settings`; (c) `local` mode behaves as today; (d) the join QR always encodes the configured base URL, which a non-admin cannot change.

### CR-2. Student photo hygiene: strip metadata, safe extension, purge on leave/delete
- **Why:** `app/api/builds.py` (~line 208-210) writes the uploaded bytes unchanged to `outputs/<id>/source.<ext>` (EXIF such as GPS/camera info stays; extension comes from the client filename). `classrooms.remove_student()` and `classrooms.delete()` erase class projects and progress but **not** the students' own builds/source photos in `outputs/`, although the README says "all class data erased".
- **What:** (1) On photo upload, re-encode the image (e.g. Pillow, orientation applied, EXIF/ICC/GPS dropped) and save as PNG/JPEG chosen from the *sniffed* format, not the filename. Do this for the Edit-workspace photo path in `app/services/editproj.py` too. (2) On `remove_student` and `delete`, also delete every build/edit project whose `owner_sid` is that student (use `history.store.delete`). (3) Add a `delete_my_data` endpoint for class students (builds + progress + class projects) and a "Delete my stuff" button on the student banner. **[decision]** optional auto-expiry of class-student builds (e.g. 30 days after last activity) — Education suggests yes.
- **Accept:** test uploads a JPEG with GPS EXIF → stored `source.*` has no EXIF; filename `x.exe.png` or a JPEG named `.png` is stored with the correct extension; after `DELETE /api/classrooms/{code}` and `DELETE …/students/{sid}`, no `outputs/<id>` with that student's `owner_sid` remains; `tests/` pass.

### CR-3. Showcase is off by default for class-student sessions (teacher can enable)
- **Why:** Class students are anonymous cookie sessions, but nothing stops them browsing the public Showcase, liking, downloading, or reading public descriptions written by strangers (`app/api/community.py::showcase*`). The README says Spark Lab is classroom-safe "by construction", which is true for Spark Lab but not for the rest of the app the student is sitting in.
- **What:** Add `showcase_enabled` (default `false`) to each classroom (`app/community/classrooms.py`; teacher toggle in `/api/classrooms/{code}/settings` and in Teacher tools). For a session that is a member of a class with it disabled: `GET /api/showcase*`, `/p/*`, `/u/*`, like, download, report-from-Showcase return 404 (or a friendly "Your teacher has turned this off"), and the Showcase nav item is hidden/disabled in `static/community.js`. When enabled, students get view-only (no likes) unless the teacher also enables likes.
- **Accept:** a student session in a default class gets 404/friendly-off for all Showcase routes and cannot like; after the teacher enables it, listing works; likes need a second toggle; test covers both states and that a non-class visitor is unaffected.

### CR-4. Seat reset so a student who loses their browser/cookie can come back
- **Why:** Student identity is the `p3d_sid` cookie. `classrooms.join()` rejects a nickname already used in the class, so a student on a shared school laptop who clears cookies (or is on a different Chromebook next day) is locked out of their own nickname and loses progress/projects. Shared devices also mean two students can end up as one `sid`.
- **What:** Teacher button **"Reset seat"** per student (`POST /api/classrooms/{code}/students/{sid_prefix}/reset`): detaches the old `sid` from the nickname but keeps the nickname's progress/projects, and allows exactly one new join with that nickname (code + password + nickname) within e.g. 24 h. Also add a visible "I'm on a shared computer" join option that does not persist the cookie beyond the browser session (`max_age` unset for that case). **[decision]** longer term: teacher-pasted roster of nicknames with per-seat login codes (see research: Tinkercad "Seats").
- **Accept:** test: student A joins as "Fox", cookie dropped, new session cannot join as "Fox" (409 as today) until teacher resets the seat, then can, inheriting progress; the old session loses access; another student cannot take the seat.

### CR-5. Photo-permission acknowledgement before upload and publish
- **Why:** The only consent prompt is `pub_ok` ("follows the Community Guidelines") in `static/index.html` ~line 272; the Guidelines mention photos of other people (item 5) but nothing is asked at the moment a photo is uploaded, and the lithophane lesson currently suggests "a pet or a face".
- **What:** (1) Studio and Edit photo drop zones show a one-line notice and required checkbox: "This is my photo/drawing or I have permission from everyone in it. No addresses, school names or license plates." (2) For class-student sessions the checkbox cannot be pre-ticked and the choice is stored in `meta.json` (`photo_ack: true`). (3) Publish dialog text names photo permission explicitly. (4) Optional (stretch): offer a built-in school-safe image pack (`static/imagepack/`, originals or public-domain with attribution file) behind a "Use a class image" button next to "Try a sample photo".
- **Accept:** cannot Build from an uploaded photo without ticking; `meta.json` records `photo_ack`; text appears in publish dialog; built-in sample/image-pack path does not require the checkbox.

---

## P1 — before a wider school pilot

### CR-6. Replace `prompt()` / `confirm()` with accessible dialogs; give students a way to report
- **Where:** `static/community.js` uses `prompt()` for the Showcase report (reason typed as a code word such as `minor_safety`), details, teacher feedback, and "Which build? Type a number" (`submitToClass`), plus one `confirm()` for deleting a class.
- **What:** Use `<dialog>` forms with labelled radio buttons for reasons in plain language ("Something about a person or a child is not safe" → `minor_safety`, "Not family-friendly", "Mean or unkind", "Shares private info", "Copyright", "Something else"), a build picker with thumbnails for submit, a textarea for feedback with the 500-character counter. Add a **Report** button for class students on teacher feedback and on classmates' projects (`POST /api/classrooms/{code}/projects/{pid}/report`, goes to the teacher first, then to the moderation queue). Dialogs must trap focus, close on Esc, return focus to the opener.
- **Accept:** no `prompt(`/`confirm(` remain in `community.js`/`edit.js`/`app.js`; keyboard-only user can file a report; screen-reader labels present (checked with axe, see CR-12); existing tests still pass and a new test covers the class-project report route.

### CR-7. Lesson panel re-renders the whole page on every checkbox and scrolls
- **Where:** `static/community.js::openLesson` — ticking a step calls `openLesson(id)` which rebuilds the panel and calls `box.scrollIntoView(...)` each time; a correct quiz answer does the same after 700 ms.
- **What:** Update only the changed step/progress bar, preserve scroll and keyboard focus, announce "Step 3 of 5 done" via an `aria-live="polite"` region; scroll into view only when the lesson is first opened.
- **Accept:** ticking steps by keyboard keeps focus on the same checkbox and does not move the page; a screen reader announces the progress change.

### CR-8. Lesson content fixes now, schema extension next
- **Now (copy only, `app/community/education.py`):**
  1. `lithophanes` step 2: "a pet or a face" → remove "face"; use the photo guidance in `education.md` §3.1 (own photo/drawing/class image pack; no photo of another person without permission).
  2. `lithophanes` `teacher_notes`: "A class set of 2.4-4 mm lithophanes prints in about 1-2 hours each" matches neither the Standard preset (0.8-3.2 mm, `app/core/autotune.py`) nor a measured time. Replace with "test-print one on your printer first and write the real time on the board", and say the printer is operated by the teacher.
  3. Add safety steps to `first-print`: printer is operated by an adult; no hands near moving/hot parts; do not open an enclosure mid-print; wait for the print bed to cool before removal; students do not use scrapers/blades; printers away from desks and ventilated (see research, WA DOH). Use "ask your grown-up" wording consistently.
  4. `first-print` says "Open the Studio… pick Relief" while the `try` button opens a thin relief — fine, but state the printer is teacher-run.
- **Next (schema):** add optional fields to each lesson: `grade_band`, `audience` (`teacher_led` | `independent`), `prep`, `materials`, `safety`, `assessment`, `extension`, `alignment_hints`; render them on `/l/<id>` and in the lesson panel (teacher-only parts hidden from student sessions); allow `try.view = "edit"` so Spark Lab can open the Edit workspace (three draft lessons need it); allow multi-question quizzes with a short explanation per answer.
- **Drafts to paste in (after Education review with a teacher):** `reports/education-lessons-draft.json` (same keys as `LESSONS`; `answer` is the 0-based option index).
- **Accept:** lesson text matches the drafts; `/l/<id>` shows materials/safety for new fields; no lesson mentions faces as a recommended subject; quiz data validated by a test (answer index in range).

### CR-9. `noindex` for user-generated pages
- **Where:** `app/api/learn.py::_page` (used by `/p/<id>` and `/u/<id>`) has no robots meta or header.
- **What:** Add `<meta name="robots" content="noindex,nofollow">` and `X-Robots-Tag: noindex` for `/p/*` and `/u/*` (keep `/l/*` lesson pages indexable). **[decision]** later, allow public adult creators to opt in to indexing.
- **Accept:** `curl -I /p/<id>` shows `X-Robots-Tag: noindex`; `/l/<id>` does not.

### CR-10. Likes / Trending / teen publishing: safer defaults **[decision]**
- **Observed:** likes are one-per-cookie-session and need no account (`catalog.set_like`), counts are shown on every public card; Trending ranks by likes+downloads (documented, `trending_score`); example seed items show invented counts (e.g. 1,500 downloads); a teen (13-17) may publish *Public* per project (`privacy.check_level` only blocks the *default*).
- **What (each is a config flag in `app/config.py` so we can change our minds):**
  1. `LIKES_REQUIRE_ACCOUNT=true` and a per-session/IP rate limit (e.g. 30 likes/hour) on `/like`; same limit on `/report`.
  2. `SHOW_COUNTS_FOR_EXAMPLES=false` — example items show no like/download numbers (still labelled EXAMPLE) and sort by recency inside Trending.
  3. `TEEN_PUBLIC_ENABLED=false` for launch: accounts 13-17 can choose Private or Followers only; Trending/Free exclude under-18 creators' items until a human review process exists. (Education recommends flagging this to Yami/legal; the README already lists the teen-public question as "open decision".)
  4. `HIDE_COUNTS_FOR_MINORS=true`: do not show like/download counts on items by under-18 creators, and do not show the creator their own numbers as a ranking (they still see "your project was liked").
- **Accept:** tests per flag; defaults are the safe values; README "Likes"/"Trending" sections updated by Engineering to match.

### CR-11. Moderation basics: dedupe, rate-limit, queue visible to a human
- **Where:** `app/community/moderation.py`, `app/api/community.py::mod_queue`.
- **What:** (a) one open report per (reporter, item, reason); (b) rate limit reports per session; (c) keep `minor_safety` auto-hide (good fail-safe) but record who reported and when, and add an audit log line for every hide/restore; (d) a minimal admin page `/admin/moderation` (token-protected) listing open reports oldest first with item preview and Hide/Restore/Dismiss; show "oldest open report age"; (e) for class-scoped reports, teacher sees them first. (f) Do **not** add "auto-hide after N reports" for non-safety reasons (research: this produced false takedowns elsewhere).
- **Accept:** duplicate report returns the existing id; 11th report in a minute is refused; admin page lists/acts on reports; audit entries written; tests.

### CR-12. Accessibility pass with measurable exit criteria
- **Observed (not a full audit):** body text contrast passes (computed `#8b97ad` on `#0e1117` ≈ 6.4:1, `#e6eaf2` ≈ 15.7:1); only one `aria-` attribute in `static/index.html` and none in `community.js`; the 3D viewer is canvas-only; toasts have no live region; many teacher-tool buttons are emoji-only or small (`.btn.small`).
- **What:** run axe-core (or Lighthouse a11y) on Studio, Showcase, Spark Lab, Teacher tools, dialogs; fix critical/serious findings; add `aria-live` for toasts and progress; label icon buttons; ensure every dialog is keyboard-operable; give the viewer a text alternative (model name, size in mm, "triangles", watertight status) and a "reduce motion" respect (`prefers-reduced-motion`) if the viewer auto-rotates; confirm 200% zoom and touch targets ≥ 44 px on class pages. Add the axe run to `tests/ui_smoke.py`.
- **Accept:** zero critical/serious axe violations on the listed pages; keyboard-only walk-through (join class → open lesson → tick steps → quiz → submit build) passes; recorded in `reports/a11y.md`.

---

## P2 — next

### CR-13. Teacher dashboard: needs-help first, print queue with approval, CSV export, due dates
- **Why (research):** teachers describe the workflow around printers (submit/review/approve, queue, deadlines, filament use) as the hard part (see `education.md` §5).
- **What (MVP):** (1) sort students with an unread `need_help` first and show a badge; (2) "Print queue" tab per class listing submitted projects with title, student nickname, model size (mm), estimated print time & filament if the slicer is available, and **Approve / Send back with a comment / Mark printed** — it records status only; no remote printer control for students; (3) CSV export of progress (nickname, lesson, steps, completed); (4) optional due date per assigned lesson (`assigned` becomes `[{id, due}]` — keep backward compatibility).
- **Accept:** teacher can approve/send back; student sees status ("waiting", "approved", "printed", or teacher comment) and the project stays class-private; CSV opens in a spreadsheet; tests.

### CR-14. Quiz and teacher-note separation
- Teacher notes are currently shown to students inside a `<details>` in the lesson panel. Serve `teacher_notes`/`prep`/answers only to the teacher session (or behind a teacher toggle). Add short "why" explanations for wrong answers. Accept: student session API payload has no `teacher_notes`.

### CR-15. Teacher account recovery **[decision]**
- Teachers are cookie-bound accounts without passwords (`identity.py`); clearing browser data loses the account and classes. Smallest step: a one-time **recovery code** shown at account creation (stored hashed) that re-binds a new browser to the account. Proper fix is real auth (already on the ROADMAP). Accept: a new browser can regain the teacher account with the code, and the old session loses teacher rights; code can be regenerated.

---

## Not requested yet (waiting on P0/P1)
Build Plates (groups). The spec is in `reports/education.md` §4. Please do not start until CR-1…CR-5 and CR-11 are done, because groups multiply every one of those risks.
