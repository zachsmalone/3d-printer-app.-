# ZEIM

**Nightmare Ops Studios: _Uno loco aedificamus_** ("We build in one place")

**ZEIM** is an all-in-one 3D-printing maker app and community for adults (**18+ only**). Find a design, model it in CAD, sculpt it, fix it, slice it, turn a photo into a lithophane, and share what you print, all in one place.

ZEIM works as **the whole toolbox, or as one tool** next to the apps you already use: easy import, export, sharing and download, so makers can move files in and out freely. Our long-term goal is to be the one place makers need, built by studying the biggest tools in the field from public sources and then writing our own original code.

Made by **Nightmare Ops Studios**. Groups in the app are called **Build Plates**. Our five pillars live in [`reports/HQ/pillars.md`](reports/HQ/pillars.md).

## Our promises

- **Core is free forever:** CAD, sculpt, slicing, lithophanes, plate editor, community and downloads.
- **Optional supporter plans (after the pilot):** **Semi Pro $3.50/mo** and **Pro $5.50/mo** for perks like priority slicing, more storage and early access. Plans help cover hosting (about $400/mo) and never lock core features. Perks may change.
- **Safe by design:** Mild NSFW means **artistic nudity only, nothing lewd**. The maker must tag it, it is hidden by default; only people who turn it on in settings see it, as a blurred "Mature content" card that asks "Are you sure?" before opening. Lewd or suggestive figures (anime included) and explicit content are banned. All "I printed this" photos are moderator-reviewed. No school features.
- **Inclusive:** FDM and resin printers, plus accessibility options.
- **Honest:** we say what is done and what is not, and badge our own designs **Simulated** or **Test-printed**.

## What you get

| Tab | What it does |
|---|---|
| **CAD** | Sketch with exact sizes and constraints, extrude, cut, revolve, shell, fillet and chamfer, patterns, mirror and booleans; tap a face or edge for pop-up buttons and drag arrows to push, pull and round edges; editable history, parts list, measure and section view. Open your own STL, OBJ or 3MF, fix it, and save it as a new version without touching the original. |
| **Sculpt** | 7 brushes, size and strength, X symmetry, add detail where you need it, and touch support (one finger sculpts, two orbit). |
| **Showcase** | Trending, Following, search with history, favorites, follows, remix credit chains, and moderator-reviewed **I printed this** photos. |
| **Slicer** | In-app slicing with PrusaSlicer (run unmodified). Printer and nozzle picker (0.1-1.0 mm), Beginner / Advanced settings, **Will it print?** badge, layer preview, print time, grams and optional filament cost, paint-on supports, multi-file upload, and **Open in your slicer** (3MF / STL). First tested on a Creality K1. |
| **Plate editor** | Select, move, rotate and resize items, auto-center, arrange, group, merge, duplicate, hide and delete; **cut** with connectors (magnet, dovetail, pin or glue) and raised or engraved **text**. |
| **Lithophane** | Photo to lithophane: heart, circle, star, square, globe, cylinder / cup wrap and night-light, with a backlit **Light on** preview. |
| **Smart Fix** | Mesh repair, auto-orient, smart split, calibration wizard and failure photo doctor. |
| **2D to 3D** | Logo and drawing tracing to extruded shapes (keychains, signs, cookie cutters) and layered colour prints. |
| **Account** | Account, passkeys, settings, and light / dark mode. |

## Launch plan (in waves)

1. **Invite-only pilot (about Nov 12, 2026):** CAD, Sculpt, slicer with the K1, lithophanes, import / export / sharing, and the community, polished and stable.
2. **Right after:** Texture wrap (image or built-in patterns such as brick, plaid, skulls, feathers and checkered as surface relief, in the Slicer and CAD), the slicer supports upgrade (base outline, overhang highlight, normal / snug / tree supports, infill icons, feature-coloured preview) and full resin support.
3. **Later:** public launch, optional supporter plans, more printers, free CC-licensed community models with creator credit, more CAD tools (draggable pivot, Replace Face) and full AI photo-to-3D once hosting costs are known.

Details and status: [`ROADMAP.md`](ROADMAP.md).

## Tools we use

| Area | Tools |
|---|---|
| **Server** | Python 3, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), python-multipart, httpx |
| **3D geometry** | [trimesh](https://trimesh.org/), [manifold3d](https://github.com/elalish/manifold) (booleans and CAD solids), NumPy, SciPy, Shapely, mapbox-earcut, rtree, networkx, fast-simplification |
| **Images** | Pillow, pillow-heif (iPhone photos), scikit-image, matplotlib, segno (QR codes for sharing) |
| **Slicing** | [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) CLI, run unmodified as a separate program |
| **Web UI** | Plain HTML, CSS and JavaScript with [three.js](https://threejs.org/) and OrbitControls for the 3D views |
| **Accounts and security** | py_webauthn (passkeys), cryptography, lxml (safe 3MF reading) |
| **Testing** | pytest, Playwright (Chromium and WebKit browser tests) |
| **Team and hosting** | GitHub (private repo, Dependabot, secret scanning, branch protection), ngrok for test links, Docker |

## Credits

Slicing powered by [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) (AGPL-3.0), run unmodified as a separate program. See [`docs/licensing.md`](docs/licensing.md). ZEIM's CAD and sculpt code is original; we study other tools from public docs and videos only, and never copy GPL or AGPL code or assets into the app.

## Run

```bash
cd /workspace/photo3d
python3 -m venv --system-site-packages .venv && . .venv/bin/activate && pip install -r requirements.txt   # first time
./run.sh                 # background, http://localhost:8765, THIS COMPUTER ONLY (PORT=9000 ./run.sh to change; logs: server.log; stop: kill $(cat server.pid))
HOST=0.0.0.0 ./run.sh    # opt-in: reachable from your network (LAN testing). There is NO real login yet - anyone who can connect can use it; a warning is logged.
PHOTO3D_MODE=shared      # default for any server others use; ./run.sh sets local for your own machine
python -m pytest -q tests          # full test suite (~20 min); on a small machine run it alone: flock /tmp/zeim-fullsuite.lock python -m pytest -q tests
PYTHONPATH=. python tests/render_previews.py ; python tests/ui_smoke.py ; python tests/ui_cadws.py   # preview PNGs / headless UI smoke tests
```

Slicing needs a slicer CLI: `sudo apt install prusa-slicer` (the dev box has 2.9.2). Without one, **Slice** and **Send** answer gracefully with `available: false` and instructions; exports still work.

Dev extras: `pip install -r requirements-dev.txt` (adds pytest and Playwright). Runtime pins are in `requirements.txt`; the full resolved tree is in `constraints.txt` (`pip install -r requirements.txt -c constraints.txt`). Copy `.env.example` to `.env` for deploy flags. Env overrides for tests: `PHOTO3D_OUT`, `PHOTO3D_DATA`.

## Layout

```
app/main.py            app factory           app/branding.py  names (single source)   app/config.py  limits/paths
app/core/              geometry, exporters, CAD ops, sculpt, memory guard, thumbnail
app/services/          slicer, printers, handoff, settings, accounts, history, edit projects
app/community/         identity, privacy, catalog, moderation, safety, store
app/api/               HTTP routes
static/                web UI (cad.html / cad.js for CAD and Sculpt)
workbench/             opt-in design workbench at /workbench/ (see workbench/perplexity/README.md)
data/  outputs/        runtime state (git-ignored)
tests/                 pytest + UI smoke scripts
```

Code directory name on disk: `photo3d`.
