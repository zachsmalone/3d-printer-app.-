# ZEIM

**_Uno loco aedificamus_, we build in one place.**

ZEIM is a 3D-printing maker app and community for adults (**18+ only**). Turn a photo into a lithophane, model and fix parts, slice for FDM or resin, and share what you print, all in one place.

> **Status: Beta.**
> Stages: 0-89% Beta, 90-99% Alpha, 100% Final Product. Version 1.0 when finished.

## What works today

| Area | What it does |
|---|---|
| **Age gate** | 18+ confirmation before entering the app. |
| **Lithophane** | Photo to lithophane, with a Tango sample image to try. **Curved panel:** bend adjustable from flat (0°) to a half circle (180°), with an optional built-in stand and a check that it fits your printer's bed (not yet test-printed). **Memory box:** up to 4 photos, snap, frame or enclosed styles, and a light base. **Try the sample box** fills sides 1-4 with sample rose photos; empty sides use the Tango sample. Core panels stay open after a build (busy watch); only a panel just opened from its chip yields to chip layout. **Backing colour:** paper / warm / cool / custom (preview and saved with the build). Optional **Bambu lithophane preset** in 3MF (labelled not tested on a real Bambu). Adjustable **lip** width 0–10 mm with taper (default 45°, outward / inward / both / flat). **Expert tone tools:** grey method (Rec. 601 / 709 / average / lightness / max) plus brightness, contrast, and sharpen for the thickness map. **Seamless tile** with `mm_per_repeat` repeats the photo across a plate or around a sleeve so the seam matches. **Night-light LED fit** presets (tea-light ~38 mm, puck ~50/70 mm, E12 ~16 mm) set sleeve diameter, with an honest note that flame candles and hot mains bulbs are not for this. **Plate size** presets for flat lithos (4×6, 5×7, 8×10, A6, A5). Export can download the **panel** or **stand** alone (`part=`). After generate: three side-by-side buttons — **Save work** | **Send to Slicer** (or **Send to TorchC0** for resin) | **Send to CAD**. Multi-head / filament colour pickers stay out of Lithophane; those live only in the FDM Slicer. |
| **FDM Slicer** | Wraps the PrusaSlicer CLI. Creality K1 profile, printer picker covering many brands (Longer included), and a CFS / AMS / MMU / ACE filament slot picker with per-head material and colour (multi-head UI only here — not in Lithophane, CAD, TorchC0, or other export pickers). Unused heads are stripped from the G-code so idle AMS/CFS/MMU ports are never heated, primed, or purged. **Honest limit:** the PrusaSlicer path still does a single-material merge for toolpaths; ZEIM records the per-slot plan and cleans unused-head lines, but true multi-material toolpathing is not there yet. On the plate, dragged objects stay where released (orbit damping is frozen mid-drag so the camera does not drift the bed mapping). |
| **TorchC0 (resin)** | Resin program with resin cost estimate and island / suction-cup detection. |
| **ZEIM CAD / Edit** | Smart Split and Smart Merge, manual merge, hinges, print-in-place joints, Measure (including the angle between faces), simplified import for big models, and select mode. **Edit upgrades 1–10:** (1) cut joins with glue / magnet / pin / dovetail and tolerance sliders; (2) print-check colour problem highlights on the model; (3) user-placed resin drain holes when hollowing; (4) curved-surface text (optional wrap); (5) print-check list with one-tap fixes; (6) material and cost from volume; (7) scale to longest edge / fit bed / target volume; (8) custom fonts (TTF/OTF upload) and saved text styles; (9) threaded connectors; (10) adjustable support paint (tip, thickness, filament slot). |
| **Showcase** | Community feed. Remix Yes / No switch per upload, credited remixes, and re-upload protection using a shape fingerprint plus **Report a copy**. **AI-made** label set by the creator (automatic and locked for 2D→3D models, and carried through edit / remix / 3MF re-upload lineage), with a Show / Hide / Only filter that remembers the choice. Filters for printer, material, supports, licence, and mature content (mature defaults to hide; missing metadata is Not stated). A **Printed by the community** yes/no badge appears once a model has an approved **I printed this** photo (no counts or ranking). Optional creator tip link (https only, hardened against private hosts / shorteners / personal info); the tip line shows the destination domain; moderators can clear a tip; ZEIM takes no cut. **Collections:** creators group their own Showcase models into named lists (public or private), manage them from Account, add or remove from a project page, and show public collections on the profile strip for other adults to browse (no ranking or boosting). |
| **Export** | One format picker with file naming: STL, 3MF, OBJ, SVG, PLY, GLB, AMF, and G-code from the slicer. |
| **Smart Fix** | Mesh repair and auto-orient. |
| **2D→3D** | Makes a rough Figure or Bust from one photo using TripoSR (MIT-licensed open model) in an optional separate worker container (GPU or CPU). Results are labelled **AI-made**, auto-repaired, and private by default. 5 min cooldown between models and a daily cap of 5 per account during testing. Without the worker the tab says the engine is not installed. Results are rough guesses of the hidden sides and have not been test-printed. |
| **Learn** | Guided lessons inside the app. On phones (≤420px wide) Learn leaves the bottom tab bar but stays reachable from Showcase / home. |
| **Themes** | Japanese-inspired theme per section. |

