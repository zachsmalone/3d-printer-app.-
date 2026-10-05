# Engineering polish pass — first-time user on a phone-sized screen

Author: Haruto Tanaka (Engineering) · 2026-10-04 · Task from Zach via Yami · **Read-only review** (no edits to `app/`, `static/`, tests or the live tree).

## 0. How this was done (and what it is NOT)
- Scratch copy: `git archive haruto/work` (commit 59b205d) extracted under `/workspace/make-scratch/polish/`, own data/out dirs, own uvicorn on **port 8817** (local mode). Live app (8765) and the other dev instances were not touched. Scratch is deleted at the end of this pass.
- Walk-through at **390×844**: headless **Chrome** (mobile + touch emulation) and headless **WebKit** (Playwright "iPhone 13" profile = 390×664 viewport). Flow: Studio (sample image → lithophane) → Print dialog (+ Send sheet) → Edit (sample vase) → Hollow / Add base / Fix / Slice → Showcase (+ item) → Learn / Spark Lab lesson.
- Screenshots: `reports/qa_screens/polish/chrome_*.png`, `webkit_*.png`.
- **Headless-only / emulation.** No real iPhone, Safari, camera, Photos picker, touch-gesture feel, VoiceOver, cellular network, battery/thermals or iOS memory limit was tested. WebKit-on-Linux is not iOS Safari. Creality Print / Creality Cloud hand-off and the actual K1 were not exercised.
- **This box is shared and was heavily loaded** (RAM 15.4/16 GB used at one point; kernel log showed OOM kills of two ~4 GB python processes that are not mine, plus Chrome). Timings below swing 2–5× with load; I give ranges. My first scratch server died mid-run and headless Chrome tabs crashed ("Target crashed") three times (after Studio res-600, an Edit flow, and during the 3G-throttled run). I cannot attribute those to ZEIM vs box memory pressure — I list it as "flaky, unattributed", not as a proven app bug.

## 1. Timings (seconds, this box, scratch server)
Sample = `sample.png` 480×360 unless noted. Ranges = repeated runs under different load.

| Operation | Time | Notes |
|---|---|---|
| Studio lithophane, Beginner defaults | 1.8–2.1 s API; **3.0–3.3 s tap→result visible** (Chrome & WebKit); 2.3 s on a quiet moment | "Making your 3D model…" shows within 0.1–0.2 s. 282k-triangle model |
| Expert lithophane res 200 / 400 / **600** | 1.1 / 5.6 / **9.2–13.1** | |
| Relief res 300 | 2.1 | |
| Pop-art res 200 / **res 400, 8 levels** | 1.7 / **10.5–13.3** | |
| Large phone photo 4000×3000 JPEG (11.6 MB), Beginner | 2.7 | fine |
| Build response size | **3.2–4.0 MB** (pop-art 400: **11.3–11.6 MB**) | preview mesh base64 inside JSON; reopening a build (`GET /api/builds/{id}`) 0.26 s but still ~11 MB |
| Same build, UI over throttled "4G-ish" (9 Mbps/170 ms) | **6.1 s** vs 2.3 s unthrottled | measured. 3G-ish (1.6 Mbps) = ~20 s *calculated* from payload size; the throttled run crashed the headless tab, so **not measured** |
| Edit: import sample vase (1,872 tris) | 0.7 | |
| Edit: repair / scale / goto | 0.12 / 0.07 / 0.07 | |
| Edit: **Hollow** | **9.6** (UI 4.2 s in WebKit on a quiet moment; 3.4 MB response) | |
| Edit: **Add base** | **8.3** (UI 1.5–5.9) | |
| Edit: cut / simplify / boolean / undo / redo | 2.4 / 1.4 / 1.3 / 1.1 / 0.9 | |
| Edit: text on top face | 422 "would float free" | expected guard behaviour |
| Benchy (225,706 tris, 10.8 MB): import / repair / **hollow** / simplify / slice | 3.7 / 6.5 / **14.6** / 1.6 / 4.5 | |
| Slice (PrusaSlicer, generic profile) | 3.2–4.6 (res 400), **10.3 (res 600)**; Edit vase 2.3; UI click→result 1.4–4.6 | text: "Done: 381 layers, about 2h 5m 30s, about 23.1 g" |
| Showcase first paint | 0.3–2.8 | |
| Preview | there is no separate/instant preview: it arrives with the full build | see wow |

