# ZEIM slicer and infill: engineering plan

Author: Haruto Tanaka (Engineering) · Date: 2026-10-04 (evening) · Status: **PLAN + MEASUREMENTS ONLY. No file under `app/`, `static/` or `tests/` was changed.**
Scratch runs are in `/tmp/h_infill/` (outside the repo). Everything labelled **[box]** I ran myself on this machine with PrusaSlicer 2.9.2 (Debian `2.9.2+dfsg-1`). Nothing here has run on a real K1 or a real phone.

**Voice.** ZEIM aims to be the best place for families, classrooms and makers to turn ideas into prints, free. This plan is about earning "slice it right in ZEIM". Sections that say *verified / unverified* are for engineering and are deliberately plain; launch copy comes from the claims table in `reports/catalog-spec.md` §14.

**Label key:** **[box]** run here · **[help]** read in `prusa-slicer --help-fff` here · **[src]** public page I read (URL given) · **[est]** my estimate, not measured · **[unverified]** do not repeat as fact.

---

## 0. Summary (read this first)

1. **Infill is a real choice today.** The installed PrusaSlicer accepts **18 `fill_pattern` values** [help] and all 18 sliced a test model without error [box]. A 19th, made-up value fails with a clear error [box]. ZEIM's current call passes only `--fill-density` and never a pattern, so users silently get PrusaSlicer's CLI default (`stars` per `--help-fff`) [help].
2. **Infill often matters less than people think, and ZEIM can say so with numbers.** On Zach's open-top box (2.33 mm walls) every pattern at 10–40 % came out at 157–161 g and within 11 minutes of each other [box] (§1.4). On a solid-ish 50 mm sphere, lightning used about half the filament of gyroid at 15 % (12.5 g vs 22.0 g) [box]. A "what will this change?" readout, from the slicer's own numbers, is the wow feature (§1.7).
3. **Phase A (PrusaSlicer as the engine) is small: about 11–12 working days for the core, 14–15 with the readout and licence hygiene** for K1-first slicing with presets, supports, brim, stats, G-code and 3MF export, a job queue and tests. The engine, K1 profile and stats parsing already exist in `app/services/slicer.py` and `app/profiles/creality_k1.ini`.
4. **Phase B (in-browser layer preview) is about 8–10 days**, using the vendored three.js and a server-side G-code → compact-layers converter. Phone performance is a design target, not yet measured (§2.B).
5. **Phase C (our own engine) is a long-term research track.** Public MIT-licensed code exists (Kiri:Moto, `GridSpace/grid-apps`) that is worth a 3-day spike. A from-scratch engine to PrusaSlicer parity is **months**, so it stays out of the near-term roadmap.
6. **Licensing needs counsel before launch.** PrusaSlicer is AGPL-3.0. Calling it as a separate command-line program from a hosted app is, on the public facts, a common and plausible pattern, and Prusa's own FAQ says a cloud slicing service is allowed provided the source rules are met. But the facts that decide it (modifications, how we ship the container, how "separate" our program is) are things a lawyer must confirm. **NEEDS COUNSEL** (§3).
7. **Resin:** no resin slicing in Phase A. Resin users get a clean STL (and later a resin-checked STL, MAKE-16) and a how-to for Chitubox / Lychee. PrusaSlicer's own SLA export makes PNG layers for Prusa-format printers, which is not what Chitubox-class printers read, so we do not promise it [help].

---

## 1. Infill

### 1.1 What the installed PrusaSlicer supports (verified here)

`prusa-slicer --help-fff` [help] and test slices [box], PrusaSlicer 2.9.2:

| Key | CLI flag | `.ini` key | Allowed values (from `--help-fff`) | Run here? |
|---|---|---|---|---|
| Sparse infill pattern | `--fill-pattern` | `fill_pattern` | rectilinear, alignedrectilinear, grid, triangles, stars, cubic, line, concentric, honeycomb, 3dhoneycomb, gyroid, hilbertcurve, archimedeanchords, octagramspiral, adaptivecubic, supportcubic, lightning, zigzag (CLI default: `stars`) | **All 18 sliced OK [box]**; `bogus` rejected [box] |
| Infill density | `--fill-density` | `fill_density` | 0 %–100 % (CLI default 20 %) | 5, 10, 15, 20, 30, 40, 60 OK; **100 % with any non-rectilinear pattern is refused**: "The selected fill pattern is not supposed to work at 100% density" [box]. 100 % with `rectilinear` works [box] |
| Infill angle | `--fill-angle` | `fill_angle` | degrees, default 45 | in help only |
| Top surface pattern | `--top-fill-pattern` | `top_fill_pattern` | rectilinear, monotonic, monotoniclines, alignedrectilinear, concentric, hilbertcurve, archimedeanchords, octagramspiral (default monotonic) | in help only; `monotonic` ran as the default |
| Bottom surface pattern | `--bottom-fill-pattern` | `bottom_fill_pattern` | same list | in help only |
| Walls | `--perimeters` | `perimeters` | integer | ran with 3 [box] |
| Top / bottom solid layers | `--top-solid-layers`, `--bottom-solid-layers` | same with `_` | integer | ran with 5 / 4 [box] |
| Combine infill layers | `--infill-every-layers` | `infill_every_layers` | integer (thicker infill, thin walls) | in help only |
| Force solid below area | `--solid-infill-below-area` | `solid_infill_below_area` | mm², default 70 | in help only |
| Supports | `--support-material` (+ `--support-material-auto`, `--support-material-buildplate-only`, `--support-material-threshold`) | `support_material`, … | boolean / degrees | `--support-material --support-material-auto` ran: 401 `;TYPE:Support` blocks in the dragon's G-code [box] |
| Support style | `--support-material-style` | `support_material_style` | grid, snug, **organic** (default grid) | `organic` ran OK [box] |
| Brim | `--brim-width`, `--brim-type` | `brim_width`, `brim_type` | mm; outer_only / inner_only / outer_and_inner / no_brim | width 5 ran [box] |
| Raft | `--raft-layers` | `raft_layers` | integer | ran with 2 [box] |
| Layer height | `--layer-height`, `--first-layer-height` | same with `_` | mm | already used by ZEIM |
| Perimeter engine | `--perimeter-generator` | `perimeter_generator` | classic, arachne (default arachne) | in help only |
| Ironing (smooth tops) | `--ironing`, `--ironing-type` | `ironing`, `ironing_type` | boolean; top, topmost, solid | in help only |
| Thumbnails | `--thumbnails` | `thumbnails` | `WxH,WxH` | **0 thumbnails produced headless [box]**: the CLI wrote none even with `--thumbnails 96x96,300x300`. ZEIM renders its own preview PNG instead |
| Binary G-code | `--binary-gcode` | `binary_gcode` | boolean | wrote a `.bgcode` [box]; **do not use for the K1** (stock firmware reads plain G-code; bgcode support unverified) |
| 3MF export | `--export-3mf` | n/a | n/a | wrote a `.3mf` [box]; **it did not embed the print settings** (no `Slic3r_PE.config` in the zip). To keep settings we save them ourselves (§4) with `--save <ini>` [box] |

