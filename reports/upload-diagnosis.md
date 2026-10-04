# Upload diagnosis: "upload image doesn't work" + "no camera option"
Date: 2026-10-04 ~16:55 CT. Author: executor (read-only diagnosis; no app code touched). Test files and scripts: /workspace/qa/upload/.

## Summary
**The server-side upload path works.** I could not reproduce a failure in either the Studio or the Edit endpoint, by curl or by driving the real UI in Chrome (desktop and iPhone-sized emulation). I did NOT test a real iPhone/iPad/Android, so the exact failure Zach saw is **not confirmed**. The code and tests point to the following likely causes, in order. Zach's exact device/browser and what he saw would settle it.

## Likely causes (ranked)
1. **UX: nothing visible happens after choosing a photo, and Build is off-screen on a phone (MEDIUM-HIGH, probable).** Picking a photo only shows a small preview in the drop box (`setFile`, static/app.js:48). The model is built only when "Build 3D model" is pressed. In a 390x844 viewport the button sits at y=882-930, below the fold (measured). A user who picks a photo and sees no model reasonably says "upload doesn't work". Edit workspace differs: it uploads and imports immediately on selection (edit.js:49).
2. **iPhone/Android HEIC / HEIF photos (MEDIUM-HIGH, plausible; not tested on a device).** No HEIC support exists (no pillow-heif in the venv or requirements; Pillow 12.3.0 only). Studio returns 400 `cannot read image: cannot identify image file <_io.BytesIO object at 0x...>` (raw Python repr shown in a toast). Edit returns 415 `Unsupported file type...` for `.heic`/`.heif`/`.webp`-style extensions not in `meshedit.IMAGE_EXT = {png,jpg,jpeg,webp,bmp,gif}` (meshedit.py:596). iOS Safari normally converts HEIC to JPEG when `accept="image/*"` and a photo is picked from the library, but not always (Files app, AirDrop'd files, "Most Compatible" off in some paths, Android/Windows/Mac file pickers keep HEIC). Page text says "JPG / PNG" only.
3. **"Build history is full" dialog (LOW-MEDIUM).** 5-build cap per browser session. The 6th build/edit import returns 409 and opens a modal (`dlgFull`). Works as designed (reproduced: 5 x 200, 6th = 409 + dialog), but a tester who has built a few things sees a dialog instead of a model. Edit sample/upload while the dialog is open is blocked by the modal.
4. **Camera/secure-context (for "no camera option").** See below.
5. **Not causes (checked):** no auth/CSRF/CORS requirement (anonymous, cookie-less curl and an `Origin: http://evil.example` request both return 200); `get_actor` just mints a session cookie. Recent commits (7d9fd49 JSON body limit; 72a8fbb; cbe7f2c bind to 127.0.0.1) do not touch multipart uploads: the JSON body-limit middleware only fires for `Content-Type: application/json`. Uncommitted working-tree changes (app/api/edit.py: adds ChatBlocked/ValueError handling in `_act`; index.html: header button labels; style.css) do not touch uploads. The `PHOTO3D_PHOTO_ACK_REQUIRED` flag exists in config.py:58 but is **not used anywhere** (no consent checkbox is enforced, so it cannot block uploads). server.log shows no tracebacks; the only 4xx on upload routes are my own bad-input tests plus 409 history-full.

## Camera: confirmed missing
- `static/index.html:35` `<input type="file" id="file" accept="image/*" hidden>` and `:137` `<input type="file" id="editFile" accept=".stl,.obj,.3mf,image/*" hidden>`. No `capture` attribute, no "Take a photo" button, no `getUserMedia` anywhere in static/*.js (grep: zero hits).
- On phones, `accept="image/*"` usually makes the OS picker offer "Take Photo", but this is OS-dependent, hidden behind an unlabeled drop box, and absent on desktop. Edit's `accept` lists mesh extensions first, which on iOS can suppress the Take Photo option.
- Desktop webcam needs `getUserMedia`, which requires a **secure context** (HTTPS or localhost). Zach reaching ZEIM over `http://<LAN-IP>:8765` from a phone/tablet cannot use `getUserMedia` (plain `<input capture>` does not need HTTPS). The running server is bound to `0.0.0.0` (started by hand, not run.sh default), so LAN access is currently possible.

## Evidence: curl (server at localhost:8765, also via LAN IP 172.30.0.2 -> 200)
Files generated with PIL in /workspace/qa/upload/.
| Endpoint | File | Result |
|---|---|---|
| POST /api/generate | small.png 80x60 | 200, 0.2 s |
| POST /api/generate | small.jpg | 200, 0.3 s |
| POST /api/generate | big.jpg 4000x3000, 9.1 MB, EXIF orientation=6 | 200, 4.0 s (485k triangles; size 106 x 139.7 mm: EXIF rotation honored) |
| POST /api/generate | IMG_0001.HEIC (really JPEG bytes) | 200 (content sniffed, extension ignored) |
| POST /api/generate | fake_real.heic (HEIF header bytes) | 400 `cannot read image: cannot identify image file <_io.BytesIO object at 0x...>` |
| POST /api/edit/new | small.png, big.jpg | 200 |
| POST /api/edit/new | IMG_0001.HEIC (JPEG bytes), fake_real.heic | 415 `Unsupported file type...` (extension-gated; a JPEG renamed .heic is refused) |
Limits: Studio 25 MB (config.MAX_UPLOAD), Edit 50 MB / photos 25 MB. A 9 MB photo is fine.

Curl form used: `curl -F file=@big.jpg -F mode=lithophane -F beginner=true -F preset=standard -F width_mm=100 -F auto_delete_oldest=true http://localhost:8765/api/generate`

## Evidence: UI (Playwright + system Chrome)
- Desktop 1280x800 and iPhone-UA 390x844: clicking `#drop` opens the file chooser; `set_files(big.jpg)` enables Build, preview shows, Build -> POST /api/generate 200, toast "Model built". No page errors; only WebGL perf warnings.
- 5 builds then a 6th: 409 -> "Build history is full" dialog (screenshot /workspace/qa/upload/full.png); Edit drop zone unclickable while it is open.
- Phone: after selecting a photo, `#btnBuild` top=882px vs viewport 844px (m2.png).
- Not tested: real iOS Safari, Android Chrome, HEIC from a real phone, Safari quirks, drag-drop on touch.

## Suggested fixes (for Engineering; I did not change code)
1. After a photo is chosen in Studio, scroll the Build button into view / make it sticky at the bottom on phones, or auto-start the build in Beginner mode; show a visible "Photo ready: Build" state. (Quick win.)
2. Add an explicit **"Choose photo"** button and a **"Take a photo"** button in Step 1 (visible, 44 px, labeled), using a second input `accept="image/*" capture="environment"` (works over HTTP on phones). Add a desktop "Use camera" using `getUserMedia` only when `window.isSecureContext` and show a plain explanation otherwise. Draw to canvas and upload as JPEG, which also strips EXIF/GPS; apply the same to Edit (separate photo input, so the 3D-file input keeps its extension list).
3. HEIC/HEIF: either add `pillow-heif` (check licence and pinned constraints; Dockerfile build deps), or convert client-side, or at minimum say "iPhone HEIC photos: use Most Compatible or take the photo with the in-app camera" and give a friendly error. Add `.heic/.heif` to Edit's image handling; replace the raw `<_io.BytesIO object ...>` message with "We couldn't read that photo. Try a JPG or PNG."
4. Edit `accept`: split photo vs. 3D file inputs.
5. Regression tests: Studio + Edit upload of 4000x3000 EXIF-oriented JPEG; HEIC-named file; history-full 409 path; friendly error text.
6. Wire up or remove the unused `PHOTO_ACK_REQUIRED` flag (Kenji's call; consent-first wording).

## Severity
- Upload-flow clarity on phones (cause 1): **High for Zach's use case (phone/iPad)**, low engineering effort.
- Missing camera control: **Medium** (feature gap; confirmed).
- HEIC unsupported: **Medium** (unconfirmed trigger for Zach).
- Server endpoint defects: **none found.**

## Questions for Zach
Which device and browser (iPhone/iPad Safari? desktop Chrome?), how he reaches ZEIM (localhost or LAN IP), what he saw after choosing a photo (nothing / error text / the dialog), and whether the photo came from the Photos app or Files.

## Housekeeping
My curl and browser tests created about 10 small builds under throwaway sessions in /workspace/photo3d/outputs (and data store); they are not in Zach's session. They can be deleted if desired.
