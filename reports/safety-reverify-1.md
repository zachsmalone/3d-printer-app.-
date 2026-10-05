# Safety re-verification 1 (Batch 1 fixes S-01..S-06 + tunnel-gate items)

Author: Kenji (Trust, Safety & Legal). Date: 2026-10-04, ~16:58-17:10 CT.
**I am not a lawyer. Nothing here says ZEIM is or is not compliant with any law.** This is a technical re-test of fixes against my original repros.

## How this was tested
- Code under test: **committed code only**, extracted with `git archive` into `/tmp/zeim-v1` (HEAD `322dd31`, first pass) and `/tmp/zeim-v2` (HEAD `7428e05`, final pass; the only later commit, `d3ce5de`, touches no `app/` code). Uncommitted working-tree edits by Engineering were NOT tested.
- Separate instances on 127.0.0.1 ports 8796-8799 with temp `PHOTO3D_OUT`/`PHOTO3D_DATA` under `/tmp/zeim-t/` (A 8797 = shared mode, admin token set, no public base URL; B 8798 = shared + `PHOTO3D_PUBLIC_BASE_URL`; C 8799 = `PHOTO3D_MODE=local`, what `run.sh` does by default). All stopped afterwards. **Live instance on 8765 and its data were not touched or probed.** No app code, tests or word lists edited.
- Scripts and raw outputs: `/workspace/scratch/reverify1/` (`scr/*.py`, `v2_*.out`, `pytest2.out`, `v1res/`). No offensive strings are printed anywhere; the language-filter test picks a listed word at run time.
- Test client is on loopback, so uvicorn trusts its `X-Forwarded-For` (see S-04/S-05 notes).

## Result table

| ID | Item | Result | One-line reason |
|---|---|---|---|
| S-01 | Settings / accounts gate (anonymous PUT/DELETE/connect) | **PASS** in shared mode, **FAIL if started with `run.sh`** | 403 for anonymous and for an adult without admin token; **but `run.sh` sets `PHOTO3D_MODE=local`, where the original repro still returns 200** |
| S-01 | Base URL validation | **PASS** | scheme/host only; credentials, paths, `javascript:` rejected (400) |
| S-01 | Forged Host header | **PARTIAL** | signed links now refused without a configured base URL (PASS); **classroom QR still follows a forged Host** unless `PHOTO3D_PUBLIC_BASE_URL` is set (then PASS) |
| S-01 | SSRF / printer targets | **PARTIAL** | anonymous can no longer set printers; but an admin can still point a printer at loopback, and any self-declared "adult" can then trigger sends (by design, see notes) |
| S-02 | Long-text freeze | **PASS** | 30,000-char fields rejected in 0.00 s; in-bounds worst cases <= 0.043 s; concurrent `/api/config` 0.00 s |
| S-03 | Teens Private only | **PASS** | every public/followers path 403; adults and teens cannot follow a teen (404); existing teen data migrated at start-up |
| S-04 | Age gate | **PASS** (same session) / **PARTIAL** (new browser) | neutral identical message, no threshold, same session locked; a client with no cookies can still retry |
| S-05 | Join-password limiter | **PASS** with caveats | fresh cookies no longer help (429 at attempt 6); min password 8 + weak list; caveats below |
| S-06 | OAuth callback reflection | **PASS** | `<b>`, `<script>` come back HTML-escaped |
| Links | Signed `/f/<token>` scope / expiry / log | **FAIL at 322dd31, PASS at 7428e05** | one file only, 10 min, token shown as `[redacted]` in the access log |
| Seeds | EXAMPLE items likes/downloads | **PASS** | `likes: null`, `downloads: null`, `counts_hidden: true` for anonymous, adult and teen |
| Edit | Text op length cap + filter | **PASS** (core) / **PARTIAL** (evasions) | cap 60, filter on create; known evasions still pass (below) |
| Tests | pytest with temp dirs | **PASS** | HEAD `7428e05`: **169 passed, 1 xfailed** (obfuscated e-mail, known). At `322dd31`: 155 passed, 1 failed (`test_pinned_requirements_and_ops_files`, because the pinning files were committed later), 1 xfailed |

## Details (exact requests and responses; `$B` = test instance)

