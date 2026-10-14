# ZEIM

**ZEIM** is an all-in-one 3D-printing maker app and community for adults (**18+ only**): find a design, fix it, slice it, turn a photo into a lithophane, and share what you print, all in one place.

- **Core is free forever:** make, slice, lithophanes, plate editor, community and downloads.
- **Optional supporter plans (after the pilot):** **Semi Pro $3.50/mo** (priority slicing, more cloud storage, supporter badge, no wait on heavy jobs) and **Pro $5.50/mo** (everything in Semi Pro plus fastest jobs, early access to new tools, and later AI photo-to-3D credits). Plans help cover hosting costs (about $400/mo) and never lock core features. Tier perks may change.
- **Clean and safe:** no NSFW, no school features. All "I printed this" photos are moderator-reviewed.
- **Inclusive:** FDM and resin printers both supported.

Our five pillars live in [`reports/HQ/pillars.md`](reports/HQ/pillars.md). Groups are called **Build Plates**.

## What you get

| Tab | What it does |
|---|---|
| **Showcase** | Trending, Following, search with history, favorites, follows, remix credit chains, and moderator-reviewed **I printed this** photos. |
| **Slicer** | In-app slicing with PrusaSlicer (run unmodified). Printer and nozzle picker (0.1-1.0 mm), Beginner / Advanced settings, **Will it print?** badge, multi-file upload, and **Open in your slicer** (3MF / STL) for Creality, Bambu Lab, Prusa, Elegoo and Anycubic. First tested on a Creality K1. |
| **Plate editor** | Shapr3D-style: select, move, rotate and resize single items, auto-center, arrange, group/ungroup, merge/separate, duplicate, hide and delete. |
| **Lithophane** | Photo to lithophane: heart, circle, star, square, full-sphere globe, Cylinder / Cup wrap and night-light, with a backlit **Light on** preview (warm or cool light). |
| **Smart Fix** | Mesh repair, auto-orient and smart split. |
| **2D to 3D** | Logo / drawing tracing to extruded shapes (keychains, signs, cookie cutters), then layered colour prints. |
| **Account** | Account, settings, and light / dark mode. |

**ZEIM Originals** are our in-house designs, each badged **Simulated** or **Test-printed**.

## Coming next

1. First layer-by-layer preview, calibration wizard, and failure photo doctor.
2. Paint-on supports, cut tool with connectors, text/emboss, snap measure.
3. Print time and filament cost estimate, a "Print this next" queue, and one-click remix (credit kept).
4. Full resin support: resin slicing, auto-hollow with drain holes, resin supports, resin lithophane settings, and safety notes (gloves, ventilation, IPA).
5. Free CC-licensed community models, each credited to its creator and source site.
6. Database storage upgrade.
7. Optional supporter plans (after the pilot).
8. Full AI photo-to-3D (after launch, once hosting costs are known).

## Timeline

- **Invite-only pilot first**, then **public launch around Nov 12, 2026**.
- Details and status: [`ROADMAP.md`](ROADMAP.md).

## Credits

Slicing powered by [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) (AGPL-3.0), run unmodified as a separate program. See [`docs/licensing.md`](docs/licensing.md).

## Run

```bash
cd /workspace/photo3d
python3 -m venv --system-site-packages .venv && . .venv/bin/activate && pip install -r requirements.txt   # first time
./run.sh                 # background, http://localhost:8765, THIS COMPUTER ONLY (PORT=9000 ./run.sh to change; logs: server.log; stop: kill $(cat server.pid))
HOST=0.0.0.0 ./run.sh    # opt-in: reachable from your network (LAN testing). There is NO real login yet - anyone who can connect can use it; a warning is logged.
PHOTO3D_MODE=shared      # default for any server others use; ./run.sh sets local for your own machine
python -m pytest -q tests          # end-to-end tests: tests/test_app.py + tests/test_features.py (temp data dirs; slicer + printer upload tests use mocks)
PYTHONPATH=. python tests/render_previews.py ; python tests/ui_smoke.py ; python tests/ui_edit.py ; python tests/ui_showcase.py   # preview PNGs / headless UI smoke tests (ui_edit.py writes previews/ui_edit*.png)
```

Slicing needs a slicer CLI: `sudo apt install prusa-slicer` (already installed on the dev box: 2.9.2). Without one, **Slice** and **Send** answer gracefully with `available: false` + instructions; exports still work.

Dev extras: `pip install -r requirements-dev.txt` (adds pytest and optional Playwright for `tests/ui_*.py`). Runtime pins are in `requirements.txt`; the full resolved tree is in `constraints.txt` (`pip install -r requirements.txt -c constraints.txt`). Copy `.env.example` to `.env` for deploy-oriented flags. Env overrides for tests: `PHOTO3D_OUT`, `PHOTO3D_DATA`.

## Layout

```
app/main.py            app factory           app/branding.py  names (single source)   app/config.py  limits/paths
app/core/              geometry, exporters, autotune, thumbnail
app/services/          slicer, printers, handoff, settings, accounts, history, edit projects
app/community/         identity, privacy, catalog, moderation, safety, store
app/api/               HTTP routes
static/                web UI
data/  outputs/        runtime state (git-ignored)
tests/                 pytest + UI smoke scripts
```

Code directory name on disk: `photo3d`.
