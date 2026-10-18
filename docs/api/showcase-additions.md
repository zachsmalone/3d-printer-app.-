# Showcase additions — API reference

New endpoints and parameters for the licence picker, sort options, and related
items (docs/specs/showcase-gaps.md items 1, 4, 5). Collections and comments are
deliberately **not built** — deferred until moderation hooks exist (see
"Not built" at the end). All payloads below were verified against the live API.

All routes are under the existing `/api` prefix and require the session cookie
unless noted. Errors are the app's existing convention: HTTP status +
`{"detail": "<user-facing message>"}` — there are no separate machine error
codes.

## Licence picker

### `GET /api/showcase/licenses`

No auth required (used to render the picker before signup). Returns the full
licence menu plus the default:

```json
{
  "licenses": [
    {"id": "cc0-1.0", "name": "CC0 1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/",
     "derivatives": true, "commercial": true, "default": false,
     "blurb": "Public-domain dedication: anyone may share, remix and sell it, no credit needed."},
    {"id": "cc-by-4.0", "name": "CC BY 4.0", "url": "...", "derivatives": true, "commercial": true,
     "default": false, "blurb": "..."},
    {"id": "cc-by-sa-4.0", "name": "CC BY-SA 4.0", "url": "...", "derivatives": true, "commercial": true, "default": false, "blurb": "..."},
    {"id": "cc-by-nd-4.0", "name": "CC BY-ND 4.0", "url": "...", "derivatives": false, "commercial": true, "default": false, "blurb": "..."},
    {"id": "cc-by-nc-4.0", "name": "CC BY-NC 4.0", "url": "...", "derivatives": true, "commercial": false, "default": false, "blurb": "..."},
    {"id": "cc-by-nc-sa-4.0", "name": "CC BY-NC-SA 4.0", "url": "...", "derivatives": true, "commercial": false, "default": false, "blurb": "..."},
    {"id": "cc-by-nc-nd-4.0", "name": "CC BY-NC-ND 4.0", "url": "...", "derivatives": false, "commercial": false, "default": false, "blurb": "..."},
    {"id": "private-use", "name": "Private use", "url": "", "derivatives": false, "commercial": false,
     "default": true, "blurb": "Keep it personal: print it, gift it, keep it to yourself and this site."}
  ],
  "default": "private-use"
}
```

- `blurb` is the one-line description to show in the picker; `url` links the
  licence deed (empty for private-use).
- The list is generated from `app/community/licensing.py`, so the menu and the
  validator cannot drift apart.

### `POST /api/showcase`

The existing publish endpoint now accepts an optional `license_id` field:

```json
{"build_id": "...", "title": "...", "description": "...", "tags": ["lamp"],
 "accept_guidelines": true, "nsfw": false, "visibility": "public",
 "remix_of": null, "license_id": "cc-by-4.0"}
```

Rules, enforced server-side in `catalog.create_project` (not just the UI):

- Omitted or empty → `private-use`. **New listings never grant rights
  silently.** A user who publishes without choosing gets the most restrictive
  option. Verified: the stored record and the public payload both show
  `license_id: "private-use"`.
- Unknown `license_id` → `400` with
  `{"detail": "unknown licence: pick one from the licence list"}` (per the spec's
  acceptance criterion that an invalid value is a 400).
- Every id in the menu above is accepted; nothing else is.
- `license_id` is stored on the project record and returned in the public
  payload of showcase items (`""` for legacy listings published before the
  picker existed).

### Remix enforcement (server-side, at the remix boundary)

`POST /api/showcase` with `remix_of: <item_id>` is refused with `422` and
`{"detail": "That project's licence doesn't allow publishing remixes of it. Pick a project marked as remixable, or ask its maker to change the licence."}`
when the source project's licence does not permit derivatives:

- `cc-by-nd-4.0`, `cc-by-nc-nd-4.0` — no-derivatives: **refused**.
- `private-use` — **refused**.
- **No licence recorded (legacy listings)** — **refused** (verified). Absence of
  a licence is treated as all-rights-reserved; a remix never succeeds just
  because the source predates the picker.
