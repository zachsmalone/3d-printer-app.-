# Trust & Safety polish pass (first-time user on an iPhone-sized screen)

Author: Kenji Watanabe (Trust, Safety & Legal). Date: 2026-10-04 evening (CT). Not a lawyer; nothing here says ZEIM is or is not compliant with any law.

## 1. Method, and what is untested

**Code under test.** The committed head of the Engineering worktree, branch `haruto/work`, commit `59b205d`, extracted with `git archive` into `/tmp/zeim-polish/code`. Uncommitted edits in `/workspace/photo3d-wt` (about 10 modified files at the time) were **not** tested. `main` (`375f9c4`) differs only by iphone-test notes.
**Instances.** My own server on `127.0.0.1:8796`, `PHOTO3D_MODE=shared`, `PHOTO3D_PUBLIC_BASE_URL=http://127.0.0.1:8796`, `PHOTO3D_OUT`/`PHOTO3D_DATA` under `/tmp/zeim-polish/`, admin token set. A second throw-away local-mode instance (port 8797) was used for one check. Both stopped at the end. **Port 8765 was never touched or probed.** No app code, tests or word lists were edited.
**Browser.** Google Chrome headless through Playwright, 390x844 at 2x, touch emulation, an iPhone Safari user-agent string. **This is emulation only, not real Safari and not a real iPhone.** Native `prompt()` boxes, the real camera, HEIC from a real phone, the share sheet, keyboard behaviour and iOS date pickers are untested. Scripts: `/workspace/scratch/polish/` (`s*.py` UI walks, `reg*.py`/`api*.py` request checks). Screenshots: `reports/mockups/safety-polish/` (listed per finding).
**How the sessions were made.** The three audiences were real sign-ups through the UI: an adult (DOB 1985), a teen (DOB 2011) and a class student (joined a class I created as the adult). The under-13 attempt used DOB 2018. Per-visitor addresses were simulated with an `X-Forwarded-For` header from loopback, which uvicorn trusts here; that is a test trick, not how a school network looks.
**Mild placeholders only.** The language filter was exercised with a single mild word from the English list ("butt") and structured fake contact details (`kid@example.com`, `555-123-4567`). No slurs or explicit text were used, printed or stored.
**Load.** The box was heavily loaded by other agents (load average 12 to 56). Chrome tabs crashed twice on the 280,000-triangle 3D viewer and several UI test timings are unreliable. I did not open built models in the viewer for the publish dialog or Edit text step, so those two screens are **code-read plus request evidence, not screenshots**.
**Not covered.** Real teachers or kids, a filtered school network, real iOS camera/HEIC, Safari-specific layout, VoiceOver, push or email (none exist), the live tunnel build, anything after commit `59b205d`, and the Edit text step in the UI (API only).

## 2. Top 5 roughest trust/safety edges (ranked)

Ranking = how likely a child, parent or teacher is to hit it times how much it hurts trust. "Known" means it was already in an earlier report; I confirmed it is still true at `59b205d`.

### Edge 1. Every safety message is a vanishing toast hidden behind the dialog, and the form stays unchanged (High)
- **What a child sees.** Under-13 sign-up: a dim red toast at the very top, partly behind the dark scrim; the dialog still shows the name and birth date and an active "Create account" button (`03_under13_refusal.png`). Wrong class password and a blocked nickname: two toasts stack and fade after 4 to 8 seconds, while the join dialog looks untouched (`16_student_join_wrongpw.png`, `17_student_join_blocked_nick.png`).
- **Why it matters.** `decisions.md` says refusals appear inline next to the field and the box keeps what was typed. That is **not** built for sign-up, join, Share-to-Showcase or the Edit text step: code read, `community.js` publish/join and `edit.js` `act()` all call `toast(e.message,"err")`. An under-13 child gets no calm explanation in the place they are looking, may retry, and a teacher cannot tell what a student saw.
- **Wording gap.** Filter responses for contact details say "Chat doesn't allow sharing contact details or links. Please keep personal info private." (seen on every endpoint). The recorded line is "Please don't put names, phone numbers, emails or links here." The language line matches.
- **Owner.** Engineering (one shared inline-message helper) with Design (placement, tone).
- **Fix.** One `role="alert"` paragraph under the field in each dialog; the under-13 refusal replaces the form with a short calm panel and a "Join a class" button; use the recorded personal-info wording; keep the typed text. Test: no `toast` call remains on a refusal path.

