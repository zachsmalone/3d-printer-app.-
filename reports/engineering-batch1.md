# Engineering — Batch 1 (Haruto Tanaka)

Status: PLAN (written before any app-code edit). Baseline: `python -m pytest -q tests` = **101 passed** (23 s) on 2026-10-04 16:22 CT.

Scope (per Yami): CR-1..5, CR-11, CR-10 flags, CR-15, then Ops basics. Not in this batch: auth/DB/upload-hardening blockers, CR-12, Build Plates, CR-6..9/13/14.

## Plan (order of commits)
1. **Config flags** (`app/config.py`, env-overridable): `PHOTO3D_MODE` (shared|local), `LIKES_REQUIRE_ACCOUNT`, `SHOW_COUNTS_FOR_EXAMPLES`, `TEEN_PUBLIC_ENABLED`, `HIDE_COUNTS_FOR_MINORS`, rate-limit sizes.
2. **CR-1** gate `/api/settings` PUT, printer CRUD and `/api/send/*` in shared mode (admin token or adult account; class students always 403); GET hides printer URLs from non-privileged; QR + slicer links use the configured base URL (not Host header) in shared mode.
3. **CR-2** re-encode uploads (Pillow, EXIF transpose, drop metadata), extension from sniffed format, same in Edit photo path; purge student builds on remove/delete; `DELETE /api/classrooms/{code}/me/data` ("Delete my stuff") + button.
4. **CR-3** per-class `showcase_enabled` (+ `showcase_likes`), default off; enforce on showcase/p/u/like/download/report routes for class-student sessions; UI hides nav.
5. **CR-4** teacher "Reset seat" + shared-computer join (session cookie).
6. **CR-5** photo-permission checkbox on Studio + Edit photo, `photo_ack` in meta.json (server-enforced), publish dialog text.
7. **CR-10** flags implemented + tests per flag; README Likes/Trending updated.
8. **CR-11** report dedupe, rate limit, audit log, `/admin/moderation` token-protected page, oldest-open-age; class-scoped reports to teacher first (minimal).
9. **CR-15** teacher recovery code (hashed), regenerate, rebind.
10. **Ops basics**: verify git/.gitignore; pin requirements; `.env.example` (merge with Ren's compose vars), root Dockerfile + .dockerignore, `/healthz`, CI, rebuild `/workspace/photo3d.zip` via Python zipfile.
11. README "Known limits", this report (hansei), restart 8765 via `./run.sh` at the end.

## Notes on what I found while reading (to verify, not yet claims)
- `MAX_BUILDS` is already enforced per owner session (`BuildStore.list(owner)`); Ops's note that it is global looks outdated. 
- Ren (DevOps) already added `.gitignore`, `.dockerignore`, `.env.example` (compose-oriented), `reports/deploy/Dockerfile` (proposal), `.github/workflows/ci.yml` (proposal) — I will reuse them rather than duplicate.
