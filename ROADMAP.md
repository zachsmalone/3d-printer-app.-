# Roadmap

## Vision
One place to go from **photo or existing 3D file → printable object → printed → shared**. ZEIM is a free, all-in-one 3D-printing maker app and community for **adults (18+ only)**. No payments, no NSFW, no school features (no teachers, classes or grades). Easy for beginners (auto-everything), with every setting available to experts. It is a young project and still growing; many parts are scaffolds (see below).

*Long-term aspiration only (not a claim about today):* "all you need to turn an idea into a print".

## Where we are (this repo)
Newest: **Edit workspace** (upload STL/OBJ/3MF/photo or a Studio build → move/rotate/scale/mirror/drop/cut/hollow/base/booleans/text/repair/simplify/measure, non-destructive undo/redo), **privacy controls** (Private / Followers / Public everywhere, follow opt-out), **likes + download-aware Trending**, and a **multilingual language filter** that blocks disallowed words in anything other people can read.
Working: photo→lithophane/relief/pop-art, STL/OBJ/3MF, preview, PrusaSlicer slicing, slicer deep links, OctoPrint/Moonraker upload, build history (5), Beginner/Expert, Showcase (free, example seed data), local For You personalization, reports + moderation stub, follow scaffolding, link-outs to your other accounts, shareable project pages.
Scaffold/stub only: OAuth providers (no posting/verification), PrusaLink/Bambu/Duet/Repetier uploads, DMs, feed, real auth.

## Near term
1. Real auth (email/passkey), sessions, password-less login; move JSON stores → SQLite/Postgres; object storage for files.
2. Showcase: tags/search index, licence picker (CC variants), remix links, comments (moderated), project collections.
3. Follow → feed of followed creators; notifications; creator profile pages with verified link-outs.
4. Promote-your-accounts: finish OAuth for TikTok / Instagram / Reddit / Patreon to *verify* handles and show a "verified" badge; **one-click share** of a build (turntable video/photo + link) to linked accounts. Patreon is a **link-out only** (creators send fans to their own page) — no selling or paywalls inside the app.
5. More printers: PrusaLink, Bambu LAN (MQTT+FTPS), Duet; printer profile library; per-printer slicing profiles; live status.
6. Edit workspace next steps: on-model drag gizmos, face/edge selection, snapping, sketch-extrude, fillet/chamfer, section view, thickness analysis, mesh-quality heatmap, multi-object scenes with colour/material kept on 3MF import, auto-arrange, text on curved surfaces, a proper (non-fan) hole-filler, a faster non-voxel hollow.
7. Studio: curved/cylindrical lithophanes, hanging holes/stands, lamp kits, text/QR, multi-photo bundles, AMS/MMU colour mapping, better pop-art (outline layers, drop-shadow offsets), mesh decimation for big outputs.

## Learning content (optional)
- Troubleshooting and maker how-tos may grow over time. No quizzes, scores or grades.
- Accessibility + localisation where it helps adults using the app.

## Adoption strategy
- **Import**: open STL/3MF/OBJ library import (drag-drop, folder watch) so existing collections work on day one; bulk import of a user's own files from other sites via their export/zip.
- **Compatibility**: first-class slicer hand-off (Prusa, Bambu, Orca, Cura), standard 3MF/STL output, standard printer protocols (OctoPrint, Moonraker, PrusaLink). Never lock files in.
- **Positioning**: confident and proud (Zach, 2026-10-04) — ZEIM brings photo→print, edit, slice and share into one free place for adult hobbyists. Every claim we make must be true, and we make no unverifiable claims about named competitors. Grow by listening to users.
- **Growth**: shareable project pages (already built), one-click share to linked social accounts, maker-club partnerships.

