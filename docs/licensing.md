# Licensing notes

> This is the ZEIM team's reading of the licences involved. It is not legal advice.

## PrusaSlicer (AGPL-3.0) — decision 2026-10-13 (Zach)
ZEIM follows the same model as MakerWorld, which slices in the cloud with Bambu Studio (AGPL) while keeping its own platform private.

- **ZEIM's own code stays private.** ZEIM does not publish its own source code, and the repository's visibility is not changed.
- **PrusaSlicer is used unmodified, as a separate program.** ZEIM runs the stock `prusa-slicer` command-line program in its own process and reads the files it writes. ZEIM never imports, links or embeds PrusaSlicer code.
- **ZEIM shares only PrusaSlicer's own source.** The credits page names PrusaSlicer, its licence (AGPL-3.0), that it is unmodified, and links to its upstream source at https://github.com/prusa3d/PrusaSlicer.

### Rule for everyone working on ZEIM
**Nobody may modify, patch, fork-and-ship, or link PrusaSlicer's code into ZEIM.** No copying its source files into this repo, no Python/C bindings to its libraries, no patched builds. PrusaSlicer is only ever called as a separate, unmodified program through its command line. If a change would need any of that, stop and ask Zach first; it would change these licence obligations.

## Copyright (DMCA) takedowns
The Terms page has a copyright takedown section with a placeholder contact.
TODO: register a DMCA designated agent with the US Copyright Office (small fee; needs Zach's OK before paying), then put the agent's contact in `static/terms.html#copyright`.

## Legal pages
Decision 2026-10-12 (Zach): ZEIM launches with no lawyers. Terms, Privacy and Rules are plain-words pages based on common free templates. Keep every statement true (18+ only, free, no payments, photo moderation, users can delete their own stuff) and do not add compliance claims.
