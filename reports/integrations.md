# ZEIM integrations research: Send hub, Creality Cloud, Shapr3D, printers

Author: Daichi Hayashi (Growth & Operations) · Date: 2026-10-04 · Status: research only. **No app code was changed.**
Nothing here was run on a real iPhone, iPad, K1 or other printer. Where I could not find official evidence I say **NOT FOUND / unverified** and name what I searched.

**Evidence labels**
- **VERIFIED**: I read an official vendor page, official repo or official source file (URL in Sources).
- **REPORTED**: forum post, issue tracker, third-party repo or integration. The text is real, but it is not the vendor's own statement.
- **UNVERIFIED**: inference, a search-result summary I did not confirm on the page, or a gap. Treat as untested.

Note on method: web-search summaries were used only to find pages. A claim is VERIFIED only if I opened the page (or the raw source file) and read it. Pages I saw only in search results are listed separately at the end.

---

## 0. Summary table

| Integration | What's possible | Evidence | Call | Owner |
|---|---|---|---|---|
| Download STL/OBJ/3MF to this device | `<a download>` is supported in iOS Safari from 13; a server `attachment` link is the safest form | VERIFIED (support data), behaviour on Zach's devices untested | **ADOPT NOW** | Haruto |
| Web Share API with files (iOS share sheet: Files, AirDrop, Mail, other apps) | Supported in Safari/iOS from 14 (`canShare`). Needs HTTPS and a tap. **Whether iOS accepts `.stl`/`.3mf` files is not documented** | VERIFIED (API rules), file types UNVERIFIED | **ADOPT NOW** (with download fallback) + **NEEDS TESTING** | Haruto, Sakura |
| Email to yourself | Through the share sheet's Mail option. Server-side email stays off until accounts + provider exist (HQ decision) | VERIFIED (decision), Mail target UNVERIFIED | **LATER** (share sheet only now) | Haruto, Kenji |
| Creality Cloud: public API / import-by-link / URL scheme for third parties | **NOT FOUND.** Only manual upload (web or app) is documented | NOT FOUND (see §1) | **NOT POSSIBLE** (as an API). Plain link-out: **ADOPT NOW** | Daichi (watch), Haruto |
| Creality Cloud app on iOS: receive a file from the share sheet | App Store notes say it can preview/print local 3MF/STL files. Whether it shows up in the share sheet is unknown | App Store notes VERIFIED, share sheet UNVERIFIED | **NEEDS TESTING** | Zach (device), Sakura |
| Creality Print deep link | A `crealityprintlink://open?file=` scheme is used by two third parties. Creality Print is **desktop only** (Windows/macOS), so it does nothing on an iPhone | REPORTED | **NEEDS TESTING** (desktop only) | Haruto |
| Shapr3D import from ZEIM | **STEP, IGES, Parasolid, SolidWorks native: yes. STL: "for reference only" (a mesh, not editable solid). OBJ and 3MF are not in the import list** | VERIFIED | STL as reference: **NEEDS TESTING**. 3MF/OBJ: **NOT POSSIBLE** (per list) | Haruto, Aiko |
| Shapr3D API / URL scheme / plugin | No public API; Shapr3D staff say so | REPORTED (staff, community forum) | **NOT POSSIBLE** | Daichi (watch) |
| Printer send: OctoPrint, Moonraker | Already in ZEIM; upload endpoints and auth match the vendor docs | VERIFIED (docs), ZEIM untested on hardware | **ADOPT NOW** (server-side) | Haruto |
| Creality K1/K1C/K1 Max, stock firmware | Creality's own LAN protocol (HTTP upload + WebSocket 9999), read from OrcaSlicer source. Moonraker only after root + community add-on | VERIFIED (source), not Creality-documented | **LATER** (new `creality` type) + **NEEDS TESTING** | Haruto |
| Prusa Link (MK4/XL/Mini etc.) | Documented OpenAPI: `PUT /api/v1/files/{storage}/{path}`, digest auth | VERIFIED | **LATER** | Haruto |
| Bambu Lab LAN | MQTT 8883 + FTPS 990. Normal LAN mode now needs Bambu Connect/authorization; **Developer Mode** (LAN-only) restores open access | VERIFIED | **LATER**, advanced users only | Haruto, Kenji |
| Bambu Connect URL scheme | Takes a local file path on the same computer, so a website cannot use it | VERIFIED | **NOT POSSIBLE** from the web | n/a |
| Snapmaker U1 | Runs Moonraker (open-sourced by Snapmaker). Should work with the existing Moonraker type | VERIFIED (firmware is Moonraker), ZEIM untested | **NEEDS TESTING** | Haruto |
| Snapmaker J1/J1S/Artisan | Own protocol (SACP); Moonraker only via a community bridge | VERIFIED (SACP repo exists), bridge REPORTED | **LATER / NOT NOW** | Haruto |
| Elegoo Centauri Carbon (stock) | SDCP v3: UDP discovery, WebSocket 3030, HTTP upload on 3030. Moonraker only with community firmware | VERIFIED (protocol doc), firmware claim REPORTED | **LATER** | Haruto |
| Duet / Repetier | Duet: `rr_upload`. Repetier: server API with API key | VERIFIED (partly) | **LATER** | Haruto |
| Browser sends straight to a LAN printer | Blocked from an HTTPS page (mixed content) and needs printer-side CORS. Chrome-only local-network permission, not in Safari | VERIFIED (MDN + support data) | **NOT POSSIBLE** as the main path | n/a |
| Slicer deep links (desktop) | OrcaSlicer: yes, any URL (source read). Cura: yes (vendor note). **PrusaSlicer: restricted to allow-listed sites (our current link will probably be refused).** Bambu Studio: 3MF only (reported) | mixed, see §5 | Orca/Cura **ADOPT**; Prusa **FIX/REMOVE**; Bambu **NEEDS TESTING** | Haruto |
| PWA "Add to Home Screen" | Works from a manifest with `display: standalone`. **Share Target (receiving files into ZEIM) is not supported in Safari on iOS** | VERIFIED | **ADOPT NOW** (install only) | Sakura |

