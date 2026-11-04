# PERF8: slicer engine warm-up (measured)

**What changed:** `app/services/slicer_warm.py` runs one tiny 10 mm cube slice (nice 19) 20 s after start-up, and again after 20 minutes without any slice (`ZEIM_SLICER_WARM_MIN`). `ZEIM_SLICER_WARM=0` turns it off.

**What it cannot do:** PrusaSlicer has no server mode. Every slice still starts a new process, so a slice is not "instant". The warm-up keeps the 36 MB engine and its 222 shared libraries in the OS page cache, so a slice doesn't have to read them from disk first.

## Measurement (prod container zeim-app-1, 2 vCPU / 16 GB, 2026-11-04 ~01:00 CST)
Command: `tools/perf8_bench.py 15`. It slices a 20 mm cube with a 10 mm hole (K1 default profile) 15 times in each state, at nice 19.
- **cold** (before): before each run, the engine and libraries are dropped from the page cache (posix_fadvise DONTNEED). This is the state after a deploy, a restart, or memory pressure.
- **warm** (after): the state the warm-up keeps.

| state | p50 | p95 | min | max |
|---|---|---|---|---|
| cold (no warm-up) | 2.65 s | **5.01 s** | 2.42 s | 5.01 s |
| warm (with warm-up) | 1.20 s | **1.37 s** | 1.16 s | 1.37 s |

**Honest limits:**
- This uses a synthetic small model. On a big model the slicing itself dominates, so the saving (about 1.4–3.6 s) matters less.
- Prod has about 11 GB of free RAM, so caches rarely go cold on their own. The main win is the first slice after each deploy or restart, and after long idle periods if memory gets tight.
- This is not a measurement of real user click-to-G-code. That would need timing on the client, which isn't collected today.
