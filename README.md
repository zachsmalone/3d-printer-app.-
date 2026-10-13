# ZEIM

**ZEIM** is a free, all-in-one 3D-printing maker app and community for adults (**18+ only**).

No payments. No NSFW. No school features — no teachers, classes, or grades.

One place to find designs, fix and slice them, turn a photo into a lithophane, and share what you print. Built with pride for makers who want the full path from idea to print without the clutter.

Our five pillars live in [`reports/HQ/pillars.md`](reports/HQ/pillars.md).

## What you get

| Tab | What it does |
|---|---|
| **Showcase** | The landing feed. Trending, Following, search with history, favorites, follows, remix credit chain, and **I printed this** photos held for moderator review. |
| **Slicer** | In-app slicing built on PrusaSlicer. Printer and nozzle picker (0.1–1.0 mm), Beginner / Advanced settings, a **Will it print?** badge, multi-file upload as one plate or separate prints, shrink-to-fit, and **Open in your slicer** (3MF / STL) for Creality, Bambu Lab, Prusa, Elegoo, and Anycubic. First tested on a Creality K1. |
| **CAD** | Coming soon. |
| **Lithophane** | Photo → lithophane. Shapes planned: heart, globe, circle, star, square, night-light cover — plus color options. |
| **Smart Fix** | Mesh repair and auto-orient. |
| **Account** | Your account, Settings, and light / dark mode. |

**ZEIM Originals** — our in-house flagship designs. Each is simulation-checked and badged **Simulated** or **Test-printed**.

Hobbyist groups are called **Build Plates**.

## Roadmap

- **Launch-ready target:** around **Nov 12, 2026** (invite-only pilot first)
- **Simple model editor:** about 3–4 months after launch
- **Full CAD / sculpting:** 6–12 months

Details and status: [`ROADMAP.md`](ROADMAP.md).

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