**Concurrency (the important one):** build work holds one global lock through geometry *and* export. While session A ran a res-600 build (8.7 s), session B's Beginner build (1.9 s alone) took **9.0 s** and `GET /api/builds` took **7.2 s**. Showcase GET was unaffected (0.01 s). In a class of 25 on one server, builds serialise.

**Memory:** server RSS 146 MB at start → ~890 MB after 7 builds → ~2.0–2.2 GB after 14 sessions. Per extra session ≈ +25 MB (Beginner) and ≈ +200 MB (res 600); the in-memory model cache is only freed on delete. Live app (8765) was ~1.3 GB RSS and the dev instance (8796) ~1.9 GB when I looked. Extrapolation (not measured): 30 Beginner students ≈ 0.75 GB; many res-600 builds = several GB.

**Disk:** per build ≈ **25 MB (Beginner lithophane), 112 MB (res 600), 91 MB (pop-art 400)** — STL, 3MF and OBJ are all written eagerly. With the 5-build cap that is up to ~560 MB per user. 14 sessions ≈ 1.1 GB. The shared root disk was at 85% during the run (3.9 → 2.4 GB free) and hit 100% earlier today.

## 2. What works well (so the list below is in proportion)
- No horizontal scroll on any screen at 390 px (scrollWidth = 390), Chrome and WebKit; first load 0.4–0.6 s; defaults to Beginner.
- Studio sample → model in ~3 s, result is scrolled into view (QA-4 fix), Print dialog fits the screen (Creality Cloud app first, slicer links under "On a computer"), Send sheet works.
- No console/page errors in WebKit; Chrome only shows swiftshader "GPU stall" WebGL warnings; no failed requests. Edit shows a "Hollowing…" overlay; Spark Lab/lesson pages render fine.

## 3. The 5 roughest edges, ranked by impact on Zach
Ranking = how likely Zach (or a class) is to hit it on a phone/shared server and how bad it feels.

### 1. Heavy operations are slow, unqueued, and block everyone (speed / flaky under load)
Res 600 (9–13 s), pop-art 400 (10–13 s), Hollow (5–15 s), Add base (~8 s), Slice at res 600 (~10 s). UI shows only a spinner/overlay: no progress, ETA, cancel or queue position. Because of the global lock, one heavy build makes **other users' 2 s builds take 9 s and even the history list 7 s**. Real-class risk. Evidence: §1 concurrency; `chrome_03b_expert600_building.png`, `chrome_10a_edit_hollow_busy.png`, `webkit_10a_edit_hollow_busy.png`.
Fix direction: move geometry/export out of the lock into a small job queue with a worker cap, `queued → running → done` states with plain-words text ("You're 2nd in line"), cancel, and separate light vs heavy lanes (same job design as SLICE-2 / Make-tab MAKE-queue).

### 2. Multi-megabyte responses and no instant feedback on phones
Every build returns 3–4 MB (up to 11.6 MB) of base64 preview in JSON; reopening a build re-downloads it. On emulated 4G the same build went 2.3 → 6.1 s; on 3G it should be ~20 s (calculated, not measured). Nothing is shown until everything arrives. Fix: smaller/binary preview (decimated, gzip/brotli, `GET .../preview.bin`), fetch lazily, and show a draft first (this is the wow below).

### 3. Memory growth and disk bloat (memory/disk)
Model cache never evicted (146 MB → ~2 GB with 14 sessions), 25–112 MB written per build in three formats, 5-build cap ⇒ up to ~560 MB/user, shared disk already hit 100% today and the box shows OOM kills. A school deployment will fall over on RAM or disk before CPU. Fix: LRU cap on the cache (reload from disk on demand), write STL first and 3MF/OBJ lazily on first download, TTL purge for anonymous sessions, show "storage nearly full" as a friendly error rather than a 500.