Rule: the `.ini` key is the CLI flag with `-` → `_`. Only keys in the table above go into ZEIM's allowlist. A new test (SLICE-1) sends every allowed value to the installed PrusaSlicer, so a PrusaSlicer upgrade that renames or drops one fails CI instead of failing a student's slice.

### 1.2 What ZEIM does today (code-read)

`app/services/slicer.py::slice_model(model, outdir, layer_height, fill_density, upright, supports, brim, bed, profile_ini)`:
- passes `--layer-height`, `--first-layer-height`, `--fill-density N%`, `--filament-density 1.24`, `--center`, `--bed-shape`, `--brim-width`, optional `--support-material`, optional `--load <K1 ini>`;
- **no pattern, no wall/top/bottom counts, no support style**;
- runs with `timeout=600`, no memory or CPU cap, no queue;
- reads time and grams from the G-code comment lines (all-file search, because 2.9 writes them before the config block).

### 1.3 Pattern measurements (50 mm sphere, 20 %, PrusaSlicer built-in defaults, not the K1 profile) [box]

Time is the slicer's estimate on its generic machine limits. Treat as **relative**.

| Pattern | Time | PLA g | Plain-language note (source for the description in column 4) |
|---|---|---|---|
| lightning | 47 m 50 s | **13.1** | branching, saves the most; supports top surfaces only; weak inside [src: Prusa Knowledge Base] |
| supportcubic | 50 m 43 s | 16.7 | denser near tops, lowest cost of the cubic family; does not add strength [src] |
| adaptivecubic | 58 m 8 s | 20.4 | denser near walls, hollow centre; about 1/4 less material than rectilinear [src] |
| archimedeanchords | 59 m 46 s | 24.8 | spiral; suits flexible filament [src] |
| line | 1 h 3 m | 25.4 | similar to rectilinear |
| rectilinear, zigzag, alignedrectilinear | 1 h 4 m 30 s | 25.9 | fast and simple; only pattern allowed at 100 % [src] |
| concentric | 1 h 6 m | 26.1 | follows the outline; good for flexible parts; slow on complex shapes [src] |
| stars, cubic, grid, triangles | 1 h 6 m–1 h 7 m | 25.6–26.0 | grid can bump the nozzle at crossings [src] |
| gyroid | 1 h 24 m 42 s | 25.4 | "strong in every direction", good strength-to-weight, can be liquid-filled [src: Prusa] |
| hilbertcurve | 1 h 27 m | 26.1 | decorative; liquid-fillable [src] |
| octagramspiral | 1 h 18 m | 26.3 | decorative [src] |
| honeycomb | 1 h 43 m | 29.7 | strong but slow: Prusa says up to 2× the time and ~25 % more material [src]; here it was +60 % time and +15 % filament over rectilinear [box] |
| 3dhoneycomb | 1 h 45 m | 23.7 | lighter than honeycomb (29.7 g) on this model, but slow; odd 3D cell packing, not offered to beginners |

Wall-clock to produce each of these slices on this box was about 0.8 s (19 slices in 16 s, with the machine busy) [box].

**Density sweep, K1 profile, sphere** [box]:

| Pattern | 5 % | 15 % | 30 % | 60 % |
|---|---|---|---|---|
| gyroid | 45 m / 15.3 g | 58 m / 22.0 g | 1 h 25 m / 31.8 g | 2 h 31 m / 50.2 g |
| cubic | 45 m / 15.1 g | 57 m / 22.3 g | 1 h 15 m / 32.7 g | 1 h 49 m / 53.3 g |
| lightning | 41 m / 11.8 g | 44 m / 12.5 g | 47 m / 13.0 g | 49 m / 13.5 g |

Lightning's cost barely moves with density because it only builds what top surfaces need. That is exactly why it is wrong for anything that carries weight (reasoning from the Prusa description [src]; **no strength testing was done by us**, so ZEIM must say "decorative / light-duty", never give a load number).

### 1.4 Honest finding: for thin-walled models infill is nearly irrelevant

Zach's open-top box (`/workspace/qa/zach_test.stl`, 2.33 mm walls), K1 profile [box]:

| Pattern | 10 % | 20 % | 40 % |
|---|---|---|---|
| gyroid | 8 h 22 m / 157.9 g | 8 h 24 m / 158.8 g | 8 h 32 m / 161.5 g |
| cubic | 8 h 22 m / 157.8 g | 8 h 24 m / 159.0 g | 8 h 27 m / 161.5 g |
| lightning | 8 h 22 m / 157.2 g | 8 h 27 m / 158.1 g | 8 h 33 m / 159.4 g |
| grid | 8 h 22 m / 157.8 g | 8 h 24 m / 159.0 g | 8 h 27 m / 161.4 g |

The walls are almost all solid shell, so the infill choice moves the result by about 2 % in grams and minutes. (Earlier plan numbers: 10 h 58 m on a generic profile vs 8 h 22 m on the K1 profile for the same file; the K1 profile has much higher machine limits. **Neither has been checked against a real K1 print time.**) The lesson for the UI: show the effect before the user cares, and default to a sensible, cheap choice.

### 1.5 Beginner vs Expert