- All `-by-`, `-by-sa-`, `-by-nc-`, `-by-nc-sa-` ids — allowed.

The check happens in `catalog.create_project` before anything is written, so
every path that creates a project (API today, any future importer) gets the
same rule. The source must also be visible to the remixer (pre-existing rule).

**Scope note:** enforcement is only this gate. It does not verify that the
remixer is the rights holder, that attribution is actually included, that a
share-alike remix carries the same licence, or that a non-commercial licence is
respected — those are community/reporting matters, not code checks.

### Limits

- 8 licences total (the CC 4.0 suite plus private-use). No custom or free-text
  licence uploads in this version.
- A project's licence cannot be changed after publish in this version —
  re-publishing with a new licence is the current path.

## Sort options

### `GET /api/showcase?sort=<sort>`

Existing endpoint, new optional `sort` query parameter. Default `""` (the
tab's own order — unchanged legacy behavior). Accepted values:

| Sort | Meaning |
|---|---|
| `""` (omitted) | The tab's own order (Trending keeps its decay ranking, etc.) |
| `newest` | Most recently published first |
| `likes` | Most likes first; ties broken by newest |
| `printed` | Most approved prints first; ties broken by newest |

- Invalid `sort` → `400` with
  `{"detail": "sort must be one of newest | likes | printed (or omitted)"}`.
- Sorting applies to the tab's **existing result set** and does not widen the
  query (same visibility and maturity filters). The result set itself is
  **unbounded** — this endpoint returns every visible item for the tab with no
  page or limit parameter, so an explicit sort is an in-memory sort of the
  whole filtered list, and response size scales with the catalogue.
- `printed` counts only prints with `status == "approved"` from the engagement
  store (`social.prints_for`), so pending prints never inflate ranking.

## Related items

### `GET /api/showcase/{iid}`

Existing endpoint. The item payload now includes a `related` array (compact
summaries, not full project payloads):

```json
{
  "ok": true,
  "id": "...", "title": "...", "license_id": "cc-by-4.0", "...": "...",
  "related": [
    {"id": "x1", "title": "Lamp base", "creator_id": "u2", "why": "maker",
     "license_id": "cc-by-4.0", "photo": "/api/showcase/x1/thumb",
     "url": "/api/showcase/x1"}
  ]
}
```

Selection rules:

- Pool: `catalog.list_items(actor, "free")` — the same visibility and
  maturity filter the showcase uses — **minus items with an open report**:
  per the spec, hidden or reported projects never appear in related lists, so
  an open report keeps an item out of related while a human reviews it (the
  item itself stays visible in the showcase tab — only `minor_safety` reports
  auto-hide, so reporting is not a hide-any-item vector; tested). Concretely,
  related items are **visible to the requesting actor**: hidden and age-gated
  items never appear for anyone, and private items never appear for other
  users. Follower-only items follow the actor: the maker's **followers** can
  see them in related lists (verified), strangers cannot, and the item's
  **owner** always sees their own non-public projects in their own related
  lists (verified).
- Up to 3 items from the **same maker** (newest first from the pool), then
  same-tag matches fill the remaining slots up to 6 total — so an item with no
  same-maker matches can get 6 tag matches (tested). `why` is `"maker"` or
  `"tag"` so the UI can label the grouping.
- An item already returned is not repeated; the item itself is never related to
  itself.
- Summaries are compact by design: `id`, `title`, `creator_id`, `why`,
  `license_id`, `photo` (the thumb URL), and `url` (the API item URL). No
  description, tags, or nested objects are embedded.
- The source item must be visible to the actor; a hidden or private item
  returns its existing error, not a related list.

## Not built (deliberately)

- **Collections** — deferred. Requires moderation hooks (reporting + hidden
  management) and a collection-visibility model first.
- **Comments** — deferred for the same reason: user-generated text needs the
  word-list filter wired to a moderation queue before launch.
- **Licence changes after publish**, **custom licence text**, **licence-based
  search filters** — not in this version.