### S-01 settings gate
- `PUT $B/api/settings` `{"public_base_url":"http://evil.example","printers":[{... "url":"$B/api/me"}]}` with no cookie -> **403** `Server settings can only be changed by the server admin (X-Admin-Token) on a shared server.`
- Same with a signed-up adult (no token) -> 403. `DELETE /api/accounts/tiktok` -> 403. `GET /api/accounts/tiktok/connect` -> 403. Wrong `X-Admin-Token` -> 403.
- `GET /api/settings` anonymous -> 200 with printer **names only** (URLs removed, `has_key` only); `can_edit:false`.
- Admin token: base URL `http://u:p@evil.example` -> 400; `https://x.example/a?b=1` -> 400; `javascript:alert(1)` -> 400; `https://zeim.example.org` -> 200.
- **Local mode (instance C, same as `./run.sh`):** `PUT /api/settings` with no token -> **200** and `public_base_url` became `http://evil.example`. A class student got 403 in local mode (good).
- `PHOTO3D_PUBLIC_BASE_URL` set (B): forged `Host: evil.example` -> `base_url` stays `https://zeim.example.org`; QR identical; settings locked in the UI (`public_base_url_locked:true`).
- No public base URL (A), forged `Host: evil.example` on `GET /api/print/{bid}/links` -> `base_url: "http://evil.example"` in the JSON, but `slicers: []` and `slicer_links_disabled: "Slicer links are off until the site's public address is set..."`. `GET /api/classrooms/{code}/qr.svg` with the forged Host returns a **different** SVG (it encodes the forged host). At `322dd31` the forged host also appeared inside signed file links (FAIL then).
- Printer test (admin saved `http://127.0.0.1:<port>/api/me` as an OctoPrint printer): an adult session `POST /api/send/{bid}` printer_id=<id> -> 200 `octoprint answered HTTP 404: {"detail":"Not Found"}` (the target's response body is still echoed to the caller). Private/loopback addresses are not blocked; that is admin-only now, and may be intended for LAN printers.

### S-02
`POST /api/me/signup` display_name 30,000 x "a" -> 400 `Display name is too long (max 40 characters).` 0.00 s. 300 KB JSON -> 413 `Request too large.` Showcase description 30,000 -> 400 (max 500); title 5,000 -> 400 (80); one tag 5,000 -> 400 (30); 21 tags -> 400; class name 30,000 -> 400 (60); build title 30,000 -> 400; links handle 30,000 -> 400. In-bounds worst cases (500 characters of `a@a.`, `1 `, `a-1`, `http://aaa...`) all <= 0.043 s. Concurrent `GET /api/config` while a 499-char description is scanned: 0.00 s.
Gap: the 256 KB body cap trusts `Content-Length`. A **chunked** 20 MB JSON body was read and parsed (0.20 s) before the field cap rejected it. Not a freeze, but the body limit is not enforced for chunked requests.

### S-03 (teen DOB 2011; adult DOB 1985 as control)
Teen signup privacy: profile private, default_visibility private. Then: `PUT /api/builds/{id}/visibility` public -> 403, followers -> 403 (`Accounts under 18 keep their projects Private for now...`); `POST /api/showcase` visibility public / followers -> 403; publish with default -> 200 but `visibility:"private"`; `PUT /api/showcase/{id}/visibility` public/followers -> 403; Edit project (from photo) visibility public -> 403 and publish public -> 403; `PUT /api/me/privacy` profile public/followers -> 403, default_visibility public/followers -> 403. Anonymous: teen item absent from Trending/Newest, `GET /api/showcase/{id}` 404, `/p/{id}` 404, `/api/users/{teenId}` 404, `/u/{teenId}` 404. Adult `POST /api/follow/{teenId}` -> **404** `unknown creator`; second teen following the teen -> 404. Teen can still follow an adult (200); I treat that as outside the decision. Case/format tricks (`PUBLIC`, ` public`, `public\x00`, list, null) -> 400. Adult control: public build 200, public profile 200.
Migration: a seeded legacy data dir (teen profile/default public, public Showcase item, public build meta, adult following the teen) was rewritten at start-up to private/private/private/private and the follow was removed (checked on `322dd31`; `privacy.py` unchanged since).

### S-04
- `POST /api/me/signup` DOB 2018-01-01 -> **403** `We can't create an account for you right now. If you're learning with a class, ask your teacher for the class code and password - you don't need an account for that.` Body contains no "13" and no "age"; sets `p3d_ag` cookie.
- Same cookie jar, DOB 2000-01-01 -> **403 (same text)**, again with 1990 -> 403; `/api/me` `signed_up:false`.
- New session id but keeping the `p3d_ag` marker cookie -> 403.
- A client with **no cookies at all** -> 200 adult account (residual: a child who clears site data can retry; unavoidable with self-declared DOB).
- Day before the 13th birthday vs a 5-year-old: byte-identical 403 body. Exactly 13 today -> 200. Future DOB -> 400 `invalid date of birth`; garbage -> 400 (these differ from the refusal but reveal nothing about the threshold). Empty display name + under-13 -> still the neutral 403.
- Storage: `2018-01-01` is not in `users.json`; `age_blocks.json` holds only a hash and an end time.
- Per-address limiter: fresh sessions from one address -> 429 `Too many tries from this network. Please wait a while.` after the quota (30/h counted across all earlier signups, so it tripped at attempt 5-7 in my run). **With `X-Forwarded-For: 203.0.113.9` the next signup succeeded** (200), because loopback clients are trusted by uvicorn's default `--forwarded-allow-ips`.

### S-05
- Create class password: `""`, `abc`, `1234567` -> 400 (needs 8-64); `12345678`, `password`, `aaaaaaaa` -> 400 `too easy to guess`; 65 chars -> 400; missing field -> 400; `plum-otter-42` and `correct horse` -> 200.
- Original repro: 60 wrong guesses, **new cookie each time**, one address -> `404 x5` then **`429 x55`** (first 429 at attempt 6, 0.5 s). Message: `Too many wrong passwords from this network. Try again in 5 minutes, or ask your teacher.`
- Caveats: (1) the **correct password from the locked address is also refused (429)** while locked, so on a school network where all students share one public address a single student (or prank) can lock the class out for 5 minutes, doubling on repeats up to 24 h. (2) Locks are keyed to (class code, address) and held in memory: a restart clears them (code-read; not tested by restarting). (3) Because address comes from `X-Forwarded-For` when the peer is trusted, 30 guesses each with a different spoofed address were all evaluated (30 x 404, no 429); **whether this is exploitable depends on the real proxy overwriting the header. Not verified with Caddy/Cloudflare.** (4) An unknown class code returns the same 404 and similar timing (median 0.047 s vs 0.057 s): no enumeration found. (5) Teacher view shows `failed_joins_last_hour` (counted 5 after 8 wrong tries, because tries during a lockout are not counted).
- The "three short words" passwords proposed in HQ-1 remain guessable offline-style only if the word list is small; online guessing is limited by the lockout above (5 tries / 5 min / address).

### S-06
`GET /api/accounts/tiktok/callback?error=<b>x` -> 400 `text/html`, body `<p>Authorization failed: &lt;b&gt;x.</p>...`; `error=<script>alert(1)</script>` -> escaped; 5,000-char error is cut to 200; `code=zzz&state=<i>s</i>` -> `Could not connect: ValueError: invalid or expired OAuth state` (no raw HTML). No CSP header is sent (see new items).

### Signed `/f/<token>` links (tested on B, `PHOTO3D_PUBLIC_BASE_URL` set)
- Each slicer link has its own token: `/f/<expiry>-<sig>/<build>/model.3mf` (PrusaSlicer, Bambu, Orca) and `.../model.stl` (Cura).
- Token expiry: 10.0 minutes after creation (was 2.00 h at `322dd31`).
- Token for `model.3mf` on the same build: `model.3mf` 200, `model.stl` 404, `model.obj` 404, `thumb.png` 404; same token on another build 404; tampered expiry 404; stl token opens stl only. (At `322dd31` one token opened stl, obj, 3mf and thumb for the build.)
- Access log (default uvicorn format, not `--no-access-log`): lines read `GET /f/[redacted]/<build>/model.3mf HTTP/1.1" 200`; neither token nor signature appears anywhere in `server.log`, including 404 lines. At `322dd31` the full token was logged.
- Remaining: a link is still a bearer URL for its 10 minutes (anyone holding it can fetch that file); the token itself is still in the URL the browser/slicer uses (history, referrer for non-redirecting pages).

### Example (seed) items
Anonymous, adult and teen: `GET /api/showcase?tab=trending|free` -> 9 EXAMPLE items, all `"likes": null, "downloads": null, "counts_hidden": true`. `GET /api/showcase/ex09` same. Seed numbers are excluded from `_likes`/`_downloads` (code-read: `catalog._all`), so they do not enter the Trending score. Real public adult item shows real counts (`likes: 2` after two likes). Note: an anonymous session can still "like" an EXAMPLE item (200, `{"liked":true,"likes":null}`); harmless but it records engagement on a made-up item.

### Edit text op (project from photo, adult)
- Accepted: `Hello 2026`, 60 characters. Refused: 61 chars -> 400 `Text must be 1-60 characters.`; 201 and 30,000 chars -> 400 `'text' is too long.`; number, null -> 400 `Text must be text.`; dict/list for `text` or `font` -> 400; control character -> 422.
- Blocked (422, `language_blocked` / `contact_blocked`, nothing stored): a listed word plain, UPPER, leet-ish (`a`->`@`, `e`->`3`), spaced letters, dotted letters; `kid@example.com`, `kid (at) example (dot) com`, `555-123-4567`, `5551234567`, `https://x.example/a`, `x.com`, `insta: kidname`. Messages are the recorded wording.
- **Still accepted (known filter gaps, matches filter-redteam.md):** a listed word with a zero-width character inside; `kid at example dot com`; `five five five one two three`; `@kid_name`; `12 Oak Street`. The xfail test covers only the spelled-out e-mail.
- Exports: project title `My Card` and the embossed text are not present in 3MF/OBJ/STL; the 3MF object name is `model` and metadata `Title`/`Application` are `photo3d`.
- Replay safety (stored text step that no longer passes is skipped) exists and has a passing test; I did not hand-edit stored data to exercise it myself.

### Bonus checks (not in my brief, from the latest commits)
- Upload with GPS EXIF (JPEG with GPS IFD, orientation 6): stored `source.jpg` has 0 EXIF tags and no GPS, for both Studio and Edit photo paths; orientation applied (80x60 became 60x80). Garbage file -> 400 `We couldn't open that photo. Try a JPG or PNG.` Filename `a./x` -> 200 (was 500 with orphan folder). So S-08 and the filename 500 look fixed. I did not test HEIC files.

## New things I noticed (ranked)
1. **`./run.sh` starts in `PHOTO3D_MODE=local`** (comment: "run.sh = your own machine"). In local mode anyone who can reach the port can change settings, printers and the base URL (reproduced: 200). **Any tunnel or LAN exposure must start the app with `PHOTO3D_MODE=shared`** (Ren's `reports/deploy/iphone-test/start.sh` does: shared, public base URL set, no admin token, no access log; I read it but did not run it). The existing 8765 instance was started by `run.sh`; I did not inspect its environment, and I saw earlier in `ps` that it had been bound to `0.0.0.0` (now `127.0.0.1`).
2. **Shared mode + QR + Host:** without `PHOTO3D_PUBLIC_BASE_URL`, classroom QR codes follow the request Host. Require the setting in shared mode (as was done for slicer links) or build QR only from it.
3. **"Adult" is self-declared.** In shared mode with an admin-configured printer, anyone who types a 1985 birth date counts as an adult and can send jobs to it (`guards.require_send`). Fine for a private pilot with no printers configured; not fine otherwise.
4. **Join lockout can be used against a class** on a shared school address (S-05 caveat 1). Consider letting the teacher unlock/regenerate, and counting only attempts from distinct sessions toward the lock, or lock on (code, address) only after the first wrong guess from that session.
5. **IP-based limiters trust `X-Forwarded-For`** from 127.0.0.1 (uvicorn default). Behind a local proxy that is correct only if the proxy replaces, not appends, the client's header. Needs a test through the real tunnel.
6. Body-size cap not applied to chunked JSON (S-02 note). Admin token has no throttling (200 wrong tokens in 0.6 s, all 403); fine only with a long random token.
7. Unchanged and not in Batch 1 (my earlier S-15, S-24): cookie has no `Secure`; no CSP/X-Frame-Options/nosniff/Referrer-Policy; `/docs` and `/openapi.json` public; any 16+ character cookie value is accepted as a session; `users.json`, `classrooms.json`, `age_blocks.json` are mode 644 (DOB in plaintext in `users.json`).
8. Code-read: `store.JsonFile.read` returns the default value if the file is unreadable/corrupt and the next `update` writes that default back, which would silently wipe the data. Writes are not atomic. Hansei-worthy for Ops.
9. Cosmetic: exports and metadata still say "photo3d", not ZEIM.

## What I could not verify
- Real browsers, iPhone/iPad, HEIC files, camera flow (HTTP API only).
- Behaviour through the real tunnel/proxy (Caddy, Cloudflare): forwarded-address handling, Secure cookies, header rewriting. Docker was not run.
- Lockout and age-lock **expiry** (5 min / 24 h) and the 10-minute token expiry were checked from values and code, not by waiting.
- Persistence of the join limiter across restarts (code-read only).
- Class-student Showcase switch (CR-3), CR-11 moderation changes, CR-15 recovery, report dedupe: outside this brief.
- Multi-process / concurrency races; load behaviour; languages other than English; the other 15 word lists.
- The live 8765 instance: deliberately untouched, so its mode, bind and data are unknown to me.
- Whether any later uncommitted Engineering edits (staged `app/api/*`, `main.py`, `classrooms.py` at ~17:10) change these results.

## Hansei
- I re-ran my original repros but changed little in how I chose them; the `run.sh` local-mode finding came only because I tested a second mode after the first pass looked clean. I should have started with "how does production actually start?" instead of "does the code gate work?".
- HEAD moved twice while I was testing (`322dd31` -> `5b17e3d`/`7428e05`). I redid every script on the final commit and kept the first-pass results for the signed-link comparison, but the pytest failure at `322dd31` was an artefact of a mid-flight commit, not a regression.
- Some of my "PASS" lines are narrow (HTTP API on loopback). They say nothing about the deployed path.