Beginner mode never shows pattern names. It asks what the part is *for*. Each preset is a bundle of validated keys (kept in one server-side table, one source of truth, so tests can check them):

| Beginner preset | Keys | When | Plain-language line |
|---|---|---|---|
| **Quick & light** | `fill_pattern=lightning`, `fill_density=10%`, `perimeters=2` | figurines, desk decor, display pieces | "Prints faster and uses the least filament. Fine for things that sit on a shelf." |
| **Everyday** (default) | `gyroid`, `15%`, `perimeters=2`, `top/bottom_solid_layers` as profile | most things | "A good balance of strength, speed and filament." |
| **Strong** | `gyroid`, `35%`, `perimeters=4`, `top_solid_layers=5`, `bottom_solid_layers=4` | holders, hooks, gears, stands | "Takes longer and uses more filament, but holds up better." |
| **Solid** | `rectilinear`, `100%`, `perimeters=4` | tiny parts, small hooks | "Filled all the way. Slowest." |
| **Flexible (TPU)** | `concentric` or `archimedeanchords`, TPU filament profile | **Coming soon**: needs a TPU filament profile and a real K1 print to be honest about | hidden until tested |

`gyroid 15 %` as the default is a choice, not a measurement. It rests on Prusa's own description of gyroid as their preferred general-purpose infill [src] and on its time/material cost being middling in §1.3. **Unverified: we have not printed or tested any part.** Zach's first K1 prints (§2.A, SLICE-5) are what move these from "reasoned" to "tested".

Expert mode shows a pattern dropdown with the 18 patterns grouped (**Strength**: gyroid, cubic, adaptivecubic, honeycomb, grid, triangles · **Speed / light**: lightning, supportcubic, rectilinear, line, zigzag · **Flexible / decorative**: concentric, archimedeanchords, hilbertcurve, octagramspiral, 3dhoneycomb, stars, alignedrectilinear). It also shows density 0–100 % in steps of 5 (the UI auto-switches to `rectilinear` at 100 %, as PrusaSlicer does, with a visible note), walls 1–8, top/bottom layers, layer height, supports (off / auto / build-plate only; style grid / snug / organic), brim width, raft layers, and the top-surface pattern. Anything outside these is not exposed.

Each Expert control has a help line in the same words as the Beginner presets. The three-way "strength / speed / flex" tag in the dropdown is the plain-language layer.

### 1.6 Validation rules (server)

- Allowlist of keys and ranges: density 0–100 (multiple of 1), walls 1–10, layers 0.08–0.35 on a 0.4 nozzle (K1 range is 0.1–0.35 per `reports/creality-k1-research.md`), brim 0–20 mm, raft 0–5, supports enum.
- 100 % density forces `rectilinear` (response says so).
- Unknown key → 422 with the name of the key; never passed to the CLI.
- Values are formatted by us (`f"{int(x)}%"`), never concatenated from user text. Arguments go in a list, never through a shell.

### 1.7 "Wow": the what-will-this-change readout

When the user changes the preset or a slider, ZEIM runs **2–3 candidate slices** (low / chosen / high) in the queue and shows a small bar: *"Everyday: 4 h 12 m, 58 g. Strong: 4 h 40 m, 71 g (+28 min, +13 g)."* For thin-walled models like Zach's box the bar shows *"These all finish within 11 minutes of each other. Infill changes little for this model."* That is real, honest information users do not get from a bare dropdown. The cost is 3 slices per change (about 1–5 s each for our biggest library file, §2.A.4), so it needs the queue and a cache keyed on `(model hash, settings hash)`.

---

## 2. Making ZEIM a slicer, in phases

Effort is working days for one engineer, **including tests and review**, excluding Zach's print time. These are estimates, not commitments. I padded A and B by about 25 % for iPhone-only surprises.

### Phase A: PrusaSlicer as the engine (≈ 11–15 days, see §5)

What the user gets: pick a printer (K1 first; "Generic" second), choose a Beginner preset or Expert settings, see time, filament grams and layer count, and download G-code and a 3MF that carries our settings. Everything the free tier needs; no account beyond what ZEIM already requires.

**A.1 What already exists** (code-read): `slicer.status()`, `slice_model()`, `parse_stats()`, `app/profiles/creality_k1.ini` (marked experimental, untested on a printer), K1 start/end macros, `POST /api/slice/{bid}` and `POST /api/send/{bid}` in `app/api/printing.py` (synchronous, one `model.gcode` per build), `handoff.py` slicer deep links, tests in `tests/test_b2_k1.py`.

**A.2 Printer profiles.**
- Registry file `app/profiles/printers.json` listing id, label, bed, max height, nozzle, `.ini` path, `tested: false|true`, `tested_by`, `tested_on`. K1 first (existing `.ini`), then "Generic 220 × 220". Every entry shows "Not yet tested on a printer" until a human print proves it (same labelling as `tested.json` in the Make plan).
- Filament profiles: PLA (temp 215–220 / bed 60) first; PETG next. **TPU/ABS: Coming soon.** Temperatures in the K1 `.ini` today are 220 / 60 [read]; Creality's published K1 limits are 300 / 100 °C [src: `reports/creality-k1-research.md`]; filament-specific values for each brand are **unverified** and the UI says "check your filament's label".
- K1 variants (K1C, K1 Max with 300 × 300 × 300) are separate registry entries; only the base K1 exists today.
- Bed fit warning is computed from the mesh before slicing: if it exceeds the profile, say so and offer "scale to fit" (`--scale-to-fit` exists [help]) rather than letting the CLI fail.

**A.3 Settings → CLI.** One function builds the argument list from a validated `SliceSettings` model (§1.6). The existing `profile_ini` mechanism stays: `.ini` first, our options override. Print the final argument list into the job log (no file names that carry user text; use the job id).

**A.4 Measured engine cost (so the queue is sized from data) [box, box was busy: load average 13–26]:**

| Case | Result |
|---|---|
| 3DBenchy.stl (11.3 MB, our largest library file), K1 profile | 5.1 s wall, ~294 MB peak memory, 160 layers, 2.2 MB G-code, ~76 k moves |
| `dino-phone-stand` / `ember-baby-dragon` / `wave-book-stand` (Originals) | 3.0 / 2.9 / 1.5 s |
| Benchy with `--threads` 1 / 2 / 8 | 11.2 / 6.6 / 4.5 s |
| 4 Benchy slices at once, `--threads 2` each | 8.1 s for all four |
| 19 slices, one pattern each (small model) | 16 s in total |

