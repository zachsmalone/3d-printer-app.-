# ZEIM

**_Uno loco aedificamus_, we build in one place.**

ZEIM is a 3D-printing maker app and community for adults (**18+ only**). Turn a photo into a lithophane, model and fix parts, slice for FDM or resin, and share what you print, all in one place.

> **Status: Beta.**
> Stages: 0-89% Beta, 90-99% Alpha, 100% Final Product. Version 1.0 when finished.

## What works today

| Area | What it does |
|---|---|
| **Age gate** | 18+ confirmation before entering the app. |
| **Lithophane** | Photo to lithophane, with a Tango sample image to try. **Curved panel:** bend adjustable from flat (0°) to a half circle (180°), with an optional built-in stand and a check that it fits your printer's bed (not yet test-printed). **Memory box:** up to 4 photos, snap, frame or enclosed styles, and a light base. **Try the sample box** fills sides 1-4 with sample rose photos; empty sides use the Tango sample. |
| **FDM Slicer** | Wraps the PrusaSlicer CLI. Creality K1 profile, printer picker covering many brands (Longer included), and a CFS / AMS filament slot picker. |
| **TorchC0 (resin)** | Resin program with resin cost estimate and island / suction-cup detection. |
| **ZEIM CAD** | Smart Split and Smart Merge, manual merge, hinges, print-in-place joints, Measure (including the angle between faces), simplified import for big models, and select mode. |
| **Showcase** | Community feed. Remix Yes / No switch per upload, credited remixes, and re-upload protection using a shape fingerprint plus **Report a copy**. |
| **Export** | One format picker with file naming: STL, 3MF, OBJ, SVG, PLY, GLB, AMF, and G-code from the slicer. |
| **Smart Fix** | Mesh repair and auto-orient. |
| **2D→3D** | Makes a rough Figure or Bust from one photo using TripoSR (MIT-licensed open model) in an optional separate worker container (GPU or CPU). Results are labelled **AI-made**, auto-repaired, and private by default. 5 min cooldown between models and a daily cap of 5 per account during testing. Without the worker the tab says the engine is not installed. Results are rough guesses of the hidden sides and have not been test-printed. |
| **Learn** | Guided lessons inside the app. On phones (≤420px wide) Learn leaves the bottom tab bar but stays reachable from Showcase / home. |
| **Themes** | Japanese-inspired theme per section. |

## In progress

These are not finished yet:

1. **Live Sculpt.**
2. **Subscriptions:** the core stays free forever; optional Semi Pro and Pro plans are planned. Details are not final.

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

Tests use temporary data folders; slicer and printer tests use mocks. `pytest --collect-only` currently counts 2391 tests.

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
