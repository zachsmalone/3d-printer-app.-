# Creality K1 support: research (read-only)

Author: Haruto Tanaka (Engineering) · Date: 2026-10-04 · Status: research only, **no app code was changed**.
Nothing here has been run on a real K1. The only thing I executed myself is PrusaSlicer 2.9.2 on this box (section 4).

**Label key**
- **V-official**: read on a Creality page, Creality GitHub repo or Creality manual.
- **V-repo**: read in a public third-party repo or docs (OrcaSlicer, Moonraker, Guilouz wiki). The text is real, but it is not Creality's own statement.
- **V-box**: I ran it on this box.
- **Community**: forum, Reddit or issue-tracker report. Useful, but not authoritative.
- **Unverified**: inference or gap. Treat as untested.

---

## 0. Summary

1. **The profile is easy and well documented.** K1 is 220 × 220 × 250 mm, 0.4 mm nozzle, 300 °C nozzle, 100 °C bed (V-official).
2. **Moonraker is the biggest surprise.** Stock K1 firmware does *not* appear to expose Moonraker on a standard port (V-repo/Community).
   - Creality's own tools use a different LAN protocol: `POST http://<ip>/upload/<file>` plus a WebSocket on port **9999** (V-repo, read from OrcaSlicer source).
   - Moonraker (port 7125, Fluidd on 4408, Mainsail on 4409) only exists after the owner enables root and installs a community add-on (V-official that root exists, V-repo for the add-on).
   - So "wire it through the existing Moonraker flow" will work **only if Zach has rooted his K1 and installed Moonraker**. A stock K1 needs a new `creality` printer type.
3. **Creality Print has a URL scheme, but I cannot confirm it opens a plain model URL** (V-official source, behaviour Unverified). Default to "download + open in app" with clear instructions, and offer OrcaSlicer's `orcaslicer://` (which ZEIM already has) because Orca ships K1 profiles.
4. **G-code:** a K1-aware PrusaSlicer profile works in the PrusaSlicer on this box (V-box). It emits `START_PRINT EXTRUDER_TEMP=… BED_TEMP=…` and `END_PRINT`, which are the macros in Creality's own Klipper config (V-official). It has not run on a printer.
   - ZEIM's *current* slicing call uses a generic profile (Marlin flavour, `G28`, 250 × 210 bed, no macros). It will probably run on a K1 but skips the K1's own start-up routine, and its bed size is wrong for the K1. Unverified on hardware.
5. **Architecture caveat:** "Send to printer" only works if the ZEIM server can reach the printer's LAN address. It does not work from a cloud-hosted ZEIM to a home K1.

---

## 1. K1 printer profile

### 1.1 Base K1 (what Zach has, assumed)

| Item | Value | Label | Source |
|---|---|---|---|
| Build volume | 220 × 220 × 250 mm | V-official | https://www.creality.com/support/creality-k1-3d-printer ; Creality Cloud product page https://www.crealitycloud.com/product/fff-3d-printer/K1-644a3313b508e0e6e4f5d884 ; manual (§1.2) |
| Nozzle diameter | 0.4 mm standard | V-official | same support page |
| Max nozzle temp | 300 °C | V-official | same |
| Max bed temp | 100 °C | V-official | same, and manual §1.2 |
| Filament | 1.75 mm; PLA, TPU95A, PETG, ABS, PA-CF, PLA-CF listed | V-official | support page |
| Max speed / accel | 600 mm/s (lab "Surface Mode" at 0.1 mm layers); typical 300 mm/s; travel 800 mm/s; accel up to 20 000 mm/s² | V-official | https://www.creality.com/products/creality-k1-3d-printer |
| Layer height | 0.1–0.35 mm | V-official | support page |
| Kinematics, extruder | CoreXY, direct drive, auto-leveling | V-official | support page |
| Firmware base | Klipper (Creality fork), `kinematics: corexy`, `max_velocity 800`, `max_accel 20000`, `max_z_velocity 20` | V-official (config in their repo) | https://github.com/CrealityOfficial/K1_Series_Klipper/blob/main/config/K1_CR4CU220812S12_1/printer.cfg (last commit 2025-12-13) |
| Axis limits in Klipper | X 0..229, Y −0.5..226, Z 0..255 (so the *printable* 220 × 220 × 250 sits inside the machine travel) | V-official (config) | same file |
| Heater safety limits in Klipper | extruder `max_temp: 320`, bed `max_temp: 115` (hardware limit; the advertised limits are 300/100) | V-official (config) | same file |
| Storage path used by Klipper | `/usr/data/printer_data/gcodes` | V-official (config) | same file, `[virtual_sdcard]` |