---

## 1. Creality Cloud and Creality Print

### 1.1 Does Creality Cloud have a public API / developer program / import link / URL scheme?

**NOT FOUND.** What I searched and read:
- Creality Wiki "Creality Cloud" page (FAQ lists upload formats; no developer or API section): https://wiki.creality.com/en/creality-cloud (VERIFIED, read).
- Creality Cloud Help Center index (long list of help topics; no developer/API/open-platform entry; the only "API-like" topic is "How to install Creality Cloud Plugin on OctoPrint"): https://www.crealitycloud.com/help-center/62e39f89224c8be602cc75c3 (VERIFIED, read).
- Creality's GitHub plugin for Cura: https://github.com/crealitycloud/CrealityCloudIntegration. README says it is a Cura plugin that works "with Creality Cloud App and Creality Cloud WIFI box" and uploads G-code. It is a client for Creality's own services (it bundles Aliyun OSS libraries), **not** a documented third-party API (VERIFIED that the repo exists; I did not read its source).
- Search queries tried: "Creality Cloud open API developer third-party import model URL", "Creality Cloud API developer open platform OpenAPI third party", "Creality Cloud app iOS import model from Safari Open in share sheet".

Two things that are *not* evidence of a public API, to avoid misreading:
- The Chinese Creality Cloud privacy policy defines the service as including "SDK and API for third-party websites and apps" (https://file-cdn.creality.com/privacy-mi.html, read). That is a definition inside a privacy policy. I found **no developer documentation, registration flow or endpoint list**, so it is not usable. (VERIFIED text, **no usable API found**.)
- The App Store listing mentions a "Designer Partner Program" for model creators (contact by email). That is for designers, not an integration API (VERIFIED, https://apps.apple.com/us/app/creality-cloud-3d-printing/id1577663728).

**Call:** treat Creality Cloud as **link-out only**. Do not guess endpoints. If Zach wants more, the honest next step is to email Creality (APPservice@creality.com is the contact in the App Store listing) and ask whether a partner/import API exists.

### 1.2 Accepted import formats (user uploads)
- Creality Cloud web **model upload**: `.stl, .obj, .ply, .off, .3mf, .3ds, .wrl, .dae, .step, .stp` (VERIFIED, https://wiki.creality.com/en/creality-cloud). A batch upload tool exists for desktop.
- 3MF has two kinds on Creality Cloud: a **model** 3MF and a **print-settings** 3MF exported by Creality Print. Uploading the wrong kind can fail (REPORTED by Creality's own forum blog, https://forum.creality.com/t/how-to-upload-3mf-files-to-creality-cloud/22430, search excerpt plus first-party blog; I did not read the full thread). ZEIM's 3MF is a plain model 3MF.
- Creality **Print** (desktop slicer): import STL, OBJ, STEP, STP; open projects 3MF and CXPRJ (VERIFIED, https://www.creality.com/help/help-creality-print-quick-start-guide). System requirements list Windows 10/11 and macOS only, **no iOS/iPadOS version** (VERIFIED, same page).
- Creality Cloud **mobile app**: App Store says it can slice STL in the cloud, print 3MF "without the need for slicing", and release 7.3.2 "added preview and print support for local files such as 3MF and STL" (VERIFIED, App Store page above). The app is "Designed for iPad" and requires iOS 15+ (same page). Age rating **13+**, "Contains User-Generated Content, Social Media" (same page), which matters for Kenji (see §6).
- Caveat: "print 3MF without slicing" most likely means a **sliced** Creality-style 3MF. ZEIM's model 3MF still needs slicing. UNVERIFIED, test it.

### 1.3 How does an iOS user get a file from Safari into the Creality app?
- **UNVERIFIED / NOT FOUND.** I found no Creality page that says "use the share sheet / Open In" on iOS. The App Store note about "local files" suggests an in-app file picker (Files app), but I did not find the wording.
- What ZEIM can safely tell Zach today: *download the file, then in the Creality Cloud app use its add/upload option and pick the file from Files.* Mark this "untested".
- Share sheet listing depends on the app declaring document types, which I cannot see from outside. **Test on device** (§8).

### 1.4 Third-party "send to Creality Print" (desktop)
- Manyfold (open-source model manager) added an "Open in Creality Print" button using scheme `crealityprintlink` with the same shape as the other slicers: `crealityprintlink://open?file=<signed url>` (REPORTED; code read: https://github.com/manyfold3d/manyfold/pull/5711 and raw `app/lib/file_handlers/creality_print.rb` and `slic3r_family.rb`). Formats it offers: 3MF, AMF, OBJ, STEP, STL, SVG, with a comment that this comes from reading Creality Print's source.
- Meshy ("Send to Creality Print", user "confirms the browser prompt to open Creality Print") is another third party doing the same (REPORTED, https://www.meshy.ai/integrations/creality-print). Requires Creality Print installed on the computer.
- Creality does not appear to document this scheme in the pages I read. **Label: REPORTED, desktop only, NEEDS TESTING.** Not useful on iPhone/iPad.

---

## 2. Shapr3D

### 2.1 Import formats (official)
From Shapr3D's Help Center "Supported file types" (updated Dec 9, 2025; VERIFIED, read): https://support.shapr3d.com/hc/en-us/articles/7874523890076-Supported-file-types

- **3D bodies (import):** X_T / X_B (Parasolid), STEP, IGES, **STL (for reference only)**, SHAPR, SLDPRT, SLDASM. Enterprise adds CATIA/Creo/NX/Solid Edge/JT.
- **2D:** DWG, DXF. **Images:** PNG, JPG, 2D PDF, TIFF, BMP, ICO, RAW, GIF.
- **OBJ and 3MF are not in the import list.** They appear only under **Export** (3MF, OBJ with colors, STL, STEP, IGES, USDZ, GLB, etc.).
- Plan limits on that page: **Basic** can import "2D and 3D industry-standard formats, limited up to 2 projects only"; Basic export is "low-resolution STL and 3MF only"; Pro has the full export list. (VERIFIED. Check what plan Zach has.)
- Shapr3D's own file-type page says STL meshes are imported "for reference only", and that turning a B-rep into a mesh is easy but "converting a mesh file back into a precise, editable CAD solid often requires manual rebuilding" (VERIFIED, https://www.shapr3d.com/product/cad-file-types).

### 2.2 iPad import path
- Official: in Shapr3D on iPadOS use the **More menu → Import**, or **Import in the Dashboard**, or **Insert → File** inside a project; pick the file (VERIFIED, https://support.shapr3d.com/hc/en-us/articles/7874501645724-Import, updated May 27, 2026). The page also lists the design space limit (1 km³) and advice to check the device has enough memory.
- A file must already be on the iPad (Files app, iCloud Drive, etc.). So ZEIM's job is to get the file into **Files** (download or share sheet → "Save to Files"); Zach then imports from Shapr3D.
- "Open in Shapr3D" from Files / share sheet: **not stated** on the Help Center pages I read. Old community threads show people using Files and "Open in" with mixed results and mention file-extension and cloud-provider problems (REPORTED, https://discourse.shapr3d.com/t/cant-import-files-stp-step-iges/842, 2018-era; may be outdated). **UNVERIFIED on current versions: test.**

### 2.3 Mesh handling and mesh-to-solid
- STL imports are a **mesh used as a reference**. Shapr3D staff on the community forum: "STL-brep conversion is not in the scope of our development" (REPORTED, Oct 2023, https://discourse.shapr3d.com/t/draw-modify-stl-files/28518). Other users report you cannot precisely move/snap on an imported STL (REPORTED, https://discourse.shapr3d.com/t/is-there-any-way-to-work-with-an-imported-stl-precisely/35264).
- A Shapr3D staff post warns that converting a mesh STL to STEP (in a third-party tool) makes one face per triangle, which is too much for Shapr3D (REPORTED, https://discourse.shapr3d.com/t/unable-to-import-step/2862). ZEIM's lithophanes/reliefs are dense meshes (README: up to about 1.4 M triangles at 600 px), so **ZEIM should not offer "convert to STEP"** from a mesh.
- Implication for the CAD vision: lithophanes and photo reliefs are the wrong thing to hand to Shapr3D for editing. A good Shapr3D use is *design a holder/frame/base in Shapr3D and bring it into ZEIM as an STL* (ZEIM Edit already opens STL/OBJ/3MF), or use the STL as a reference to model around.
- Future idea (not researched, UNVERIFIED feasibility): if ZEIM ever builds **primitive-based** parts (plates, frames, text bases), it could write STEP for those. That would be a separate engineering project.

### 2.4 API / URL scheme
- Shapr3D staff: "While it is amongst our long-term plans, at the moment we don't offer a public API." Later reply says it does not offer a public API for custom interfaces or embedding (REPORTED, https://discourse.shapr3d.com/t/shapr3d-api/29917). Plugin requests are feature requests only (REPORTED, https://discourse.shapr3d.com/t/user-creatable-plugins/26921).
- No URL scheme documented in the pages I read. **NOT FOUND.** Call: **NOT POSSIBLE**; file hand-off only.

---

## 3. Printer network APIs and what a web app can realistically do

### 3.1 Per-printer findings

| Printer / firmware | Protocol (evidence) | Auth | Web-app reality |
|---|---|---|---|
| **OctoPrint** | `POST /api/files/{location}` multipart upload (VERIFIED, https://docs.octoprint.org/en/master/api/files.html). CORS must be switched on with `api.allowCrossOrigin` (VERIFIED, https://docs.octoprint.org/en/master/api/general.html and config docs) | API key (`X-Api-Key`, as ZEIM already uses) | Works server-side. ZEIM already implements it (mock-tested only) |
| **Moonraker / Klipper** | `POST /server/files/upload`, multipart, optional `root`, `path`, `print=true` (VERIFIED, https://moonraker.readthedocs.io/en/latest/external_api/file_manager/) | Untrusted clients need `X-Api-Key` or a Bearer JWT; `trusted_clients` IPs get full access; CORS only if `cors_domains` is set (VERIFIED, https://moonraker.readthedocs.io/en/latest/external_api/authorization/ and https://moonraker.readthedocs.io/en/latest/configuration/) | Works server-side. ZEIM already implements it (mock-tested only) |
| **Creality K1 / K1C / K1 Max, stock firmware** | Creality's own protocol, read from OrcaSlicer's `CrealityPrint` host: `GET /info`, `POST /upload/<name>` (multipart, `Authorization: Bearer <key>`), then a **WebSocket on port 9999** with `{"method":"set","params":{"opGcodeFile":"printprt:<path>"}}` to start (VERIFIED in source: https://github.com/SoftFever/OrcaSlicer/blob/main/src/slic3r/Utils/CrealityPrint.cpp; **not Creality-documented**) | Bearer value from slicer settings (what it contains on a real K1: UNVERIFIED) | Needs a new ZEIM printer type. A K1C "2025" hardware revision reportedly has **no web UI on port 80**, though Orca upload/print still worked for that user (REPORTED: https://forum.creality.com/t/k1c-2025-orcaslicer-workarounds-for-missing-web-interface/47164). Ask Zach which K1 and firmware he has |
| **K1 with Moonraker** | Not on by default. Creality's own repo describes an *optional* Fluidd + Moonraker install via root, served on port 4408, with the warning that Moonraker running long-term on the K1 "poses a risk of memory overflow" (VERIFIED: https://raw.githubusercontent.com/CrealityOfficial/K1_Series_Annex/main/fluidd/README_en). Community helper script wiki covers the same (REPORTED: https://guilouz.github.io/Creality-Helper-Script-Wiki/configurations/access-to-web-interface/) | As Moonraker | Do not tell kids/teachers to root a printer. Mention only as an advanced owner option, **REPORTED** |
| **Creality Sonic Pad / Ender** | Creality Help Center has "How to connect Sonic Pad on Creality Cloud" (title only, VERIFIED to exist). I did **not** verify whether Moonraker is exposed. **NOT FOUND / unverified** | n/a | Unverified |
| **Prusa Link** (MK4, XL, Mini, Core One etc.) | OpenAPI in Prusa's repo: `PUT /api/v1/files/{storage}/{path}` (octet-stream), headers `Print-After-Upload` and `Overwrite`; `GET /api/version` advertises `capabilities.upload-by-put`, otherwise fall back to legacy OctoPrint-style POST (VERIFIED, https://raw.githubusercontent.com/prusa3d/Prusa-Link-Web/master/spec/openapi.yaml, header says "version 1.0.0-draft") | **HTTP Digest** auth in the spec (some setups use an API key; unverified) | Implementable server-side. Stub exists. Prusa Connect (cloud): no public third-party API found (searched; not read in depth: **NOT FOUND**) |
| **Bambu Lab** | LAN mode ports: MQTT 8883, FTP 990 + 50000-50100, video 322/6000 (VERIFIED, https://wiki.bambulab.com/en/general/printer-network-ports). Since the 2025 "authorization control" firmware, in normal LAN and cloud mode starting a print from software other than Bambu Studio "will require Bambu Connect"; status pushes and SD-card prints are unaffected. **Developer Mode** (LAN-only, printer-side switch after LAN Only) works "the same as in previous firmware versions" and opens MQTT, live stream and FTP (VERIFIED: https://wiki.bambulab.com/en/software/third-party-integration page dated 03/18/2026 and https://wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode dated 10/14/2025). Developer Mode "will not allow the printer to be connected to Bambu Cloud" (same page) | Access code (MQTT user/password; details UNVERIFIED by me) + FTPS | Only for advanced owners who enable Developer Mode. Not suitable as a default for families/schools. **Bambu Connect URL scheme** `bambu-connect://import-file?path=…` takes an **absolute file-system path** on the same computer (VERIFIED, third-party-integration page), so a website cannot use it |
| **Snapmaker U1** | Firmware is built on Klipper + Moonraker + Fluidd and Snapmaker open-sourced its Moonraker changes (VERIFIED: https://wiki.snapmaker.com/en/FAQ/u1 and repo https://github.com/Snapmaker/u1-moonraker) | Moonraker rules | Likely works with ZEIM's Moonraker type. **Untested.** The wiki also says Snapmaker recommends its own "Snapmaker Orca" slicer for profiles (REPORTED in search excerpt; not confirmed on the page) |
| **Snapmaker J1/J1S/Artisan** | Official **SACP** protocol docs/SDK exist: https://github.com/Snapmaker/Snapmaker-SACP (VERIFIED to exist; I did not read the spec). A community bridge exposes a Moonraker-style API on 7125 and talks SACP on TCP 8888 (REPORTED: https://github.com/goeland86/snapmaker_moonraker) | n/a | Not a quick win. **LATER** |
| **Elegoo Centauri Carbon (stock)** | **SDCP v3.0.0**: UDP broadcast `M99999` on port 3000 for discovery; WebSocket `ws://<ip>:3030/websocket`; file upload by `POST http://<ip>:3030/uploadFile/upload` (multipart, 1 MB packets with MD5/offset/uuid fields) (VERIFIED, official-style spec by the board maker: https://github.com/cbd-tech/SDCP-Smart-Device-Control-Protocol-V3.0.0, also summarized at https://docs.opencentauri.cc/software/api/ which notes Centauri-specific quirks) | Not stated in the parts I read | Implementable server-side, but a chunked upload is more work than Moonraker. **LATER**. Community "COSMOS" firmware gives Moonraker (REPORTED, https://docs.opencentauri.cc/) |
| **Duet / RepRapFirmware** | `POST /rr_upload?name=<path>` with the raw body (VERIFIED, https://github.com/Duet3D/RepRapFirmware/wiki/HTTP-requests) | Session via `rr_connect` | **LATER** |
| **Repetier-Server** | Server API with `x-api-key` header or session (VERIFIED, https://www.repetier-server.com/manuals/programming/API/index.html). Upload command not confirmed by me | API key | **LATER**, unverified |

### 3.2 Browser constraints (why sending must usually go through the ZEIM server)
1. **Mixed content.** MDN: browsers "block insecure requests" from a secure page for most resource types, and "should also block mixed downloads by default"; loopback addresses such as `http://localhost` count as secure origins (VERIFIED: https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Mixed_content). A ZEIM page on HTTPS therefore cannot `fetch()` `http://192.168.x.x` printers. Most printers speak plain HTTP.
2. **Local network access (newer, Chrome-based).** MDN describes a permission prompt and a way to relax mixed-content for local devices (VERIFIED it exists: https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Local_network_access; I read only the introduction). MDN's browser-compat data (v8.1.4, fetched today) shows `Request.targetAddressSpace` in Chrome/Edge 142+ and **not** in Safari or iOS Safari (VERIFIED data: https://unpkg.com/@mdn/browser-compat-data/data.json). So Zach's iPhone/iPad should not rely on it.
3. **CORS.** OctoPrint blocks cross-origin API use unless `allowCrossOrigin` is set; Moonraker unless `cors_domains` is set (VERIFIED: links in §3.1). Asking families to edit printer config is not realistic.
4. **Consequence.** Printer sends are **server-to-printer**. That only works if the ZEIM server can reach the printer's LAN address (same network, VPN, tunnel, or a small relay agent). A cloud-hosted ZEIM cannot reach a home printer (Haruto's K1 research said the same). For the near term the honest options are: (a) ZEIM runs on the user's own network, (b) the user downloads G-code and sends it with their printer's own app, (c) slicer deep link (desktop only).
5. **Cert note for testing on iOS.** A Caddy "internal" certificate is not trusted automatically. Apple: a manually installed certificate profile is not trusted for SSL until you switch on "Enable full trust for root certificates" in Settings > General > About > Certificate Trust Settings (VERIFIED: https://support.apple.com/en-us/102390). This applies to the approved local HTTPS test plan.

---

## 4. iOS web constraints for the Send hub

| Topic | Finding | Evidence |
|---|---|---|
| Web Share API availability | `navigator.share`: Safari 12.1, **iOS Safari 12.2**. `navigator.canShare`: **Safari/iOS Safari 14**. Chrome desktop 128+ (earlier versions partial: Windows/ChromeOS only), Firefox desktop not supported | VERIFIED (MDN compat data v8.1.4; caniuse Web Share page https://caniuse.com/web-share) |
| Requirements | **Secure context (HTTPS or localhost)**; Permissions Policy `web-share`; `share()` needs **transient activation** (a tap), else `NotAllowedError`; files unsupported gives `TypeError`. `canShare()` is for checking and does not need a tap | VERIFIED (MDN https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share and https://developer.mozilla.org/en-US/docs/Web/API/Navigator/canShare) |
| WebKit behaviour | In WebKit's `Navigator.cpp`, `share()` consumes the transient activation, then `canShare()` only checks that files are non-empty and the file feature is enabled. It does **not** filter by file type at that layer | VERIFIED (source read: https://github.com/WebKit/WebKit/blob/main/Source/WebCore/page/Navigator.cpp). The OS share sheet may still limit what it accepts: UNVERIFIED |
| Which file types? | MDN's "usually shareable" list has PDF, images, audio, video, CSS/CSV/HTML/TXT. **No STL, OBJ or 3MF** (MDN notes it is a usual list and says to test with `canShare()`) | VERIFIED (MDN list). Whether iOS accepts `.stl`/`.3mf` (and with what MIME type): **UNVERIFIED, must test** |
| Practical rule | Build the `File` **before** the tap (fetch the blob first), then call `canShare({files})`, then `share()` directly in the click handler. A slow `fetch` between the tap and `share()` risks losing the user activation (my inference from the MDN activation rule; UNVERIFIED how long iOS allows) | Inference |
| Download | HTML `download` attribute on `<a>`: **iOS Safari 13+** (VERIFIED, MDN compat data; WebKit bug 167341 "[iOS] Add support for the download attribute" is RESOLVED FIXED: https://bugs.webkit.org/show_bug.cgi?id=167341). Blob URLs plus `download` and `Content-Disposition: attachment` behaviour for unusual types like `.3mf` on iOS: **UNVERIFIED** | VERIFIED / UNVERIFIED as stated |
| mailto | `mailto:` cannot attach a file (general knowledge, RFC 6068; I did not read a source here). Treat as UNVERIFIED and rely on the share sheet's Mail target | UNVERIFIED |
| PWA install | Safari "Add to Home Screen" via the Share menu; a manifest with `display: standalone` or `fullscreen` makes it a Home Screen web app that opens like an app (VERIFIED: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/). `manifest.display` iOS Safari 11.3 | VERIFIED |
| PWA as a share **receiver** | Web Share **Target** (manifest `share_target`) is `false` for Safari and iOS Safari in the compat data (linked to WebKit bug 194593). So files shared *to* ZEIM from other apps will not work on iOS | VERIFIED data (https://unpkg.com/@mdn/browser-compat-data/data.json) |

---

## 5. Slicer deep links relevant to ZEIM

ZEIM today builds `prusaslicer://open?file=`, `bambustudio://open?file=`, `orcaslicer://open?file=`, `cura://open?file=` links (app/services/handoff.py). All are **desktop** slicers, so none help on an iPhone/iPad. The file URL must be **HTTPS and reachable from the user's computer** (a localhost ZEIM is not).

| Slicer | What I found | Evidence | Call |
|---|---|---|---|
| **OrcaSlicer** | Recognizes `orcaslicer://open`, `prusaslicer://open`, `bambustudio://open` / `bambustudioopen://`, `cura://open` (`libslic3r/Utils.hpp`); `Downloader::start_download` accepts `…open?file=<url>` and downloads it with no domain allow-list in that file (source read: https://github.com/SoftFever/OrcaSlicer/blob/main/src/slic3r/GUI/Downloader.cpp). Uses the last URL segment as the file name, so keep `model.3mf`-style names | VERIFIED (source), runtime untested | **ADOPT** |
| **Cura** | UltiMaker's 5.7 release notes describe "Open in Cura" from Thingiverse for STL, 3MF, OBJ (https://ultimaker.com/learn/ultimaker-cura-5-7-stable-release-notes/). A recent PR describes the handler as `cura://open?file=…` (open PR, https://github.com/Ultimaker/Cura/pull/21537). Whether Cura accepts arbitrary hosts: **not stated** | VERIFIED (feature), host rules UNVERIFIED | **ADOPT**, mark best-effort |
| **PrusaSlicer** | Prusa's tracker issue quotes the check `FileGet::is_subdomain(url, "printables.com")` and "Download won't start. Download URL doesn't point to https://printables.com"; a Prusa team member replied "We currently have no plans to change this restriction" (Dec 2024). A comment (Apr 2025) says Thingiverse was added since. The issue was later closed and is still active in comments as of Oct 2026 | REPORTED (https://github.com/prusa3d/PrusaSlicer/issues/13752) | **FIX**: our `prusaslicer://` button will probably be refused for ZEIM URLs. Hide it or label "download then open", pending a real test |
| **Bambu Studio** | Manyfold's code comment: "Bambu Studio doesn't seem to open anything except 3MF by URL"; on macOS it uses `bambustudioopen://<encoded url>` | REPORTED (raw `bambu_studio.rb` in manyfold3d/manyfold) | **NEEDS TESTING**; offer 3MF only |
| **Creality Print** | See §1.4 (`crealityprintlink://`) | REPORTED | **NEEDS TESTING** |
| **Elegoo Slicer** | Manyfold has `elegooslicer://open?file=` | REPORTED | Out of scope for now |

Official docs for these schemes (Prusa/Orca/Bambu/Creality) were **not found**; the evidence above is source code and third-party integrations, so treat links as best-effort and always offer plain download beside them.

---

## 6. Privacy and safety flags for Kenji (not legal advice)
- Any third-party hand-off (Creality Cloud app, Shapr3D, email, AirDrop) sends a file the user chose; HQ decision already says minors' and student photo-based models are **not** sent outside ZEIM by default. A lithophane STL can embed a recognizable face. Keep "Send" off for class students until Kenji's `send-privacy.md` lands.
- The Creality Cloud app is rated 13+ with user-generated content and social features (App Store page). The Chinese privacy policy lists many SDKs and device identifiers. Do not send under-13 users to it.
- Signed file links (`/f/<token>/…`) used for slicer deep links are valid for 2 hours (README). Anyone with the link can fetch the file in that time. Fine for a desktop slicer, wrong for kids' photo models; keep it behind an explicit user step.
- Bambu Developer Mode and K1 rooting both reduce printer security (Bambu's own Developer Mode text says users accept the risks). Do not push families toward them.

---

## 7. Recommended Send hub plan (ordered)

1. **Download** STL / OBJ / 3MF (already there). Use server `Content-Disposition: attachment` links and a visible file name; test on iPhone/iPad Safari. *(Haruto)*
2. **Share sheet** button (`navigator.canShare({files})` → `share()`), shown **only when the check passes**; otherwise show plain Download. Pre-build the `File` before the tap. Add a small "Save to Files / AirDrop / Mail / Shapr3D / Creality Cloud: depends on what your iPhone shows" note instead of promising a target. Needs HTTPS (the Caddy internal-cert plan, plus iOS certificate trust steps in §3.2). *(Haruto, Sakura)*
3. **Email to yourself** = the share sheet's Mail item for now. No server-side email until accounts + a provider exist (HQ decision). *(Haruto, Kenji)*
4. **Creality Cloud**: a link-out button to the Creality Cloud upload page and a short, clearly "untested" how-to ("download the file, then add it in the Creality Cloud app or website"). No API calls. Contact Creality if Zach wants a real integration. *(Sakura, Daichi)*
5. **Shapr3D**: a "Use in Shapr3D (iPad)" help card: download/save to Files, then Shapr3D → More → Import. Say plainly that STL arrives as a **reference mesh**, not an editable solid; OBJ/3MF are not on Shapr3D's import list. Do not claim editability. *(Aiko, Sakura)*
6. **Printers, one provider at a time** (server-side, same LAN only): keep OctoPrint/Moonraker; then Snapmaker U1 (test with Moonraker), Prusa Link, then Creality (stock K1 protocol), Elegoo SDCP, Bambu Developer Mode (opt-in advanced). Each is labelled "untested" until Zach tries it. *(Haruto)*
7. **Desktop slicer deep links**: keep Orca and Cura; fix or hide the PrusaSlicer button; Bambu 3MF only. *(Haruto)*
8. **Cloud storage (Dropbox/Drive)** via OAuth: later, behind the provider interface (matches Haruto's plan). I did not research these APIs here. *(later)*

Pre-requisite before anything is shared: Engineering's open items from decisions.md (pop-art OBJ/3MF non-manifold edges fixed before Send ships).

---

## 8. What we could not verify, and how to test on real devices

Test on Zach's own iPhone and iPad (Safari, then the Home Screen web app) with the ZEIM test server on HTTPS:

| # | Question | How to test | Pass = |
|---|---|---|---|
| T1 | Does iOS Safari save `model.stl`, `model.3mf`, `model.obj` from a normal link and a blob link? | Tap each Download; look in Files > Downloads | File with right name and extension |
| T2 | Does `canShare({files})` return true for `.stl`, `.3mf`, `.obj`? With which MIME type (`model/stl`, `model/3mf`, `application/octet-stream`)? | Test page that logs the result for each type | `true`, with the share sheet showing the file |
| T3 | Which apps appear for each type: Files, AirDrop, Mail, Shapr3D (iPad), Creality Cloud? | Open the share sheet and note the list | Creality Cloud and Shapr3D appear (or not); record it |
| T4 | Does Creality Cloud app import a file from Files/share sheet? Does it accept ZEIM's plain 3MF? Does it slice STL in the cloud? | Use its add/upload option | File appears and slices |
| T5 | Does Shapr3D import ZEIM's STL (small and ~1 M-triangle)? Is it editable or reference only? Speed/crash? | More → Import | Matches §2; note size limits |
| T6 | Does `share()` still work if the file is fetched *after* the tap? | Compare pre-built vs fetch-on-tap | Decide whether pre-building is mandatory |
| T7 | Does the Home Screen web app behave like Safari for T1 to T3? | Add to Home Screen, repeat | Same results |
| T8 | Which K1 model and firmware does Zach have? Is port 80 serving a web UI? Does Orca's "CrealityPrint" host type connect? | Printer settings > network; Orca on desktop | Decides whether a `creality` type is worthwhile |
| T9 | Do slicer deep links open from a **public HTTPS** ZEIM URL (Orca, Cura, Prusa, Bambu, Creality Print) on a desktop? | Click each on a desktop with the slicer installed | Record which ones load the file |
| T10 | Which Shapr3D plan does Zach have (Basic limits imports to 2 projects and exports low-res STL/3MF)? | Ask Zach | Know the limits |

Not found / not read, for honesty:
- No official Creality statement about third-party import, URL schemes, or iOS Open In. (Searched wiki.creality.com, crealitycloud.com Help Center, Creality GitHub.)
- Prusa Connect third-party API, Bambu blog posts, Elegoo wiki LAN pages, PrusaLink docs on help.prusa3d.com: seen in search results only, not read.
- Cloud-provider APIs (Dropbox, Google Drive, iCloud): not researched.

---

## 9. Hansei (what I would change)
- Several search-engine summaries contradicted each other (for example on Creality Print's URL scheme and iOS share-sheet claims). I discarded them and relied on source files and vendor pages, which cost time but avoided inventing facts.
- The Bambu wiki is script-rendered and my plain fetch returned only boilerplate; I had to open it in a headless browser. A reader should expect the wiki to change.
- Biggest surprises for the team: (1) Shapr3D does not import OBJ/3MF and treats STL as reference only; (2) ZEIM's `prusaslicer://` link is probably refused; (3) the share sheet is not known to accept `.stl`/`.3mf` until tested; (4) there is no public Creality Cloud API.
- I did not touch any app code or other agents' files.

---

## Sources

**Read (VERIFIED or REPORTED as labelled above)**
- Creality Wiki, Creality Cloud: https://wiki.creality.com/en/creality-cloud
- Creality Cloud Help Center index: https://www.crealitycloud.com/help-center/62e39f89224c8be602cc75c3
- Creality Cloud Help Center, upload print files (G-code); no local-file import wording: https://www.crealitycloud.com/help-center/Creality-app-Upload-Print-Files
- Creality Print Quick Start Guide: https://www.creality.com/help/help-creality-print-quick-start-guide
- Creality Cloud privacy policy (Chinese): https://file-cdn.creality.com/privacy-mi.html
- Creality Cloud App Store listing: https://apps.apple.com/us/app/creality-cloud-3d-printing/id1577663728
- Creality forum, uploading 3MF to Creality Cloud (search excerpt): https://forum.creality.com/t/how-to-upload-3mf-files-to-creality-cloud/22430
- Creality forum, K1C 2025 workarounds: https://forum.creality.com/t/k1c-2025-orcaslicer-workarounds-for-missing-web-interface/47164
- Creality K1_Series_Annex Fluidd README: https://raw.githubusercontent.com/CrealityOfficial/K1_Series_Annex/main/fluidd/README_en
- Creality Cloud Cura plugin repo: https://github.com/crealitycloud/CrealityCloudIntegration
- Creality Helper Script wiki (community): https://guilouz.github.io/Creality-Helper-Script-Wiki/configurations/access-to-web-interface/
- OrcaSlicer `CrealityPrint.cpp`: https://github.com/SoftFever/OrcaSlicer/blob/main/src/slic3r/Utils/CrealityPrint.cpp
- OrcaSlicer `Downloader.cpp` and `Utils.hpp`: https://github.com/SoftFever/OrcaSlicer/blob/main/src/slic3r/GUI/Downloader.cpp , https://github.com/SoftFever/OrcaSlicer/blob/main/src/libslic3r/Utils.hpp
- Manyfold PR "Add open in Creality Print": https://github.com/manyfold3d/manyfold/pull/5711 and raw handlers under https://github.com/manyfold3d/manyfold/tree/main/app/lib/file_handlers
- Meshy Creality Print integration: https://www.meshy.ai/integrations/creality-print
- Shapr3D Supported file types: https://support.shapr3d.com/hc/en-us/articles/7874523890076-Supported-file-types
- Shapr3D Import: https://support.shapr3d.com/hc/en-us/articles/7874501645724-Import
- Shapr3D file types page: https://www.shapr3d.com/product/cad-file-types
- Shapr3D community (API, STL, STEP, import threads): https://discourse.shapr3d.com/t/shapr3d-api/29917 , https://discourse.shapr3d.com/t/user-creatable-plugins/26921 , https://discourse.shapr3d.com/t/draw-modify-stl-files/28518 , https://discourse.shapr3d.com/t/is-there-any-way-to-work-with-an-imported-stl-precisely/35264 , https://discourse.shapr3d.com/t/unable-to-import-step/2862 , https://discourse.shapr3d.com/t/cant-import-files-stp-step-iges/842
- Bambu Lab Wiki, third-party integration: https://wiki.bambulab.com/en/software/third-party-integration
- Bambu Lab Wiki, Developer Mode: https://wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode
- Bambu Lab Wiki, printer network ports: https://wiki.bambulab.com/en/general/printer-network-ports
- Prusa-Link-Web OpenAPI: https://raw.githubusercontent.com/prusa3d/Prusa-Link-Web/master/spec/openapi.yaml
- PrusaSlicer issue 13752 (download URL restriction): https://github.com/prusa3d/PrusaSlicer/issues/13752
- Snapmaker Wiki, U1 FAQ: https://wiki.snapmaker.com/en/FAQ/u1 ; U1 Moonraker repo: https://github.com/Snapmaker/u1-moonraker ; SACP repo: https://github.com/Snapmaker/Snapmaker-SACP ; J1S Moonraker bridge (community): https://github.com/goeland86/snapmaker_moonraker
- Elegoo SDCP v3.0.0: https://github.com/cbd-tech/SDCP-Smart-Device-Control-Protocol-V3.0.0 ; OpenCentauri API notes: https://docs.opencentauri.cc/software/api/
- OctoPrint docs: https://docs.octoprint.org/en/master/api/files.html , https://docs.octoprint.org/en/master/api/general.html , https://docs.octoprint.org/en/master/configuration/config_yaml.html
- Moonraker docs: https://moonraker.readthedocs.io/en/latest/external_api/file_manager/ , https://moonraker.readthedocs.io/en/latest/external_api/authorization/ , https://moonraker.readthedocs.io/en/latest/configuration/
- Duet RRF HTTP requests: https://github.com/Duet3D/RepRapFirmware/wiki/HTTP-requests
- Repetier-Server API: https://www.repetier-server.com/manuals/programming/API/index.html
- UltiMaker Cura 5.7 notes: https://ultimaker.com/learn/ultimaker-cura-5-7-stable-release-notes/ ; Cura PR 21537: https://github.com/Ultimaker/Cura/pull/21537
- MDN: https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share , https://developer.mozilla.org/en-US/docs/Web/API/Navigator/canShare , https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Mixed_content , https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Local_network_access
- MDN browser-compat-data v8.1.4 (JSON): https://unpkg.com/@mdn/browser-compat-data/data.json
- caniuse Web Share: https://caniuse.com/web-share
- WebKit `Navigator.cpp`: https://github.com/WebKit/WebKit/blob/main/Source/WebCore/page/Navigator.cpp ; WebKit bug 167341: https://bugs.webkit.org/show_bug.cgi?id=167341
- WebKit blog on Home Screen web apps: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- Apple Support, trust installed certificate profiles: https://support.apple.com/en-us/102390

**Seen only in search results, not read (do not rely on them)**
- Bambu blog posts: https://blog.bambulab.com/firmware-update-introducing-new-authorization-control-system-2/ , https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect/
- Prusa Knowledge Base "Prusa Connect and PrusaLink explained": https://help.prusa3d.com/article/prusa-connect-and-prusalink-explained_302608
- Elegoo Wiki LAN control: https://wiki.elegoo.com/en/centauri-carbon-2-combo/how-to-control-the-printer-via-lan
- Reddit pages were not used.
