# Engineering — Batch 1 (Haruto Tanaka)

Status: IN PROGRESS. Plan below was written before any app-code edit; the **Status log** at the end is what is actually done (updated 2026-10-04 ~17:30 CT). Nothing here was run on a real iPhone/iPad. Baseline: `python -m pytest -q tests` = **101 passed** (23 s) on 2026-10-04 16:22 CT.

Scope (per Yami): CR-1..5, CR-11, CR-10 flags, CR-15, then Ops basics. Not in this batch: auth/DB/upload-hardening blockers, CR-12, Build Plates, CR-6..9/13/14.

## Plan (order of commits)
1. **Config flags** (`app/config.py`, env-overridable): `PHOTO3D_MODE` (shared|local), `LIKES_REQUIRE_ACCOUNT`, `SHOW_COUNTS_FOR_EXAMPLES`, `TEEN_PUBLIC_ENABLED`, `HIDE_COUNTS_FOR_MINORS`, rate-limit sizes.
2. **CR-1** gate `/api/settings` PUT, printer CRUD and `/api/send/*` in shared mode (admin token or adult account; class students always 403); GET hides printer URLs from non-privileged; QR + slicer links use the configured base URL (not Host header) in shared mode.
3. **CR-2** re-encode uploads (Pillow, EXIF transpose, drop metadata), extension from sniffed format, same in Edit photo path; purge student builds on remove/delete; `DELETE /api/classrooms/{code}/me/data` ("Delete my stuff") + button.
4. **CR-3** per-class `showcase_enabled` (+ `showcase_likes`), default off; enforce on showcase/p/u/like/download/report routes for class-student sessions; UI hides nav.
5. **CR-4** teacher "Reset seat" + shared-computer join (session cookie).
6. **CR-5** photo-permission checkbox on Studio + Edit photo, `photo_ack` in meta.json (server-enforced), publish dialog text.
7. **CR-10** flags implemented + tests per flag; README Likes/Trending updated.
8. **CR-11** report dedupe, rate limit, audit log, `/admin/moderation` token-protected page, oldest-open-age; class-scoped reports to teacher first (minimal).
9. **CR-15** teacher recovery code (hashed), regenerate, rebind.
10. **Ops basics**: verify git/.gitignore; pin requirements; `.env.example` (merge with Ren's compose vars), root Dockerfile + .dockerignore, `/healthz`, CI, rebuild `/workspace/photo3d.zip` via Python zipfile.
11. README "Known limits", this report (hansei), restart 8765 via `./run.sh` at the end.

## Notes on what I found while reading (to verify, not yet claims)
- `MAX_BUILDS` is already enforced per owner session (`BuildStore.list(owner)`); Ops's note that it is global looks outdated. 
- Ren (DevOps) already added `.gitignore`, `.dockerignore`, `.env.example` (compose-oriented), `reports/deploy/Dockerfile` (proposal), `.github/workflows/ci.yml` (proposal) — I will reuse them rather than duplicate.


---

# Status log (honest, newest last)

Test count: baseline 101 -> **300 passed, 0 failed, 0 xfail** (`pytest -q tests`, 2 min 8 s, includes 3 real-headless-Chrome tests). Browser tests (`tests/test_b1_ui.py`, headless Chrome via playwright) skip themselves when Chrome is absent, so CI (no Chrome) does not run them.

## Done, with tests
| Item | Commit | Tests |
|---|---|---|
| S-01 / CR-1 / B-01 / B-06: `/api/settings`, connect/disconnect, printer send gated (shared mode: admin token; students never); base URL validated; OAuth error escaped | 72a8fbb | `test_b1_cr1_settings.py` |
| S-03 / B-03: teens 13-17 Private only; adults cannot follow teens; all visibility/profile/follow routes; startup migration of existing teen data | b6e8788 | `test_b1_teen_posture.py` |
| S-04 / S-05 / S-02: neutral age gate + session lock, DOB not stored before passing; join guesses limited per class code + IP with backoff, 8-char minimum password; text caps before the language filter, JSON body limit | 7d9fd49 | `test_b1_safety_high.py` |
| Bind to 127.0.0.1 by default (`HOST` opt-in, start-up warning), `app.serve`, Dockerfile/README/.env.example | cbe7f2c | `test_b1_ops.py` |
| HQ browser-test fixes: stale print dialog, slice time/filament, pop-art non-manifold root cause (`fix_checkers` both diagonals), EXAMPLE counts null, Free->Newest, empty states, Search button | 164dc28 | `test_b1_hq.py` |
| Edit text op: cap + language/contact filter on create and replay; generic 3MF object name; phone top bar | 322dd31 | `test_b1_edit_text.py` |
| **IOS-5 upload + camera** (see diagnosis below) | d259d0d | `test_b1_upload.py`, `tests/ui_photo.py` (real headless Chrome) |
| IOS-1: no horizontal scroll at 320/375/390/768 (headless Chrome, Studio/Showcase/Edit/Learn) | d395b2c | `test_b1_ui.py::test_no_horizontal_scroll...` |
| Tunnel gate: `/f/<token>` links scoped to ONE file and 10 min (was 2 h, whole build); tokens redacted in the access log; no slicer links on a shared server until a public base URL is set | 5c681c2 | `test_b1_tunnel.py` |
| SEND-1: server-side Send policy, per-class switch (default OFF), capabilities on `/api/me` (`send`), teacher switch + confirm dialog, audit log line | (this commit) | `test_b1_send_policy.py`, `tests/ui_send.py` |
| SEND-0: hidden `/sharetest` page, labelled UNTESTED, adults only | (this commit) | `test_b1_send_policy.py::test_sharetest_page...` |

## IOS-5 diagnosis: what actually failed (reproduced)
Reproduced with `reports/upload-diagnosis.md` and the files in `/workspace/qa/upload/`, then by running the real endpoints:
1. **HEIC/HEIF (what iPhones send)**: Pillow cannot open it. Studio answered with a raw Python repr as the error; Edit answered 415 on the file extension. Fix: `app/core/imagesafe.py` converts server-side (`pillow-heif==1.8.0`, pinned in requirements/constraints; the manylinux wheel bundles libheif, so the Dockerfile needs no apt package on its glibc base - comment added).
2. **Nothing visibly happened after choosing a photo**: Studio waited for "Build 3D model", which on a 390x844 phone is below the fold (y=882). Fix: Beginner mode builds as soon as a photo is chosen with a "Making your 3D model..." line; Expert mode gets a sticky Build bar above the iOS safe area; both show a thumbnail + "Change photo".
3. **EXIF orientation / GPS**: photos kept their EXIF (rotation ignored in preview, GPS stored). Fix: `exif_transpose`, then re-encode from pixels only (no EXIF/GPS/XMP/ICC); stored format comes from the sniffed content, not the file name. Closes S-08.
4. **Huge photos**: pixel cap 100 MP (friendly "very large" message), long side scaled to 4096.
5. **5-build cap**: PARTIAL. Studio still opens the existing "history full" dialog and now also leaves an inline message next to the buttons. I did not verify or change the Edit drop zone's behaviour with the cap, so Yami's point (3) is not closed for Edit.
6. **Camera**: two big buttons "Take a photo" / "Choose a photo" + a quieter "Use a sample image" (>=44px, keyboard operable). Phones: `<input capture=environment>`. Desktop: `getUserMedia` with live preview, Capture / Retake / Use photo, opened only after the tap, stream stopped after capture. No camera / permission denied / insecure context: calm inline message "ZEIM can't use the camera. You can choose a photo instead." with Choose right there. The Take button is hidden on desktops with no video input. Unreadable file: persistent inline "We couldn't open that photo. Try a JPG or PNG." (no toast). Photo is not stored until Build.

**Verified in a real (headless) Chrome:** phone viewport 390x844 and desktop; fake camera device; denied/missing camera; HEIC upload; bad file; Beginner auto-build; no request before Build. Screenshots in `previews/`. **NOT verified:** real iOS Safari (iOS file picker, HEIC from the actual Photos app, `capture` behaviour, getUserMedia permission sheet). Headless Chrome on the box has no webcam, so the live-camera path ran against Chrome's fake device only.

## SEND-1 behaviour (design-ios-send.md 2.2 + Kenji's edits)
| Audience | download | send to teacher | share | printer | slicer links |
|---|---|---|---|---|---|
| Adult (signed up 18+) | yes | - | yes | yes | yes |
| Teen 13-17 (own account) | yes | - | no | no | no |
| Visitor who has not passed the age gate (shared mode) | yes (treated as teen) | - | no | no | no |
| Class student, switch OFF (default) | yes | yes | no | no | no |
| Class student, switch ON | yes | yes | only if signed in as 13+; **no-account students count as under 13, so never** | no | no |
Decision to confirm (Kenji/Yami): in **local mode** (`./run.sh`, one person's own machine) a visitor with no account is treated as the owner (adult) so Yami can still use Print on localhost; teens and class students are still blocked in local mode. If the 8765 instance is ever exposed through a tunnel it MUST run `PHOTO3D_MODE=shared`, otherwise every anonymous visitor is an "adult" there.
- Switch endpoint: `PUT /api/classrooms/{code}/send {enabled, confirm}` (turning ON requires `confirm:true`; teacher of that class only; others get 404). Audit line `AUDIT class send switch: class=<CODE> enabled=<bool> at=<ISO time>` - no student names (tested).
- Not done from SEND-1: the student-facing "Sending to other apps is turned off for this class" note (there is no Send sheet yet - SEND-2). The page currently just hides the Print button when the server says `links:false`.

## Not done yet (in the order Yami gave)
- IOS-2 (44px targets, 16px inputs, safe areas, viewer vs page scroll): next.
- (Filter fixes: DONE, see the re-check section below.)
- Ren's mesh items (Hollow void shells / real min wall, Simplify & Cut warnings, aspect-ratio output cap): not started. Pop-art manifold fix is done.
- SEND-2..9, K1 profile / Test Connection, teacher onboarding (HQ-1), CR-2 remainder / CR-3 / CR-4 / CR-5 / CR-11 / CR-15: not started or only partly covered by the safety items above; see Plan.
- Server on :8765 restarted at ~17:42 CT with commit 97a63d6 (127.0.0.1:8765 only, `PHOTO3D_MODE=local`).

## Hansei
- I first put everything in one `test_batch1.py`; splitting per item (and a shared `tests/b1.py`) made red/green much clearer and should have been done from the start.
- Several of my fixes were "make the check pass" at first (e.g. an xfail for the obfuscated e-mail case) - honest, but it is a debt on the list above.
- I ran `pkill -f app.serve -n` once while cleaning up a temp server; it can hit someone else's server. Use the specific PID.
- The full suite takes about 2 minutes now and can collide with another agent's test run on fixed mock-printer ports (`test_printer_send` failed once for that reason and passed alone). Worth moving those ports to ephemeral ones.
- The Send policy is easy to get wrong silently, so the capability table lives in ONE function (`guards.send_caps`) used by `/api/me` and by every refusing route.


---

# Kenji's re-check 1 (reports/safety-reverify-1.md) - done 2026-10-04 ~17:40 CT

| # | Finding | Fix | Tests (`tests/test_b1_reverify.py` unless noted) |
|---|---|---|---|
| 1a | S-01 only held in shared mode; `run.sh` = local mode let anonymous callers change settings | In local mode only the **owner on this computer** counts: loopback peer address AND loopback `Host` AND none of the proxy/tunnel headers (`X-Forwarded-*`, `Forwarded`, `X-Real-IP`, `CF-*`, `Via`). A tunnel or LAN visitor is treated like shared mode (admin token needed; anonymous = "teen", Download only). The admin token still works everywhere. | `test_local_mode_still_works_for_the_owner_on_this_computer`, `test_local_mode_refuses_settings_from_tunnel_or_lan[x4]`, `test_local_mode_other_peer_address_is_not_the_owner` |
| 1b | QR followed a forged Host | `settings.trusted_base_url`: configured/saved address, else the request host ONLY if it is a loopback name; otherwise the QR answers 409 "set the public address". The links endpoint no longer echoes the forged host. | `test_qr_does_not_follow_a_forged_host` |
| 1c | S-04 limiter bypassed by cookie-less clients | The refusal also locks the (hashed) network address for `PHOTO3D_AGE_IP_LOCK_MINUTES` (default 30). Trade-off written in README: a shared school address blocks other sign-ups for that long. | `test_age_gate_holds_for_a_client_with_no_cookies_from_the_same_address`, `test_age_ip_lock_expires` |
| 2 | Join lockout refused the correct password (one student could lock out a class) | **Slow mode instead of a lock-out**: after 5 wrong tries (per class + address) only ONE password try is evaluated per 30 s (doubling per further wrong try, max 5 min). The right password is never refused outright: it gets in as soon as the next slot opens and clears the slow mode for the next student. A student already in the class is never slowed. Teacher button **Unlock joining** (`POST /classrooms/{code}/unlock-joins`, logged). | `test_s05_*` in `test_b1_safety_high.py` (5 tests) |
| 3 | Edit text filter evasions | Full filter work below (zero-width, spelled-out e-mail/phone, @handles, addresses). | `tests/test_b1_filter.py` (102 cases), `test_b1_edit_text.py` |
| 4 | Admin-token guessing unthrottled | 10 wrong tokens / 10 min / address -> 429, even for the right token until the window passes. | `test_admin_token_guesses_are_throttled` |
| 5 | Cookies without `Secure`; no security headers | `Secure` when the request came over https (`PHOTO3D_COOKIE_SECURE=auto|true|false`), HttpOnly + SameSite=Lax always (session and age cookies). Headers on every response: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` (camera allowed for ZEIM only), **CSP** (`script-src 'self'` + hashes of our 2 inline scripts, no unsafe-eval, `frame-ancestors 'none'`, `object-src 'none'`), HSTS when https. Style stays `'unsafe-inline'` (the UI builds inline styles). | `test_session_cookie_is_secure_over_https...`, `test_cookie_secure_flag_can_be_forced`, `test_age_cookie_has_flags_too`, `test_security_headers_on_pages_api_and_files`, `test_inline_scripts_are_covered_by_csp_hashes`; the 3 headless-Chrome tests pass UNDER the CSP |
| 6 | Public `/docs` | Off (404) unless `PHOTO3D_API_DOCS=1`. | `test_api_docs_are_not_public` |

**Honest caveat on 2:** a correct password tried within the first 30 s slot is answered "please wait N seconds" (nothing is evaluated), so a student can be asked to wait briefly; that is the price of not letting an attacker test unlimited guesses. Kenji/Yami: if you want a hard guarantee that the correct password is never delayed, the only other option is a per-class secret in the join link/QR, which changes the product. **Not changed:** the limiter and age lock key on the address uvicorn reports; behind a proxy that does not overwrite `X-Forwarded-For` they can still be dodged (needs a test through the real tunnel). Not done from his list of "new things": #3 self-declared adult can use a configured printer (documented in README Known limits), body cap for chunked JSON, file modes 644 / non-atomic JSON writes (Ops), "photo3d" names in exports.

## Language/contact filter (red-team items 1-7) - commit 97a63d6
Red-team harness `reports/filter_redteam.py` re-run on the new code (copy writing to /tmp; masked results saved as `reports/filter-redteam-batch1-before.json` / `-after.json`):

| Area (Kenji's harness) | Before | After |
|---|---|---|
| Benign inputs wrongly blocked | 69 of 305 | **32 of 305** (31 of them are the "policy-debatable" anatomical/slang/history terms and short foreign words; 1 contact false positive: `hello.Org`) |
| PII e-mail missed | 15 of 26 | **0 of 26** |
| PII phone missed | 22 of 33 | 10 of 33 (left: bare 10-digit numbers, other-script/emoji-separated digits, 'my number starts with') |
| PII link missed | 24 of 35 | 4 of 35 (left: `tinyurl com abc`, `example.cc/.to`, youtube channel sentence) |
| PII handle missed | 33 of 40 | 13 of 40 (left: 'snap me', 'dm me', 'text me' - these are solicitation, not handles) |
| PII address missed | 16 of 17 | 12 of 17 (best effort only, as agreed) |
| Evasion transforms (84) | zero-width/Cyrillic/Greek/small-caps/squared/insert-symbol at 0-18 % | **0 regressions; all of those now 91-100 %**; mid-split with a space only 30 % (by design - no cross-word gluing) |
| Minor-safety (grooming phrases) | 95 of 105 missed | unchanged (95 missed) - **not addressed**, needs a decision on a pattern layer |
Must-pass list from Kenji/Zach (all pass, `test_b1_filter.py::test_must_pass`): Niger, Nigeria, Nigerian, white power supply, power supply, `Printed on 2026-10-04`, `0.2 0.4 0.6 0.8 1.0 mm`, 10-digit serial, benchy.me, index.io, main.dev, Fusion360.app, `Meet @ 5pm. at home.`, class/assess/assemble/cockpit/Hancock/nozzle/infill/raft/brim, `rabbit chair`, `mini game`, licence words.
Done: (1) only intended files read; (2) stems matched inside one word only, squeezed only when really stretched; (3) one `normalize()` for lists, language and contact checks; (4) fail closed -> HTTP 503 `filter_unavailable`; (5) PII rules above (phone patterns need separators, so a bare 10-digit number passes - per Zach's serial-number case, which means `5551234567` alone is no longer blocked); (6) profile link handles go through `safety.check`; (7) one error shape (`code`, `message`, `context`, `detail`) for language_blocked / contact_blocked / too_long / filter_unavailable on every route (filter failures that used to be HTTP 400 `{detail}` are now 422; tests updated).
Not done: grooming-phrase layer, new languages, emoji, per-language false-positive tuning (short foreign words, `Peter`, `hard`...), street addresses beyond "12 Oak Street"/PO box.

## Deferred / still open (from the whole queue)
IOS-2 (44px targets, 16px inputs, safe areas, viewer vs scroll), SEND-2..9, K1 profile + Test Connection, Ren's mesh items 2-4 (Hollow shells / min wall, Simplify+Cut warnings, aspect-ratio cap) and the minor ones (base_mm=0, lithophane border), teacher onboarding (HQ-1), CR-2 remainder / CR-3 / CR-4 / CR-5 / CR-11 / CR-15 status check against the original acceptance criteria, Edit drop zone with the 5-build cap.

## Hansei (additions)
- The two re-check "FAIL"s that were really "I tested only one mode" (local vs shared) are my fault: I wrote the S-01 test for the mode I was running. New rule: every gate gets a test per mode and per request path (direct, proxied).
- A test of mine used string `wait_for_function`, which a CSP without `unsafe-eval` rightly blocks - the real browser test caught it. Good sign for the CSP, but tests should avoid string evals.
- Making the filter stricter made 5 old tests fail only because status codes changed 400 -> 422; I changed the tests on purpose and listed it above so nobody is surprised by the API change.
- The join limiter is now a design trade-off I made alone (slow mode). It needs Kenji's explicit OK.