(Memory: `ru_maxrss` is cumulative across the children of that process, so 294 MB is a ceiling for the largest case, not a per-model figure.)

**A.5 Job queue and limits for hosted use.** Slicing is CPU-bound and runs a subprocess, so it must never run in a request thread unbounded. Design:
- `app/services/slice_jobs.py`: in-process queue (asyncio + `ThreadPoolExecutor`, **workers = 2**, configurable `PHOTO3D_SLICE_WORKERS`); `PrusaSlicer --threads 2` each. This box has 8 cores and 16 GB, so 2 × 2 threads leaves room for the web app. The hosting plan (Ren) sets real numbers.
- Per owner (session id): **1 running + 2 queued**, extra → 429 with "Your slice is still working". Per class: configurable cap. Global queue ≤ 20, then 503 "busy, try again in a minute".
- Hard limits per job: wall time **120 s** (the existing 600 s is far too long for a hosted app; our biggest library file takes ~5 s), `RLIMIT_AS` ≈ 2 GB and `RLIMIT_CPU` ≈ 240 s via `preexec_fn`, `nice 10`, working directory in a per-job temp folder removed after the job, a **triangle cap** (reuse `MAX_FACES`), and a bed-size sanity cap.
- Subprocess runs with an argument list (no shell), an environment containing only `PATH` and a per-job `HOME`/`--datadir` (PrusaSlicer otherwise writes `~/.config/PrusaSlicer`; **I did not verify `--datadir` behaviour headless**: the folder was not created in my run, so SLICE-2 must test it).
- Results cached by `(model sha256, settings hash, profile id)`; results are owner-scoped and deleted with the build ("delete my stuff" and class removal already purge builds; the slice folder lives inside the build folder so the same purge covers it, SLICE-3 adds a test).
- Cancel: `POST /api/slice/jobs/{id}/cancel` kills the process group.
- Metrics: queue length, wait time, run time, failures, timeouts (logs only, no user content).
- Scale-out is a later problem: one process, one box. If we need more, jobs move to a worker container reading from a spool directory. **Not built, not needed for a pilot.**
- Disk: the box hit 100 % earlier today (Ren's flag). G-code is ~2 MB for Benchy; with a 24 h TTL and 5-build cap per owner the footprint is bounded, but SLICE-2 adds a free-space check that refuses new jobs under 1 GB free.

**A.6 API.** Today's route is `POST /api/slice/{bid}` (form fields `layer_height, fill_density, upright, supports, brim, printer_id`; owner-only; code-read in `app/api/printing.py`). It slices **synchronously inside the request**, writes `slice_input.stl` and `model.gcode` into the build folder (so two slices of one build overwrite each other and the 3-candidate readout in §1.7 would collide), and `POST /api/send/{bid}` slices the same way before upload. Both move to the job queue; per-job output folders fix the overwrite. The old route keeps working for one release by creating a job and waiting for it. New, owner-scoped like builds:
- `POST /api/slice` body `{build_id, printer, filament, preset | settings{…}, upright?}` → `202 {job_id, position}`; respects the same Send/Make switches where relevant.
- `GET /api/slice/jobs/{id}` → `{state: queued|running|done|failed|cancelled, position, stats{time,grams,m,layers,warnings}, files{gcode,3mf}}`.
- `GET /api/slice/jobs/{id}/gcode` and `…/3mf` through the existing signed-download path (`/f/<token>`), never an open URL.
- `GET /api/slice/presets` → Beginner presets with their words (so Aiko/Sakura edit wording in one place).

**A.7 Supports, brim, raft.** Beginner: one switch "Add supports for overhangs" (auto, build-plate-only by default so it is easy to remove) and a "Helps it stick" brim toggle (5 mm). Expert: the full set in §1.1. A pre-slice **overhang check** (reuse the mesh's >45° downward-facing area; same check the Make plan uses for FDM-friendly tags) suggests supports with the percent of area affected.

**A.8 Preview-lite (Phase A, before Phase B).** Show: estimated time, filament (g and m), layer count, size on bed, warnings (thin walls under 1.2 mm [Make plan §16], model touches bed edge, supports used). Layer preview is Phase B; until then the Print dialog's existing model viewer plus numbers is what ships. The numbers carry the existing disclaimer: *"Estimates from the slicer using PLA (1.24 g/cm³). Your filament, printer and settings will change them."* **A K1's real time will differ; no accuracy claim until Zach compares at least three prints.**

**A.9 Export.** G-code (plain, `.gcode`), and 3MF with **our** `zeim_settings.json` inside (PrusaSlicer's CLI 3MF does not embed its config [box]). For people who want PrusaSlicer-compatible settings we also offer the `.ini` produced by `--save` [box]. Exports follow the existing Send privacy rules: generic object names, no source photos/EXIF, no user text in file names or metadata, one-file signed link for 10 minutes.

**A.10 Tests (Phase A).**
- Unit: settings validation (ranges, 100 % → rectilinear, unknown key), argument builder (exact list, no shell), preset table (each preset passes validation).
- Contract against the installed engine: one slice per allowed `fill_pattern`, per support style, per brim/raft setting (skipped with a clear message if no slicer is installed; CI image installs it).
- Stats parser: time/grams/layers on a fixed tiny model, including the 2.9 comment order that broke the old parser.
- Queue: concurrency cap, per-owner limit, timeout kill, cancel, memory-limit kill (a deliberately huge input), purge on delete, low-disk refusal.
- Privacy: G-code and 3MF headers contain no filename of the upload, no EXIF/GPS; log has no user text.
- WebKit/Chrome UI at phone size: presets render, 44 px targets, 16 px inputs, progress text announced.
- Real engine "golden" test: Benchy slice stays within ±15 % of the numbers above (guards against a PrusaSlicer upgrade silently changing defaults).
- **Not testable here, needs Zach:** a K1 print from ZEIM G-code, filament behaviour, start-macro behaviour, real time accuracy, the Creality Print / Cloud open flow on a phone.

### Phase B: in-browser layer preview (≈ 8–10 days)

Goal: a layer slider you can drag on an iPhone, coloured by feature (walls, infill, supports, top surface), with time-of-layer and filament-used shown.

**B.1 Data.** PrusaSlicer's G-code carries what we need as comments [box, Benchy]: `;LAYER_CHANGE`, `;Z:`, `;HEIGHT:`, `;WIDTH:`, and `;TYPE:` blocks (External perimeter, Perimeter, Overhang perimeter, Internal infill, Solid infill, Top solid infill, Bridge infill, Skirt/Brim; "Support material" appears when supports are on [box]). Benchy: 2.27 MB of G-code, 1,441 `;TYPE:` blocks, ~76 k G0–G3 moves.
**B.2 Approach.** Parse **on the server** (Python, one pass; the job already has the file) into a compact binary: per layer, per feature, arrays of segments as int16 millimetres ×100 plus a per-segment width. Send gzip'd. **[est]** Benchy ≈ 65 k extruding moves → ~1.6 MB raw before quantising, well under 1 MB after, a few hundred KB gzipped; **to be measured in SLICE-9**. Parsing 2.3 MB of text on a phone's main thread is the thing to avoid, so the phone never sees the G-code text.
**B.3 Rendering.** Existing `static/vendor/three.module.min.js` (671 KB, MIT). One `LineSegments` (or thin instanced quads for a "tube" look) **per feature type**, a single shared `uMaxLayer` uniform clipped in the vertex shader, so dragging the slider is a uniform update, not geometry rebuilds. Draw calls ≈ 8. Camera: same orbit controls as the existing viewer, with the existing fix that the viewer must not capture page scroll on touch (IOS-1..8 list).
**B.4 Mobile performance plan** (design targets, **not measured**): cap total drawn segments (decimate collinear moves, drop travel by default), target 60 fps drag on an iPhone 12-class device for ≤ 150 k segments, fall back to a "walls-only / every 2nd layer" mode over the cap, load lazily when the user opens Preview, show the Phase A numbers immediately. Memory budget ~50 MB of GPU buffers.
**B.5 Alternatives considered:** `xyz-tools/gcode-preview` (MIT, active, 203 stars, last push 2026-10-04 [src: GitHub API]): parses G-code in the browser; good reference and a possible stop-gap, but parsing on the main thread is the risk on phones, so we adapt its ideas rather than depend on it. three.js `GCodeLoader` (MIT): same. PrusaSlicer's `libvgcode` viewer and `libbgcode` (AGPL-3.0): **reject for copying** (§3, Phase C table).
**B.6 Tests.** Parser golden (layer count, feature totals against the slicer's own numbers), converter round-trip, size budget assertion (fails if Benchy payload > agreed cap), WebKit + Chrome UI test (slider moves, layer label updates, no console errors), a perf smoke in headless (frame time budget; **real iPhone perf is a Zach/Ren check**).

### Phase C: our own engine (long-term; research spike ≈ 3 days, then decide)

Why consider it: no AGPL boundary question, in-browser/offline slicing, tighter integration (e.g. lithophane-aware slicing, education explanations of each step). Why not now: slicing quality (bridging, overhangs, seams, supports, pressure/accel models, firmware-specific start code) is what PrusaSlicer has had a decade of work on.

Public projects, licences as reported by the GitHub API on 2026-10-04 [src: `api.github.com/repos/<owner>/<repo>`]:

| Project | Licence | Activity | What it offers | Verdict |
|---|---|---|---|---|
| PrusaSlicer (`prusa3d/PrusaSlicer`) | AGPL-3.0 | pushed 2026-09-21 | our current engine; K1-capable via custom profile | **Use as a separate program (A)**; **reject copying code** into ZEIM unless counsel and Zach accept ZEIM becoming AGPL (§3) |
| CuraEngine (`Ultimaker/CuraEngine`) | AGPL-3.0 | pushed 2026-10-02 | alternate CLI engine (Arcus/libArcus is LGPL-3.0) | **Adopt as an optional second backend behind the same job interface** only if PrusaSlicer fails a case we care about; same licence class, so same counsel answer |
| OrcaSlicer (`OrcaSlicer/OrcaSlicer`) | AGPL-3.0 | pushed today | ships K1 machine/process profiles; `orca-slicer` is already in ZEIM's `CANDIDATES`; Creality's own tooling is based on this family | **Adapt profile *values* from public Creality specs** (not copy the JSON files, which are AGPL repo content; counsel to confirm that data files are treated the same way); possible third backend |
| SuperSlicer (`supermerill/SuperSlicer`) | AGPL-3.0 | pushed 2026-09-06 | a PrusaSlicer fork | **Reject** (no need) |
| Slic3r (`slic3r/Slic3r`) | AGPL-3.0 | last push 2024-06-18 | the ancestor | **Reject** (stale) |
| Kiri:Moto (`GridSpace/grid-apps`) | MIT | pushed 2026-10-04 | slicer written in JavaScript that runs in the browser (FDM, SLA, CNC modes) | **Evaluate (spike):** can it slice Benchy in under ~30 s in iPhone Safari, and are its supports and bridges good enough for kids' prints? Read its `license.md` in full before adopting anything (the API says MIT) |
| gcode-preview (`xyz-tools/gcode-preview`) | MIT | pushed 2026-10-04 | G-code → three.js | **Adopt ideas / reference for Phase B** |
| three.js (`mrdoob/three.js`) | MIT | active | already vendored | **Keep** |
| libbgcode (`prusa3d/libbgcode`) | AGPL-3.0 | pushed 2026-09-16 | binary G-code library | **Reject** (not needed) |
| Our own, using manifold3d (Apache-2.0), shapely, trimesh already in `requirements.txt` | ours | n/a | contour a mesh at z, offset perimeters, hatch infill, emit G-code | **Feasible for a "fast estimate" engine; not for parity.** [est] 25–40 days for FDM-lite (perimeters, rectilinear/gyroid-like infill, no supports, basic bridges), **not** recommended before Phase A has real users |

Spike deliverable (SLICE-13): a short report with Benchy and two Originals sliced by Kiri:Moto and by us in the browser, timing on an iPhone if Zach lends one (otherwise Chrome emulation labelled as such), and a recommendation. No decision until it exists.

### Resin note (all phases)

- **Phase A does no resin slicing.** Resin users export a clean STL (the Make plan's `printer: resin` path, MAKE-15/16) and slice in **Chitubox** or **Lychee**; the Print dialog shows a short how-to and links to those apps' official pages (links to be verified before shipping; I have not verified current download pages).
- PrusaSlicer can `--export-sla` PNG layers [help], but that targets Prusa SL1-family and similar formats. Chitubox-class printers read other containers (`.ctb`, `.goo`, `.photon…`). **Unverified; not offered.**
- Resin presets (layer 0.05 mm, exposure) are printer-specific and we own no resin printer. Marked **Coming soon**. The resin figures in the Make plan (walls ≥ 0.8 mm, drain holes 2–4 mm) are from public guides and remain unverified.

### Privacy for slicing

- A slice job holds the user's model (which for photo-based builds contains the picture). Rules from the Send/privacy decisions apply unchanged: Download of own builds only for class students and teens; per-class Send switch off by default, enforced server-side; minors' and students' photo-based models are not sent outside ZEIM.
- Jobs and outputs are owner-scoped; ids are random; no model names or text in the CLI arguments or logs.
- Slice settings contain no personal data. If settings are shared with a project, they are public with that project and visible only as much as the project is (§4).
- G-code ends with PrusaSlicer's config comment block. It should contain no file names or user text, because ZEIM passes only a job id and a numbered temp file name. SLICE-7 adds a test that scans the G-code for the upload's file name and any user text.
- No third-party calls from the slicing path (no cloud slicer, no analytics).

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| K1 profile untested on hardware; a bad start macro could waste a print | medium | label "Not yet tested on a printer"; Zach's first print is SLICE-5; keep Download primary |
| AGPL obligations unclear for hosted use | **medium–high until counsel answers** | §3; keep PrusaSlicer unmodified, separate process; publish a source/credits page; counsel before public launch |
| CPU abuse (a class slices 30 big models at once) | medium | queue, per-owner and per-class caps, triangle cap, 120 s kill |
| Disk fills (it already hit 100 % today) | medium | TTL, 5-build cap, low-disk refusal, purge on delete |
| PrusaSlicer upgrade changes defaults/keys | medium | contract tests, golden Benchy ±15 %, pin version in Docker |
| Time estimate off vs the K1 | high | no accuracy claim until measured against ≥ 3 real prints |
| Phone layer preview too heavy | medium | server-side parse, quantised binary, segment caps, fallback modes |
| "Slicer" overpromised in launch copy | low if we follow `catalog-spec.md` §14 | claim = "Slice for the Creality K1 in ZEIM (experimental)" until a real print passes |

---

## 3. Licensing question for Kenji: PrusaSlicer is AGPL-3.0. Can a hosted ZEIM call it as a separate program?

**NEEDS COUNSEL. I am an engineer, not a lawyer, and nothing below is legal advice.**

### 3.1 Facts I verified from public sources

1. **PrusaSlicer's licence is AGPL-3.0** (GNU Affero General Public License v3): the `LICENSE` file in `prusa3d/PrusaSlicer` is the AGPL v3 text, and the README states it [src: https://raw.githubusercontent.com/prusa3d/PrusaSlicer/master/LICENSE ; https://github.com/prusa3d/PrusaSlicer/blob/master/README.md]. The GitHub API reports `AGPL-3.0` for it, CuraEngine, OrcaSlicer, SuperSlicer, Slic3r and libbgcode as of 2026-10-04.
2. **Prusa's own FAQ speaks to hosting.** "We would like to use PrusaSlicer to create a cloud slicing service. A: Feel free to do so, but just like when releasing a modified version, you will have to release the full source code including all the changes that you've made." [src: https://help.prusa3d.com/article/faq-prusaslicer_1789, read today]. Read literally, the obligation they describe attaches to **changes you make to PrusaSlicer**.
3. **AGPL §2** (same licence file): "This License explicitly affirms your unlimited permission to run the unmodified Program. The output from running a covered work is covered by this License only if the output, given its content, constitutes a covered work." So running the unmodified program is permitted, and G-code output is not automatically covered.
4. **AGPL §13 ("Remote Network Interaction")** applies "if you modify the Program": your modified version "must prominently offer all users interacting with it remotely through a computer network … an opportunity to receive the Corresponding Source of your version". The text is conditioned on modification.
5. **AGPL §5, last paragraph** (the "aggregate" paragraph): a compilation of a covered work with "separate and independent works, which are not by their nature extensions of the covered work, and which are not combined with it such as to form a larger program" is an *aggregate*, and inclusion in an aggregate "does not cause this License to apply to the other parts of the aggregate." (Note: this paragraph is about distribution on a medium.)
6. **The FSF's GPL FAQ on separate vs combined programs** (the AGPL shares this reasoning; the FAQ text itself was quoted to me via mailing-list archives because gnu.org blocked my fetch): "pipes, sockets and command-line arguments are communication mechanisms normally used between two separate programs. So when they are used for communication, the modules normally are separate programs. But if the semantics of the communication are intimate enough, exchanging complex internal data structures, that too could be a basis to consider the two parts as combined into a larger program." It also says where the line falls is "a legal question, which ultimately judges will decide." [src: https://mail.python.org/pipermail/python-list/2006-January/385468.html quoting gnu.org/licenses/gpl-faq.html; **I did not read the live gnu.org page**]
7. **How ZEIM uses it today (code-read):** `subprocess.run([prusa-slicer, "--export-gcode", flags…, stl])`, reads a G-code text file back. Data crossing the boundary: an STL file, flag strings, an optional `.ini`, and a G-code file. No linking, no shared memory, no copied PrusaSlicer source. ZEIM has **not** modified PrusaSlicer. It calls the Debian package `prusa-slicer 2.9.2+dfsg-1` [box].
8. **Shipping:** the `Dockerfile` installs that Debian package (`apt-get install prusa-slicer`). ZEIM's own code has no declared licence in the repo (README/ROADMAP only say "PrusaSlicer is AGPL — review if distributing/hosting").

### 3.2 What the facts suggest (engineering reading, not an opinion on the law)

- **Calling an unmodified PrusaSlicer binary as a separate program from a hosted app** is the pattern Prusa's FAQ names as allowed ("feel free"), with the source obligation tied to modifications.
- Command-line plus files is the kind of boundary the FSF FAQ describes as "normally … separate programs", but the same FAQ keeps the "intimate" exception.

### 3.3 What is unclear (all of this is for counsel)

1. Whether a hosted web app that **invokes** an unmodified AGPL program on behalf of users has any AGPL obligation at all. §13 is worded around a modified version "supporting remote interaction"; whether the user "interacting" with ZEIM is "interacting remotely with" PrusaSlicer is a question I cannot answer.
2. Whether our **`.ini` profiles, flags and parsing of its output** make the combination "intimate enough". We exchange no internal data structures, but we do read its comments and feed it a config derived from user choices.
3. **Distribution:** if we **publish a container image** (Dockerfile → registry, or give Ren's compose to a school), that is "conveying" object code. AGPL §6 then needs the **Corresponding Source** offer for the PrusaSlicer binaries (Debian publishes `2.9.2+dfsg` source, but who owes what when *we* convey it, and what a compliant notice looks like, is for counsel). Merely running it on our server is not conveying under §0 ("mere interaction … is not conveying") but that is again a question for them.
4. If we ever **patch** PrusaSlicer (e.g. to emit a custom comment, or fix a bug) §13 applies and we would need to publish the patched source to users of the hosted service.
5. **Phase C and adapting any AGPL code (libslic3r, CuraEngine, OrcaSlicer files, libvgcode, profile JSON)** into ZEIM's own server code would make ZEIM a "work based on" it (§5(c)): the whole of ZEIM would have to be offered under AGPL. That is a **Zach decision** (does ZEIM become open source?) with legal input, not an engineering call.
6. **Profile data** (OrcaSlicer's K1 JSON, Prusa vendor bundles) is licensed as part of AGPL repos. I used it as a *source of numbers* and wrote our own `.ini`; whether independently typed values from a public spec are free of that licence is for counsel.
7. **Trademarks:** "PrusaSlicer", "Creality", "Creality Print", "Bambu Studio", "Cura" names in the UI: nominative use only, no logos, no implied endorsement (existing Print dialog already uses names as link labels). Trademark review sits with Kenji.
8. Whether a **school pilot** changes anything (not a lawyer's area I can speak to).

### 3.4 What I propose engineering does regardless (cheap, reversible)

- Keep PrusaSlicer **unmodified**, package version pinned, separate process, no code or data files copied (SLICE-0).
- Add a visible **"Credits & licences"** page: PrusaSlicer (AGPL-3.0, link to its source and to the Debian source package), three.js, manifold3d, etc. (SLICE-0, small).
- Do not publish a container image publicly until counsel answers item 3.
- Keep an `engine` interface so the backend is swappable (CuraEngine, OrcaSlicer, a future permissive engine) without UI changes.

---

## 4. Marketplace, projects and settings (FREE exchange, no payments)

Existing decisions: free forever product, no paid content, no payments; learning, sharing files and projects; Build Plates (groups), Likes, Trending, classrooms, Spark Lab; teens Private by default; class students' Showcase off unless the teacher allows; per-class Send switch off by default; counts hidden for minors. Nothing in the slicer changes those.

### 4.1 A shared project carries its slicer settings

Today a Showcase item has `files[]` (3MF + STL), `tags`, `mode`, `visibility`, `owner_sid`. Add, **inside the listing record** (JSON, no new database needed at this size):

```json
"print": {
  "printer_tag": "fdm|resin|both",
  "recipe": {                       // optional; present only if the creator chose "share my print settings"
    "printer_id": "creality-k1",
    "filament": "PLA",
    "preset": "everyday",           // or null if Expert
    "settings": {"layer_height": 0.2, "fill_pattern": "gyroid", "fill_density": 15,
                 "perimeters": 2, "supports": "auto", "brim_width": 0},
    "engine": "PrusaSlicer 2.9.2",
    "zeim_slicer_version": "…",
    "estimate": {"time_s": 15120, "filament_g": 58.2, "layers": 214, "note": "estimate, PLA 1.24 g/cm³"},
    "tested": {"status": "untested|printed-ok|printed-with-issues", "by": "creator", "printer": "…"}
  }
}
```

- **Opt-in, never automatic**, default off for minors (nothing public for teens at launch anyway).
- **The recipe is settings only.** No G-code is stored with a shared project by default (G-code is printer-specific and large). A shared project offers **"Slice with these settings"** (re-runs the job for the *viewer's* chosen printer, so a K1 owner gets K1 G-code) and **"Use these settings in Expert"**.
- **Honest labelling:** "Estimate", "Settings shared by the creator, not tested by ZEIM", and `tested` shows what the creator reported. ZEIM Originals get `tested` from our own prints once we have them; until then they say "Not yet printed by the ZEIM team".
- **Remix:** "Open in Edit" and "Slice with these settings" both create a *new* build owned by the viewer. The creator, licence line and "remix of …" pointer carry over (catalog-spec §3). Nothing writes back to the original.
- **Likes / Trending** use the existing distinct-visitor rules; settings do not affect scoring.
- **Build Plates (groups):** a group page can pin a "recipe" (e.g. the class's printer settings) that members can apply with one tap. This only needs `recipe` on a group post; no new engine.
- **Classrooms:** a teacher can set a class default preset (e.g. "Everyday, K1, PLA") that students' Print dialog uses; students cannot change printer profiles. Behind the same teacher-switch pattern as Send/Make (default off, server-enforced, log = class + time, no names). Needs Aiko's wording.
- **Spark Lab:** a lesson step can carry a recipe ("slice this with Quick & light, then with Strong, compare the numbers") because the what-will-this-change readout (§1.7) is a built-in comparison activity.
- **Moderation:** the recipe is structured data (enums and numbers) and has no free text, so it adds no new text-filter surface. The `tested` free-text note, if ever added, goes through the existing filter.
- **Downloads of G-code from a shared project** are generated on demand for the viewer, owner-scoped like all builds, counted once per distinct visitor like current downloads.

### 4.2 What is not in scope

Payments, tips, paid models, per-download fees, creator payouts, ads. Nothing in this plan needs them; none will be added.

---

## 5. Tickets (SLICE-n), ordered after: (1) phone-test merge, (2) Make tab (MAKE-1…), (3) Originals Showcase (CAT-*/MAKE-11/SHOW-LIB-1)

Sizes: S ≤ 1 day, M 1–3, L 3–5. Days are working days with tests. **Z** marks a Zach decision, **K** Kenji, **A** Aiko, **S** Sakura.

| ID | Ticket | Size | Depends on | Notes |
|---|---|---|---|---|
| SLICE-0 | Licence hygiene: pin PrusaSlicer version, "Credits & licences" page, no public image until counsel answers, `engine` interface | S | counsel (**K**/**Z**) | §3.4 |
| SLICE-1 | `SliceSettings` model, key allowlist, ranges, Beginner preset table, `printers.json` registry; contract test slicing every allowed pattern/style | M (2d) | phone-test merge | §1; replaces ad-hoc args in `slicer.py` |
| SLICE-2 | Job queue + limits: workers, per-owner/class caps, 120 s/memory/CPU kill, temp dirs, `--datadir`, low-disk refusal, cancel, metrics | M (2.5d) | SLICE-1 | §2.A.5 |
| SLICE-3 | API `/api/slice*`, owner-scoped results through signed download, cache by hash, purge on build delete | M (2d) | SLICE-2 | A.6 |
| SLICE-4 | Print/Slice UI: printer + filament pick, Beginner presets, Expert panel, progress, 44 px / 16 px, inline errors, "Coming soon" labels (TPU, resin) | L (3d) | SLICE-3, **S** design | A.7, §1.5 |
| SLICE-5 | K1 real-print validation: slice 3 Originals, Zach prints them, compare time/weight, fix profile; flip `tested` only if good | S + **Z** print time | SLICE-4 | needs a physical K1 |
| SLICE-6 | What-will-this-change readout (2–3 candidate slices, cached) + thin-wall "infill barely matters" message | M (2d) | SLICE-3 | §1.7 |
| SLICE-7 | Export: G-code + 3MF with `zeim_settings.json` + `.ini` via `--save`; privacy scan of outputs | S (1d) | SLICE-3 | A.9 |
| SLICE-8 | Shared-project `print.recipe`, "Slice with these settings", group/classroom defaults | M (2.5d) | SLICE-7, CAT-5 | §4; **K** (minors, classroom switch), **A** wording |
| SLICE-9 | Phase B1: server G-code → compact layers converter + size budget test | M (2d) | SLICE-3 | B.1–B.2 |
| SLICE-10 | Phase B2: three.js layer viewer (slider, feature colours, layer stats) | M–L (3d) | SLICE-9 | B.3 |
| SLICE-11 | Phase B3: mobile performance pass + real iPhone check | M (2d) | SLICE-10, Zach's phone | B.4; label emulation vs real |
| SLICE-12 | Resin path docs in Print dialog (STL-first, Chitubox/Lychee how-to, verified links), resin presets "Coming soon" | S | MAKE-15/16 | resin note |
| SLICE-13 | Phase C spike: Kiri:Moto in-browser slice test + own-engine feasibility report (no product code) | M (3d) | none | decision doc for **Z**/**K** |
| SLICE-14 | Hosted ops: container pinned version, resource caps in compose, queue dashboards (log-based), runbook | M | Ren, SLICE-2 | A.5 |

**Rough totals:** Phase A core (SLICE-1…5 and 7) ≈ 11–12 days; adding SLICE-0 and the what-will-this-change readout (6) makes it ≈ 14–15. Phase B (9–11) ≈ 7 days (the 8–10 in §2 includes review and device checks). Shared-project integration (8) ≈ 2.5 days. Spike (13) 3 days.

## 6. Decisions needed

**Zach**
1. Is "slice in ZEIM" a launch feature, or "coming soon" until a real K1 print passes (SLICE-5)? My recommendation: show it as **Experimental for the Creality K1**, honestly labelled, from the first release that has it.
2. May we hold a **K1 print session** (3 Originals) to validate the profile and time estimates? Which filament brand and colour do you have for the first prints?
3. Does ZEIM itself become **open source** (AGPL-compatible)? It changes what Phase C may do and may simplify §3. Counsel should hear this question.
4. How much **CPU** may a hosted ZEIM spend on slicing (affects worker count and class caps)?
5. Which **resin printer** (if any) should the future resin presets target?

**Kenji**
1. The §3 questions (needs counsel; I can prepare a one-page brief for them).
2. Trademark/nominative-use check for printer and slicer names in the dialog.
3. Minors: shared `recipe` default off; any objection to showing settings on public adult projects?
4. Classroom slice switch: default off, server-enforced, log = class + time, no names (same pattern as Send/Make).

**Aiko / Sakura**
- Aiko: Beginner preset wording (§1.5), Spark Lab "compare presets" activity, classroom default preset wording.
- Sakura: Slice panel, layer-preview layout on a phone, the what-will-this-change bar, and "Coming soon" styles.

## 7. Verified vs unverified (engineering summary)

| Verified [box] | Unverified |
|---|---|
| 18 infill patterns accepted by installed PrusaSlicer 2.9.2; invalid pattern rejected | any strength claim for any pattern (no mechanical testing) |
| 100 % needs rectilinear | K1 print time/weight accuracy; K1 start macro; filament temperatures |
| Support styles incl. organic, brim, raft, perimeters, top/bottom layers accepted | thumbnails headless (produced none); `--datadir` behaviour; `.bgcode` on a K1 |
| Benchy (11 MB) slices in ~5 s, ~294 MB peak | phone performance of any layer viewer |
| PrusaSlicer's CLI 3MF omits print config | resin output formats; Chitubox/Lychee current pages |
| G-code has `;TYPE:`, `;LAYER_CHANGE`, `;HEIGHT:`, `;WIDTH:` markers | any legal conclusion in §3 |
