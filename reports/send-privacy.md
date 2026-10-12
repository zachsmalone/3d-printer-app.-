# ZEIM "Send" hub: trust, safety and privacy review

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


Author: Kenji Watanabe (Trust, Safety & Legal) | Date: 2026-10-04 (CT) | Status: DRAFT for Engineering, Design and Mr. Kato
**This is not legal advice and does not claim compliance with any law or any third party's terms.** Items for a lawyer are listed in section 8. "Verified" means I ran it or read the cited page; "unverified" means I did not.

## 1. Short version
- The plan is safe in shape: every path is started by the user, and ZEIM itself sends nothing to anyone. Keep it that way.
- The exported files carry **no personal metadata** (section 3). The bigger point is that a lithophane/relief **is** the photo. A child's face in a photo can be read back out of the STL, so "no metadata" does not mean "no personal data".
- The weak spots are: the signed `/f/<token>` link (not file-scoped, token still written to the log), a base URL that falls back to the Host header, printer send from an HTTPS page to a LAN printer (browsers block it), and no classroom switch to turn Send off.

## 2. What data leaves, per path

Risk: L low, M medium, H high. Owner is who acts first.

| # | Send path | Data leaving | Recipient | Consent needed | Risk | Guardrail | Owner |
|---|---|---|---|---|---|---|---|
| 1 | **Download** STL/OBJ/3MF | The file, from the ZEIM server to the user's own browser. Nothing else. | The user's device (Downloads/Files). On a shared school device the next user can see it. | A click is enough. Show "Saved on this device" so kids know where it went. | L | Keep the cookie-checked `/api/download` (verified: `photo3d_<id>.stl`, no personal name). Add `Cache-Control: no-store`. | Eng |
| 2 | **Web Share with files** (iOS/iPadOS share sheet) | The file's bytes, from the browser to **whichever app the user picks** (Files, iCloud, AirDrop, Mail, Dropbox, Drive, Shapr3D, Creality). ZEIM does not see the choice. | A third party or a person, under *that app's* terms. AirDrop can reach a stranger nearby. | The OS sheet is the consent step, but kids cannot judge "where does this go". Add one plain sentence first. | M | Build a `File` from the cookie-checked download, never share a signed link. Pass a generic title/text only. Feature-detect with `navigator.canShare({files})`; fall back to Download. Off for class students by default. | Eng/Design |
| 3 | **Email to yourself** via share sheet (Mail) or `mailto:` | With the share sheet: the file goes to the user's mail app. With `mailto:`: only text (no file). | The address the user types or picks in their own mail app. ZEIM cannot check that it is "yourself". | The user types the address themselves. | M | ZEIM never asks for, stores or pre-fills an address. No signed link in the body. Say "ZEIM does not send this email; your mail app does." Label it "Mail" not "to me". | Eng/Design |
| 4 | **Server-side email** | The file, from ZEIM to a mail provider to an inbox. | ZEIM, a mail provider, and the inbox owner. | Needs accounts, a verified address and a provider contract. | **H** | **Do not build yet.** Stays blocked until accounts, provider terms and a legal review exist. Decision rule: only to the signed-in adult's own verified address, rate-limited, never to minors or class students. | Legal/Eng |
| 5 | **Cloud OAuth** (Dropbox / Google Drive), later | The file, uploaded from the ZEIM server to the user's cloud account, using an OAuth token ZEIM stores. | Dropbox / Google, under their terms. | An explicit "Connect" screen naming the provider and the scope, plus a disconnect button. | M | **Adults (18+) only.** Smallest scope (Drive `drive.file`). Per-user tokens (today `/api/accounts` is server-wide, admin-gated only). Tokens are Fernet-encrypted at rest (code-read); key lives in `data/secret.key` or env. Delete tokens on disconnect or account deletion. | Eng/Legal |
| 6 | **Direct to printer** (OctoPrint, Moonraker, Creality K1) | Sliced G-code (plus the printer's API key as a header), to the printer's LAN address. | The user's own printer. | A "Send to \<name\>" button. "Start print" must be a separate, unchecked option (today `start` defaults to false: verified). | M (H if the URL or key leaks) | See section 5. Local mode, or browser-to-printer. Teacher/adult only. Never in a hosted server (it cannot reach a home LAN, and trying is an SSRF risk). | Eng |
| 7 | **Creality Cloud link-out** | Nothing from ZEIM except, at most, the referrer origin. | creality.com. The user uploads there themselves. | A line: "This opens Creality Cloud. You upload there yourself and their rules apply." | L | Plain link with `rel="noopener noreferrer"`. No API assumed (none verified). **Hide for teens and class students**, like the existing social link-outs. | Design/Legal |
| 8 | **Signed `/f/<token>/<id>/<file>` link** (slicer deep links) | The file, served to **anyone holding the URL** for 2 hours, with no cookie. | Whoever receives or sees the URL. | Owner action only. | M | See section 4. Keep it desktop-slicer only. Never show it as "copy link" or put it in an email or share text. | Eng |

## 3. What is inside an export (I opened real files in `outputs/`)
Sample: `outputs/088dd5d4f7d0` (lithophane) and `outputs/d75e77e72475` (an Edit project made from an uploaded STL). Files: `model.stl`, `model.obj`, `model.3mf`, `thumb.png`, `meta.json`, `source.png`.

| File | What I found | Verdict |
|---|---|---|
| `model.stl` | 80-byte header is `photo3d binary STL (mm)`; attribute bytes are all zero (0 of 282,108 non-zero). | Clean. |
| `model.obj` | One comment `# photo3d OBJ (units: mm)` and `o lithophane`. | Clean. |
| `model.3mf` | 3 zip entries only (`[Content_Types].xml`, `_rels/.rels`, `3D/3dmodel.model`). `Title` = `photo3d`, `Application` = `photo3d`. **No thumbnail, no author, no creator name.** Zip timestamps = build time. | Clean for photo builds. |
| Edit project `model.3mf` | `Title` = `photo3d`, but the **object name = the project title**, taken from the uploaded file name or typed text (`sample_vase`). | **Low-Medium: use a generic object name, or make the title opt-in.** A title like "Emma_birthday" would travel with the file, and the language filter does not catch names (safety.md S-10, S-13). |
| `thumb.png` | No EXIF/text chunks. It is a render of the model. Not part of the planned Send. | Clean. |
| `meta.json` | Holds the title, the owner's **session ID** (`owner_sid`) and creation time. It is not served by any route (`FILE_NAMES` allows only model.*, thumb.png, model.gcode). | Do not ever add it to a share or zip. |
| `source.<ext>` | The uploaded original. **Not exported**, but it still keeps EXIF/GPS on disk (S-08, not fixed yet; my samples are PNGs so I could not re-test GPS). | Strip metadata at upload. Never put the source in a Send bundle. |
| G-code from the built-in slicer | I sliced a sample: the header has the PrusaSlicer version and a UTC time; the config block has no user name, host name or path. | Clean (one sample). |
| Download file name | `photo3d_<12-hex-id>.<ext>`; send-to-printer name is the same. | No personal data. |

**The photo is the data.** A lithophane stores the picture as thickness, so a photo of a child can be recovered from the mesh. Treat a photo-based model as the photo itself. Decision #6 in `HQ/decisions.md` (minors' and students' photo-based models are not sent outside ZEIM by default) is the right rule. It needs to be a code rule, not a convention.

## 4. Signed links, base URL and logs (checked against the running app)
- **Token is not file-scoped.** One token works for every file of that build, including `thumb.png` and `model.gcode`. I fetched the model and the thumbnail without a cookie: both 200. The private `/files/...` URL gave 404 to the same anonymous request.
- **Bearer link.** The token is in the URL path (`/f/<exp>-<sig>/<id>/...`). Anyone who sees it (forwarded message, screenshot, browser history, school web filter or proxy log) gets the model for up to 2 hours. It cannot be revoked short of rotating `data/link.key`.
- **Referrer leakage is low** because `/f/` returns a file, not a page. Browsers default to `strict-origin-when-cross-origin` (MDN, fetched). Still, ZEIM sets no `Referrer-Policy` itself (S-15). Set `no-referrer`.
- **Token still lands in the log.** `server.log` contains `/f/` lines (2 found); redaction (S-18) is not done. Fix before hosting.
- **Base-URL poisoning, verified.** With `PHOTO3D_PUBLIC_BASE_URL` unset, `GET /api/print/<id>/links` with `Host: evil.example` returned `http://evil.example/f/<token>/...`. The admin-only setting (S-01 fix) is in place, but the fallback to the request's Host header remains. A reverse proxy that forwards arbitrary Host values would build signed links to the wrong server. In every shared deployment, set `PHOTO3D_PUBLIC_BASE_URL` and ignore Host.
- **Who can mint tokens.** `print_links` is owner-only but not blocked for class students. Students should not get signed links at all.
- **Suggested change:** bind the token to one file name and a 5-10 minute lifetime, and show it only for the desktop-slicer button. Mobile Send does not need it.

## 5. Printers, API keys and mixed content
- **Storage (code-read, verified file mode):** printer URL and `api_key` live in `data/settings.json` as plain text, mode 0600. They are masked in the API (`has_key` only), and URLs are hidden from class students and, in shared mode, from non-admins. OAuth tokens (separate) are encrypted. Recommend encrypting printer keys with the same Fernet key, and keeping them per user.
- **Transmission:** the key goes only as an `X-Api-Key` header over whatever scheme the URL uses. Most home printers are plain `http://`. That is normal on a home network but is not private on school or public Wi-Fi. Say so in the dialog.
- **Logs:** no ZEIM code writes the key (code-read of `printers.py`). Printer error replies are echoed back up to 200 characters, so strip them. The access log does not record headers.
- **SSRF:** in shared mode, only an admin can set printer URLs now. Still block loopback, link-local and cloud-metadata addresses and redirects before any hosted deployment (S-01 follow-up).
- **HTTPS page to HTTP printer (MDN, fetched):** browsers block `fetch()`/XHR to `http://` from an `https://` page, and addresses written as an IP are not auto-upgraded. So a browser-to-printer call from a hosted ZEIM will fail. Moonraker also has CORS **off** unless `cors_domains` is set (Moonraker docs, fetched). Realistic options: (a) local mode, server on the same network as the printer (works today, tested only against mock servers); (b) download G-code and upload in the printer's own page; (c) a small local helper later. The server-side call from a hosted ZEIM cannot reach a home LAN.
- **iOS test setup:** Web Share needs a secure context (HTTPS; MDN, fetched). Plain `http://192.168...` on an iPhone will not offer it. The Caddy internal-certificate test is approved, but Zach's devices must trust that certificate, which I did not verify.

## 6. Consent and wording by audience (plain language, drafts for counsel)
- **Under-13 class students (nickname + cookie):** no Send hub. Their "Send" is the existing "Send to my teacher". Teacher gets Download/Print. Default **off**, with a per-class teacher switch (suggest `send_enabled`, default false). Reason: students cannot judge where a file goes, and the model may contain a classmate's photo.
- **Teens 13-17 (Private only):** Download and share sheet only, for **their own** builds. No cloud connect, no Creality link-out (Creality Cloud's own pages disagree on age: "under 13" on one, "under 18 / parental consent" on another; both fetched). No printer send (the code already needs an adult account). Prompt: "This sends your file to the app you pick. ZEIM does not see where it goes. Only send photos you have permission to use."
- **Adults:** same plus cloud connect and printer. Prompt before first use of each: provider name, what is sent, "disconnect any time".
- **Everyone:** the existing "I have permission to use this photo" box stays. Add "Don't send photos of other people without their OK."
- **Never:** pre-ticked boxes, silent sends, ZEIM contacting anyone on the user's behalf.

## 7. Third-party terms (only what I read; the rest is unverified)
| Party | What I found | Source | Effect on ZEIM |
|---|---|---|---|
| Web Share API | Secure context only; needs a user click; `canShare` should be tested. MDN's "usually shareable" file list has images, audio, video, PDF and text, **not .stl/.obj/.3mf**. | MDN `Navigator.share`, `canShare` (fetched) | Whether iOS accepts `model/stl` etc. is **untested**. Plan the Download fallback as the main route. |
| `mailto:` | No attachment mechanism; `body` is for short text; the user's client should show the whole message before sending; no length limit stated in the RFC (client limits differ: unverified). | RFC 6068 (fetched) | Use the share sheet for files; `mailto:` only for a short note with no signed link. |
| Dropbox | Developer terms need production approval and least-privilege permission. Users must be 13 (US) / 16 (elsewhere); a help page says **18+ from 2027-01-01**. | dropbox.com/developers/reference/tos, /terms, help page (search snippets, not full pages) | Adults only. Re-check dates before building. |
| Google Drive | `drive.file` is "non-sensitive" and needs only basic verification; broad Drive scopes are restricted and need a security assessment. Privacy policy required. | developers.google.com Drive scopes, restricted-scope pages (search snippets) | Use `drive.file` only. Whether Google limits sign-in for minors in an app like ours: **unverified**. |
| Creality Cloud | Platform privacy page: not for under 13. Accounts Center page: not for under 18 without parent/guardian consent. Terms bar real firearm models and content that infringes rights. No public API for third parties was found in my search (not exhaustively checked; Daichi's `integrations.md` owns that). | file2-cdn.creality.com/privacy-en.html; id.creality.com/privacy-policy, /terms (search snippets) | Link-out only, adults. Do not claim integration. |
| Shapr3D | Imports STEP/IGES/Parasolid/STL etc. on iPad; **STL is reference-only mesh**; OBJ and 3MF are listed as export, not import. Basic plan limits. | support.shapr3d.com (Supported file types, Import), shapr3d.com/download/ipad (search snippets) | Offer **STL** first for Shapr3D; do not promise editing. |
| Apple (App Store/PWA rules for kids, Add to Home Screen) | **Not read.** | n/a | Unverified; counsel/Design to check before any App Store route. |

## 8. Must-do before building (Engineering unless noted)
1. **Class switch:** `send_enabled` per class, default off; class sessions get no Send/share/mint-token routes. Test it.
2. **Rule in code:** nothing photo-based leaves ZEIM for minors or class students except Download by the owner. Test it. No server-side email or upload at all for them.
3. **Fix before Send ships:** pop-art non-manifold (decisions.md), strip EXIF at upload (S-08), generic object name in 3MF for edit projects, redact `/f/<token>` in logs (S-18), `no-referrer` and security headers (S-15).
4. **Base URL:** require `PHOTO3D_PUBLIC_BASE_URL` in shared mode; do not build links from the Host header.
5. **Signed link:** file-scoped, 5-10 min, desktop slicer only, never in share text or email.
6. **Share sheet:** build `File` from the cookie-checked download; test `canShare` with STL/OBJ/3MF on a real iPhone and iPad (nobody has yet); Download is the fallback.
7. **Printers:** SSRF blocklist for hosted mode; encrypt keys; "start print" separate and off; teacher/adult only.
8. **Copy (Design, with my review):** the consent sentences in section 6, "ZEIM does not see where it goes", and the age rules for link-outs.
9. **No analytics or third-party scripts:** none found in `app/` or `static/` (grep; only the optional base URL placeholder mentions a URL). Keep it that way; the Send hub must not add trackers or call-home.
10. **Deletion:** state in plain words what "Send" cannot undo. Once a file is in another app, deleting the ZEIM build does not delete that copy.

## 9. Needs real legal review
Ranked with the existing list in `safety.md`.
1. COPPA / school-authorisation and any "send outside" feature for under-13 data, including whether a model made from a photo of a child counts as personal information.
2. Any future server-side email (CAN-SPAM-style duties, provider terms, children's data to a mail provider).
3. Google OAuth for an app used by minors and schools; Dropbox developer approval; whether the 2027 Dropbox 18+ change affects us.
4. Terms of Service / privacy notice: licence to host and process uploads; our role when a user sends a file to a third party; no ZEIM licence over a user's model; the "I have permission" statement.
5. Models of other people's work (characters, brands, other users' Showcase items): the app has no per-model licence field today, and public items can be downloaded. Decide before Send is offered on other people's items. I recommend Send for **own** builds only at launch.
6. Printed-object safety: a one-line notice on printer send (hot parts, supervise) and the weapons policy as it applies to onward sending.
7. Creality's and Shapr3D's terms for links and file hand-off (my reading is from search snippets only).
8. Breach and incident duties when printer keys and OAuth tokens are stored.

## 10. Hansei (what I could not verify, and what I would change)
- **Not tested on any iPhone or iPad.** I cannot say whether Safari accepts STL/OBJ/3MF in `navigator.share`; MDN's list suggests it may not. Everything about the share sheet is unverified until Zach tries it over HTTPS.
- Most vendor pages (Dropbox, Google, Creality, Shapr3D) came as **search snippets**, not full pages. Dates and age limits (especially Dropbox 2027) need a re-read by a person before anyone relies on them. Apple's terms: not read.
- I checked one lithophane and one edit project. Pop-art, relief and multi-body 3MF were not opened; a colour 3MF may carry other names. EXIF/GPS: my samples were PNG; I relied on the earlier S-08 test.
- I did not test K1/Moonraker or a real printer; printer code has only been exercised against mock servers (printers.py docstring). Mixed-content behaviour comes from MDN, not from Safari.
- The test build I created for the Host-header check (title "kenji-send-privacy-probe") was deleted after the test. No app code was changed.
- `reports/integrations.md` (Daichi) did not exist yet and I did not read `design-ios-send.md` (Sakura), so this review may need to be reconciled with both.
- What I would change next time: ask Engineering for a bundle-contents test (a unit test that fails if an export gains metadata) at the same time as the review, rather than finding it by hand.