## Product pillars and CAD approach (decision 2026-10-17: option 3, "ideas only")
ZEIM aims to be four things in one place, each built as **original code** (common conventions and public file formats only; no copying of any other product's code, look or assets):
1. **Showcase / library** (the model-sharing role): search, tags, licences, remixes, collections, comments; private by default.
2. **Slicer** (the desktop-slicer role): PrusaSlicer CLI underneath, with a full per-printer / material / object settings editor and layer preview.
3. **Lithophane and relief maker**: the narrow launch hook; aim to be the most complete (crop, curved/cylindrical, lamps, frames, hanging holes, colour, verified prints).
4. **CAD** (the mobile/desktop sculpt-and-sketch role): sketch, constraints, extrude/revolve, fillet/chamfer, face/edge selection, gizmos, a parametric feature tree, and imported files editable as if native.
CAD sketch/constraint features are written by ZEIM from first principles in Python. Nobody working on them reads ZEIMCad's Rust or SolveSpace code. ZEIMCad stays a separate GPL project. Only claims that are true go in the app: say what is done and what is not.

## CAD-lite (long term)
**Status 2026-10-18 (branch `cad-workspace`):** first CAD workspace built: sketch + original least-squares constraint solver, extrude/revolve/boolean/approximate fillet-chamfer/shell/face offset/move/scale/pattern/align/mirror as editable history steps, History/Items panels, view cube, section, measure. Done / not done list: docs/specs/cad-workspace.md.
**Decision 2026-10-17:** ZEIMCad (SolveSpace-derived Rust port) is a separate GPL-3 project on its own branch (`PerplexCopilot`); it is not part of the private ZEIM app code. Boundary: ZEIM's own Python (feature detector, feature tree, replay engine) stays original and must never re-express ZEIMCad/SolveSpace code; ideas yes, code no. If ZEIM ever needs its constraint solver, it runs as a separate tool or service (like the PrusaSlicer CLI). Its `.exe` is a build artifact (CI should build it and run `--self-check`); the next milestone for the port is a C++ reference harness on the pinned SolveSpace revision.
Parametric primitives + booleans, text/emboss, sketch-extrude, snap/measure, import-and-edit of Showcase remixes, all in the browser.

## Social features (design hooks already in place)
`history.BuildStore` records carry `owner`/`visibility`; `community/*` modules sit behind small functions over JSON files (swap for a DB); routers are mounted in `app/main.py`; public pages are server-rendered with stable URLs. Planned: profiles, follows/feed, comments, shares, creator pages, saved collections.

## Launch readiness (judgement estimate, ~55-65%)
Core product is solid; blockers are trust, safety and infrastructure. Order of work:
1. Real auth, database (SQLite/Postgres) + object storage, CSRF, upload scanning.
2. Safety: moderation workflow, image checks / hash matching, report SLAs and appeals, DMCA agent, retention policy.
3. Deploy with backups + monitoring; small private beta; test large/self-intersecting meshes and load.
4. Full slice-settings UI (per-printer/material/object overrides), Edit polish (sketch-extrude, fillet/chamfer, gizmos), first-run guided flow.
5. After launch: PrusaLink/Bambu/Duet, feed, notifications, verified OAuth.
Launch with a narrow hook (photo to lithophane) and make only claims that are true.

## Launch research findings (2026-10-17, external research; not legal advice)
Source: a Perplexity research report supplied by Zach. Claims are unverified by us; re-check sources and prices before relying on them.
- **Launch scope:** a narrow, adult-only "photo → printable keepsake" (lithophane/relief) pilot: private by default, downloadable files, a few verified printer profiles. Public sharing and remote printer control are separate launch gates. Do not claim general "photo to 3D" or CAD parity. The moat is completion (crop → preview → thickness/orientation → frame/base → verified slice → real print), since free lithophane tools already exist.
- **Niches to test (hypotheses):** private photo keepsakes; phone-first small edits; mesh-preserving repair/personalise (keep originals, disclose simplification); cross-brand guided slicing for 1-2 printer families; reproducible project pages (model, edits, printer/material/profile, real print photos).
- **Legal/safety gates before public uploads:** register a DMCA designated agent ($6, renew every 3 years) and publish matching contact, repeat-infringer policy and notice/counter-notice steps; written NCMEC CyberTipline procedure with restricted one-year preservation (18 USC 2258A) and a human escalation contact; apply for PhotoDNA / Google child-safety tools, add Cloudflare CSAM scanning as an extra layer, quarantine new public images until review; neutral age screen, reject under-18, store minimal age evidence; privacy notice, terms, retention schedule (failed uploads 24-72h, logs 14-30d, backups 30-90d, legal holds override); UK Online Safety Act and EU DSA scope review (an 18+ checkbox is not a substitute).
- **Printers:** a hosted server cannot reach a user's LAN address, and user-supplied printer URLs are an SSRF risk: use a paired local connector or file/deep-link handoff, never default public port-forwarding. Order: keep OctoPrint/Moonraker, add PrusaLink (HTTP Digest, `PUT /api/v1/files/{storage}/{path}`, keep auto-start off), then Duet/Repetier on demand. Bambu: critical commands need authorization outside Developer Mode, so keep it experimental or handoff only.
- **Licensing:** run PrusaSlicer (AGPL-3.0) unmodified as a pinned separate CLI; do not copy/link its code; re-check if modified or if distributing binaries/containers. manifold3d (Apache-2.0), trimesh (MIT), DejaVu (Bitstream Vera terms) and LDNOOBW (CC BY 4.0) need a third-party notices page.
- **Hosting estimate (planning only):** about $30-65/mo at 100 MAU, $65-190 at 1,000, $320-850 at 10,000, driven by storage, slicing CPU and abuse. Use object storage (R2/B2) separate from the app host plus independent backups; test a restore.
- **Auth:** email code/link bootstrap, then passkeys (`py_webauthn`), a second passkey and recovery codes; recent-auth for sensitive changes; revocable sessions, CSRF, rate limits; stronger protection for the founder/moderator account.

### Top 10 first actions (effort estimates are rough)
1. Fix pilot scope and print-test plan (4-8h + print time).
2. Persistent accounts, sessions, recovery, admin protection (3-7d).
3. Move multi-user JSON records to a transactional DB; access tests for private originals, thumbnails, exports, signed links (3-7d).
4. Upload hardening: content checks, quotas, quarantine, timeouts, memory-limited workers (3-6d).
5. NCMEC procedure and secure preservation; apply for detection tools (1-2d + approval).
6. DMCA agent registration and policy pages (2-4h + $6).
7. Truthful privacy/terms/rules, retention schedule, deletion/export (1-3d).
8. Staging/production, automated backups, restore test, alerts (2-4d).
9. Secure printer pairing: no arbitrary backend URLs, encrypted credentials, explicit print confirmation, real-device tests (2-5d).
10. Third-party notices, geographic scope review, then a capped pilot with a staffed report mailbox (1-3d).

## Legal & safety (REQUIRED before any public launch)
ZEIM is **18+ only** and free. Decision 2026-10-12 (Zach): ZEIM launches with no lawyers. Terms, Privacy and Rules are plain-words pages based on common free templates; they make no compliance claims. **Still NOT done:**
- **No NSFW.** No adult/mature content marketplace, no paid-mature tier. **Nothing involving minors in a sexual, exploitative or unsafe context is ever allowed; zero tolerance**, immediate removal, escalation and mandatory reporting where required (e.g., NCMEC in the US).
- Age: accounts are 18+ only; an under-18 date of birth is refused and not stored. Underage reports → moderator suspends (reversible). Accounts and data are never deleted by the app or admins. Data-retention policy and the final privacy notice are still to do. ZEIM holds no grades, scores or school records (school features removed 2026-10-12).
- Terms of Service, Community Guidelines (`COMMUNITY_GUIDELINES.md` is a draft), DMCA/copyright takedown process (section added to Terms with a placeholder contact; TODO: register a DMCA designated agent with the US Copyright Office, small fee, needs Zach's OK before paying), trademark clearance of product/section names.
- Moderation at scale: trained reviewers, report SLAs, appeals, audit logs, hash-matching/CSAM detection, rate limits (DMs don't exist yet).
- Age signals: date of birth is self-declared today (18+ gate, bypassable); consider privacy-preserving age assurance where required.
- Security: real auth, CSRF, upload scanning, secrets management (OAuth tokens are Fernet-encrypted at rest locally; printer API keys are Fernet-encrypted in `data/settings.json`; the key lives in `PHOTO3D_SECRET_KEY` or a 0600 key file, so set the env var in production), third-party licences (PrusaSlicer is AGPL-3.0 and is run unmodified as a separate command-line program; ZEIM's own code stays private — see `docs/licensing.md`, decision 2026-10-13).


## Edit workspace (shipped as an MVP)
Works: upload STL/OBJ/3MF (50 MB, validated by content), photo → lithophane/relief base, "Edit this" for Studio builds; move/rotate/scale with numeric inputs and mm/cm/in; mirror; drop/center; cut or split with a plane; hollow with wall thickness (+drain hole); flat base/brim; union/difference/intersection with box/cylinder/sphere (manifold3d); emboss/deboss text (bundled DejaVu fonts); repair (normals, duplicates, holes, floating bits); decimate; two-point measure; undo/redo/jump; original always kept; exports STL/OBJ/3MF, slice, deep links, network printers through the existing flows.
Partial: multi-colour/material data is merged away on import; hole filling is a centroid fan (rough on very concave holes); hollow is voxel-accurate (≈ one voxel); text sits on the bounding-box face (curved surfaces may not touch); no drag handles; large meshes (>150k triangles) are previewed simplified; booleans need a watertight mesh (run Fix first); not tested with very large or self-intersecting real-world meshes.

## Build Plates (future — hobbyist groups)
Planned, **not built**: interest-based groups called **Build Plates** (e.g. a local maker club, a printer-model group). Each has its own visibility (private / invite / public), moderators, shared project boards and the same privacy and language rules as everything else. Names are configured in `app/branding.py` (`GROUP_NAME`, `GROUP_NAME_PLURAL`).

## Privacy, safety and moderation (current state)
- Visibility Private / Followers-only / Public on every build, edit project and Showcase project; default **Private**. Enforced server-side on every route (lists, search, Trending, For You, direct URLs, thumbnails, share pages, files, likes, reports). Denials look like 404. Slicer deep links use signed 2-hour file links so a private build still opens in the owner's slicer.
- Follow opt-out (no following, no followers, no counts, existing follows removed at once). Private profile.
- Language filter (PG-13): LDNOOBW word lists (CC BY 4.0) for 16 languages + ZEIM additions, whole-word matching with leetspeak / stretched-letter / spaced-letter handling and an editable allowlist for false positives. A blocked message is **not sent or stored**; the sender sees "Chat doesn't allow that language. Please use appropriate language." There are no strikes or bans. Report and the moderator queue remain.
- Honest limits: a word list is not a moderation service (misses new slang, context, images, many languages); sessions are cookie-based until real auth exists, so anonymous identity can be reset by clearing cookies.

## School features: removed (2026-10-12)
Zach removed the school aspect of ZEIM on 2026-10-12; none of it is planned to come back. ZEIM is free and **18+ only**.

