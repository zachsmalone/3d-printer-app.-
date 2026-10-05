# Phone test: "page loads, none of the buttons work" (diagnosis, read-only)

Date: 2026-10-04 (CT). Author: executor for Mr. Yami Kato. No app code was edited, nothing was restarted.
Passcode/ngrok token were never printed. Test scripts: `/workspace/qa/phone-dead/` (t.py, t2.py, t3.py).

## Verdict (confidence: probable, not proven on the device)
The tunnel, Caddy basic-auth, ngrok and the CSP are **not** the cause. The phone test instance (port 18765) serves the
**live working tree** of `/workspace/photo3d` (run-info: `app_dir=/workspace/photo3d`, `working_tree_dirty_app_static=6`; it was
started without `--snapshot`). Engineering was editing `static/app.js`, `edit.js`, `send.js`, `style.css` while Zach was testing, and
`/static/*` carries `ETag`/`Last-Modified` but **no `Cache-Control`**, so Safari reuses old JS modules without asking. The page is
plain HTML + CSS (so it "looks nice"), but all buttons are wired by the ES-module graph, so if the module graph is mismatched or throws,
every button is dead. The Caddy log shows exactly that happening on Zach's first two loads and not on the third.

## Evidence
1. **Zach's iPhone (UA iOS 26_6_1, client IP 2600:6c42:...) in `caddy-access.log`:**
   | time CT | what Zach's phone fetched | startup API calls (`/api/builds`, `/api/config`, `/api/me`) |
   |---|---|---|
   | 18:23:51 | `/` + style + ALL modules (app.js 22626 B, edit.js 29366 B, send.js, photo.js, viewer.js, three, OrbitControls) | **none** => app did not start |
   | 18:26:37 | `/`, style, edit.js, app.js (23780 B) = 200; send.js = 304; photo/viewer/community/three NOT re-requested (served from Safari cache) | **none** => app did not start |
   | 18:28:00 | `/`, style 304, edit.js 304, app.js 200 (23853 B), send.js 304 | `/api/config`, `/api/builds`, `/api/me` => **app started** |
   | 18:29:28 | `POST /api/generate` (6.9 MB result, 83 KB thumb = not the 10 KB sample) | Zach built a model from his own photo |
   | 18:30:10-17 | Showcase list, `/api/showcase/ex09`, STL download | working |
   So on loads 1 and 2 every file came back 200/304 (no 401/403/404, no failed request) yet the app never initialised; on load 3 it did.
2. **File timeline:** `app.js` was rewritten at 18:29:05 (earlier copies seen on the wire: 22626, 23780, 23785, 23853 B; now 23974 B),
   `edit.js` at 18:24:36 (29366 -> 29881 B), `send.js` at 18:23:35, `style.css` changed. Zach's first load (18:23:51) landed between
   edits. I cannot recover the exact bytes served at 18:23:51/18:26:37 (uncommitted), so I cannot name the exact line that threw.
3. **No `Cache-Control` on `/static/*`** (checked via the tunnel: only `etag` + `last-modified`). With a Last-Modified hours old, Safari
   applies heuristic freshness and reuses cached modules (visible at 18:26:37: photo.js/viewer.js/community.js/three were not requested).
4. **Current build is healthy through the real tunnel.** WebKit 26.6 (Playwright, iPhone 13 profile; installed with two user-space libs, no sudo)
   and Chrome, with http_credentials: all 10 static/module files 200 with correct `text/javascript` MIME, importmap OK (its sha256 matches the
   CSP), zero page errors, zero console errors, startup API calls fire, `tap()` on **Choose a photo** opens the file chooser, **Use a sample image**
   loads `sample.png` and shows "✔ sample.png / Change photo". Direct `127.0.0.1:18765` behaves identically to the tunnel; no difference found.
5. **Things I checked and ruled out:** 401 on subresources (none; unauthenticated requests do get 401, authenticated get 200, same bytes as direct);
   wrong MIME (all `text/javascript`/`text/css`); CSP blocking (hash matches, no inline handlers, no violations in WebKit or Chrome); mixed content
   (all same-origin https); importmap/three.js (loads); ngrok interstitial (see caveat 2).

## Root cause (most likely)
Live-tree serving + no cache validation => Safari ran a mixed set of JS modules while files were being edited => the module graph
(`app.js` -> `viewer.js` -> `three`, `photo.js`) failed to start => static HTML shown, buttons inert. A normal reload eventually fetched a consistent set.

## Fix (who applies it)
1. **Immediate, Zach/Yami (no restart needed):** on the iPhone close the tab, reopen the link (tap "Visit Site" if shown), or Settings > Safari > Advanced >
   Website Data > remove the ngrok site, then reload. Ask Haruto/engineers to **not touch `/workspace/photo3d/static` or `app/` until the test ends**
   (or tell Zach to reload after each announced edit).
2. **Ren Okabe (kit, patch ready, not applied):** `reports/deploy/iphone-test/phone-dead-buttons-caddy-nocache.patch` adds
   `@zeimstatic path /static/* /favicon.ico /` + `header @zeimstatic Cache-Control "no-cache"` to `Caddyfile.template` (validated with `caddy validate`
   on a rendered copy). It takes effect only on the next start (Caddyfile is rendered at start), so apply with `patch -p0 < ...` then restart later.
   Also: **always start the phone test with `start.sh --snapshot`** (already supported; archives git HEAD so edits cannot reach the phone). Commit the fixes first,
   because the snapshot is HEAD only.
3. **Haruto (app, optional hardening):** send `Cache-Control: no-cache` for `/static/*` and `/` in the app itself (or version the module URLs, e.g. `?v=<git short sha>`),
   and make the app show a visible banner if the module graph fails to start (a `window.onerror`/`unhandledrejection` message plus a `<noscript>`/"loading" state
   in the HTML), so a dead page never looks like a working one. Add a test that loads the app in WebKit and fails on any pageerror.

## Caveats
- I did not see Zach's device console. The mismatch explanation fits the log but I could not reproduce the failure with current files; if it still happens
  after a clean reload, ask for a screenshot or connect Safari Web Inspector from a Mac.
- ngrok free interstitial: it also answers **subresources** (JS/CSS) with its HTML warning page whenever the browser lacks ngrok's cookie (verified with curl and an iPhone UA).
  Zach's CSS loaded, so his cookie worked; but a private tab, content blocker or cleared cookies would produce a similar "styled but dead" state. Adding the
  `ngrok-skip-browser-warning` header at Caddy for requests (`header_up ngrok-skip-browser-warning 1`) would not help (it is the ngrok edge that decides, before Caddy);
  the dependable fix is a paid/static-domain setup or Zach tapping "Visit Site" in a normal tab.
- The timing of Zach's "none of the buttons works" message relative to 18:23-18:30 is unknown to me; his phone clearly built a model at 18:29:28.
- WebKit 26.6 is Playwright's engine, not Mobile Safari; nothing here is a real-iPhone test.
