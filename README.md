# ZEIM

**_Uno loco aedificamus_, we build in one place.**

ZEIM is a 3D-printing maker app and community for adults (**18+ only**). Turn a photo into a lithophane, model and fix parts, slice for FDM or resin, and share what you print, all in one place.

> **Status: Beta, roughly 88%** by the owner's internal estimate.
> Stages: 0-89% Beta, 90-99% Alpha, 100% Final Product. Version 1.0 when finished.

## What works today

| Area | What it does |
|---|---|
| **Age gate** | 18+ confirmation before entering the app. |
| **Lithophane** | Photo to lithophane, with a Tango sample image to try. **Memory box:** up to 4 photos, snap, frame or enclosed styles, and a light base. |
| **FDM Slicer** | Wraps the PrusaSlicer CLI. Creality K1 profile, printer picker covering many brands (Longer included), and a CFS / AMS filament slot picker. |
| **TorchC0 (resin)** | Resin program with resin cost estimate and island / suction-cup detection. |
| **ZEIM CAD** | Smart Split and Smart Merge, manual merge, hinges, print-in-place joints, Measure (including the angle between faces), simplified import for big models, and select mode. |
| **Showcase** | Community feed. Remix Yes / No switch per upload, credited remixes, and re-upload protection using a shape fingerprint plus **Report a copy**. |
| **Export** | One format picker with file naming: STL, 3MF, OBJ, SVG, PLY, GLB, AMF, and G-code from the slicer. |
| **Smart Fix** | Mesh repair and auto-orient. |
| **Learn** | Guided lessons inside the app. |
| **Themes** | Japanese-inspired theme per section. |

## In progress

These are not finished yet:

1. **2D to 3D tab** using a free, open model (being built now).
2. **Bust mode.**
3. **Live Sculpt.**
4. **Subscriptions:** the core stays free forever; optional Semi Pro and Pro plans are planned. Details are not final.

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

Tests use temporary data folders; slicer and printer tests use mocks.

## Layout

```
app/api/         HTTP routes
app/core/        geometry, export, resin, mesh tools
app/services/    slicer, printers, settings, accounts
app/community/   showcase, moderation, fingerprint, licensing
static/          web UI
tests/           pytest suite
```

## Community rules

ZEIM is for adults only (18+). Please read the [Community Guidelines](static/COMMUNITY_GUIDELINES.md).