### Edge 2. A family cannot see, export or delete what ZEIM keeps (High for any school pilot; known S-07)
- **Evidence.** "My data" opens "My personalization data" and only covers For You interests and searches; its note reads "Stored only on this server (data/prefs.json), keyed by your browser session" (`08_teen_mydata.png`). `GET /api/me/export` is 404; there is no account-delete route; `DELETE /api/me` is 405. The student "delete my stuff" and class-delete purge exist on the server (commit `8fc9f0a`) but **no button reaches them** (no UI string for it in `static/`). Personalization is **on by default, including for teens**.
- **Why it matters.** A parent asks "what do you have on my child, and can you delete it?" and ZEIM has no answer a person can use. Counsel needs this for COPPA/FERPA-style deletion and for any school data agreement.
- **Owner.** Engineering (endpoints, UI), Legal (retention, what counts as deletion, backups), Education (teacher wording).
- **Fix.** The "What ZEIM knows about you" page in section 4. As a smaller first step: a "Delete my stuff" button for class students and a "Delete everything I made" for accounts, with plain consequences; turn personalization **off by default for under-18** and class students.

### Edge 3. A photo's file name becomes the project title and is pre-filled into the Share dialog (Medium-High, new)
- **Evidence.** Uploading `IMG_2231_MiaJohnson.jpg` as a class student gave `title='IMG_2231_MiaJohnson'` (Studio and Edit both; request in `reg3.py`). The Share dialog pre-fills `#pub_title` from the current build's title (`community.js`: `$("#pub_title").value = S.current.title`). The export files do **not** carry it (checked, STL/OBJ/3MF clean), but the title shows in Recent builds, the teacher's project list, and a public Showcase page if someone presses Publish without reading.
- **Why it matters.** Camera and school-assignment file names often hold a child's name or school. The filter cannot catch names: `my name is Mia Johnson` and `I go to Lincoln Elementary` pass every title/description field (200 on Edit title). Only structured contact details are blocked. The only protection is wording, and the title fields have no help text.
- **Owner.** Engineering (default title), Design (help text).
- **Fix.** Never derive a title from a file name; default to "My photo" or "My relief". Under every title/description/tag box: "Don't use real names, school names, phone numbers or addresses." In the Share dialog show a read-only preview and, for accounts under 18 and class students, no public option (already enforced on the server).

### Edge 4. Reporting and the rules are hard to reach and hard to use on a phone (High for launch, Medium today because no public items exist yet)
- **Evidence.** Report uses two native `prompt()` boxes: the first asks the person to type a code word, "Report reason: minor_safety, not_family_friendly, copyright, harassment, personal_info, other" (captured from the running page, `s5.py`). That is already CR-6 from Education and is not built. Report and Follow are also offered on **EXAMPLE** cards (`09_example_item_dialog.png`).
- **Community Guidelines page.** It has **no viewport meta tag**, so an iPhone lays it out about 980 px wide with tiny text (`11_guidelines_top.png`; measured scroll width 980 at a 390 px screen). The seven rules are run into one paragraph. A developer note ("see ROADMAP.md") is shown to users. It says "repeat or severe cases lose access", while the decision is "no strikes or bans". The only link to it is inside the Share dialog; there is **no** privacy notice, terms, or contact link anywhere in the app.
- **Owner.** Design + Engineering (dialog, page), Education (kid wording), Legal (what the page may promise).
- **Fix.** Replace `prompt()` with the radio-button dialog from CR-6 ("Something about a person or a child is not safe", "Not family-friendly", "Mean or unkind", "Shares private info", "Copyright", "Something else"), hide Report/Follow on EXAMPLE cards, add a "Rules and help" link in the footer of every screen, give the guidelines page a viewport tag, a list, and a kid version at grade 4 to 6.

### Edge 5. Shared school addresses punish the wrong people (Medium-High for a classroom pilot; partly known)
- **Evidence.** After one under-13 refusal, the very next sign-up from the same address, a teen and an adult, got the refusal message ("We can't create an account for you right now...") for the lock period (my own run: `Teen Alex` was refused until I changed the simulated address). Code and README: the address lock lasts 30 minutes by default. Separately, after 5 wrong class passwords the **correct** password from that address is also refused (429) for 5 minutes, doubling up to 24 hours (S-05 caveat, still true: `reg.py`). A teacher has an Unlock button, but it is only shown once failures are counted.
- **Why it matters.** A school usually sits behind one public IP. One child's refusal or one prank locks out other students and adults at that school, and the refusal text tells a teen to "ask your teacher for a class code", which is confusing for a 15-year-old.
- **Owner.** Engineering (limiter design), Legal (the neutral age screen itself needs counsel), Education (teacher unlock wording).
- **Fix.** Make the age lock cookie-first and apply the address lock only after several refusals; let the correct password through while still counting it; show the teacher's Unlock button whenever a lock is active, with a plain note ("Students on your school network may be blocked for 5 minutes").

