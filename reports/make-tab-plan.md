# Make tab: engineering plan (parametric generators + ZEIM Originals)

Author: Haruto Tanaka (Engineering). Date: 2026-10-04. Status: **PLAN ONLY, no app code was changed** (a phone test is running).
**Update 2 (2026-10-04, evening):** new direction from Zach via Yami, a **printer type choice (FDM or Resin)** across Studio, Make, Edit and Print. New sections **16** (printer type), **17** (manifest field `printer`, plus licence fields) and **18** (inspection of Zach's test STL); tickets MAKE-15 to MAKE-19 added to section 13; section 15 now records the answered decisions (Make builds count toward the 5-build cap, previews do not; CJK font is a low-priority ticket; Make for class students sits behind a teacher switch, default OFF). Sections 1–14 are otherwise unchanged except where marked *(updated)*.
Everything below is a design. The only things I ran are small scratch experiments in `/workspace/make-scratch/` (outside the repo); each is labelled **[scratch]**. Nothing has been printed, and nothing has run on a real iPhone or on Zach's Creality K1.

Read first: `README.md`, `app/core/{geometry,exporters,meshedit}.py`, `app/api/{builds,edit}.py`, `app/api/guards.py`, `app/community/{safety,catalog}.py`, `app/services/{history,slicer}.py`, `reports/{design-ios-send,send-privacy,creality-k1-research}.md`, `reports/HQ/{README,decisions,board}.md`, `library/originals/source/*`.

## 1. What we are building (one paragraph)

A fifth top-level tab, **Make**: pick a design, move sliders (size, text, pattern), watch a live 3D preview, then **Build** to get STL / 3MF / OBJ through the same download, Print, Send and privacy path every other ZEIM build uses. All geometry is code-generated from ZEIM's own parametric recipes, so there are no third-party models inside. First batch: flexi animal, catchall bowl (twist pattern), piggy bank with name text, planetary gear toy, pet hideout box, bottle scoop, book stand, pen cup. Separately, a read-only **ZEIM Originals** library (CC0) appears in Showcase with a clear label. *(updated)* Every design and build also carries a **printer tag (FDM / Resin / Both)** and the user has a **My printer** preference; validation, hints and export defaults differ per type (section 16).

## 2. What already exists that we reuse (so the new code stays small)

| Need | Existing piece | Note |
|---|---|---|
| Mesh kernel | `manifold3d 3.5.4` (Apache-2.0), `trimesh 5.1.1`, `shapely 2.1.2`, `numpy`, `scikit-image`, `fast-simplification` in the repo venv (`requirements.txt`, Python 3.13.5) | **No** CadQuery, OpenSCAD, build123d installed. Nothing new needs installing. |
| Model container | `geometry.Model` / `Body` (named bodies, colour, `single` merged mesh) | Generators return a `Model`, so STL/OBJ/3MF writers (`exporters.WRITERS`), `mesh_stats`, `preview_payload`, history cards and the viewer work unchanged. |
| Exports | `exporters.to_stl/to_obj/to_3mf` | 3MF object names come from `Body.name`, so part names must be generic ("body", "cap"), never user text. |
| Mesh health | `meshedit.analyze()` (watertight, boundary/non-manifold edges, components, internal voids), `builds.mesh_stats` | Reuse; add part-aware checks (section 7). |
| Text → outline | `meshedit.text_polygon()` (matplotlib `TextPath`, bundled DejaVu) | **[scratch]** first call 160 ms, later calls about 2 ms. **Gap found:** DejaVu has no kana/CJK (`あ` is not in the font's cmap), yet `text_polygon("さくら")` returns shapes (almost certainly "missing glyph" boxes; not looked at). The Edit text tool has the same gap. Needs a glyph-coverage check (section 8). |
| Text filter | `safety.check(text, context)` → `ChatBlocked` 422/413/503, `textcap.text_in()` length cap first | Use exactly as `editproj.check_op_text` does. |
| History / privacy | `services.history.store` (5-build cap per owner, `kind` field), `community.privacy`, `guards.send_caps` | Add `kind: "make"`; the existing owner-only, visibility, Send-policy rules then apply unchanged. |
| Limits / rate limit | `core.ratelimit.hit()`, `config` env flags, `MAX_FACES` | Same pattern. |
| Slicer smoke | `services.slicer` (PrusaSlicer 2.9.2 present on the box) | **[scratch]** a 2,894-triangle twisted bowl sliced in 1.9 s with the generic profile (224 layers). |
| Viewer / UI | `static/viewer.js` (three.js), Beginner/Expert pattern, `/api/config` names | Make tab reuses them. |
| Originals so far | `library/originals/` has `.stl` + `.png` pairs and `source/{zkit,m_figures,registry,run}.py` (SDF + marching cubes, own `validate()`, `min_gap_between_bodies`) | **No manifest yet** (being generated). Section 11 proposes one. |

## 3. Module layout

```
app/generators/
  __init__.py        REGISTRY: dict[str, Generator]; register(); get(); public_list()
  base.py            Param types (Float, Int, Choice, Bool, Text), Generator dataclass, validate_params(), BuildResult
  kit.py             shared helpers: manifold<->trimesh/Model bridge, lobed_profile(), rounded_rect(), gear_profile(),
                     text_plate(), place_on_bed(), segments_for(quality)
  checks.py          validate_result(): watertight / winding / volume / components / min_gap / size / triangle caps / flat base / overhang %
  tested.json        data file: per generator {version, status: "untested"|"printed", printer, date, filament, note}  (not code)
  pen_cup.py  catchall_bowl.py  book_stand.py  bottle_scoop.py  piggy_bank.py  pet_hideout.py
  planetary_gear.py  flexi_animal.py  coupon.py (proposed, see MAKE-3)
app/api/make.py      router /api/make  (included in app/main.py next to builds/edit)
static/make.js, static/make.css      tab UI (Studio/Edit-style Beginner/Expert); not touched until the tickets start
tests/test_make_framework.py  test_make_api.py  test_make_<generator>.py  ui_make.py (headless browser, phone size)
library/originals/manifest.json     (Originals, section 11)
```

A generator is one small file:

```python
GEN = Generator(
    id="catchall-bowl", version=1, title="Catchall bowl", blurb="A small bowl with a twisting pattern.",
    category="useful", print_in_place=False, orientation="flat on the bed, no supports",
    params=[Float("diameter", "Width", 40, 120, 80, unit="mm", beginner=True), Int("lobes", "Number of waves", 3, 12, 7),
            Float("twist", "Twist", 0, 90, 45, unit="°"), ...],
    presets={"Small": {...}, "Medium": {...}, "Large": {...}},
    constraints=lambda p: [("wall", "Wall must be thinner than half the width")] if ... else [],
    est_triangles=lambda p, q: ...,        # pre-flight cost estimate, checked BEFORE any geometry runs
    build=build,                           # (params, quality) -> list[Part]; Part(name, manifold, color=None, moving_pair=None)
)
```

`build()` works with `manifold3d.Manifold` / `CrossSection` (guaranteed-manifold CSG, extrude with twist, revolve, `min_gap`, `decompose`). `kit` converts to `geometry.Model`: **[scratch]** `Manifold.to_mesh()` → `vert_properties[:, :3]` + `tri_verts` → `trimesh.Trimesh` worked, and the twisted bowl came back watertight with 0 boundary and 0 non-manifold edges, same result through the existing `meshedit.analyze()`. Generators never import from `app/api` or touch files.

## 4. API

All under `/api/make`, session-based like the rest (`Depends(get_actor)`); no new auth concepts.

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/make/generators` | List designs + parameter schemas | Per design: `id, title, blurb, category, version, print_in_place, orientation, params[]` (key, label, type, min, max, step, default, unit, help, group, `beginner`), `presets`, `tested` (status/label from `tested.json`), `est_bed_mm`. Cacheable; same for every visitor. |
| `POST /api/make/{id}/preview` | Fast low-detail mesh for live preview | Body `{params}`. Nothing stored, no history slot. Returns `{preview: preview_payload, stats: {size_mm, triangles}, warnings[], checks: "draft", took_ms}`. |
| `POST /api/make/{id}/build` | Final mesh + files in history | Body `{params, title?, auto_delete_oldest?}`. Same shape as `/api/generate` (summary + preview + `stats` + `history`), same `409 history_full`, same `title` filter. Writes `model.stl/.obj/.3mf` + thumb. |
| existing `/files/{bid}/…`, `/api/download/…`, Print/Send, visibility, delete, Showcase publish | unchanged | A Make build is `kind: "make"` with `{generator, version, params}` in `meta.json`; `builds.load_model()` rebuilds it from those after a restart (like photo builds rebuild from the source image). |

Errors: `400 {code:"bad_params", fields:[{field, message}]}` (inline per field); `422` filter blocks exactly as elsewhere (`code, message, context`); `422 {code:"make_check_failed", message, checks}` if the final mesh fails validation (nothing stored); `429` rate limit; `503 {code:"busy"}` when the compute queue is full.

## 5. Parameter validation and limits

1. **Schema first, geometry second.** Unknown keys rejected; types strict (`True` is not an int; NaN/inf rejected); every number has `min/max` from the schema and is **refused**, not silently clamped, with a per-field message (sliders cannot send out-of-range values anyway, so a refusal means a hand-made request).
2. **Cross-field constraints** per design (`constraints(params)`), e.g. wall ≥ 1.2 mm and < ½ width, coin slot narrower than the body, text fits its plate. Messages are plain words, shown next to the field.
3. **Cost estimate before building:** `est_triangles(params, quality)` must be ≤ the cap (draft 20,000; final 400,000, lower than `meshedit.MAX_FACES` = 3,000,000 because phones download these) or the request is refused with "Reduce Number of … or Detail".
4. **Size cap:** bounding box must fit the printer envelope setting *(updated: FDM envelope shown here; Resin uses its own, section 16)*; default **220 × 220 × 250 mm** (K1, `creality-k1-research.md`, official spec) with a hard ceiling of 300 mm per side. Over 200 mm in any direction shows a "check your printer's bed" warning. Per-design `est_bed_mm` is shown on the card.
5. **Printability floors by construction:** wall ≥ 1.2 mm (≥ 2 perimeters at 0.45 mm line width, the Prusa default for a 0.4 nozzle), no detail smaller than 0.8 mm, flat bed contact ≥ 20 mm², overhang past 45° reported (not hidden).
6. **Print-in-place clearance floor 0.20 mm per side**; below that the request is refused (section 7).
7. **Text:** `text_in(value, 12)` for piggy bank (design-specific cap, never above 24), NFKC-normalised, control and zero-width characters stripped **before** both the filter and the renderer, filtered with `safety.check(text, "make:text")`, then glyph-coverage checked (section 8).

## 6. Live preview: fast vs final

* **Draft quality** (preview): fewer circular segments (about 24–32 instead of 96), fewer twist divisions, coarse text outline, no min-gap/decompose checks; triangle cap 20,000 (a payload under about 0.5 MB base64 over cellular). **Final quality** (build): 96 segments, full `checks.validate_result`.
* **Client:** slider `input` events debounced about 200–250 ms, one request in flight (new request aborts the old with `AbortController`), a small "Updating…" `aria-live` status, the old mesh stays visible until the new one arrives, numbers always editable by keyboard.
* **Server:** LRU cache keyed by `hash(id, version, quality, params)` (e.g. 64 entries, size-bounded); compute in a bounded worker pool (2 workers, queue of 8; a full queue answers 503 "busy"). In shared mode use a **process** pool so a runaway request can be killed at a timeout (draft 3 s, final 15 s); manifold calls cannot be interrupted from a Python thread. In local mode and tests threads are fine. *Process-start/pickling overhead is not measured; to be measured in MAKE-2.*
* **Speed evidence so far [scratch]:** twisted bowl (2,894 triangles) built in 11–16 ms; a 5-body gear set (2,820 triangles) in 25 ms; text outline 2–160 ms. That says simple designs are comfortably interactive on this box. **Not measured:** flexi animal (many joints), pet hideout with vents (many boolean cuts), anything on a phone-class or hosted server. **Budget to hold:** draft p95 ≤ 400 ms, final ≤ 3 s on this box; if a design misses it, reduce draft detail before reaching for tricks.
* **Rejected for now:** running the geometry in the browser (manifold's WASM build). It would give zero-latency sliders but means a second code path that must match the server byte for byte, plus vendoring. The server stays the source of truth; revisit if hosted CPU cost is a problem.

## 7. Print-in-place, tolerances and the "untested" label

**Starting values come from public sources and are not validated on Zach's K1:**
* Prusa Knowledge Base, "Modeling with 3D printing in mind": "an initial good measurement for movable parts is at least 0.3 mm"; one extrusion line (0.45 mm for a 0.4 nozzle) is the basic unit of accuracy.
* Prusa forum thread "What Are The Minimum Reliable Printing Distances?": separation between print-in-place parts "is easy down to about 0.25 mm"; polygon approximation of curves can leave "barely 0.1 mm" in spots.
* A third-party hinge guide (meshra.ai, a blog; treat as weaker evidence): 0.15–0.25 mm per side on a tuned PLA printer, 0.30–0.40 on entry-level, +0.05–0.10 for PETG, and a 0.4–0.6 mm chamfer at the bottom of moving joints against first-layer squish.

**Design decisions that follow:**
1. Parameter **Fit**: Snug 0.25 / **Standard 0.35** / Loose 0.45 mm per side (Beginner: three buttons; Expert: number, minimum 0.20). Default is the conservative Standard.
2. Clearance is measured on the **real output mesh**, not the ideal parameters: `min_gap(partA, partB)` for each declared moving pair must be ≥ 0.9 × the requested clearance, which also catches facet effects. Curves use ≥ 96 segments in final quality.
3. Hinge/pin axes vertical (gap is horizontal on every layer), 0.5 mm chamfer on the underside of moving interfaces, designs flat-bottomed so they print without supports.
4. Print-in-place sets are emitted as **one body with several separate shells** in 3MF/STL, so positions are kept. *Unverified:* some slicers split multi-object 3MF files and auto-arrange them; to be checked in PrusaSlicer on this box and in Creality Print by Zach (open question 10).
5. **Planetary gear arithmetic (found with the scratch prototype):** ring teeth R = S + 2·P, and N planets only mesh at equal spacing when (S + R) / N is a whole number. **[scratch]** my first quick gear set used S=12, P=10, R=32, N=3 (44/3 is not whole); `min_gap` reported 0 between the sun and two planets, and `decompose()` returned 1 component instead of 5. So these two checks do catch a wrong gear set. The generator will therefore offer only valid (S, P, N) combinations and compute R. The teeth in that scratch were crude blocks, not a real tooth profile; the real generator needs a proper involute-style profile plus backlash and a rotation sweep test. This is the riskiest design in the batch.
6. Every design card and every Make build shows a pill. Print-in-place designs read **"Untested: not yet printed on a Creality K1. The gap may need adjusting."** Others read **"Untested on a printer."** Status comes from `tested.json` and is keyed to the generator `version`; **any geometry change bumps the version and resets the status to untested.** Only Engineering edits it, and only after Zach reports a print (date, filament, printer, result, optional photo). The word "tested" is never shown otherwise.
7. Supporting proposal (MAKE-3): a tiny **clearance coupon** generator (pins/gaps at 0.20 … 0.45 mm). One short print on the K1 tells us which Fit setting to trust before the gear and flexi animal are claimed to work.

## 8. Safe by default

* **Text** (only piggy bank in batch 1, but built as `kit.text_plate()` for reuse): flat plate or band **designed into the model** (avoids the curved-surface problem Edit text has); cap, normalise, strip invisible characters, `safety.check`, then **glyph coverage**: refuse any character the bundled font cannot draw, with a plain message ("Use letters A–Z and numbers 0–9 for now"). *Japanese names need a CJK-capable font; that is an open decision.* The 3MF `Title`/object names stay generic; the text exists only as geometry the user sees (follows Kenji's "no personal metadata in files").
* **Name text and the filter:** the existing filter blocks bad language, emails, phones, links, handles and addresses. It does not stop a first name, which is the point of a piggy bank. Whether names are allowed, for whom (teens, class students) and what the Showcase publish warning says is Kenji's call (open question 3). Default proposal: allowed, build is Private as usual, text re-filtered on publish.
* **Rate limits** (`ratelimit.hit`, env-tunable): preview 120/min per session and 600/min per address; builds 20/hour per session on top of the 5-build history cap; bounded compute queue; per-request time limit; pre-flight cost estimate.
* **No server emailing.** Make adds no outbound path. Output leaves ZEIM only through the existing Send rules (`guards.send_caps`): teens, un-gated visitors and class students get Download only; adults get the rest. A Make build contains no photo, so the "photo inside the file" warning does not apply, but text on a piggy bank is user text; same table, no new rule.
* **Original designs only.** Every recipe is written from primitives (circles, extrusions, twists, revolves, gear maths); no imported STL/SCAD, no scraped listings. Each design gets a one-paragraph brief in its file header saying what it is and that it is original. Names, tags and titles avoid trademarks and character names; **no weapons** (none in this batch; the scoop and stand are household items). A test fails if a generator title/tag contains an entry from a small deny list kept in `tests/` that Kenji maintains. "Flexi" is used as a generic description of a jointed print, not a product name; Kenji please include "Make" itself in the trademark check (open question 6).
* **Honest labels on three designs:** *Pet hideout:* "Not tested with animals. Check your filament is safe for pets." *Bottle scoop:* "Not food-safe (3D prints are porous). Not a measuring tool; the volume is approximate." *Piggy bank cap / small parts:* "Contains small parts. Adult supervision for children under 3." Wording is a draft for Kenji; counsel should look at the toy and food-contact lines.
* **Class use** *(updated, decided)*: Make for class students sits **behind a teacher switch, default OFF**, enforced server-side like the per-class Send switch (ticket MAKE-18). The log of the switch records the class and the time, no student names (Kenji's rule for the Send switch). The only free text in Make is the name field, which goes through the filter as above.

## 9. Validation and slicer test per generator

Shared (`checks.validate_result`, runs on every final build and in tests): finite coordinates; per-part watertight + winding consistent + positive volume; no degenerate faces; **components == expected** (print-in-place: N shells; others: 1); declared moving pairs `min_gap ≥ 0.9 × clearance`; bounding box ≤ envelope; triangles ≤ cap; lowest point at z = 0 with flat contact ≥ 20 mm²; overhang area past 45° reported (the same measure `library/originals/source/zkit.validate` uses); estimated minimum wall by sampled inward rays (`trimesh` ray, same idea as zkit, not a proof). A failure refuses the build; it never reports "✔ watertight" on a bad mesh (decision already made for Hollow/Simplify).

Per generator (tests; all in the default run unless marked):
| Design | Extra checks |
|---|---|
| Pen cup, catchall bowl | Twist vs `n_divisions` (Manifold's docs warn high twist with few divisions can self-intersect; we derive divisions from twist, then test the extreme corner). Flare limited so the wall angle stays within the overhang limit. Rim and base thickness floors. |
| Book stand | Centre of mass projects inside the base footprint with margin for a book of the chosen thickness (approximate model; labelled approximate). Lip height vs slot. |
| Bottle scoop | Cavity volume is measured from the cavity solid and shown as "about X mL"; level-edge and handle thickness floors. |
| Piggy bank | Slot fits the body; body + cap are separate shells with the cap clearance; text plate stays inside the body outline; text filter/glyph tests (blocked text creates no geometry and no history item). |
| Pet hideout | Door arch height/width vs box; vent pattern never leaves < 1.2 mm bridges; hollow shell (no sealed voids: `internal_voids == 0`). |
| Planetary gear toy | Only valid (S, P, N); assembly condition; **rotation sweep**: rotate the sun through one tooth pitch in steps and assert zero intersection volume between meshing pairs; `min_gap` ≥ backlash; 5 shells. |
| Flexi animal | Shells == segment count; **pose sweep**: rotate each joint to ± its limit and assert zero intersection volume between neighbours; gap ≥ clearance at rest. |

Sweeps for every design: defaults, all-minimum corner, all-maximum corner, and 20 seeded random in-range sets. Plus export round-trip: write STL and 3MF, load with `meshedit.load_mesh`, compare volume within 0.1 %.

**Slicer test** (`@pytest.mark.slicer`, skipped if no slicer; not in the quick run): slice defaults + both corners with PrusaSlicer 2.9.2, assert exit 0, layers > 0, G-code inside the bed, and no "auto-repaired" / "open edges" lines in the log. About 2 s per slice on this box for a simple part [scratch], so roughly 8 designs × 3 sets × a few seconds. **Limit:** this proves the slicer accepts the mesh, not that the print works, and not that a K1 prints it. Only a real print changes `tested.json`.

## 10. UI on phones and iOS (to be reviewed by Sakura)

* New nav button **Make** (name in `branding.py` `SECTIONS`, configurable like the others). The top bar already overflowed at 390 px (IOS-1); a fifth button depends on that fix landing first.
* Picker: card grid, 2 columns at 390 px, each card a 44 px-minimum target, thumbnail rendered from default parameters, name, one-line blurb, the tested/untested pill.
* Design page: viewer on top, controls below in grouped accordions; Beginner shows size presets + the 2–4 most important controls (marked `beginner=True` in the schema) + Fit; Expert shows everything with numbers.
* Controls: native `<input type=range>` with a paired number box (`font-size ≥ 16px`, so iOS does not zoom), −/+ steppers, every target ≥ 44 px, visible labels with units, `aria-live` status for "Updating preview…", reduced-motion respected.
* Sticky bottom bar with **Build** (and Download after a build), above the home bar with `env(safe-area-inset-bottom)`; QA-5 showed the current sticky bar only sticks inside its panel, so Make should use a fixed bar tested at 390 and 320 px.
* The viewer must not capture page scroll on touch (IOS finding); reuse whichever fix IOS lands.
* Tests: the headless-browser pattern of `ui_mobile.py`/`ui_touch.py` at 320/375/390 px (no horizontal scroll, targets ≥ 44 px, inputs ≥ 16 px). **Real iOS Safari: unverified.**

## 11. ZEIM Originals (CC0) in Showcase

Facts: `library/originals/` currently has `.stl`/`.png` pairs and the generator sources; **no manifest yet**; the team is still generating. Proposal (to agree with Yami's team before MAKE-11; field names are mine):

```json
{"schema": 1, "license": "CC0-1.0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
 "items": [{"slug": "sleepy-loaf-cat", "title": "...", "category": "Figures & Desk Art", "description": "...", "use": "...",
            "material": "PLA ...", "tags": ["cat","desk"], "printer": "fdm", "files": {"stl": "sleepy-loaf-cat.stl", "png": "sleepy-loaf-cat.png"},
            "sha256": {"stl": "..."}, "size_bytes": 3750084, "bbox_mm": [..], "validation": {"watertight": true, "...": "..."},
            "provenance": {"method": "sdf-marching-cubes", "source": "library/originals/source/m_figures.py", "reviewed_by": "", "reviewed_on": ""},
            "printed_on": null, "created": "2026-10-04"}]}
```
* **Loader:** `catalog._originals()` next to `_seed()`, reading the manifest at start-up; items get `original: true`, `creator: "ZEIM Originals"`, `owner_sid: None`, public, `example: false`. Files are served only by manifest name (no path from the URL), and `sha256` is checked at load; an item whose file is missing or whose hash differs is skipped and logged.
* **Label:** a pill **"ZEIM Original · CC0"** on cards and project pages, distinct from the **EXAMPLE** pill used by invented seed items. Download text: "CC0: free to use for anything, no credit needed (credit is appreciated)." A "ZEIM Originals" filter chip or shelf, not mixed into Trending (open question 7). Real like/download counts only (no invented numbers, per decisions.md); counts hidden rules unchanged.
* **Honest status:** each item shows "Untested on a printer" unless `printed_on` is filled in.
* **Licensing hygiene:** CC0 only covers what ZEIM owns; provenance field plus a human sign-off (Kenji: trademark/look-alike check; counsel: whether CC0 on code-generated models is sound) before anything is marked public. 3MF can carry `LicenseTerms`/`Copyright` metadata (from memory of the 3MF core spec; verify before relying on it); STL cannot, so the license text lives in the library folder (`LICENSE-CC0.txt`) and the Showcase page.
* **Dependencies' licences (all read from public package pages):** manifold3d Apache-2.0, trimesh MIT, shapely BSD, DejaVu fonts permissive (Bitstream Vera-derived; confirm the exact text before shipping glyph-derived geometry under CC0).

## 12. Melting-pot: public research (adopt / adapt / reject)

| Source / approach | What I read | Decision |
|---|---|---|
| **manifold3d** (Apache-2.0; `Manifold.extrude(cross_section, height, n_divisions, twist_degrees, scale_top)`, `revolve`, `min_gap`, `decompose`, `genus`). manifoldcad.org class reference, PyPI page, pyproject | Docs warn: high twist with few divisions "may cause self-intersection. This is not checked here". `min_gap` returns 0..searchLength. **[scratch]** twist-extrude bowl and `min_gap` both worked as described in 3.5.4 | **Adopt** as the construction kernel. Already installed. Add our own twist/division rule and tests. |
| **trimesh** (installed, used by `meshedit`) | Mesh checks, export, ray queries | **Adopt** for validation and conversion only (not for construction). |
| **OpenSCAD** (GPL-2-or-later; combined with Apache-2.0 Manifold binaries are GPLv3; CLI `openscad --backend=manifold -o x.stl`; CLI STL defaults to ASCII). openscad-playground LICENSE.md, OpenSCAD PR #4533, command-line wikibook, mailing-list note | Needs a separate binary on every server, a second language, and GPL obligations if we ever bundle it. Not installed here | **Reject** as a runtime dependency. **Adapt its Customizer idea:** parameters declared with `[min:step:max]` ranges, choice lists and grouped tabs (OpenSCAD manual "Customizer", MakerBot/Thingiverse Customizer docs) map directly onto our `Param` schema (`min/max/step`, `Choice`, `group`). |
| **CadQuery** (Apache-2.0; `pip install cadquery`, pulls `cadquery-ocp`; OCP wheels about 59–65 MB for Linux/Python 3.13 per the ocp-build-system release page; conda is "better tested" per their docs) | B-rep kernel (true fillets, chamfers, STEP) | **Reject for now:** large new dependency chain for geometry Manifold + shapely already cover. **Revisit** only if we need real fillets/STEP. |
| **SDF + marching cubes** (what `library/originals/source/zkit.py` uses) | Great for organic figures; surface resolution is limited by the grid (0.55 mm in `m_figures.py`) | **Adapt, Originals only.** Not for print-in-place parts where gaps of 0.3 mm must be exact. |
| **Prusa Knowledge Base, Prusa forum, a hinge-guide blog** (section 7) | Clearance ≥ 0.3 mm to start; ~0.25 mm "easy"; curve faceting can eat the gap | **Adopt as starting values and as the reason to measure gaps on the output mesh.** Not a substitute for printing a coupon. |
| **Public resin-printing guidance** (3DSPRO SLA design guidelines; Forge Labs SLA design guide PDF; Formlabs hollowing blog; Lychee Slicer docs on hollowing and file formats; Carbon orientation/supports guide; Chitubox docs on file formats) | Walls ≥ 0.8 mm (0.5–0.6 mm fragile); fine features ≥ 0.5–0.7 mm; minimum gap 0.5 mm; hollow models need drain holes (2–3 mm typical, Forge Labs says 4 mm minimum) with one at the lowest point and at least two; self-supporting overhangs about 40°+ from horizontal; tilt flat faces 10–30°; Chitubox/Lychee import STL, OBJ and 3MF; Lychee treats STL/OBJ units as mm | **Adopt as starting values for the Resin profile, labelled to be verified** (I read excerpts, not full documents, and printed nothing). **Note:** the 0.2 mm minimum feature requested is not supported by these sources; kept as an opt-in "fine detail" profile. |
| **Browser-side WASM geometry** | Not researched in depth beyond manifold's own JS/WASM binding being listed on its PyPI page | **Defer** (section 6). |
| build123d, FreeCAD, Fusion-style feature trees | Not evaluated | **Out of scope** for this plan. |

Honest limits of this research: I read search-result excerpts and package pages, not full licence texts; I did not install CadQuery or OpenSCAD; the clearance numbers are community and vendor guidance, not measurements on our printer.

## 13. Tickets (priority order, effort: S ≤ ½ day, M = 1–2 days, L = 3–5 days)

The table is in priority order (IDs are not). Make starts **after** the current order Yami set (camera/upload IOS-5, top bar IOS-1, Kenji's follow-ups); nothing here blocks that work.

| ID | Ticket | Size | Depends on |
|---|---|---|---|
| MAKE-1 | Framework: `app/generators/` registry, `Param` schema + validator, `kit` bridge (manifold ↔ `Model`), `checks.validate_result`, sweep-test harness; **pen cup** as the reference design | M | none |
| MAKE-2 | API `/api/make/generators`, `/preview`, `/build`; history `kind:"make"` + `load_model` rebuild; rate limits, bounded compute queue, timeouts, text hook; tests (owner-only, 5-cap 409, filter, size caps) | M | MAKE-1 |
| MAKE-15 | **My printer setting + per-model printer tag (FDM / Resin / Both)** across Studio, Make, Edit, Print, Showcase: first-run choice, filters and mismatch warnings (warn, never block), `printer` request parameter, tag stored on builds, tests (section 16) | M | MAKE-2 |
| MAKE-3 | **Clearance coupon** generator + `tested.json` + "Untested" pill logic (proposed addition; lets Zach print one thing early) | S | MAKE-1 |
| MAKE-4 | Make tab UI: picker, schema-driven controls, live preview (debounce/abort), Beginner/Expert, phone layout (44 px, 16 px inputs, safe-area, fixed Build bar), a11y; headless tests at 320/375/390 | L | MAKE-2, IOS-1 |
| MAKE-5 | **Catchall bowl** (twist) sharing the lobed-vessel code with pen cup; slicer smoke marker | S | MAKE-1 |
| MAKE-6 | **Book stand** + **bottle scoop** (stability and cavity-volume checks) | M | MAKE-1 |
| MAKE-16 | **Resin validation + hollow with drain holes + orientation/support hints + STL-first export** (resin profile in `checks`, Edit Hollow resin mode, hint overlay, optional PrusaSlicer SLA smoke test) (section 16) | L | MAKE-15, MAKE-1, Edit Hollow bug fix (Ren: 333 shells) |
| MAKE-18 | **Teacher switch for Make** (per class, default OFF, server-enforced; log = class + time, no names); students see "Your teacher has turned Make off" | S | MAKE-2 |
| MAKE-7 | **Piggy bank + name text**: text pipeline (normalise, filter, glyph coverage, flat plate), cap clearance, small-parts label | M | MAKE-2, Kenji decision on names (class/teen use also needs MAKE-18) |
| MAKE-8 | **Pet hideout box** (arch door, vent patterns, hollow-shell checks, pet label) | M | MAKE-1 |
| MAKE-9 | **Planetary gear toy** (valid tooth-count combinations, backlash, rotation sweep, K1 coupon-based default) | L | MAKE-3 |
| MAKE-10 | **Flexi animal** (joint design, pose sweep, orientation, chamfers) | L | MAKE-3 |
| MAKE-19 | Library manifests: `printer`, `license`, `attribution`, `source_url` fields and a validator script for `library/originals/` and `library/models/`; tests | S | agree schema with Yami's team |
| MAKE-11 | Originals in Showcase: manifest loader (with `printer` and `license` fields, section 17), hash check, CC0 label + filter chip, license page, tests | M | manifest from Yami's team; Kenji sign-off; MAKE-19 |
| MAKE-12 | "Estimate print time/filament" button using the existing slicer + K1 profile, labelled estimate; slicer smoke tests wired to the marker | S | MAKE-1 |
| MAKE-13 | Publish a Make build to Showcase (stores generator + params) and "Remix" (opens the Make tab pre-filled; text re-filtered); check "Edit this" on Make builds | M | MAKE-2, MAKE-4 |
| MAKE-14 | Docs: README section, Spark Lab hook for Aiko ("change a number, see the shape"), ROADMAP, decisions | S | any |
| MAKE-17 | CJK font: bundle an open-licence CJK-capable font, glyph-coverage check for Make text; also fix the Edit text tool accepting characters the font cannot draw (**low priority**) | S | MAKE-7; font licence + size check |

Suggested release order for Zach *(updated)*: MAKE-1 → 2 → **15** → 3 (print the coupon on the K1) → 4 → 5/6 (useful shapes) → **16** (resin) → **18** → 7/8 → 19 → 11 → 9/10 (after the coupon result) → 17 last. MAKE-15 goes in early because the `printer` field changes the parameter schema and the checks; adding it later would mean touching every generator twice. Not scheduled: unit toggle (mm/in), text on a second design, custom fonts.

## 14. Risks

1. **Print-in-place may simply not work on the first K1 try** (gap, squish, orientation). Mitigation: coupon first, conservative default, honest pill. Highest-risk designs: planetary gear, flexi animal.
2. **Preview latency** for heavy designs (many booleans/joints) is unmeasured. Mitigation: draft detail, cache, process pool, budgets above; fall back to "Update preview" button for the heavy two.
3. **CPU cost when hosted** (every slider move is a compute request). Local-only for now; limits above; hosting is Zach's decision.
4. **Text in non-Latin scripts** silently draws wrong shapes today (DejaVu); Make refuses unsupported characters, and the same bug exists in Edit text (suggest a small fix ticket).
5. **Float precision:** Manifold returns 32-bit coordinates; at 0.3 mm gaps on 100 mm parts this is fine (gap check runs on the output), but gap tests must use output coordinates.
6. **3MF multi-object re-arrangement** by slicers (unverified) could break print-in-place layout.
7. **Safety wording** (pets, food contact, small parts, names on models) needs Kenji; counsel for the toy and food lines.
8. **Originals provenance and CC0 claim** need review; manifest not yet defined; naming look-alikes.
9. **Test time:** keep the default suite fast (sweeps are cheap geometry, slicer tests are marked).
10. **Disk:** each Make build stores three formats (about 0.1–4 MB); the shared box hit 100% earlier today; the 5-build cap and the existing delete flow bound this.
11. **Scope creep into Edit:** Make builds are editable through "Edit this" (merges shells; may weld print-in-place gaps if "Fix" is run). Mitigation: warning when editing a print-in-place build.
12. **Resin rules are unverified here** *(new)*: the numbers in section 16 come from public design guides, not from a resin printer; the 0.2 mm "fine detail" figure asked for is well below what those guides state as a safe minimum (0.5–0.7 mm). Everything resin is labelled "to be verified" until someone prints it.
13. **Resin hollowing depends on Edit's Hollow being fixed first** *(new)*: Ren's QA still has Hollow leaving 333 sealed shells on the vase; resin mode must not ship until that passes and the cavity-to-outside check in section 16 is in place.
14. **Library licences** *(new)*: `library/models/` now holds 156 folders of third-party-looking STLs with no manifest or licence file (section 17). They must not be shown as CC0 or ZEIM Originals.

## 15. Open questions

1. **Zach:** which K1 (K1 / K1C / K1 Max), nozzle, and usual filament (PLA?) The envelope and default clearance depend on it. Will he print the coupon first?
2. ~~Should Make builds count toward the 5-build history?~~ **ANSWERED (Yami): yes, Make builds count toward the 5-build cap; previews do not.** Built into MAKE-2.
3. **Kenji:** may the piggy bank carry a first name; for teens and class students; cap 12 characters; wording of the block and Showcase-publish messages ("Please don't put full names, phone numbers, emails or links here")?
4. ~~CJK font for Japanese names?~~ **ANSWERED: fine, low priority.** Ticket MAKE-17; until then Make refuses characters the bundled font cannot draw.
5. ~~Make for class students: default or teacher switch?~~ **ANSWERED: behind a teacher switch, default OFF.** Ticket MAKE-18. (Still open for Aiko: lesson hooks.)
6. **Kenji:** trademark check of the tab name "Make", the eight design names and tags; the small deny list for tests.
7. **Yami's team + Daichi:** Originals manifest schema (section 11); shelf vs Trending; who signs off provenance; is `LICENSE-CC0.txt` enough?
8. **Zach/Kenji:** licence of Make outputs (my default: the user owns what they generate, ZEIM claims nothing) and of the generator code itself (the repo has no LICENSE file yet).
9. **Zach/Daichi:** acceptable server CPU for live preview once hosted (affects process pool and limits).
10. **Zach (needs his slicer):** does Creality Print keep a multi-shell 3MF in place, or split it? (I can test PrusaSlicer on the box.)
11. **Kenji:** wording for the pet, food-contact and small-parts labels.
12. **Sakura:** nav placement given the top bar, card thumbnails (who renders them), viewer touch-scroll fix.
13. **Yami:** OK to add the clearance coupon as a ninth design?
14. **Zach/Yami (new, printer type):** which resin printer and slicer (Chitubox or Lychee) and its build volume? Until known, resin mode asks for the build volume instead of assuming one.
15. **Zach/Yami (new):** the "fine detail" resin profile with a 0.2 mm minimum feature: is there a printer/resin you know can do it? The public guides I read say 0.5–0.7 mm, so I propose Standard (0.5 mm) as the default and 0.2 mm as an opt-in profile labelled "to be verified".
16. **Yami (new):** first run with no "My printer" set: ask once (FDM / Resin / Not sure), with Not sure treated as FDM rules and both tags shown? Or default silently to FDM?
17. **Kenji (new):** is the "My printer" preference fine to keep in the browser only and send per request (section 16.2)? Also the licence/attribution plan for `library/models/` (section 17).
18. **Yami/Zach (new):** which Make designs should get a Resin-capable tag in batch 1? My proposal in section 16.3 is: bowl, pen cup, bottle scoop, piggy bank = Both; book stand, pet hideout, planetary gear, flexi animal, coupon = FDM.

## 16. Printer type: FDM or Resin (new)

Direction from Zach via Yami: let people say what they print on, tag every model, and validate differently per type. Zach's own printer (Creality K1) is **FDM**. Everything resin below is a design built from public guidance and **to be verified**: I have no resin printer, no resin slicer here, and nothing has been printed.

### 16.1 Concepts
* **Per-model tag `printer`: `fdm` | `resin` | `both`.** Meaning: "validated and sensible for this printer type". Make designs declare it in the generator; Studio builds get a default per mode (lithophane/relief: `both`, with a resin note that thin 0.8 mm lithophane panels are fragile); Edit projects get an advisory tag from analysis (section 16.4); Showcase and library items carry it in their manifest (section 17); an uploaded or published project stores the tag chosen by its owner.
* **My printer** = `fdm` | `resin` | unset. Unset triggers a one-time question (open question 16). It decides: which validation profile runs, which parameter limits sliders show, which export is the default download, which Print/Send rows appear, and how Showcase/library lists are filtered.
* **Filter and warn, never silently hide or block.** Lists default to "Works with my printer" (tag equals my type or `both`) with a visible chip to show everything. Opening or building a model whose tag does not match shows a plain banner ("This design is meant for FDM printers. Your printer is set to Resin. Show anyway"). Downloads stay available.
* Not the same thing as the existing **Settings > Printers** (OctoPrint/Moonraker network printers, admin-only in shared mode). Naming in the UI: "My printer type" vs "Network printers". Resin printers get no Send-to-printer rows (none are implemented); they get Download.

### 16.2 Privacy note
"My printer" is a **device preference, not account data and not needed for any account**. Proposal for Kenji: it lives in the browser (`localStorage`), is sent to the server only as a per-request parameter (`printer=fdm|resin`) on preview/build/export and stored on the resulting build record next to its other settings; it is not written to profiles, not shown to other users, not part of Showcase, not logged beyond the normal request line, and "My data > delete" clears the local value. Class students and teens use the same device-only preference; teachers do not see it. If someone has no account and clears the browser, the setting is gone and the first-run question returns. Nothing about the person is collected; counsel need not look at it unless we later add it to profiles or analytics.

### 16.3 Per-mode validation (the part that must differ)

| Check | FDM mode (unchanged rules, K1 = 220 × 220 × 250) | Resin mode (to be verified) |
|---|---|---|
| Minimum wall (solid) | 1.2 mm (2 perimeters at 0.45 mm line width) | **0.8 mm** standard. Public guides: 3DSPRO "safe default 0.8 mm", 0.5–0.6 may print but fragile; Forge Labs SLA guide "minimum wall 0.8 mm". |
| Minimum feature (fins, bosses, text strokes) | 0.8 mm | **0.5 mm** standard (3DSPRO says fine features ≥ 0.5–0.7 mm). **0.2 mm "fine detail" profile = opt-in, labelled "to be verified"**: it is below every figure in the guides I read, and may be possible only on high-resolution printers and resins. |
| Gaps / print-in-place clearance | 0.25 / 0.35 / 0.45 mm per side, floor 0.20 (section 7) | **Not offered in batch 1.** Guides give a minimum gap of about 0.5 mm (Forge Labs), plus trapped resin and support-removal problems inside moving joints. Print-in-place designs are tagged `fdm`. |
| Bed adhesion | flat bed contact ≥ 20 mm² | not a concern; instead warn on **large flat layer areas facing the build plate** (suction/peel force) and suggest tilting. |
| Overhangs | report area past 45°; designs are made support-free | supports are normal in resin; **list the areas needing supports** (faces less than about 40° from horizontal; Carbon's guide says 40° or more is most common for self-supporting) as a hint overlay, do not fail. |
| Closed cavities | allowed, reported (`internal_voids`) | **error unless drained**: a sealed hollow traps liquid resin and causes cupping (Formlabs, Lychee docs). |
| Hollowing | optional (Edit Hollow, wall default 2 mm) | recommended for large solids: wall default **1.8 mm** (what a Lychee author reports using; guides say 0.8 mm is the minimum, hollow shells are fragile), **at least 2 drain holes**, one at the lowest point and one near the top, **diameter default 3 mm** (guides: 2–3 mm, "over 2 mm" in Lychee docs; Forge Labs says a minimum of 4 mm to drain; to be verified per resin). Holes placed on the side facing away from the viewer by default and moved by the user. |
| Size envelope | printer bed setting | **resin build volume is asked**, not assumed; warn above it. A 157 mm part (section 18) is larger than many desktop resin plates (check Zach's printer). |
| Material estimate | grams from PLA density (existing slicer note) | **millilitres of resin** from model volume (1 mm³ = 0.001 mL), labelled approximate; supports and failure waste not included. |
| Default download | 3MF (colour, units) and STL | **STL first** (Chitubox Docs: import and export STL/OBJ, import 3MF; Lychee Docs: STL, OBJ, 3MF; Lychee treats STL/OBJ units as 1 unit = 1 mm). OBJ and 3MF offered second. STL units are mm already in ZEIM. |
| Slicer smoke test | PrusaSlicer FFF CLI (2 s per part [scratch]) | PrusaSlicer's CLI lists `--export-sla` (layers as PNG); an SLA smoke test would need an SLA printer profile. **Not tried; untested idea.** |

Cavity-to-outside check (the one new geometric test): after hollowing in resin mode, the result must be **one watertight component with `internal_voids == 0`**, and the mesh's Euler number must equal `2 − 2·(drain_holes − 1)`; if any sealed shell remains the build is refused with "The inside is still sealed. Add a drain hole." This reuses `meshedit.analyze()`.

Orientation and support hints (heuristic, **ZEIM never changes the user's model orientation**): evaluate tilts of 0 / 15 / 30 / 45° about X and Y (guides: tilt flat faces about 10–30° to reduce layer lines and peel force; keep overhangs above 40°; put supports on non-visible faces), score each by (area needing supports, largest layer cross-section, height), then show "Suggested: tilt 30° about X" plus the support-area overlay in the viewer. Make generators may set a default `resin_tilt`. Accuracy of the heuristic against real prints is unknown.

### 16.4 How it plugs into each place
* **Studio (photo builds):** `printer` request parameter on `/api/generate`; resin mode adds the minimum-feature check to relief/lithophane detail (warn when the pixel pitch at the chosen width is below the minimum feature, e.g. a 600-px-wide 100 mm model has about 0.17 mm pitch) and puts STL first. FDM unchanged.
* **Make:** `Generator.printer` tag + `profiles = {"fdm": limits, "resin": limits}` so a design can have different slider ranges per type (e.g. wall minimum); `checks.validate_result(profile)`; resin-tagged designs include a hollow + drain-hole option (piggy bank, bottle scoop already hollow). Batch 1 tags (open question 18): bowl, pen cup, bottle scoop, piggy bank = `both`; book stand, pet hideout, planetary gear, flexi animal, coupon = `fdm`.
* **Edit:** `printer` stored in the project; resin mode makes Hollow ask for ≥ 2 holes, runs the cavity check after every op, and shows the hints. Advisory tag from analysis: `resin`-leaning if the longest side ≤ about 100 mm AND (fine features below 0.8 mm or organic/figurine-like with many triangles); `fdm`-leaning if it is large (any side > 150 mm) or flat-bottomed and support-free; else `both`. The thresholds are my guesses and will be shown as a suggestion only.
* **Print:** the Print dialog hides FDM slicer rows and G-code Slice for Resin (PrusaSlicer FFF would be the wrong slicer) and shows "Download STL for Chitubox or Lychee"; deep links `prusaslicer://` etc. stay FDM-only. No Send-to-printer for resin.
* **Showcase / library:** tag pill on cards, "Works with my printer" chip, mismatch banner on the project page.

### 16.5 Tickets: see MAKE-15 (setting, tag, filters, warnings) and MAKE-16 (resin validation, hollow/drain holes, hints, STL-first export) in section 13.

## 17. Manifest schema addition: `printer` (new)

Add to every library item (and to Showcase `listings`/seed items later):

```json
"printer": "fdm" | "resin" | "both",
"printer_note": "optional one line, e.g. 'Large flat base; resin needs tilt and a big plate'"
```
Rules: required; unknown value = item rejected by the validator (MAKE-19); default for an item not yet reviewed is `fdm`, since the machine in hand is a K1; the validator also flags an item whose bounding box exceeds 150 mm tagged `resin`.

Which manifests need it (state of `library/` when I looked):
| Manifest | State | Needs `printer` |
|---|---|---|
| `library/originals/manifest.json` (Yami's team) | **does not exist yet**; only `.stl`/`.png` pairs and `source/*.py` | **Yes.** Section 11 schema now includes `"printer"`; they are SDF figures (penguin, cat, dragon, octo) so `both` is plausible for the small ones (the penguin measures 54.9 × 44.0 × 69.0 mm), but thin parts need the checks in 16.3 before any gets `both`. When I looked there were **29 STLs** (sizes 32 mm to 149 mm on the longest side; many are whistles/calls, stands, plaques, trinket jars) and **2 were not watertight** (`rocket-comic-panel.stl`, `space-cadet-bust.stl`; the run may still be in progress). The loader (MAKE-11) must skip any item that fails validation, and Kenji may want to review titles such as the hunting/predator "call" items for a school-friendly app. |
| `library/models/` (156 folders of STL files; names suggest NASA, Smithsonian, GitHub and Printables-style sources) | **no manifest, no licence or attribution file** | **Yes, plus `license`, `attribution`, `source_url`.** These are third-party; they must not be labelled CC0 or "ZEIM Original". Some licences (for example a well-known calibration boat) may forbid derivatives or require credit; I have **not** verified any of them. Kenji to review before anything is shown. |
| Showcase seed items (`catalog._seed()`) and user listings | no field | Add the same field (default from the build's `printer`). Not a library manifest. |
| Make generators | n/a (code) | Declared in code (`Generator.printer`), exported through `/api/make/generators`. |

Full proposed Originals/library item (extends the section 11 example):
`{"slug", "title", "category", "description", "use", "material", "tags", "printer", "printer_note", "files": {"stl", "png", "3mf"?}, "sha256", "size_bytes", "bbox_mm", "validation": {"profile": "fdm"|"resin", "...": "..."}, "license": "CC0-1.0" | "<spdx>", "attribution": "", "source_url": "", "provenance": {...}, "printed_on": null}`. Validation results are stored per profile, so an item tagged `both` should carry both a passing FDM and a passing resin profile result.

## 18. Zach's test STL: inspection (new)

File: attachment copied to `/workspace/qa/zach_test.stl` (original name unknown). Tools: trimesh 5.1.1 plus ZEIM's own `meshedit.load_mesh` / `analyze`. Render: `reports/qa_screens/zach_test.png` (a quick matplotlib view; its shading has painter's-order artefacts, shape is clear but not pretty).

| Property | Result |
|---|---|
| Format / size | Binary STL, 32,084 bytes, 640 triangles |
| Units | No units in STL; extents look like millimetres |
| Bounding box | **156.90 × 109.26 × 81.51 mm**, min corner at (0, 0, 0) (already sitting on the bed) |
| Fits a K1 (220 × 220 × 250)? | Yes |
| Mesh health | Raw file is a "triangle soup" (1,920 unshared vertices; a naive load reports 1,920 open edges), but after welding vertices (what `meshedit.load_mesh` does) it is **watertight, winding consistent, 0 open edges, 0 non-manifold edges, 1 component, 0 internal voids, Euler number 2**. ZEIM's Edit import accepts it with no warnings. |
| Volume / area | 137,150.85 mm³ (137.2 cm³), surface 117,945 mm²; centre of mass z = 30.4 mm |
| Shape (from face normals and slices) | A plain **open-top box / tray**: a 156.9 × 109.3 mm floor and four straight walls up to 81.5 mm. Vertices sit only at z = 0, 2.3, 79.5, 81.5. A slice at z = 80 splits into two pieces about 14 mm apart, which suggests a ~14 mm wide, ~2 mm deep notch in the top edge of the two long walls (one-slice reading; not looked at closely). |
| Thinnest-wall estimate | 4,000 inward-ray samples, **every one 2.33 mm** (min = median = max). So floor and walls are a uniform **2.33 mm**. Cross-section at z = 20 is 1,225 mm² with one hole, consistent with a ring wall of that thickness. |
| Overhangs / bed contact | 0 % of the area faces down past 45°; flat bottom of 17,139.5 mm² (the whole footprint) |
| Generic FDM slice (PrusaSlicer 2.9.2, 0.2 mm layers, generic profile, not the K1 profile) | 407 layers, estimate **10 h 58 min**, 51.5 m of filament; the slicer's own gram figure is 0 because that profile has no density, so my estimate from volume is about 153 g PLA (123.8 cm³ at 1.24 g/cm³). Estimates only. |

**Verdict: FDM-friendly, not resin-leaning.** FDM: flat, support-free, walls 2.33 mm (well above the 1.2 mm floor), fits the K1; the long open walls on a 157 × 109 mm floor may warp at the corners (unverified). Resin: possible, but the 157 mm length is bigger than many desktop resin plates (check Zach's), it is a big open cup whose whole flat floor (171 cm²) sits on the plate (high peel/suction force; tilt and supports advised), and it is solid-walled at 123–137 mL of resin; it has no closed cavity so it needs no drain holes. Tag suggestion: `fdm`. It looks like a CAD-made test box; I do not know what Zach intends it to test.