## In progress

These are not finished yet:

1. **Bust mode:** a dedicated mode for busts beyond the basic 2D→3D Bust option.
2. **Live Sculpt.**
3. **Subscriptions:** the core stays free forever; optional Semi Pro and Pro plans are planned. Details are not final.

See [`ROADMAP.md`](ROADMAP.md) for more.

## Run with Docker (Windows)

From the repo root in PowerShell:

```powershell
docker build -t zeim:dev .
docker volume create zeim-data
docker volume create zeim-outputs
copy .env.example .env      # then fill in your own values; never commit .env
docker run -d --name zeim -p 8765:8765 --env-file .env `
  -v zeim-data:/data -v zeim-outputs:/outputs zeim:dev
```

Open <http://localhost:8765>. Health check: <http://localhost:8765/healthz> returns 200 when the app is up.

**Testing mode:** add `-e ZEIM_TESTING_MODE=1` to lift usage quotas and cooldowns while testing. It is off by default; do not use it in production.

## Optional: 2D→3D worker

The 2D→3D tab needs a separate worker container (TripoSR). It is not part of the main image; the rest of ZEIM works without it. Model weights (about 1.7 GB + 176 MB) are downloaded into the worker's volume on first start, not stored in the repo. CPU-only works but is slow and needs about 3-4 GB free RAM.

```powershell
docker network create zeim
docker network connect zeim zeim          # attach the ZEIM container
docker compose -f workers/ai3d/docker-compose.ai3d.yml up -d --build
```

NVIDIA GPU: build with `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121` and uncomment the `deploy:` block in the compose file.

Then recreate the ZEIM container with these added to `.env` (or as `-e` flags):

```
ZEIM_AI3D_URL=http://zeim-ai3d:8765
ZEIM_AI3D_TOKEN=<optional shared secret, same value on the worker>
```

The worker's `GET /health` returns `"ready": true` once the model is loaded. Limits: `ZEIM_AI3D_DAILY_CAP` (default 5), `ZEIM_AI3D_COOLDOWN_MIN` (default 5). Details: [`workers/ai3d/README.md`](workers/ai3d/README.md).

## Run locally (Linux / macOS)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -c constraints.txt
./run.sh                      # http://localhost:8765, this computer only
```

Slicing needs the PrusaSlicer CLI on `PATH` (`sudo apt install prusa-slicer`). Without it, slicing reports that it is unavailable; exports still work.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
```

Tests use temporary data folders; slicer and printer tests use mocks. `pytest --collect-only` currently counts 2565 tests (includes Showcase Collections, lithophane batch 1, slicer plate-drag, Lithophane Save work / Send to Slicer / Send to CAD handoff, FDM multi-head filament slots with unused-head strip, lithophane batch 2: tone/tile/LED fits/plate sizes/panel-or-stand export, and Edit upgrades 1–10).

## Layout

```
app/api/         HTTP routes
app/core/        geometry, export, resin, mesh tools
app/services/    slicer, printers, settings, accounts
app/community/   showcase, moderation, fingerprint, licensing
workers/ai3d/    optional 2D→3D worker (TripoSR)
static/          web UI
tests/           pytest suite
```

## Community rules

ZEIM is for adults only (18+). Please read the [Community Guidelines](static/COMMUNITY_GUIDELINES.md).