### Also noticed (not top 5)
- **Teen profile screen contradicts itself** (`04_teen_account.png`): "Allow following (I can follow others and others can follow me)" is shown to teens although nobody can follow a teen; the text says "Everything starts Private; every build and project can be changed individually" right under "accounts under 18 keep everything Private"; "My followers" and a "Public page: /u/..." link are shown (link colour is browser-default blue `rgb(0,0,238)` on dark, about 1.8:1 contrast, below WCAG 4.5:1). The same blue link appears on EXAMPLE creators.
- **Offers that the server then refuses.** Every audience, including teens and class students, sees "Followers" and "Public" in the visibility menu and a "Share to Showcase" button on a finished build (`20_*_built.png`, option lists captured). The server correctly refuses (403/401) but the child meets an error for choosing something that was on offer. The options should be disabled with a reason, the way the account privacy menu already does.
- **Teacher dialog over-claims**: "no accounts, no personal data". A nickname plus a child's work is personal data under most school-privacy reading. Say "no emails or real names are asked for". The HQ-1 line "ZEIM can't check who is a teacher. Please only make a class for students you teach." is **not built yet** (NOT FOUND).
- **Showcase empty-search state overlaps the My data button and tabs** (`10_showcase_empty_search.png`): a layout defect Design should see.
- **Over-blocking left.** "Dick Whittington cat" is refused (a real name and story). Nigeria, rabbit chair, Scunthorpe, material, Cockburn, Hancock, Essex and 6 more benign titles passed. Names cannot be solved by a word list; flag for the report path.
- **Chunked JSON body** is parsed before the field cap rejects it (400 not 413, 0.04 s for 10 MB): low risk, no freeze.
- **Data files are mode 644** (`users.json`, `prefs.json`, `classrooms.json`): still open from re-check 1.
- **Spark Lab text says "no user uploads"** while students can submit builds to their teacher. Small wording fix.

## 3. Regression results (PASS / FAIL / NOT-FOUND, only what I ran)

Commit `59b205d`, shared mode on 8796 unless noted. "Request" scripts are in `/workspace/scratch/polish/`.

