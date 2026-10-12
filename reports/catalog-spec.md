# ZEIM catalog: engineering spec

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


Author: Haruto Tanaka (Engineering) · Date: 2026-10-04 (evening) · Status: **SPEC ONLY. No file under `app/`, `static/` or `tests/` was changed.**
Owners: **Engineering** (this file, §3, §6–§8, §10–§13, §15–§16). **Aiko Nakamura** owns content (categories, difficulty wording, classroom picks, Spark Lab links). **Sakura Mori** owns design (cards, detail page, filters UI, empty/loading/error states). Their sections are marked **[AIKO]** / **[SAKURA]** below with the decisions engineering needs from them. **Kenji** owns the licence/credit rules (`reports/attribution-standard.md`, which this spec follows) and the safety sign-off.

**Label key:** **[box]** I ran or measured it here · **[code]** read in the repo · **[est]** estimate · **[unverified]**.

Companion files: `reports/slicer-and-infill-plan.md` (slicer + shared-project settings), `reports/make-tab-plan.md` (Make tab, manifest sketch in §11/§17), `reports/attribution-standard.md` (credit and licence fields).

---

## 0. Summary

- The catalog is the **front door** of ZEIM's sharing side: browse, search and filter **ZEIM Originals first**, then classroom picks, then community uploads, with Trending as a view. Every item shows who made it, under what licence, which printer type it suits, and a real 3D preview.
- **One item model for every source** (aligned with Kenji's §7.1 fields). A validator decides what may appear. An item that fails stays out of listings, search and Trending ("not ready").
- **Keep it small.** 37 Originals exist on disk today (it was 36 a few minutes earlier; the team is still adding) and 45 is the launch number. An in-memory index answers a search over 10,000 synthetic items in about 4 ms [box]; SQLite FTS5 is available (SQLite 3.46.1 with FTS5 [box]) as the upgrade when we need it. No search server.
- **Previews:** cards use pre-rendered PNGs (the Originals already have 520 × 520 images, 20–80 KB each [box]); the interactive viewer loads only on the detail page, from a decimated mesh.
- **Community uploads do not appear in public lists until** they carry creator and licence labels, have a working Report button, and the takedown route (hide first, then review) is live. **Originals go first** and do not wait for any of that (§10).
- 5 Showcase bugs from Zach's iPhone screenshot are ticketed (§15), with my finding on the "Sign up" header (§15.d).
- A **claims-we-can-back table** for launch copy is in §14. "Free forever" and "COPPA/FERPA compliant" are **not engineering claims**.

---

## 1. Goals and non-goals

**Goals**
1. Browse by category, search by text, filter by printer (FDM / Resin / Both), difficulty, material, print time, tags and licence.
2. Show only items that are **ready**: complete labels, watertight mesh (or clearly "view only"), licence valid.
3. 3D previews on every card; fast on a phone.
4. Same record, same rules for Originals, classroom picks, community uploads and (later, low priority) clearly-licensed library items.
5. Free sharing, no payments, no paid or locked files (existing decision).
6. Respect the existing privacy rules: teens Private only, class students' Showcase off unless the teacher allows, counts hidden for minors, no invented counts.

**Non-goals (now):** payments or tips; recommendation ML; a search server; comments/DMs; cross-site embeds; user-defined categories.

---

## 2. Sources and rollout order

| # | Source | What it is | Gate before it appears in public lists |
|---|---|---|---|
| 1 | **ZEIM Originals** (37 STL + PNG in `library/originals/` at 19:50 CT, 45 at launch) | in-house flagship designs, made by the team | validator passes: `provenance`, `printer`, `fit_note`, shared licence line, watertight, Kenji's family-friendly sign-off list. **No upload/moderation machinery needed.** |
| 2 | **Classroom picks** | a teacher pins items (Originals, library or class projects) for their class | only visible to joined students; teacher switch (default off, server-enforced, log = class + time, no names). Items must already be `ready` or class-only |
| 3 | **Community uploads** | projects users publish (today `POST /api/showcase`) | the §10 gate: creator + licence labels, rights confirmation, Report button, takedown route live; teens Private only (unchanged) |
| 4 | **Trending** | not a source: a *sort/view* over public ready items using the existing score | n/a (formula in `catalog.trending_score`) |
| 5 | **Library** (`library/models`, 181 manifest entries) | clearly-licensed web models (NASA, Smithsonian, Wikimedia, GitHub) | **Secondary, low priority** (Zach). Only entries Kenji has cleared; his audit holds 6 back [code: board 19:31] and 47 NASA entries have no licence-file evidence, so they are hidden by default |
| – | EXAMPLE seed items (`catalog._seed()`, 9 emoji cards) | placeholders | **removed from public lists** once Originals ship; shown only in dev. See bugs a, b, c (§15) |

Rollout: CAT-1…CAT-9 ship Originals + classroom picks. CAT-10…CAT-13 open community uploads. Library import is CAT-16, last.

---

## 3. Data model

### 3.1 Item record (one shape for every source)

Field names follow Kenji's `attribution-standard.md` §7.1; catalog-specific fields are marked ★.

| Field | Type | Req. | Rule / example |
|---|---|---|---|
| `id` | string | yes | stable. Originals `orig-<slug>`; uploads the existing 10-hex id; library the manifest id |
| `kind` ★ | enum | yes | `original` · `community` · `library` · `example` (dev only) |
| `title` | string ≤ 80 | yes | through the text filter for uploads |
| `summary` ★ | string ≤ 140 | yes | one line for the card |
| `description` | string ≤ 500 | yes | detail page |
| `creator` | string | yes | `ZEIM` for Originals; display name for community; `a ZEIM maker` for minors (credit rules) |
| `creator_id` ★ | string | uploads | links to the profile only if that profile is public |
| `creator_url` | https url | no | profile link if published |
| `creator_verified` | bool | yes | false for uploader-declared |
| `provenance` | string | yes | one line. Originals: how it was made and "not copied from any character, logo or franchise". Community: "I designed it" / "from my own photo" / "Based on {link} by {creator} ({licence})" |
| `license_id` | enum | yes | `cc0-1.0`, `public-domain`, `unlicense`, `cc-by-4.0`, `cc-by-sa-4.0`, `zeim-original-placeholder`, `private`, `class-only`; anything else blocks listing |
| `license_name`, `license_url`, `share_alike` | derived | yes | from one fixed table, never free text |
| `license_line` ★ | string | yes | the **one** line shown identically on the card, detail page, in the download and in the 3MF/STL metadata. Originals: `[LICENCE LINE: PLACEHOLDER, Zach picks, counsel confirms]` |
| `credit_line`, `credit_full`, `changes[]`, `remix_of[]` | per Kenji §1, §3 | derived/yes | `remix_of` links to ids |
| `printer` | enum | yes | `fdm` · `resin` · `both`. Default for an unreviewed Original: `fdm` (Make plan §16) |
| `fit_note` | string ≤ 160 | Originals yes | "Small parts, needs supports on the left arm" |
| `difficulty` ★ | enum | yes | `starter` · `easy` · `medium` · `advanced`. **Computed suggestion** (§5) + human override **[AIKO]** |
| `materials` ★ | list of enum | yes | `PLA`, `PETG`, `TPU`, `ABS/ASA`, `Resin`; first = recommended |
| `est_time_min`, `est_filament_g` ★ | int | derived | from a K1 "Everyday" slice at ingest (needs slicer plan SLICE-1); shown as "about …, estimate" |
| `bbox_mm` ★ | [x,y,z] | derived | from the mesh |
| `fits` ★ | {`k1`: bool, `ender_class`: bool} | derived | K1 220×220×250; generic 220×220 |
| `category` ★ | enum | yes | §4 |
| `tags` | list ≤ 8, each ≤ 30 | yes | lowercase, filtered |
| `files` ★ | list of {`format`,`name`,`bytes`,`sha256`} | yes | stl (+3mf, obj if made) |
| `preview` ★ | {`thumb`,`thumb_sha`,`mesh`,`mesh_tris`} | yes | §9 |
| `mesh` ★ | {`validated`: bool, `watertight`: bool, `bodies`: int, `min_wall_mm`, `overhang_pct`, `validator`: "x.y", `checked_at`} | yes | produced by the validator, never typed by a human |
| `status` | enum | yes | `ready` · `hold` (licence unclear) · `not_ready` (mesh/fields failing) · `paused` (reported) · `removed` |
| `status_reason` | string | when ≠ ready | staff only |
| `visibility` | enum | uploads | existing `private/followers/public` rules (teens Private only) |
| `moderation` ★ | {`state`: approved/pending/hidden, `report_count`, `last_action`, `reason_code`} | yes | §11 |
| `stats` ★ | {`likes`,`downloads`} | – | existing rules: distinct visitors, hidden for minors, no invented numbers |
| `featured_rank` ★ | int or null | – | Originals editorial order |
| `recipe` ★ | object or null | – | slicer settings, opt-in (slicer plan §4) |
| `created`, `updated`, `retrieved` | datetime | yes | |

**Listing rule (the one rule that matters):** an item appears in **any** public list, search result, facet count, Trending, sitemap or "related" strip **only if** `status == ready` **and** `mesh.validated` **and** `moderation.state != hidden` **and** the viewer is allowed to see it (visibility/class rules). Everything else is invisible, including by direct URL for the public (404; staff and owner see a "not ready / paused" badge). Facet counts are computed after this filter so they can never leak a hidden item.

### 3.2 State machine

```
draft ──validate──► ready ──report (hide-first types)──► paused ──review──► ready | removed
   │                  │                                       ▲
   └─ fails ─► not_ready ◄── re-validate fails (file replaced)┘
hold: licence unclear (Kenji); resolved by evidence → ready, or → removed
```
`removed` deletes files, previews, history copies, search entries and signed links (Kenji §5.4).

### 3.3 Originals manifest: `library/originals/manifest.json`

Does not exist yet. The Originals generator already writes per-slug records with `title, category, description, use, material, validation{…}` [code: `library/originals/source/run.py`]; the manifest wraps and extends them.

```json
{
  "schema": 1,
  "licence_line": "[LICENCE LINE: PLACEHOLDER, Zach picks, counsel confirms]",
  "items": [
    {
      "slug": "dino-phone-stand",
      "title": "Dino Phone Stand",
      "category": "Useful Items",
      "summary": "A friendly dino that holds your phone for video calls.",
      "description": "…",
      "use": "Desk or bedside",
      "creator": "ZEIM",
      "provenance": "Designed by the ZEIM team from scratch (SDF modelling). Not copied from any character, logo or franchise.",
      "printer": "fdm",
      "fit_note": "No supports; print flat on its back. Prints in about 3 h on a K1 (estimate).",
      "materials": ["PLA", "PETG"],
      "difficulty_override": null,
      "tags": ["desk", "dinosaur", "phone", "kids"],
      "files": {"stl": "dino-phone-stand.stl"},
      "preview": {"thumb": "dino-phone-stand.png"},
      "featured_rank": 12,
      "family_review": {"status": "pending", "by": null, "at": null}
    }
  ]
}
```
Hand-written fields are `slug,title,category,summary,description,use,provenance,printer,fit_note,materials,difficulty_override,tags,featured_rank`. Everything else (`sha256`, bytes, `bbox_mm`, `mesh{…}`, `est_time_min`, `fits`, `difficulty`, `license_*`, `credit_*`) is **generated** by the ingest validator and written to `library/originals/index.json` (checked in, regenerated by `make catalog-index`); a hand edit of a generated field fails CI.

### 3.4 Storage

- **Originals and library:** manifest + generated index on disk, loaded into memory at startup (hot-reload on SIGHUP or a `/api/catalog/admin/reload` for staff).
- **Community uploads:** stay in `data/projects.json` + `data/projects/<id>/` (existing `JsonFile` store); the catalog layer maps them into the item shape on read, adding the new fields with defaults (`status` = `not_ready` until validated, `moderation.state` = `pending` until the §10 gate).
- **Moderation and reports:** `data/moderation.json` (existing); gains `report_count` per item and `state` history.
- **Derived index** (in memory, rebuilt on change): a dict of items plus a token map. SQLite is **not** introduced until a measured need (§6).
- Consequences: an upload from before this change has no `license_id`; migration marks it `status: not_ready` (so it is hidden from public lists) and shows its owner "Add a licence to share this" (stays visible to the owner).

---

## 4. Categories **[AIKO + SAKURA fill in; engineering needs the final list]**

Engineering proposal (from what exists, so the filter is not empty on day one). Original categories used by the generator today [box]: **Wildlife Calls (12)**, **Outdoor Mechanisms (7)**, **Useful Items (6)**, **Figures & Desk Art (4)**, **Toys & Articulated (3)**, **Comic Book Art (3)**, **Containers (2)**, **Wall Art (1)**, **Desk Art (1)**. Library categories [box]: space/astronomy 53, school/STEM 47, tools/practical 19, nature 14, toys 12, calibration/test prints 9, games/puzzles 8, art 6, history/tools 6, …

> **[AIKO — decide]** the final list (8–12 top-level categories max, kid-readable names), which categories map to Spark Lab lessons, and a "Classroom picks" display name.
> **[SAKURA — decide]** category icons/colours, how many show before "More", and the empty state when a category has no ready items.
> **Engineering constraints:** category is a single enum per item (tags carry the rest); renaming a category is a one-line change in `categories.json`, not a code change; the API returns display names from that file.

Question for **Kenji/Zach** (not a judgement): "Wildlife Calls" are game and predator calls (duck, turkey, deer, elk, predator). They are legitimate hobby items, but hunting-related items in a family-friendly app deserve a deliberate decision, ideally within Kenji's family-friendly review of the 45.

---

## 5. Filters

All filters combine with AND; multi-select within one filter is OR. Every filter value comes from the item record, so the UI can show counts.

| Filter | Values | Source | Notes |
|---|---|---|---|
| **Printer** | FDM · Resin · Both (default view: *my printer* + Both, see Make plan §16) | `printer` | "Both" items appear under FDM and Resin. A viewer's "My printer" is a device preference sent per request (no account) |
| **Difficulty** | Starter · Easy · Medium · Advanced | `difficulty` | **Computed suggestion**, overridable **[AIKO]**: *starter* = single body, no supports, min wall ≥ 1.2 mm, est ≤ 3 h; *easy* = no supports, est ≤ 6 h; *medium* = supports or ≥ 2 bodies or est ≤ 12 h; *advanced* = print-in-place/articulated, > 12 h, or fit < 0.3 mm. Thresholds are my guesses, to be tuned against real prints |
| **Material** | PLA · PETG · TPU · ABS/ASA · Resin | `materials` | recommended first; school default PLA |
| **Print time** (K1, Everyday preset, **estimate**) | under 1 h · 1–3 h · 3–6 h · 6–12 h · 12 h+ | `est_time_min` | label always says "estimate"; hidden for items without a slice |
| **Size / fit** | fits a K1 · fits 220 mm bed · larger | `fits` | warn, don't block |
| **Tags** | free-form chips, top 20 shown, rest via search | `tags` | lowercased; tag list is per-viewer-visible only |
| **Licence** | CC0 · Public domain · CC BY · CC BY-SA · ZEIM licence | `license_id` | each chip has a one-line plain meaning and a link to the deed |
| **Source** | ZEIM Originals · Classroom picks · Community · Library | `kind` | Classroom picks only for joined students |
| **Hide mature/unsuitable** | n/a | – | not needed: everything in the catalog is family-friendly by rule |

State of the URL: filters live in the query string (`#showcase?printer=fdm&difficulty=easy&q=dino`) so a teacher can share a filtered link.

---

## 6. Search (keep it simple)

- **Approach:** in-memory token index built at startup from visible-eligible items. Lowercase, strip accents, split on non-alphanumerics, prefix match on the last token ("dino" finds "dinosaur"), all terms must match (AND). Fields and weights: title 5, tags 3, category 2, creator 2, summary/description 1.
- **Measured** [box]: synthetic items, 2 query terms: 45 items 0.01 ms, 2,000 items 0.74 ms, 10,000 items 4.15 ms for a linear scan; SQLite FTS5 (prefix + rank) 0.09 ms at 10,000. So we **do not need** FTS for the foreseeable catalog. Upgrade trigger: > 10,000 visible items **or** a need for typo tolerance/stemming beyond prefix. Then add a derived `catalog.db` with an FTS5 table rebuilt from the same records; the API does not change.
- **Typos:** "did you mean" from `difflib.get_close_matches` over tags and titles (cheap, 45–2,000 items).
- **Safety of the query:** length cap 60; goes through the existing language/PII filter only when stored (recent searches go to personalization, which already exists); queries never logged with the session id beyond what personalization stores today.
- **Empty search:** return suggestions (popular categories, "clear filters") not a blank page **[SAKURA]**.

---

## 7. Sorting, Trending, Featured

| Sort | Rule |
|---|---|
| **Featured** (default for Originals) | `featured_rank` ascending, then newest |
| **Newest** | `created` desc |
| **Trending** | existing `trending_score` (likes ×3 + downloads, log-damped, 21-day half-life) over **public, ready** items, ties newest first. Originals take part like any item; with no engagement yet they fall back to `featured_rank`. Example seed items never take part (existing rule) |
| **Quickest print** | `est_time_min` asc (items without a slice go last) |
| **A to Z** | `title` |

Counts hidden for minors/Examples stay hidden (existing `counts_visible`). "For you" (personalization) stays a separate existing tab.

---

## 8. API (all read endpoints are public for `ready` items; owner/staff/teacher endpoints are scoped)

Pagination: `limit` (default 24, max 60) and opaque `cursor`. Today the cursor encodes the offset; clients must treat it as opaque so we can move to keyset pagination or FTS ranking later without an API change. Response always carries `total` (after the listing rule).

```
GET  /api/catalog/items?q=&kind=&category=&printer=&difficulty=&material=&time=&license=&tag=&fits=&sort=&limit=&cursor=
     → {items:[Card], next_cursor, total, facets:{printer:{fdm:n,…}, difficulty:{…}, …}}
GET  /api/catalog/items/{id}         → Detail (card + description, credit_full, files, recipe, related ids, remix chain)
GET  /api/catalog/items/{id}/thumb   → PNG (immutable, long cache; sha in URL)
GET  /api/catalog/items/{id}/preview → decimated mesh for the viewer (binary STL), cacheable
GET  /api/catalog/items/{id}/files/{fmt} → download, credit and licence embedded (attribution-standard §1.4); counts one download per visitor
GET  /api/catalog/categories         → [{id, name, count}]  (names from categories.json)
POST /api/catalog/items/{id}/report  → same as today's /api/showcase/{id}/report, reasons extended (§10)
GET  /api/catalog/picks              → classroom picks for the viewer's class (students) 
PUT  /api/classrooms/{code}/picks    → teacher sets picks (teacher auth, switch on)
POST /api/catalog/items/{id}/like    → alias of existing like (public ready items only)
Staff (X-Admin-Token today; real roles later):
GET  /api/catalog/admin/queue        → reports + not_ready + hold + paused
POST /api/catalog/admin/items/{id}/status  {status, reason}   → hide/restore/remove
POST /api/catalog/admin/reload       → reload manifests, re-run validator
```
`Card` = `{id, kind, title, summary, creator, license_name + url, license_line, printer, difficulty, materials[0], est_time_min?, thumb, fits, tags[:3], likes?, downloads?, owned?, status_badge?}` (no hidden fields; counts follow `counts_visible`).

Existing `/api/showcase*` stays for one release as aliases (the Showcase tab is rebuilt on the catalog API; publish stays `POST /api/showcase`). Class students hit the same `showcase_gate`; the catalog respects "Showcase off for class students" and the second "likes" switch (existing tests `test_cr3`).

**Limits/safety:** per-session rate limit on search and report (reuse `core.ratelimit`); `q` ≤ 60; `limit` ≤ 60; no user text in logs; responses never include `owner_sid`, `status_reason` or reporter ids.

---

## 9. 3D previews

**Card thumbnails: pre-rendered PNG at ingest.** The Originals already ship 520 × 520 PNGs (20–80 KB) [box]. The ingest step (a) renders with one fixed camera/lighting set so cards look consistent, (b) stores `thumb_sha` in the URL so caches never go stale, (c) serves `Cache-Control: immutable`. Community uploads get a thumbnail the same way at publish (today `thumb.png` is copied from the build when present). Missing thumbnail → a neutral placeholder, never an emoji **[SAKURA]**.

**Interactive 3D: only on the detail page.** Reasons:
- A WebGL canvas per card on a phone is the classic way to make a list janky, and iOS Safari limits simultaneous WebGL contexts (exact limit **[unverified]**).
- Originals are up to 98,000 triangles and 4.9 MB each (36 files measured, 83 MB in total [box]); loading 24 of those per page is out of the question.

Plan: at ingest, decimate to ≤ 20,000 triangles with the existing `fast-simplification` into a binary STL (≈ 1 MB, **[est]**), store it as `preview.mesh`, and load it lazily when the detail page opens, using the existing `static/viewer.js` + vendored three.js (no new dependency). The full-resolution file is only for Download. Decimation changes the shape slightly, so the viewer says "Preview" and the validator runs on the **full** mesh, never the preview.

**Wow (optional, later, CAT-15):** a 24-frame turntable WebP sprite per Original, drawn on the card when it enters the viewport and the user taps or hovers: motion without WebGL. [est] 45 items × 24 renders using the same renderer as the PNGs; measure render time first.

**Mobile performance budget [targets, not yet measured]:** detail page interactive in < 2 s on a mid-range phone on Wi-Fi; list of 24 cards ≤ 1.2 MB of images; no layout shift (fixed thumbnail aspect ratio); lazy-loaded images below the fold; viewer never captures page scroll on touch (known issue from IOS list).

**[SAKURA]** card layout, detail layout, loading skeletons, "preview failed" state, and whether the detail view opens as a page (`#showcase/<id>`) or a bottom sheet. Engineering prefers a real URL per item (shareable, back button works, avoids the modal focus problems in §15.e).

---

## 10. Community uploads: what must exist before they appear in public lists

**Rule (from the team lead):** community uploads need **creator + licence labels, a Report button, and a takedown route (hide first, then review)** before appearing in public lists. **Originals can go first** and do not depend on any of this.

Engineering checklist, each one a test (§13), all **server-side** (the form is not the gate):

| # | Requirement | Today [code] | Work |
|---|---|---|---|
| U1 | **Creator label** on every card and detail page (display name, or `a ZEIM maker` for minors; no real names; no links in free text) | creator display name is stored and shown; the link `target=_blank` to `/u/<id>` is a default blue link (bug b) | CAT-11 + bug b fix |
| U2 | **Licence label** (required picker, nothing preselected; CC0 / CC BY 4.0 / CC BY-SA 4.0 / Private / Class only) with the one-line meaning and a deed link | **missing**: no licence field on uploads | CAT-10: add `license_id` to publish; unset = cannot publish, stays Private (Kenji §6) |
| U3 | **Rights confirmation** checkbox with the exact text, stored with timestamp + text version | `accept_guidelines` checkbox exists (guidelines only) | extend in CAT-10 |
| U4 | **Provenance** one-liner | missing | CAT-10 |
| U5 | **Report button** on every card and detail page, a real dialog (radio reasons, optional details), 44 px targets | exists, but uses two `prompt()` boxes (poor on iPhone, accepts any typed reason text) | CAT-11: replace with a dialog; same endpoint |
| U6 | **Hide-first takedown.** Reports of type *minor_safety, copyright / not mine, wrong licence, personal_info* **hide the item from public lists and downloads immediately** (owner still sees it with a "paused for review" badge). Other reasons (*not_family_friendly, harassment, other*) hide automatically at **3 distinct reporters** (threshold to be agreed with Kenji), and always enter the queue | only `minor_safety` auto-hides today; `copyright` does not | CAT-12: extend `moderation.report`, keep the minor-safety behaviour (do not regress) |
| U7 | **Review queue** with hide / restore / dismiss and a reason; audit line per decision (report id, date, item, outcome, who; **no student names**) | admin-token API and stub exist; no UI | CAT-12: minimal staff page (not public), later real roles |
| U8 | **Takedown purge:** hide + delete files + previews + cached thumbnails + search entries + history copies + signed links; remixes of a removed parent are hidden until reviewed | partial (CR-2 purges for student deletion) | CAT-12 with a test per surface (Kenji D3) |
| U9 | **Contact route** (role mailbox + `/report-credit` form) and the 2-business-day acknowledge / 10-business-day decision targets | not built; contact address is a Zach decision | CAT-12; build fails if still `PLACEHOLDER` when `PHOTO3D_PUBLIC_LAUNCH=1` (Kenji D4) |
| U10 | Text filters on title, description, tags | exist (`safety.gate` on all three, `text_in` caps) [code] | keep; add tests that the catalog index never contains unfiltered text |
| U11 | Mesh check at publish: watertight, size caps, no zero-volume | exists for builds; publish copies build files | CAT-9 validator runs on publish too; failure → `not_ready` (owner sees why) |
| U12 | Teens: Private only at launch; class students: Showcase off unless the teacher allows | enforced and tested | keep; catalog must not widen it (test) |

Counsel items (**needs counsel**, from Kenji §5.3): DMCA designated agent, counter-notice, repeat-infringer policy, Terms of Service upload grant. Engineering builds the hooks, not the legal text.

---

## 11. Moderation hooks for uploads

1. **At publish** (pre-listing): language/PII filter on title, description, tags (exists); mesh validator; licence + rights + provenance fields complete; image safety on the thumbnail is **not built** (Kenji's call whether needed before launch; flagged, not claimed).
2. **Report**: described in U5/U6.
3. **Queue**: staff list ordered by severity (minor_safety first), then age.
4. **Teacher/class**: class projects are visible to the teacher and joined students only (never public), and the teacher can hide a student's item in their class (`classrooms.hide_feedback` pattern exists for feedback; extending it to projects is CAT-13).
5. **Metrics, no content:** counts of reports/hides/restores per week for Kenji's review.
6. **Fail-safe:** if the validator or the staff queue is down, new community uploads stay `pending` (not listed). Originals are unaffected.

---

## 12. Licence labels (display rules; wording is Kenji's)

- Every card shows **creator** and **licence short text** (`CC BY 4.0`, `CC0`, `ZEIM Original`) as a chip that links to the canonical deed; no card without both (Kenji A1).
- Detail page shows the full credit line, `license_line`, source link, changes made, remix chain.
- The same `license_line` goes into the **download**: 3MF `<metadata name="Title|Designer|Copyright|LicenseTerms|Description">` (these are the 3MF core spec's well-known names [src: 3MF Core Specification v1.3.0, https://3mf.io/spec/core-v1-3-0/ , table 3-1]), the binary STL 80-byte header (a short credit, not starting with `solid`), OBJ `#` comment lines, and a `README-credit.txt` in a "download with credit" zip.
- A diff test asserts the line is identical on card, detail page, download and metadata (Kenji E3). STL header caveat: some tools ignore it; the 3MF is the reliable carrier.
- Privacy: no personal names or file names of uploads in metadata; generic object names (existing rule).

---

## 13. Tests

| Layer | Tests |
|---|---|
| Validator (unit) | each required field missing → named error; unknown `license_id` blocks; `license_url` equals table; watertight false → `not_ready`; `printer` invalid → fail; manifest hand-edit of a generated field fails; the two known bad Originals stay out until fixed (today: `whale-tail-wall-hook.stl` is not watertight after welding [box]) |
| Listing rule | table-driven: every combination of status/moderation/visibility/viewer role vs "appears in list / search / facets / trending / direct URL"; hidden item never leaks via facet counts or `related` |
| Search/filter | AND/OR semantics, prefix, accents, empty result, cursor pagination (no duplicate/missing items across pages), limit caps, sort stability |
| Privacy | teen item never public; class student gets no Showcase until the switch; counts hidden for minors/Examples; no `owner_sid`/`status_reason` in any response |
| Moderation | hide-first for minor_safety, copyright, wrong licence, personal_info; 3-reporter threshold; owner sees "paused"; purge removes file/preview/thumbnail/search/history/signed link; remixes of removed parent hidden |
| Downloads | licence line identical across card, detail, 3MF `LicenseTerms`, STL header, OBJ comment, README-credit; escaping for `"<>&'`, kana, emoji, newline injection (Kenji A9) |
| Previews | every `ready` item has a thumbnail whose sha matches; preview mesh ≤ 20 k tris; page weight budget for 24 cards |
| UI (Chrome + WebKit, 390 px) | filters usable at 44 px, 16 px inputs, no horizontal scroll, URL state round-trips, detail opens by URL, focus moves into/out of the detail view, Escape/back closes it, console clean |
| Regression for §15 bugs | one test per bug a–e |
| **Not testable here (needs a real iPhone / Zach):** real Safari scroll/focus behaviour, thumbnail/preview feel on a real phone connection, VoiceOver labels, whether a K1 prints an Original. |

---

## 14. Claims we can back with a test (for Kenji's and Daichi's launch-copy check)

Status key: **verified** = an automated test or a recorded manual check exists and passed (named); **partly**; **untested**. "Evidence" names the test or report. Re-check before launch: statuses are as of 2026-10-04 evening.

| Claim (candidate wording) | Evidence / test | Status |
|---|---|---|
| **"Print-ready FDM models"** (mesh quality) | Output meshes pass the watertight/manifold checks (`tests/test_b2_mesh.py`: hollow, simplify, cut, text, aspect-ratio refusals; pop-art OBJ/3MF 0 of 22 failing in Ren's QA). Originals: validator (CAT-3) not built; **37 STLs on disk at 19:50 CT, 1 not watertight (`whale-tail-wall-hook`) [box]** | **partly**: mesh checks verified for builds; Originals will be "verified" per item once CAT-3 passes. **Nothing from ZEIM has been printed on a real printer yet (untested)** |
| **"Slices for FDM printers in ZEIM"** | PrusaSlicer 2.9.2 slices every build; Originals sliced here (Benchy 5 s, dragon, dino stand) [box]; `tests/test_b2_k1.py` | **verified** (engine runs) · **untested** on a real printer |
| **"Resin-ready"** | Make plan §16: resin validation (wall ≥ 0.8 mm, ≥ 2 drain holes, orientation hints) = MAKE-16, **not built**; no resin printer or slicer test; PrusaSlicer SLA output is not Chitubox format | **untested / not built.** Allowed wording today: "Export clean STL files for resin slicers" (the STL export itself is tested; opening in Chitubox/Lychee is **untested**). "Resin-ready" claim waits for MAKE-16 + one real resin print or Zach's explicit OK |
| **"Creality-ready"** (three separate sub-claims) | (1) *Opens in Creality Cloud/Print:* Zach opened a ZEIM-downloaded 3MF in the Creality Cloud app on his iPhone (Yami's message, one device, one file); Print-dialog Creality block exists with Chrome + WebKit UI tests at 390 px (commit `59b205d`). (2) *K1 profile:* `app/profiles/creality_k1.ini` + `tests/test_b2_k1.py` (bed 220, Klipper flavour, `START_PRINT`/`END_PRINT`), marked **Experimental**. (3) *Prints on a K1:* nobody has run ZEIM G-code on a K1 | (1) **verified once, manually** (1 phone) · (2) **verified in software, Experimental** · (3) **untested**. Allowed: "Opens in the Creality Cloud app" and "Experimental Creality K1 profile". Not allowed yet: "prints perfectly on your K1" |
| **"Safe for classrooms": teens are Private by default** | `tests/test_b1_teen_posture.py` (teens cannot set followers/public anywhere; adults cannot follow teens; migrated old data; reopen/reclose); Kenji re-verified S-03 PASS | **verified** (automated, server-side) |
| **"Send/share off by default in classes"** | `tests/test_b1_send_policy.py` (class student: Download + teacher only; switch default off, persists, teacher-only; forged requests refused; log has class + time, no names); Kenji's regression PASS | **verified** (automated) |
| **"Students' Showcase is off until the teacher turns it on"** | `tests/test_b2_cr.py::test_cr3…` (Showcase off; likes are a second switch) | **verified** (automated) |
| **"Student data can be deleted"** | `test_cr2…` (removing a student or class deletes builds + photos; student can delete own data) | **verified** (automated) |
| **"Your photo's location data is removed"** (EXIF/GPS stripped on upload and in exports) | `tests/test_b1_upload.py` (EXIF/GPS stripped; photo not kept until build); Kenji regression PASS | **verified** (automated); real-iPhone HEIC and camera path were exercised by Zach's tests, no systematic check |
| **"Family-friendly chat/text filter"** | `tests/test_b1_filter.py`, Kenji's red-team files | **partly**: known gaps open (zero-width characters, spelled-out email/phone, @handles, addresses) until the follow-up lands. Say "has a language and personal-info filter", not "blocks everything" |
| **"No account needed for under-13s in class"** | signup refuses under 13 with a neutral message; class join without account | **partly**: Kenji's S-04: a cookie-less client can retry (age lock is per session/IP) |
| **"45 in-house flagship designs"** | count of manifest entries with `status: ready` | **untested until CAT-3**: 37 STL on disk at 19:50 CT. Use the number only when the validator reports 45 ready |
| **"Every model shows its creator and licence"** | CAT validator + test A1/A4 | **untested until CAT-3/CAT-10** |
| **"Report any model; we hide first and review"** | U6/U7 tests | **untested until CAT-12** (today only minor_safety hides) |

**Not engineering claims** (do not put these in the "verified" column; they need business or legal owners):
- **"Free forever."** That is a business and operations commitment (hosting cost, funding, policy). Engineering can say "there is no payment code, paid tier, or locked file in the product" (I grepped `app/` for stripe/paywall/checkout/subscription: only docstrings saying there is none [box]; CAT-17 adds a test), not that it will stay free.
- **"COPPA / FERPA compliant."** Compliance is a **legal determination** about a service's practices, contracts and notices; software cannot be "compliant" by itself. Engineering can state specific, tested controls (no under-13 accounts, minimal data, deletion, per-class switches, no student names in logs) and call it **"built with COPPA/FERPA readiness controls, pending legal review"**. Counsel and Kenji own the words.
- **"The best place for…"** is an aim, not a measurable claim; keep it as a mission statement ("we aim to be…"), not a comparison.
- Anything about named competitors: describe our features; no claims about others.

---

## 15. Showcase bugs from Zach's iPhone screenshot (tickets)

(Code read in `app/community/catalog.py`, `app/api/community.py`, `static/community.js`, `static/index.html`; **nothing was reproduced on a device**, and the live tree was not touched.)

**(a) EXAMPLE items offer a download named `example_model.stl` that is not a real model.** [code] Seed items declare `files: [{"name": "example_model.stl", "size_kb": 1}]`; the download route serves a generated 20 × 20 × 5 mm box and names the file `example_placeholder.stl` (so the name on the button and the saved name differ), and it **counts the download**. Fix (CAT-5): examples get **no files** ("No model yet" label, no Download button) or, better, an example card is replaced by a real Original; the route returns 404 for example items; no download is counted. Test: example detail has no download link and the route 404s.

**(b) The creator name `Example: Cleo` renders as the default blue underlined link, low contrast on the dark theme.** [code] In `openItem`: `by <a href="/u/…" target="_blank">…`. There is no global `a` colour in `style.css` (only `.sharepage a`, `.slicers a`), so the browser default applies. Also `target=_blank` opens a new tab out of the modal, with no `rel="noopener"`. Fix (CAT-6): a `.creator` link style using theme tokens (AA contrast ≥ 4.5:1 on the panel colour), same-tab navigation to the profile when it is public, plain text when it is not (private/teen profiles never link), `rel="noopener"` if a new tab stays. **[SAKURA]** to pick the colour. Test: computed contrast ≥ 4.5 in the CSS test, no `a` without a theme colour inside dialogs.

**(c) Footer text "Follow is scaffolding — a feed of followed creators isn't built yet."** [code] Hard-coded in `openItem` (`static/community.js`): "Likes and downloads are counted once per visitor and only for public projects. Follow is scaffolding — a feed of followed creators isn't built yet." That is internal wording. Fix (CAT-7): hide the follow button until a feed exists, or label it `Follow · Coming soon` with a disabled state; the counting note becomes "Each person's like and download counts once." Test: no occurrence of "scaffolding", "not built", "stub", "TODO" in served HTML/JS strings (a grep test over `static/` and user-visible API strings).

**(d) Header shows "Sign up" for Zach, earlier it showed his name. Likely cause (code-read, not confirmed against logs):**
- The header text comes from `/api/me`: `ME.signed_up ? "👤 " + ME.display_name : "👤 Sign up"` (`static/community.js`). `signed_up` is true only if `USERS.read().get(sid)` exists (`identity.get_actor`), and `sid` is the value of the `p3d_sid` cookie. **The account is the cookie plus a record in `data/users.json`. There is no login, password or recovery.**
- Ren's phone-test script starts each run with **fresh data folders**: `RUN="$RUN_ROOT/$TS"` and `PHOTO3D_DATA="$RUN/data"` (`reports/deploy/iphone-test/start.sh`). After the restart, `users.json` is empty, so even if the phone still sends its old cookie (valid for a year; the middleware only mints a new sid when the cookie is missing or shorter than 16 characters), the server finds no user for it and shows "Sign up".
- **A second, compounding cause:** the restart gives a **new tunnel address**; cookies belong to the host name, so the phone arrives as a brand-new visitor with no cookie at all. Either alone reproduces what Zach saw. I cannot tell which happened from here: the cheap discriminator is whether the new link's host name differs from the old one (if it does, that alone explains it).
- Less likely: a class join in "shared computer" mode sets a **session-only** cookie (`identity.session_only_cookie`) which iOS drops when Safari is closed; Safari private browsing or "block all cookies" would do the same. Only applies if Zach did one of those.
- Effect: not a bug in the header, but a **product gap**: an account that dies with the cookie or the data folder. For a free pilot with kids and teachers, "I lost my account" will be a support burden.
- Fix options (CAT-14, needs a Zach decision): (1) **for tests**, keep one data folder across restarts (`users.json` and the rest) and keep the tunnel host stable, or tell testers to expect a reset; (2) **in the UI**, show "Welcome back? Your saved projects are on this device's earlier session" only when we can tell (we cannot without a login), so instead show a small honest note after a reset: *"Looks like this is a fresh start. Create your account again."*; (3) **real fix** (roadmap): sign-in (email/passcode or teacher-issued) with a recovery path, which also needs Kenji's age and privacy review and a mail provider (cost = Zach decision). Test (CAT-14): restart with the same data folder keeps the name; restart with a fresh folder shows "Sign up" (documents the behaviour) and does not error.

**(e) Modal focus/close behaviour on iOS.** [code] Item, account, publish and other dialogs use `<dialog>.showModal()`; the only close control is the `✕` button (`data-close`); there is no backdrop-tap close and no focus return to the opener. `openItem` rebuilds the dialog body and calls `showModal()` again after Like/Follow (the dialog is already open), so focus jumps to the first control and a screen reader re-reads from the top. The Report action uses two native `prompt()` calls that appear above the dialog. `dialog{max-height:calc(100dvh - 24px);overflow:auto}` exists for phones, but long content can scroll the page behind it (known iOS dialog behaviour; **[unverified]** on the current code). `✕` size has not been measured against 44 px. Fix (CAT-8): item detail becomes a **real route** (`#showcase/<id>`), not a modal, which makes Back close it and removes most of the focus problems; keep modals for short confirmations only, with `autofocus` on the first field, focus return to the opener on close, `Escape`/backdrop close, `inert` page behind, a 44 × 44 close button, `aria-labelledby`, and body scroll lock; replace `prompt()` with the dialog from U5. Tests: WebKit and Chrome at 390 px (focus lands inside, returns to opener, Back closes, no console errors); **real iOS Safari verification is for Zach's phone**.

---

## 16. Tickets (CAT-n), in order

Sizes: S ≤ 1 day, M 1–3, L 3–5. Order assumes: phone-test merge → Make tab → Originals Showcase (this list) → slicer work. **Owner letters:** E engineering, A Aiko, S Sakura, K Kenji, Z Zach.

| ID | Ticket | Size | Needs |
|---|---|---|---|
| CAT-1 | Item model + `categories.json` + listing rule + status/moderation fields; migrate uploads to `not_ready` until licensed | M | **A** categories, **K** field list OK |
| CAT-2 | `library/originals/manifest.json` + hand-written field set (Yami's team fills; Engineering writes the schema + sample) | S | Originals team |
| CAT-3 | **Originals validator + ingest index** (`make catalog-index`): hashes, bbox, mesh checks, difficulty suggestion, K1 estimate (needs slicer SLICE-1), thumbnail check, shared licence line, CI fails on bad manifests; "not ready" list | M | CAT-2 |
| CAT-4 | Catalog API: list/detail/facets/categories, filters, search (in-memory), sort, cursor, caps, rate limits; `/api/showcase*` aliases | L | CAT-1, CAT-3 |
| CAT-5 | **Bug (a):** EXAMPLE items: no fake download, no counted download, replaced by Originals; dev-only examples | S | CAT-4 |
| CAT-6 | **Bug (b):** creator link style/contrast/same-tab/noopener; private profiles unlinked | S | **S** colour |
| CAT-7 | **Bug (c):** replace "scaffolding" text; follow = Coming soon or hidden; string-grep test | S | **A** wording |
| CAT-8 | **Bug (e):** detail as real route + modal focus/close fixes + Report dialog replacing `prompt()` (U5) | M | **S** layout |
| CAT-9 | Catalog UI (Showcase tab rebuilt): filters, search, cards with PNG thumbs, empty/loading/error states, URL state, phone 44/16 px | L | **S** design, **A** copy |
| CAT-10 | Publish gate: licence picker, rights confirmation, provenance, server enforcement, Private default (U2–U4, U11) | M | **K** exact text |
| CAT-11 | Creator + licence chips, credit lines, embedded licence in 3MF/STL/OBJ/README-credit, diff test | M | **K** attribution-standard |
| CAT-12 | **Takedown route:** extended hide-first report types, 3-reporter rule, staff queue page, purge on removal, audit line, contact + `/report-credit` | L | **K**, **Z** contact + policy, counsel |
| CAT-13 | Classroom picks (teacher sets, switch default off, log class + time, no names), class-scoped visibility | M | **A** wording, **K** |
| CAT-14 | **Bug (d):** account-loss behaviour: tests documenting same-folder vs fresh-folder restart, honest "fresh start" note, decision on test-run data persistence | S | **Z** decision (data persistence for pilots) |
| CAT-15 | Interactive detail viewer from decimated preview mesh; optional turntable sprites; mobile perf pass | M | CAT-3 |
| CAT-16 | Library import (low priority): only Kenji-cleared entries, same validator, hidden otherwise | M | **K** clearance |
| CAT-17 | "Claims" regression tests: strings that must/must not appear in launch copy (`scaffolding`, `compliant`, unverified claims) + sources for §14 | S | **K**, Daichi |

Phase view: CAT-1…9 + 14 = Originals browse (≈ 15–18 working days **[est]**); CAT-10…13 = community uploads opened (≈ 8–10 days **[est]**); CAT-15…17 after.

---

## 17. Open questions

**Zach**
1. The **licence line** for Originals (with counsel). Candidates are Kenji's: CC BY for reuse, or a "personal and classroom use only" custom text.
2. **Takedown contact** (a role mailbox, not a person) and the 2/10-business-day targets.
3. Keep **one data folder across phone-test restarts** (so accounts survive), or accept a reset each time? Longer term: sign-in/recovery (needs a mail provider = cost).
4. "Wildlife Calls" category in a family-friendly app (§4): keep, rename, or hold back from class views?

**Kenji**
1. Field list (§3.1) and statuses match your §7.1; any change?
2. Hide-first report types (§10 U6) and the 3-reporter threshold for the rest.
3. Is a thumbnail image-safety check required before community uploads open, or is moderation-after-report plus Private-by-default enough for the pilot?
4. Family-friendly review list for the 45 (you sign off); `family_review` field is in the manifest for it.

**Aiko**
1. Final categories (§4), difficulty wording and thresholds (§5), classroom-picks name and teacher wording, and which Originals pair with which Spark Lab lessons (so `tags`/`lesson` links can be added).

**Sakura**
1. Card, detail, filters, loading/empty/error states; detail as a route vs a sheet; creator-link colour; whether the turntable sprite (CAT-15) is worth it.

**Engineering (me), to verify during build**
1. Real iPhone behaviour for scroll, focus and the viewer; nothing in §15.e is confirmed on a device.
2. Preview mesh size/quality after decimation for the worst Originals (98 k triangles).
3. Slicer-derived `est_time_min` only after SLICE-1; until then the time filter is hidden.
