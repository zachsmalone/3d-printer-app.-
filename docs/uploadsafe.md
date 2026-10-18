# Upload safety checks (`app/services/uploadsafe.py`)

**Status: standalone, not yet wired into any route.** This module was built for
launch-safety groundwork. It is deliberately not imported by the build, photo, or
edit endpoints, because those files are owned by concurrent work. This page is
the adoption guide for whoever wires it in.

## What it does

`uploadsafe.check(data, **limits)` inspects raw upload **bytes** and either
returns a `Checked` summary or raises `Rejected`. It decides everything from
**file content, never the filename or extension** — a STL named `photo.png` is
detected as an STL. Note the module is bytes-only: it does not know what name a
file arrived under, so *endpoint-specific* rules (for example, "the photo
endpoint only accepts images") are enforced by the calling endpoint, which can
read `Checked.kind` and refuse mismatches. The module never decodes an image or
builds a mesh:

- **Content sniffing** for PNG, JPEG, GIF, WEBP, BMP (images) and binary/ASCII
  STL, OBJ, 3MF (models). Unknown content is rejected as `unknown_type`.
  ASCII STL counting is case-insensitive and whitespace-tolerant (the downstream
  loader accepts any case — verified with trimesh — so an uppercase file must
  not report zero complexity).
- **Size cap** — 25 MB default, matching `config.MAX_UPLOAD`.
- **Mesh complexity caps** — 3,000,000 faces (matching `meshedit.MAX_FACES`) and
  3,000,000 vertices. Counts come from the binary STL header, the ASCII
  facets, the OBJ records (a face with n corners counts as n−2 triangles, the
  count a triangulating loader produces), or the 3MF model.
- **Image decompression-bomb caps** — 100,000,000 pixels (matching
  `imagesafe.MAX_PIXELS`), dimensions read straight from the PNG IHDR, JPEG SOF,
  WEBP, or BMP header, or — for GIF — from a full block walk: every image
  descriptor is bounded (frames can exceed the logical screen; the pixel count
  is the max over screen and frames), and a GIF-shaped file with a block that
  is neither a descriptor, an extension, nor the trailer is refused rather
  than measured at the logical-screen size. A 29-byte header claiming 1.6
  gigapixels is refused before any decode happens.
- **3MF archive limits** — 200 members, 64 MB per uncompressed member, 128 MB
  total uncompressed across members, 32 MB of model XML. Checked from the zip
  directory (`file_size` fields) **before any member is read**, so a zip
  claiming to expand past the cap is refused without inflating it.
- **3MF complexity is the expanded count**: `<components>` objects and `<build>`
  items are resolved (memoized, with a 64-deep nesting bound — deeper graphs or
  unresolvable ones like cycles and missing references are refused as
  `archive_bad`), so an archive that multiplies a small mesh through many
  instances cannot understate its triangle count.

## Result contract

`Checked.to_dict()` produces a plain dict:

```python
{"kind": "image"|"mesh", "format": "png|jpg|gif|webp|bmp|stl|obj|3mf",
 "size_bytes": 12345, "image": {...}|None, "mesh": {...}|None, "archive": {...}|None}
```

`Rejected` is a `ValueError` subclass with:

- `.reason` — a stable machine code: `too_big`, `image_too_many_pixels`,
  `too_many_faces`, `too_many_vertices`, `archive_too_big`,
  `archive_too_many_members`, `archive_bad`, `unknown_type`,
  `image_bad_header`
- `str(e)` — a user-safe message (no paths, no stack details); `.detail` carries
  structured info for logs.

## Adoption

The intended call sites, in the order uploads currently flow (verified against the
source: mesh and photo uploads both enter through `app/api/edit.py`'s upload
branch, which picks the format from the file extension — exactly what this
module replaces; `app/api/builds.py` also has a photo/trace path that runs
`imagesafe` checks):

1. **Uploads in `app/api/edit.py`** (the upload branch that starts an edit
   project) — replace trust-the-extension format detection with
   `uploadsafe.check(data)` (the full validation call — `sniff()` alone does
   NOT enforce the pixel and complexity limits), refuse `kind != "image"` on
   the photo path and `kind != "mesh"` on the mesh path, and catch `Rejected`
   as a 4xx with `str(e)`. The caps fire before the mesh is parsed.
2. **Photo/trace uploads in `app/api/builds.py`** — the existing `imagesafe`
   checks stay; this adds content-type verification and the same pixel cap at
   the raw-bytes stage.
3. **3MF archives** — adopt the archive limits before `zipfile` inflation on
   every path that opens one.
4. **Keep the caps in sync**: the face cap equals `meshedit.MAX_FACES` by
   import, so a model that passes upload is within the cap the editor
   enforces — these are bounded guards against resource exhaustion, not a
   guarantee that any particular model will edit or slice smoothly.

All limits are keyword-overridable in `check(...)`: `max_bytes`,
`max_pixels`, `max_faces`, `max_vertices`, `max_archive_members`,
`max_member_bytes`, `max_archive_bytes`, `max_model_xml_bytes` — for tests
and for per-endpoint tightening without touching module constants.

## Tests

`tests/test_uploadsafe.py` — 46 tests, all passing. Fixtures are generated
in-test: header-shaped PNG/JPEG/GIF/WEBP/BMP, **real encoder output via PIL**
(PNG/JPEG/GIF/BMP, WEBP when the build supports it), binary/ASCII STL
(including uppercase and tab-separated forms), OBJ (including polygon
triangulation), and real minimal 3MF zips (plain, component-multiplied,
cyclic, missing-reference, deep-chain, malformed XML, unsupported
compression). Covers: sniffing by content, bomb refusal before decode or
inflation (a monkeypatched `ZipFile.read` fails the test if any member is
inflated before the limit fires), GIF frames larger than the logical screen
(including behind extension blocks and as a second frame), damaged headers,
unknown GIF blocks, STL count mismatch (a header claiming more triangles than
the file contains is unknown content, not a mesh), all limit paths including
exact-cap boundaries, summation across multiple model parts, and user-safe
error messages.

## Honest gaps

- OBJ/STL vertex counts are record counts, not deduplicated vertices — the
  same vertex listed twice counts twice. The cap is a guard, not an
  authoritative mesh statistic.
- No GLB/glTF, PLY, or AMF support — only what the app accepts today.
- WEBP dimension parsing covers VP8X (extended), VP8 (lossy), and VP8L
  (lossless) header shapes and is exercised on real encoder output, but is not
  fuzz-tested against adversarial files.
- 3MF extension assumes the standard core schema; producer extensions with
  their own geometry representations are counted as whatever triangles they
  declare in the core model part, or refused if unresolvable.
- It does not detect malware or scanning-probe payloads; it is a resource guard.

## Handoff contract: wiring the gate into /api/edit/new (and /api/edit/new-multi)

`app/api/edit.py` (and the `static/edit.js` flow that calls it) belongs to the Copilot
workstream and is deliberately not modified here. This is the exact integration once that
file is next touched — it is three lines at the top of each upload-reading handler
(`new_project`, `new_multi`), right where the UploadFile is read and BEFORE any parsing:

```python
from ..services import uploadgate          # module level

# read with the SAME cap the route already enforces (MAX_UPLOAD + 1, then 413 over):
data = file.file.read(MAX_UPLOAD + 1) if file else b""
if len(data) > MAX_UPLOAD:
    raise HTTPException(413, "file too large")
try:
    checked = uploadgate.gate(data, actor.sid, source="edit")
except uploadgate.GateError as e:
    raise HTTPException(e.status, e.message)
# checked.scan_state == "unscanned" (scanner on but unreachable) -> the upload is NOT built:
# park it (services/quarantine.py stage_pending: original bytes + request context, 0700) and
# return 202 {"status": "pending_scan", "pending_id": ...} — see app/api/builds.py's generate
# flow + /api/uploads/resume for the exact pattern (resume re-runs the whole pipeline).
```

The gate must run BEFORE any parsing of the bytes, and the returned scan state must be honored
(a pending upload is never parsed, built, served, shared, or mirrored to object storage; only
a clean scan — via resume — ever builds it, and an infected verdict discards it).

What this buys (all already implemented + tested in `app/services/uploadgate.py`):
  * per-account hourly rate limit (shared with photo uploads, db-backed in db mode);
  * the uploadsafe content checks (mesh bombs, archive caps, masquerading files);
  * the audit log entry (never file bytes) in DATA/uploads.log.jsonl;
  * ClamAV verdicts: infected -> refused + never stored; scanner-down -> parked as a pending
    upload (never built) until a clean scan via /api/uploads/resume builds it.

Acceptance test: `tests/test_edit_new_gate.py` (marked xfail until the wiring lands).