| ID | Check | Result | Evidence |
|---|---|---|---|
| S-01 | Anonymous `PUT /api/settings`, shared mode | **PASS** | 403; wrong admin token 403; anonymous GET hides printer URLs |
| S-01 | Admin-token guessing throttled | **PASS** (was open) | 10 x 403 then 429 |
| S-01 | Anonymous OAuth connect | **PASS** | 403 |
| S-01 | Base URL validation (`javascript:`, credentials) | **NOT TESTED** | the URL is locked by `PHOTO3D_PUBLIC_BASE_URL` here, PUT returns 200 but the value did not change; covered by the repo's tests |
| S-01 | Local mode (`run.sh` style, port 8797) | **PARTIAL** | anonymous loopback PUT = 200 (the owner's own machine); a LAN `Host` header or a remote `X-Forwarded-For` = 403. Not tested: local mode behind a tunnel or reverse proxy that rewrites `Host` |
| S-01 | QR code follows a forged Host | **PASS** | QR identical with `Host: evil.example` (public base URL set) |
| S-02 | 30,000-char name, 400 KB body | **PASS** | 400 / 413 in 0.00 s |
| S-02 | Chunked 10 MB body | **PARTIAL** | rejected with 400 (not 413) after parsing, 0.04 s |
| S-03 | Teen Private only (build, Showcase, profile) | **PASS** | 403 on public/followers for all four paths |
| S-03 | Adult follows teen / anonymous opens teen profile | **PASS** | 404 / 404 |
| S-04 | Under-13 refused, same session retry refused, same text, no "13" in text | **PASS** | 403 / 403 |
| S-04 | Cookie-less retry from the same address | **PASS** (was open) | 403 (address lock), but see Edge 5 |
| S-04 | Retry from another address | INFO | 200; self-declared DOB can never be proven, counsel question |
| S-05 | Weak class passwords rejected | **PASS** | `''`, `abc`, `1234567`, `password` all refused |
| S-05 | Wrong guesses with fresh cookies | **PASS** | 429 at attempt 6, held through 12 |
| S-05 | Correct password from locked address | **KNOWN GAP** | 429 (Edge 5) |
| S-06 | OAuth callback error escaped | **PASS** | script tag returned as `&lt;script&gt;` |
| Links | Signed `/f/` link scope, expiry, log | **PASS** | token works for its own `model.3mf` only (other file 404), about 10 min left on a fresh link, token absent from `server.log`, 4 lines show `[redacted]` |
| Seeds | EXAMPLE items null counts | **PASS** | 9 items, `likes`/`downloads` null; anonymous like still returns 200 and adult follow of an example creator 200 (harmless, but see Edge 4) |
| Send | New class: Send switch default off | **PASS** | `send_enabled:false`; switch ON without confirm = 400 |
| Send | Class student: print links / printer send | **PASS** | 403 "Sending to other apps isn't available..." and 403 "...done by your teacher" |
| Send | Teen: print links / printer send | **PASS** | 403 / 403 |
| Send | Teen and class-student Send sheet by UI | **PASS** | teen: Download only; student: Download + "Send to my teacher" + "turned off for this class" (`21_*_sendsheet.png`) |
| Send | Adult Send sheet wording | **PASS** | "ZEIM sends nothing to other apps...", "copies you already sent stay where they are" |
| Send | Class student can still use built-in slice (stays on the server) | INFO | `POST /api/slice` 200; not a send, noted for the record |
| Priv | Class student cannot make a build public/followers or publish | **PASS** | 403 / 403 / 401 (but the UI still offers it, Edge "also noticed") |
| Export | No photo, EXIF, GPS or upload file name in STL/OBJ/3MF (adult and class student) | **PASS** | 6 files scanned for a planted EXIF marker, camera make, "GPS"/"Exif" and the file name |
| Export | Edit-project 3MF object name generic | **PASS** | names found: Title, Application, model only; download name `photo3d_<id>.3mf` |
| Export | Downloads sent `Cache-Control: no-store` | **PASS** | header seen |
| EXIF | Stored uploads carry no EXIF/GPS/ICC/XMP | **PASS** | marker absent under `PHOTO3D_OUT` and `PHOTO3D_DATA`; 44 stored images re-read, 0 had metadata |
| HEIC | `IMG_0001.HEIC` (5 KB sample) in Studio and Edit | **PASS** | 200 both. Reader `pillow-heif 1.8.0` is in the worktree venv; whether `requirements.txt` pins it was not checked |
| HEIC | Corrupt `fake_real.heic` | **PASS** | friendly "We couldn't open that photo. Try a JPG or PNG." (400 Studio, 415 Edit) |
| Title | Upload file name used as title | **FAIL (new)** | Edge 3 |
| Tests | `pytest tests/test_*.py`, temp dirs, one run | **351 passed, 6 failed** in the full run (478 s, loaded box); after re-runs: **1 deterministic failure** (stale text test), **1 inconclusive** (timeout), 4 passed on re-run | see below |
| Headers | Security headers present | **PASS** | CSP, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options`, `Permissions-Policy`; `/docs` and `/openapi.json` return 404. Cookie has no `Secure` flag on http (not tested over https) |
| Fields | Language + contact filter, mild word and structured contact details | **PASS** | display name, build title, edit title, Edit text step, class name, class nickname, Showcase title/description/tag: all refused (422) with nothing stored; link handle: phone refused, bare handle accepted (it is a handle field) |

**Pytest detail.** Failures at `59b205d`: (1) `test_b1_edit_text.py::test_text_added_to_an_existing_project_and_from_a_studio_build_is_checked_too` fails deterministically (re-run alone): the test expects `Hello` to be accepted on a Studio-photo build, but the newer geometry guard answers 422 "The raised text would float free of the model...". That is a stale test or a default-placement question for Engineering, **not a filter regression** (blocked text is still refused). (2) Five `test_b1_ui.py` browser tests failed in the full run. I re-ran that file alone; see the result line below. Several of these time out on this overloaded box, so I cannot say which failures are real from this run alone.
UI-file re-run alone (quieter box, 370 s): **9 passed, 1 failed**. The four tests that failed in the full run passed on re-run, so those were load timeouts. The remaining failure, `test_ios2_touch_targets_16px_inputs_safe_area_and_viewer_does_not_trap_scroll`, asserted `-15 == 0`: the child browser script was killed by its timeout (SIGTERM), so it is **inconclusive**, not proof of a layout regression. Engineering should re-run it on a quiet machine.

## 4. Wow proposal: "What ZEIM knows about you" (one-screen page, live view, one-tap export and delete)

**The idea.** A page that opens from one button in the account area and from every sign-up dialog. It shows, live and in plain words, everything ZEIM holds for this person on this device: their name or nickname, their class, how many builds and photos, who can see each thing (nobody, by default), and what is **not** collected ("no email, no phone, no location, no ads"). Two big buttons: **Download my stuff** and **Delete my stuff**. A teacher version shows the same for the class with "Delete the whole class". It also closes the S-07 gap and fixes Edge 2.

**Mock wording, kid version (grade 4 to 6):**
> **What ZEIM knows about you**
> Here is everything ZEIM keeps about you. It is short!
> - Your nickname: **Zippy**
> - Your class: **Room 5B**
> - Your builds: **3**. Only you and your teacher can see them.
> - Photos you picked: **3**. We clean the secret info (like where a photo was taken) off them.
> - We do **not** keep your email, phone number, or where you are.
>
> [ Download my stuff ]   [ Delete my stuff ]
> Deleting removes your builds and photos from ZEIM. If you already saved a file to your device or sent it somewhere, that copy stays there.
> Questions? Ask your teacher or a grown-up.

**Adult / parent version (plain):**
> **Your data in ZEIM**
> ZEIM keeps your display name, date of birth (used only to set safe defaults), your builds and the photos you chose, your privacy settings, and a simple For You history. It does not store your email or phone number. Photos are stripped of location and camera details when they arrive.
> [ Download everything (zip) ]  [ Delete my account and everything I made ]
> Deletion is final. Files you saved or sent elsewhere are not removed. For a child's account or a class, the grown-up or teacher can ask for deletion here too.
> Questions or a request on someone else's behalf: [contact address, to be decided].

**Why it matters.** It answers the first question any parent or teacher asks, turns a legal promise into something a person can check and press, gives kids a calm, honest picture of what the app does, and makes the privacy default visible instead of buried. It also makes every other safety claim in the app easier to keep honest, because the page is generated from the real stored data rather than from a promise.

**Effort (my estimate, Engineering to confirm).**
- Server: one `GET /api/me/everything` that lists what exists for this session, an export zip of the person's own builds and settings, and a delete that runs the existing purge used for class students and also removes the account, Showcase copies and prefs. About 3 to 5 days including tests.
- UI: one dialog, phone-first, kid and adult wording, confirm step for delete. About 2 to 3 days.
- Teacher variant and class delete summary: 2 days. Total roughly 1.5 to 2 weeks for one engineer.

**Risks.**
- Deleting a Showcase item must really remove it for other people and from thumbnails and caches.
- Backups and logs keep session IDs; "deleted" must say what is and is not covered.
- The export contains a child's photos; it must only go to the same signed-in session, never by email.
- With no real login yet, "you" is a browser cookie. A cleared cookie means a person cannot reach their own data, so a parent request path is needed.
- Teens: a parent or teacher cannot be given more access than the teen has without a decision.
- Over-promising. The page must say what it cannot undo.

**Needs legal review.** Whether the page and the delete flow meet COPPA/FERPA-style deletion and access duties and any state student-privacy law; retention and backup wording; who may request deletion for a child; whether "we strip location from photos" is safe to state; the age screen text; and the contact address. These are questions for counsel, not conclusions.

*(Alternatives I considered and ranked below this: a one-screen class safety summary for teachers, which is valuable but depends on this page's data; a parent explainer page, which is mostly copy and could ship first as a stopgap; a "check before you share" preview of title, photo and visibility, which also addresses Edge 3 and could be a quick win.)*

## 5. Hansei (what I would change)

- **Late in my own process:** I guessed button ids from an older emulation script and lost time; I should have read `photo.js` first. Two Chrome crashes on the 280 k-triangle viewer cost the publish-dialog and Edit-text screenshots; those two screens are code-read plus request evidence only, and I say so above.
- **Test setup distorted one finding.** The address lock made my own teen sign-up fail until I simulated separate addresses. I turned that into Edge 5 on purpose, but a real school test could look different (proxy headers, one address or many).
- **I did not run** the live tunnel build, did not test real HEIC from a phone (the sample is 5 KB), did not check that `pillow-heif` is pinned in `requirements.txt`, and did not test the Edit text step in the UI. NOT TESTED beats guessing.
- **The filter cannot protect names or schools.** I keep saying so, but the product copy near each text box should say so too. That is Edge 3.
- **Ranking is mine** and favours what a child or teacher meets first. A lawyer may rank Edge 2 first, and Engineering may disagree on effort; please challenge it.
- **What I got wrong earlier:** I called signed-link and EXIF fixes "pass" from tests; this pass re-ran them against a fresh instance and they still hold. The "no personal data" teacher text was in the code when I reviewed the teacher dialog and I did not catch the over-claim until now.
