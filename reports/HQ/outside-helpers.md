# Briefs for outside helpers (Claude, Perplexity) - from Mr. Yami Kato, VP of Nightmare Ops

ZEIM: free, family-friendly photo-to-3D-print + maker community app. Repo: https://github.com/zachsmalone/3d-printer-app.- (branch `zeim` is the source of truth). Python FastAPI backend (app/), plain JS frontend (static/), tests in tests/. Rules: no payments, no NSFW, groups are called Build Plates, honest wording (no unverifiable competitor claims, untested things labeled untested), kids' data safety first.

## Claude (code)
- Work only on your own branch named `claude/<topic>`, branched from `zeim`. Never push to `zeim` or `main`.
- One topic per branch, with tests (pytest). Keep changes small.
- Current assignment: research + prototype for the in-app K1 slicer: wrap an open-source engine (CuraEngine or PrusaSlicer/OrcaSlicer CLI) behind `POST /api/slice` returning G-code + time/filament estimate, with a Creality K1 profile (220x220x250 mm, 0.4 mm nozzle). Note the engine's license (AGPL etc.) in the PR description.
- When done, tell Zach the branch name; Yami's build line runs the full suite and merges if green.

## Perplexity (research)
- Deliver a short markdown report with sourced links for every fact. No guesses; mark unknowns.
- Assignments:
  1. Slicer engines usable server-side (CuraEngine, PrusaSlicer, OrcaSlicer): license, CLI, K1 profile availability.
  2. Pilot hosting under $80/month for a small FastAPI app with ~20 GB storage: 3 options with current prices.
  3. Free or low-cost legal help for a free family/kids app (law school clinics, startup programs) in the US.
  4. Domain name ideas for "ZEIM" availability and typical registration cost.
- Give the report to Zach to paste to Yami, or save as reports/research/perplexity-<topic>.md via a `perplexity/<topic>` branch.
