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

## CAD-lite (long term)
Parametric primitives + booleans, text/emboss, sketch-extrude, snap/measure, import-and-edit of Showcase remixes, all in the browser.

## Social features (design hooks already in place)
`history.BuildStore` records carry `owner`/`visibility`; `community/*` modules sit behind small functions over JSON files (swap for a DB); routers are mounted in `app/main.py`; public pages are server-rendered with stable URLs. Planned: profiles, follows/feed, comments, shares, creator pages, saved collections.

## Legal & safety (REQUIRED before any public launch)
ZEIM is **18+ only** and free. Decision 2026-10-12 (Zach): ZEIM launches with no lawyers. Terms, Privacy and Rules are plain-words pages based on common free templates; they make no compliance claims. **Still NOT done:**
- **No NSFW.** No adult/mature content marketplace, no paid-mature tier. **Nothing involving minors in a sexual, exploitative or unsafe context is ever allowed; zero tolerance**, immediate removal, escalation and mandatory reporting where required (e.g., NCMEC in the US).
- Age: accounts are 18+ only; an under-18 date of birth is refused and not stored. Underage reports → moderator suspends (reversible). Accounts and data are never deleted by the app or admins. Data-retention policy and the final privacy notice are still to do. ZEIM holds no grades, scores or school records (school features removed 2026-10-12).
- Terms of Service, Community Guidelines (`COMMUNITY_GUIDELINES.md` is a draft), DMCA/copyright takedown process (section added to Terms with a placeholder contact; TODO: register a DMCA designated agent with the US Copyright Office, small fee, needs Zach's OK before paying), trademark clearance of product/section names.
- Moderation at scale: trained reviewers, report SLAs, appeals, audit logs, hash-matching/CSAM detection, rate limits (DMs don't exist yet).
- Age signals: date of birth is self-declared today (18+ gate, bypassable); consider privacy-preserving age assurance where required.
- Security: real auth, CSRF, upload scanning, secrets management (OAuth tokens are Fernet-encrypted at rest locally; printer API keys are stored plain in `data/settings.json`), third-party licences (PrusaSlicer is AGPL-3.0 and is run unmodified as a separate command-line program; ZEIM's own code stays private — see `docs/licensing.md`, decision 2026-10-13).


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

