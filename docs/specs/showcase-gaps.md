# Showcase gaps: what adult makers expect, and the 5 cheapest additions

Research date: October 17, 2026. Sources checked October 17, 2026; citations carry the
source's own date where one is published. This is a spec, not legal advice.

## What the big model sites offer (and adults expect)

- **Printables** — collections (private or shared curated lists), remix tracking ("the platform
  links the original and the remix"), per-model Makes & Comments tabs, print-settings tab,
  rich filters (printer brand, material, print time), per-model licenses including Store models
  with three commercial options, and a creator analytics dashboard covering Likes, Downloads,
  Views, Makes, Remixes, Collections ([stacksheriff review, 2026-10-16](https://stacksheriff.com/3d-printing/printables/),
  [Prusa blog, 2026-10-15](https://blog.prusa3d.com/revealing-the-new-detailed-analytics-for-your-models-on-printables-com_71849/),
  [antonmansson.com, 2025-02-22](https://www.antonmansson.com/3d-printing-blog/why-you-should-upload-3d-models-to-printables)).
- **Thingiverse** — makes ("user-uploaded photo or description showcasing their successful
  creation"), remixes ("more than half of Things are derived from prior Things" in the research
  literature), collections, comments, license options (CC variants), filters by license and
  makes ([Thingiverse about, 2026-09-17](https://www.thingiverse.com/about),
  [arXiv case study, 2026-05-05](https://arxiv.org/html/2406.12801v1),
  [3d-printed.org guide, 2026-07-20](https://www.3d-printed.org/what-is-thingiverse-and-how-can-it-be-used/)).
- **Cults3D** — per-design license picker (CC BY / BY-SA / BY-NC / BY-NC-SA / BY-NC-ND, CC0,
  and platform commercial licenses), defaulting to Private Use when unset; the license governs
  remix and commercial sale of prints ([Cults licenses page, 2025-11-03](https://cults3d.com/en/licenses),
  [resinandrolls review, 2026-10-09](https://resinandrolls.com/articles/cults3d-miniatures-review/)).
- Guides tell buyers to check the license before selling prints, and to check Makes for honest
  printability evidence ([3dprinting.com, 2026-06-13](https://3dprinting.com/3d-models/best-free-3d-printable-models/),
  [3d-printed.org Thingiverse search guide, 2026-10-17](https://www.3d-printed.org/thingiverse-search/)).

**User complaints that shape what adults want** (anecdotes, not prevalence): Thingiverse is
repeatedly slammed for "terrible search", the "download all" removal, and a slow, buggy site
([r/3Dprinting, 2026-01-09](https://www.reddit.com/r/3Dprinting/comments/1q2nwng/what_happened_to_thingiverse/),
[r/3Dprinting, 2025-11-03](https://www.reddit.com/r/3Dprinting/comments/tz2ivg/have_people_abandoned_thingiverse/));
Printables is praised in comparison for working search and a better viewer
([r/3Dprinting, 2025-12-05](https://www.reddit.com/r/3Dprinting/comments/zm5uy1/printables_or_thingiverse/));
and on smaller platforms users report that "few makes are uploaded, feedback is almost
non-existent" while praising Printables' remix view ("view child remixes alongside the
original") ([r/3Dprinting, 2025-11-03](https://www.reddit.com/r/3Dprinting/comments/1cvt43g/ive_been_out_of_the_hobby_for_a_couple_years/),
[r/elegoo, 2026-10-17](https://www.reddit.com/r/elegoo/comments/1x4tzhi/help_us_make_nexprint_better/)).
Search that works, honest makes, and remix lineage are the expectations ZEIM must meet.

## What ZEIM already has (verified in code)

Search (`q`), tabs (trending/free/following/foryou), categories, tags (max 8, word-filtered),
likes, follows, private favorites, **remix links with attribution validation and a remix chain**
(`catalog.create_project(remix_of=...)`, `remix_chain()`), **print-photo records rendered on
the listing page** (`loadPrints()` in `static/community.js` → `GET /api/showcase/{iid}/prints`,
`prints_count` on listings), visibility (private/followers/public), reports + moderation, and
For You personalization (`app/api/community.py`, `app/community/`).

So of the classic gaps, the real holes are: **license picker, collections, comments, sort
options, and related items** (print photos are already rendered on the listing page).

## The 5 cheapest additions (JSON stores)

### 1. License picker on publish

- **Smallest addition:** reuse the existing `license_id` convention on LISTINGS records with a
  fixed menu (CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA, CC BY-NC-ND, CC0, Private use),
  defaulting to Private use for NEW listings (Cults' convention: print for yourself or gift,
  but not sell — [Cults licenses, 2025-11-03](https://cults3d.com/en/licenses)). Shown on the
  listing page; ND licenses hide the "remix this" affordance AND are enforced server-side
  (reject `POST /showcase` with `remix_of` pointing at an ND project); NC licenses show
  "non-commercial" clearly.
- **Store + API:** `license_id` on LISTINGS items + `license_id` param on `POST /showcase`
  (validated against the menu) + `catalog.public()` passthrough. Existing listings keep
  whatever they already carry; unset legacy licenses stay unspecified (no default is
  retroactively applied) until the author edits the project.
- **Effort:** ~half a day (menu + validation + display + tests).
- **Acceptance:** publishing without a license defaults to Private use (new listings only);
  the license is visible on the public listing; an invalid value is a 400; remixing an
  ND-licensed project is rejected server-side.

### 2. Collections (public or private curated lists)

- **Smallest addition:** a `COLLECTIONS` JsonFile (`{"collections.json": []}` rows:
  `{id, sid, title, visibility, items: [iid]}`) + endpoints to create/rename, add/remove an
  item, and view one; a "Collections" strip on profile pages.
- **Store + API:** new `COLLECTIONS` store; `POST /collections`, `POST /collections/{id}/items`,
  `DELETE /collections/{id}/items/{iid}`, `GET /collections/{id}`; reuse the visibility +
  moderation guards used by showcase.
- **Effort:** ~1-2 days.
- **Acceptance:** a user can curate 5 projects into a list, share it publicly, and another
  adult can view it; hidden/removed projects drop out of the list automatically.

### 3. Comments on listings

- **Smallest addition:** a `COMMENTS` JsonFile (`{iid: [{s: sha(sid), t, text, created}]}`) +
  `POST /showcase/{iid}/comment` (text through the existing `safety.gate` word filter) and a
  comments block in `catalog.public()`. Reported comments reuse the existing moderation queue.
- **Effort:** ~1 day (filter + moderation wiring is the bulk).
- **Acceptance:** an adult can comment; slur-laden text is blocked by the existing filter;
  a moderator can hide a comment; comments are absent for suspended users.

### 4. Sort options on the showcase

- **Smallest addition:** a `sort` query param on `GET /showcase` (`newest | likes | printed`),
  default per tab as today; `catalog.list_items()` gains a sort argument. No new stores —
  likes and prints counts already exist.
- **Effort:** ~2 hours.
- **Acceptance:** `?sort=printed` orders by prints_count descending with ties broken by
  recency; invalid sort values 400; default behavior unchanged.

### 5. Related items on the listing page

- **Smallest addition:** a "More by this maker" + "More like this" (same primary tag) strip on
  the listing detail page. The print-photo gallery is NOT a gap — it already renders there
  (`loadPrints()` in `static/community.js` fetches `/api/showcase/{iid}/prints` and builds the
  gallery with mature-content handling); what's missing is discovery between listings.
- **Store + API:** no new stores — `catalog.list_items()` filtered by owner uid / tag,
  excluding hidden items and the current item, capped at 6, added to the item payload.
- **Effort:** ~half a day.
- **Acceptance:** a listing shows up to 6 same-tag or same-maker projects; hidden or reported
  projects never appear; an empty result renders nothing (no empty section).

## Deliberately not in the top 5

Creator analytics dashboards, paid licenses/store, and printer-brand filters are valuable but
expensive or out of scope for a free, no-payments site; makes/remixes themselves already exist.