**A discrepancy to note.** Creality's product page calls the K1 nozzle a "copper alloy nozzle", while the support page lists "Nozzle Material: Hardened Steel". OrcaSlicer's K1 profile says `brass`. For slicing this does not matter, but ZEIM should not tell kids the base K1 can print abrasive carbon-fibre filament. Only the K1C is sold with a hardened-steel tip (V-official, https://www.creality.com/products/k1c-carbon-3d-printer).

OrcaSlicer's K1 0.4 profile (V-repo, https://github.com/OrcaSlicer/OrcaSlicer/blob/main/resources/profiles/Creality/machine/Creality%20K1%20(0.4%20nozzle).json) agrees with the numbers above. It adds:
- `printable_area` 220 × 220
- `printable_height` 250
- `gcode_flavor: klipper`
- machine limits: accel 20 000, speed X/Y 800, Z 20
- `retraction_length 0.8`, speed 40, `z_hop 0.4`
- `thumbnails 96x96, 300x300`
- `host_type: crealityprint`
- start gcode `START_PRINT …`, end gcode `END_PRINT`

### 1.2 Variants

| | K1 | K1C | K1 Max |
|---|---|---|---|
| Build volume | 220×220×250 | 220×220×250 | **300×300×300** |
| Nozzle | 0.4, copper/brass-type (see discrepancy above) | 0.4, **hardened-steel tip** | 0.4, hardened steel per Creality's page |
| Max nozzle / bed | 300 / 100 °C | 300 / 100 °C | 300 °C (nozzle); bed temp not checked this session |
| Extras | optional camera | AI camera, air filter, CF filaments | LiDAR first-layer check, AI camera, air filter |
| Source | pages above | https://www.creality.com/products/k1c-carbon-3d-printer and https://www.creality.com/support/k1c-carbon-3d-printer | https://www.creality.com/products/creality-k1-max-3d-printer |

**K1C 2025 revision (Community, with an official forum post):**
- Some newer "K1C 2025" units run a different firmware branch (v1.0.0.x).
- They reportedly have **no root option** and no web UI on port 80.
- They reportedly do expose a Moonraker-compatible API on **7125**, built by Creality (`nexusp`).
- Source: https://forum.creality.com/t/k1c-2025-orcaslicer-workarounds-for-missing-web-interface/47164 (one user's report, December 2025).
- Do not assume this applies to Zach's K1.

**Suggested ZEIM preset "Creality K1"** (values from V-official unless noted):
`bed_x=220, bed_y=220, max_z=250, nozzle=0.4, filament=1.75, bed_shape=rectangular, origin=front-left (0,0)`.
- Origin is V-repo (Orca `printable_area 0x0…220x220`).
- Keep the safe-print temperature limits at 300/100 °C, not Klipper's 320/115.

---

## 2. Creality Print (slicer): deep link / CLI

Repo: https://github.com/CrealityOfficial/CrealityPrint (AGPL-3.0, default branch `master`, last push 2026-09-24, README says "Creality Print 6.0"). Latest release page seen: https://github.com/CrealityOfficial/CrealityPrint/releases/tag/v6.3.1 (Linux AppImage for Ubuntu 20.04/24.04 plus Windows/macOS builds; per search summary, exact asset list not opened).

| Question | Finding | Label |
|---|---|---|
| Registered URL scheme? | Yes. `crealityprintlink://`. Linux: `x-scheme-handler/crealityprintlink` in `src/platform/unix/CrealityPrint.desktop`. macOS: `CFBundleURLSchemes = CrealityPrintLink` in `Info.plist.in`. | V-official (source) |
| Does it accept `…open?file=<url>` like the others? | The shared downloader regex is `^(crealityprintlink\|orcaslicer\|prusaslicer\|bambustudio\|cura)://open[/]?\?file=` (`src/slic3r/GUI/Downloader.cpp`). So `crealityprintlink://open?file=<url>` *parses*. Separately, `crealityprintlink://open?code=…` is handled as a different (cloud "open link") command in `GUI_App.cpp`. | V-official (source) |
| Does a plain HTTP model URL then actually import? | **Unknown.** In that downloader, when the URL is a "Creality" one, it does not download the file itself. It sends the string to `Plater::request_model_download`, which fires an "import model" event (probably Creality Cloud model links). I could not find the definition of `is_creality_open` to confirm. | **Unverified** |
| Windows registration | I did not find the registry entries in `package/installer.nsi` (so unknown whether the Windows installer registers the scheme). | Unverified |
| Command-line open file | The app is registered as a handler for STL/3MF/OBJ/AMF (`MimeType=` in the `.desktop` file), so `CrealityPrint <file>` should open it. | V-official (desktop file), behaviour Unverified |
| Headless slice | README: `CrealityPrint.exe --slice 0 --outputdir <dir> [--load_settings "a.json;b.json"] [--load_filaments "f.json"] <model>`; `--slice N` = plate N, 0 = all. Note the underscore spelling in `--load_settings`. | V-official (README) |
| Official URL to download | https://www.crealitycloud.com/software-firmware/software ; wiki https://wiki.creality.com/en/software/6-0/Quick-Start | V-official |
| LAN print | "LAN Print" button → pick printer → "One-click Print". | V-official (wiki) |

**Recommendation for the Print dialog**
1. Add "Creality Print" as a choice, labelled honestly:
   - Default action: **Download the 3MF/STL, then open it in Creality Print** (File ▸ Open, or double-click), with a three-line how-to.
   - Show a "Try open-in-app link" button for `crealityprintlink://open?file=…`, marked **experimental, not confirmed**, until Zach tries it.
2. Also offer **OrcaSlicer** (`orcaslicer://open?file=` already works in ZEIM). Orca ships K1 machine, process and filament profiles and a "CrealityPrint" send-to-printer host type (V-repo).
3. Keep the Creality Print link behind the existing signed 2-hour file link, as for the other slicers.

---

## 3. Network send: what a K1 actually exposes

### 3.1 Findings

| Claim | Label | Source |
|---|---|---|
| Creality's own tools (Creality Print, OrcaSlicer's "CrealityPrint" host type) send to a K1 by **HTTP `GET /info`** (test), **`POST http://<ip>/upload/<file>`** (multipart), then **a WebSocket on port 9999** with `{"method":"set","params":{"opGcodeFile":"printprt:/usr/data/printer_data/gcodes/<file>"}}` to start. | V-repo | OrcaSlicer `src/slic3r/Utils/CrealityPrint.cpp` https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/slic3r/Utils/CrealityPrint.cpp |
| In that code the K1 family is named `K1`, `K1 SE`, `K1C`, `K1_CFS-C`; the G-code folder is `/usr/data` for K1-family and `/mnt/UDISK` for others (K2). Frames must be TEXT; heart-beat messages must be answered with `ok`; the K1 may close the socket right after accepting the start command. | V-repo | same file |
| Optional API key goes in `Authorization: Bearer <key>`. Most K1s on a home LAN seem to need none. | V-repo / Community | same file; https://github.com/joeltelling/print-farm-manager/pull/20 |
| Someone drove that exact flow end to end on a **real K1, firmware 1.3.0** (upload + start, status via WS 9999), and the same on a fleet of K1 Max. | Community (PR author's test claim; not independently reproduced) | joeltelling/print-farm-manager PR #20 |
| **Stock K1 firmware does not include Moonraker** on a standard port. Moonraker comes with the community mods (Guilouz Helper Script; "Guppy Mod"/Simple AF). | Community / V-repo | HelixScreen docs https://helixscreen.org/dev/printers/creality-k1/ ; https://github.com/prestonbrown/helixscreen/blob/main/docs/devel/printer-research/CREALITY_K1_SERIES_RESEARCH.md ; Guilouz wiki https://guilouz.github.io/Creality-Helper-Script-Wiki/helper-script/moonraker-k1/ |
| Creality officially provides **root access** on K1/K1 Max firmware ≥ V1.3.2.1: Settings ▸ Root Account Information ▸ accept warning ▸ view password. Their own notes warn: "Enabling services like Moonraker may occasionally lead to excessive memory usage and system crashes", and that root-related support is not provided. | V-official | https://github.com/CrealityOfficial/K1_Series_Klipper/releases/tag/V1.3.2.1 |
| After root + the Helper Script's "Moonraker and Nginx": **Moonraker 7125** (default per Moonraker docs), **Fluidd 4408**, **Mainsail 4409**. Creality's own web UI stays on port 80. | V-repo | https://guilouz.github.io/Creality-Helper-Script-Wiki/configurations/access-to-web-interface/ ; Moonraker docs https://moonraker.readthedocs.io/en/latest/configuration/ |
| Moonraker auth defaults: **no key needed from `trusted_clients`** (IPs/CIDRs the owner lists); otherwise an API key (`X-Api-Key`) or login. A community K1 `moonraker.conf` trusts all private ranges and sets `force_logins: False`. | V-repo | Moonraker docs (above); https://github.com/coprint/Printer-Config-Files/blob/main/Creality/K1/moonraker.conf |
| The K1 reportedly has only ~256 MB RAM (so a big-file upload or too many services can crash it). | Community | HelixScreen research doc above |
| Community mods sometimes stop working after a Creality firmware update (users re-run the Helper Script). Factory reset removes them. | Community / V-repo | https://www.reddit.com/r/crealityk1/comments/1auknec/cant_access_fluidd_web_interface_k1_max/ ; Guilouz page ("must be repeated after restoring to factory settings") |
| Creality Cloud: the printer can also be bound to Creality Cloud. LAN printing via Creality Print is a separate path. | V-official | support page: "File Transfer: USB Flash Drive, LAN, Cloud Printing" |

**So the answer is "it depends on how the K1 is set up."**
- **Stock K1 (no root):** the usable path is Creality's LAN protocol: HTTP upload on port 80 plus WS 9999. Moonraker is not there.
- **Rooted K1 + Helper Script:** standard Moonraker on **7125**, usually with no key needed on the home network.
- **K1C 2025 revision (maybe):** reportedly a Creality-built Moonraker-compatible service on 7125 with no root (Community, single report).
- **Port 4408 is the Fluidd *web page*, not the API.** Do not put 4408 in the printer URL. Use `http://<ip>:7125`.

### 3.2 What ZEIM does today (read from `app/services/printers.py`, `app/api/printing.py`, `app/services/settings.py`)

- Printer types: `octoprint`, `moonraker` implemented; `prusalink`, `bambu`, `duet`, `repetier` are stubs.
- Moonraker send: `httpx.Client(base_url=printer.url)`, header `X-Api-Key` if a key is set, then `POST /server/files/upload` with form `root=gcodes`, `print=true|false`. Success = HTTP < 300. This matches Moonraker's documented upload endpoint (V-repo).
- `POST /api/send/{bid}`:
  - requires `guards.require_send` (adult account or admin token on a shared server; students refused);
  - slices with `slicer.slice_model(...)`, using the printer's `bed_x`/`bed_y`;
  - then calls `printers.send`.
- `POST /api/slice/{bid}` hard-codes `(250, 210)` as the bed.
- `settings.save_from_client` stores `name, type, url, api_key, bed_x, bed_y`. The bed defaults to 250 × 210. The URL must start with `http(s)://` for implemented types.
- There is **no "Test connection"** function or route yet.

### 3.3 What would need to change (list only, nothing edited)

**A. Make a rooted/Moonraker K1 work (small)**
1. `printers.py` `TYPES`: sharpen the Moonraker hint to say:
   - "Creality K1: needs root + Moonraker (community add-on). Use `http://<printer-ip>:7125`, **not** the Fluidd page (4408)."
   - Add a "Creality K1 (rooted, Moonraker)" preset that pre-fills `bed_x=220, bed_y=220`.
2. `settings.py`: add optional printer fields `profile` (e.g. `creality_k1`), maybe `max_z`. `PRINTER_FIELDS` currently ignores anything else.
3. `printing.py::slice_build`: use the same per-printer bed/profile as `send_to_printer`. Today "Slice" and "Send" can disagree about bed size.
4. After upload with `print=true`, optionally read the Moonraker reply (`{"item": …, "print_started": …}`) so the UI can say "started" vs "queued" (not checked in this session; Unverified).

**B. Make a stock K1 work (medium, new code)**
5. New printer type `creality` in `printers.py`:
   - `test`: `GET {url}/info` (expect JSON, maybe `model`), then optionally a WebSocket connect to `ws://<host>:9999` and read one frame.
   - `send`: `POST {url}/upload/<name>` as **multipart** (raw-body posts reportedly corrupt files, OrcaSlicer #8128, via PR #20 text), then WS `opGcodeFile` if `start=true`.
   - Needs a WebSocket client dependency (e.g. `websockets`). Details to follow: sanitize filename (spaces → `_`), answer `heart_beat` with `ok`, tolerate the socket closing early, K1 path `/usr/data/printer_data/gcodes/`.
   - The code is public (OrcaSlicer, AGPL); reimplement from the protocol description rather than copying code, and ask Kenji/legal about licence handling.
6. `guards`/UI: the printer-address field should accept a plain IP for this type.

**C. Test Connection (small, either type)**
7. New route, e.g. `POST /api/printers/{id}/test` (same guard as `/api/send`, adults/admin only; never expose to class students).
8. Behaviour per type (all with a 5 s timeout, no secrets in responses):

| Type | Calls | OK when | Friendly messages |
|---|---|---|---|
| moonraker | `GET /server/info` then `GET /printer/info` (both documented, V-repo) | `klippy_state == "ready"` and printer `state == "ready"` | "Found the printer service but the printer is not ready (state=…)." / "Nothing answers at that address. For a K1 this usually means Moonraker is not installed, or you used port 4408 instead of 7125." / 401-403: "Printer asked for a key." |
| creality | `GET /info`; optional WS handshake on 9999 | HTTP 200 JSON | "Reached a Creality printer (model …)." / "Port 80 answers but not like a Creality printer." |
| octoprint | `GET /api/version` | 200 | (existing key hint) |

   Return `{ok, message, detail}`. Show the printer model/Klipper state read-only. Never send a print command in a test.

**D. Security / hosting**
9. The ZEIM server must be on the same network as the K1. Document this in the UI: "Send to printer works when ZEIM runs at home or school, not from the internet."
10. Printer addresses are an SSRF surface (the server connects to whatever a settings user enters). Already behind the admin/adult guard. Keep it that way, and consider blocking non-private addresses.

---

## 4. G-code compatibility and slicer recommendation

### 4.1 What the K1 expects (V-official, Creality's Klipper config `gcode_macro.cfg` for the K1 board)

- `START_PRINT` takes `EXTRUDER_TEMP` and `BED_TEMP`, and does the K1's own homing, nozzle clean, leveling calibration and purge line. https://github.com/CrealityOfficial/K1_Series_Klipper/blob/main/config/K1_CR4CU220812S12_1/gcode_macro.cfg
- `END_PRINT` turns off heaters/fans, parks and releases motors.
- `PAUSE`, `RESUME` and `CANCEL_PRINT` exist.
- OrcaSlicer's K1 profile (V-repo) wraps those with: `START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]` / `M204 S2000` / `M109 S…` / `G1 Z3 F600` / `M83` / `G92 E0` / `G1 Z1 F600` and `END_PRINT`.

### 4.2 Current ZEIM output (V-box)

`prusa-slicer --export-gcode --layer-height 0.2 --center 125,105 --bed-shape 0x0,250x0,250x210,0x210 …` produces G-code starting `M104 S200`, `G28`, `M109 S200`, `M82`, ending `M104 S0`, `G28 X0`.
- Klipper accepts `G28`/`M104`/`M109`, so it would *probably* print.
- It skips the K1's calibration and purge macros (Unverified on hardware).
- The bed is 250 × 210 versus the K1's 220 × 220. A model near the edge could be placed out of range (Y up to 210 is fine, but X beyond 220 is not).

### 4.3 Option 1: PrusaSlicer with a K1 `.ini` (recommended first step)

- PrusaSlicer 2.9.2 is installed at `/usr/bin/prusa-slicer` (V-box). **OrcaSlicer is not installed** (`which orca-slicer orcaslicer` found nothing). Creality Print is not installed.
- I wrote an experimental profile: **`reports/creality-k1-prusaslicer-experimental.ini`** (also saved at `/workspace/scratch/k1/k1_prusa.ini`).
- It reproduces the values from Orca's K1 profile and Creality's Klipper config. Values I invented as placeholders: temperatures 220/60, which are **not** from a Creality source.
- **V-box result:** `prusa-slicer --export-gcode --load k1_prusa.ini --center 110,110 --layer-height 0.2 -o k1_test.gcode a_gear_bracket_binary.stl` succeeded (about 6 s).
  - The output has `; gcode_flavor = klipper` and `; bed_shape = 0x0,220x0,220x220,0x220`.
  - It contains `START_PRINT EXTRUDER_TEMP=220 BED_TEMP=60`, `M204 S2000`, `M109 S220`, and ends with `END_PRINT`.
  - All moves are inside X 73.8–146.2, Y 73.8–146.2, Z ≤ 8.4 mm.
  - It has 96×96 and 300×300 thumbnail blocks.
- **Not tested on a K1.**

```ini
# reports/creality-k1-prusaslicer-experimental.ini  (excerpt)
bed_shape = 0x0,220x0,220x220,0x220
max_print_height = 250
nozzle_diameter = 0.4
filament_diameter = 1.75
gcode_flavor = klipper
use_relative_e_distances = 1
machine_limits_usage = time_estimate_only      # "emit_to_gcode" is refused with klipper flavour
machine_max_acceleration_x = 20000   (and y, extruding, travel; z 300; e 5000; retracting 5000)
machine_max_feedrate_x = 800 (y 800, z 20, e 100)
retract_length = 0.8 ; retract_speed = 40 ; retract_lift = 0.4
temperature = 220 ; first_layer_temperature = 220 ; bed_temperature = 60 ; first_layer_bed_temperature = 60   # placeholders
thumbnails = 96x96,300x300
start_gcode = START_PRINT EXTRUDER_TEMP={first_layer_temperature[initial_extruder]} BED_TEMP=[first_layer_bed_temperature]\nM204 S2000\nM109 S{first_layer_temperature[initial_extruder]}\nG1 Z3 F600\nM83\nG92 E0\nG1 Z1 F600
end_gcode = END_PRINT
```

Known rough edges:
- PrusaSlicer inserts its own `M190 S<bed>` *before* the start G-code, so the bed pre-heats and waits before `START_PRINT` homes. It is harmless but a little slower. Fix later if needed.
- Orca's profile also sends `T0`, which I left out.
- Speeds and accelerations other than machine limits are PrusaSlicer defaults. That means a slow, conservative print rather than a fast Creality-style print.
- Placeholder temperatures must come from a filament preset (PLA/PETG). Take them from Orca's "Generic PLA HF @Creality" etc., but I did not read those files.
- Can the ini be applied by the app? `slicer.slice_model` currently builds a long `--layer-height … --bed-shape …` command line. It would need a `--load <profile.ini>` argument plus overrides for layer height, infill, supports and brim.

| Pros | Cons |
|---|---|
| Already installed and used by ZEIM; no new dependency | K1-tuned fast speeds, input-shaping-aware settings and Creality's tested process presets are not in PrusaSlicer |
| One small `.ini`; reproducible in tests (check `START_PRINT`, bed range) | Creality's thumbnail format, flush/purge handling and "Creality-specific" G-code comments are unverified on the K1 screen |
| Output verified to run in PrusaSlicer 2.9.2 on this box | Needs a real K1 run to confirm the macros accept the call (e.g., are `EXTRUDER_TEMP`/`BED_TEMP` handled the way I read them) |

### 4.4 Option 2: OrcaSlicer CLI with its built-in K1 profiles (recommended later, if Option 1 prints well)

- Orca has K1, K1C, K1 Max machine files and matching process and filament presets (V-repo, e.g. `resources/profiles/Creality/machine/Creality K1 (0.4 nozzle).json`).
- Headless usage is documented: `orca-slicer model.stl --load-settings "process.json;printer.json" --load-filaments filament.json --slice 0 --outputdir <dir>` (V-repo, https://www.orcaslicer.com/wiki/cli/cli_mode).
- Setting overrides are `--layer-height=0.2` style flags (same page).
- Orca's ZEIM-friendly bonus: its "CrealityPrint" host type is the reference implementation of the stock K1 upload protocol (V-repo).
- ZEIM's `slicer.py` already lists `orca-slicer` among its candidate executable names, but the command line it builds is PrusaSlicer-style and would not work with Orca without changes.

| Pros | Cons |
|---|---|
| Closest to what Creality users expect (K1-tuned profiles, speeds, start/end G-code) | Not installed here; large AppImage; headless/Linux needs not tested (Unverified) |
| The profile JSONs use `inherits` (e.g. from `fdm_creality_common`), so the CLI likely needs them flattened/merged first (Unverified) | CLI flags and profile loading are more fiddly than PrusaSlicer's `.ini` |
| Same slicer family as Creality Print (Creality Print 6 is derived from the Orca/Bambu codebase; see its source) | AGPL-3.0 (as with PrusaSlicer). Running it as a separate program is normal, but redistribution (Docker image) deserves a legal check by Kenji |

### 4.5 Option 3: Creality Print CLI (not recommended now)

`CrealityPrint --slice 0 --outputdir … --load_settings … --load_filaments …` is documented in its README (V-official). It would give exact Creality profiles, but I could not confirm it runs headless on Linux without a display, how its profile JSONs are laid out, or its stability. Revisit only if Zach prefers Creality Print.

### 4.6 Recommendation

1. **Now (cheap, testable):** add a "Creality K1" printer preset (220 × 220 × 250) that selects Option 1's `.ini`; fix `/api/slice` to use the same bed as `/api/send`.
2. **Ask Zach to print one small test** (10 mm cube) from that G-code, ideally via USB first (zero network risk), and report what the printer did in its first minute.
3. **Only then** consider Orca CLI for faster, K1-tuned output.
4. Always tell the user "K1 support: experimental, tested on the maker's own printer" until Zach confirms.

---

## 5. Verified vs unverified

| # | Claim | Status |
|---|---|---|
| 1 | K1 build volume 220×220×250, 0.4 nozzle, 300 °C / 100 °C | **Verified** (Creality pages + manual) |
| 2 | K1 Klipper limits, `START_PRINT`/`END_PRINT` macro parameters | **Verified** (Creality repo config, for board `CR4CU220812S12_1`; other board revisions may differ) |
| 3 | Nozzle material of base K1 (brass/copper vs hardened steel) | **Conflicting** sources (Creality's own pages disagree) |
| 4 | Creality Print has `crealityprintlink://` and accepts a `file=` form in its URL regex | **Verified in source** |
| 5 | Creality Print actually opens a plain model URL from `crealityprintlink://open?file=` | **Unverified**, test with Zach |
| 6 | Creality Print / OrcaSlicer CLI headless on this Linux box | **Unverified** (neither installed; only the flags are documented) |
| 7 | Stock K1 firmware has no Moonraker on 7125 | **Community-reported**; consistent across several sources, but not confirmed by Creality |
| 8 | Stock K1 LAN upload = HTTP `/upload/` + WS 9999 | **Verified in OrcaSlicer source**; **Community** hardware test on K1 fw 1.3.0 |
| 9 | Rooted K1 + Helper Script gives Moonraker 7125 / Fluidd 4408 / Mainsail 4409 | **Verified in community docs** (not run by me) |
| 10 | Moonraker needs no key from a trusted LAN IP (default K1 community config) | **Verified in docs/config**; unverified on Zach's printer |
| 11 | ZEIM's existing Moonraker upload call works on a K1 with Moonraker | **Unverified** (works on mock servers; real hardware untested) |
| 12 | Prusa `.ini` slices and emits `START_PRINT`/`END_PRINT`, stays within 220×220 | **Verified on this box** |
| 13 | That G-code prints correctly on a K1 | **Unverified** |
| 14 | ZEIM's current generic G-code prints on a K1 | **Unverified** (likely, but skips K1 start-up routine) |
| 15 | K1C 2025 exposes Moonraker-compatible API on 7125 without root | **Community, single report** |

---

## 6. Questions for Zach (short, non-technical)

Please answer what you can, no need to be exact.

1. **Which printer, exactly?** Is the label on the back/front "K1", or "K1C"? Is it a 2025 model?
2. **Software version.** On the printer screen: Settings ▸ About (or similar). What does the firmware version say?
3. **Did you turn on "Root Account Information"?** Have you installed Fluidd/Mainsail or any add-on? (If you don't know, that means "no".)
4. **What do you use to print now?** Creality Print by Wi-Fi, a USB stick, the phone app/Creality Cloud?
5. **On your computer, with the printer on the same Wi-Fi**, open a browser and type `http://<printer-IP>`. What do you see? (A Creality page, Fluidd, nothing?) The IP is in the printer's Wi-Fi settings.
6. **Is the computer that runs ZEIM on the same home network as the printer?**
7. **Test print.** Can you print a tiny 10 mm cube from a file we give you (via USB first) and tell us: did it home, clean the nozzle, level the bed, print the first layer?
8. **Creality Print on your computer.** Is it installed? Which one? Try our "Open in Creality Print" link when it exists and tell us whether the model appears.
9. **Which filament** do you usually load (PLA, PETG…) and what temperatures do you normally use?
10. **Are you OK with us labelling K1 support "experimental" until you have tested it?**

---

## 7. Hansei (what could be wrong with this research)

- Several statements about stock K1 firmware come from community write-ups and from reading OrcaSlicer's code, not from Creality's documentation. I found no official Creality page that describes the LAN protocol.
- Search summaries sometimes disagreed (one claimed Moonraker is "available" on stock, another "not"). I kept only claims backed by a primary file I opened, and downgraded the rest to "Community".
- I did not open Creality Print's Windows registration or the definition of the Creality URL branch, so the deep-link answer is incomplete.
- I did not read Orca's K1 process/filament JSONs, so print speeds and temperatures are still defaults.
- The Klipper config I used is for K1 board variant `CR4CU220812S12_1`; Zach's printer may use a different variant.

## 8. Sources (all opened this session unless marked)

- Creality K1 support page: https://www.creality.com/support/creality-k1-3d-printer
- Creality K1 product page: https://www.creality.com/products/creality-k1-3d-printer
- Creality Cloud K1 page (spec table): https://www.crealitycloud.com/product/fff-3d-printer/K1-644a3313b508e0e6e4f5d884
- K1 user manual (via search result, spec table): https://m.media-amazon.com/images/I/D1TRMEVDkyL.pdf (not opened directly; text came from the search extract)
- K1C product / support: https://www.creality.com/products/k1c-carbon-3d-printer ; https://www.creality.com/support/k1c-carbon-3d-printer ; wiki https://wiki.creality.com/en/k1-flagship-series/k1c
- K1 Max product page: https://www.creality.com/products/creality-k1-max-3d-printer
- Creality Klipper repo (config + macros): https://github.com/CrealityOfficial/K1_Series_Klipper (`config/K1_CR4CU220812S12_1/`)
- Firmware V1.3.2.1 notes (root guide): https://github.com/CrealityOfficial/K1_Series_Klipper/releases/tag/V1.3.2.1
- Creality Print repo: https://github.com/CrealityOfficial/CrealityPrint (README, `Downloader.cpp`, `GUI_App.cpp`, `CrealityPrint.desktop`, `Info.plist.in`); wiki https://wiki.creality.com/en/software/6-0/Quick-Start
- OrcaSlicer CrealityPrint host: https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/slic3r/Utils/CrealityPrint.cpp
- OrcaSlicer K1 profile: https://github.com/OrcaSlicer/OrcaSlicer/tree/main/resources/profiles/Creality/machine
- OrcaSlicer CLI wiki: https://www.orcaslicer.com/wiki/cli/cli_mode
- Moonraker docs: https://moonraker.readthedocs.io/en/latest/configuration/ ; https://moonraker.readthedocs.io/en/latest/external_api/server/ ; https://moonraker.readthedocs.io/en/latest/external_api/printer/ ; https://moonraker.readthedocs.io/en/latest/external_api/file_manager/
- Guilouz Helper Script wiki: https://guilouz.github.io/Creality-Helper-Script-Wiki/helper-script/moonraker-k1/ ; https://guilouz.github.io/Creality-Helper-Script-Wiki/configurations/access-to-web-interface/
- SimplyPrint K1 guide: https://simplyprint.io/setup-guide/creality/k1/on-printer
- HelixScreen K1 notes: https://helixscreen.org/dev/printers/creality-k1/
- Creality LAN API connector PR with real-K1 test: https://github.com/joeltelling/print-farm-manager/pull/20
- Creality forum, K1C 2025: https://forum.creality.com/t/k1c-2025-orcaslicer-workarounds-for-missing-web-interface/47164
- Reddit r/crealityk1 thread on 4408 not loading: https://www.reddit.com/r/crealityk1/comments/1auknec/cant_access_fluidd_web_interface_k1_max/
- Community K1 `moonraker.conf`: https://github.com/coprint/Printer-Config-Files/blob/main/Creality/K1/moonraker.conf