### 4. Phone layout/first-impression gaps (loading / empty states)
- **Edit result lands below the fold** after sample/ops: viewer at y 1174–1430 on an 844 px screen (Chrome), 894–1155 on 664 (WebKit). Only Studio auto-scrolls; a first-timer taps "sample" and sees nothing happen. (`chrome_08_edit_start.png` → `chrome_09_edit_result.png`.)
- "Model built ✔" toast covers the top bar/logo on phones.
- **Showcase cards have no real thumbnails** (0 `<img>`; gradient + emoji placeholder), and the 9 EXAMPLE seed items download a placeholder `example_model.stl`, so the page reads as unfinished. (`chrome_13_showcase.png`, `webkit_13_showcase.png`.)
Fix: scroll/focus the viewer after every Edit result (same helper as Studio), move toast below the bar, server-side thumbnails (CAT-9 / wow option B).

### 5. Failure behaviour is unverified and the box itself is flaky (error states / flaky)
Headless Chrome tab crashed 3× and my first scratch server died during heavy runs, at times of very low free RAM; cause not attributed (box OOM vs app). I did not get to verify what a user sees if the server dies mid-build, reload-restore after a refresh, switching tabs mid-build, double-tap on the sample button, Showcase "For you"/no-match empty states, or the Join-a-class dialog fit (the extra script crashed before those). Op timings varied 3–5× with load, so "it hung" reports from a phone are likely. Fix: add timeouts + a plain "That took too long — try again" state with Retry, health ping, and write tests for those paths (QA to own).

## 4. ONE wow: "Instant draft preview, then the real thing"
**What:** the moment a photo is chosen (or a setting changes) the server returns a *draft* mesh — res ~60–100, decimated, a few hundred KB, <0.5 s — that appears in the viewer immediately with a "Draft — polishing…" chip; the full-quality build then runs as a queued job with a progress bar and swaps in smoothly (camera kept). Print/Download stay disabled until the final is ready, so nobody prints a draft by accident.
**Why it is Engineering's:** it cuts perceived wait from ~3 s (10+ s heavy, ~20 s on 3G) to <1 s, removes the 4–11 MB wait-for-everything problem (edge 2), and forces the job-queue/lock fix (edge 1). It is the same draft/final design planned for the Make tab, so it is built once.
**Effort:** M–L. ~3–4 days: draft endpoint reusing the existing generators at low res (1 d); job queue + progress events SSE/polling, light/heavy lanes, cancel (1.5 d); viewer swap/draft chip, disabled print state (0.5 d); tests (1 d). Hollow/Base reuse later.
**Risks:** draft not matching final (height scale / smoothing differ — must use identical parameters and the same normalisation); more concurrent work if users drag sliders (needs debounce + cancel-previous); queue state in memory is lost on restart; memory per session must be capped at the same time (edge 3) or it makes things worse; one more state to explain to kids ("draft" vs "ready").
**What would be untested:** real iPhone/Safari memory and WebGL swap behaviour, cellular timing, Creality Print/K1 results of the final (the final path is unchanged, so print quality is unaffected in principle — not verified), behaviour with 25+ simultaneous students, and screen-reader announcement of the progress/draft state.
**Alternatives ranked:** (B) server-side 3D thumbnails for Showcase — S–M, low risk, fixes the emptiest-looking page; (C) "Does this fit my K1?" check (220×220×250 mm) — S, very low risk, valuable to Zach but needs real K1 confirmation of usable bed size; (D) one-tap "Make it print-ready" — M, medium risk (needs explainable fixes), depends on Edit repair + hollow timings above.

## 5. Headless-only vs real phone
| Verified here (headless) | NOT verified |
|---|---|
| Layout/overflow at 390 px, tap targets reachable, flows complete, timings on this loaded Linux box, payload sizes, memory/disk growth on server | Real iPhone Safari rendering, iOS memory limit/tab reloads, camera/Photos upload, touch orbit feel, haptics, VoiceOver, cellular speed, Creality Cloud/Print hand-off, a real K1 print |

## 6. Housekeeping
Scratch server (8817) stopped and `/workspace/make-scratch/polish/` deleted. No change to `app/`, `static/`, tests or the live tree (git status checked).
