# ZEIM: Launch-Readiness & Operations Plan

Author: Daichi Hayashi (Head of Growth & Operations) · Date: 2026-10-04 · Status: DRAFT for Zach / Mr. Yami Kato
Specialist support: Ren Okabe (Deployment & DevOps)

> Honesty note: prices below were read from provider pages on 2026-10-04 and are **rough planning numbers**, not quotes. Hetzner's US prices in particular have changed recently and third-party sources disagree, so verify at checkout. Traffic and user numbers are *assumptions*, labelled as such. Nothing here is legal advice; see section 4.

---

## 1. Where ZEIM is today (from the repo)

- FastAPI app (`uvicorn app.main:app`), single process, port 8765, started by `run.sh`.
- State lives in JSON files under `data/` plus build files under `outputs/` (about 67 MB for a handful of builds). `link.key` (Fernet key) is a file on disk.
- Identity is an anonymous session cookie plus a display name and self-declared date of birth. No passwords, no email, no sessions table.
- Slicing shells out to a PrusaSlicer CLI (`subprocess`, 600 s timeout). Image-to-mesh and mesh editing are CPU- and RAM-heavy (up to about 1.4 M triangles; voxel hollow; manifold booleans).
- Limits in code: 25 MB photo upload (`MAX_UPLOAD`), 50 MB mesh upload, 5 builds of history (`MAX_BUILDS`).
- Moderation queue is gated by a single `PHOTO3D_ADMIN_TOKEN` env var. Printer API keys are stored in plain text in `data/settings.json`.
- The project folder is **not a git repository**, and there is no Dockerfile, no CI, no backups, no health endpoint noted in the README.
- Tests exist (`tests/`), which is a good base for CI.

Bottom line: a solid prototype for one person on a LAN. It is not safe to put in front of children and schools as-is.

## 2. What must change before real users

Ordered by how blocking it is. "Owner" is who would do it; **only Engineering edits app code**.

### 2.1 Blockers (do not open to the public without these)

| # | Item | Why | Owner |
|---|------|-----|-------|
| 1 | **Real authentication**: email + passkey or magic link for adults and teens; sessions in a database; CSRF protection; secure, HttpOnly, SameSite cookies | Today anyone can reset identity by clearing cookies, and privacy rules rest on that identity | Engineering |
| 2 | **Database** (SQLite with WAL to start, Postgres when we need more than one app server) replacing JSON stores in `app/community/store.py` and `app/services/*` | JSON files have no locking across processes, no transactions, and corrupt on crash | Engineering |
| 3 | **Object storage abstraction** for builds, thumbnails and uploads (local disk first, S3-compatible later) with per-user quotas and cleanup | Disk fills up; files are tied to one machine | Engineering |
| 4 | **Upload hardening**: content-type sniffing, size caps per route, rate limits, virus/malware scan, image re-encoding, EXIF stripping (photos of kids may carry GPS) | Public uploads are the main attack and privacy surface | Engineering |
| 5 | **Job queue and resource limits** for slicing, hollow, boolean and photo-to-mesh work (worker process, per-job timeout and memory cap, per-user concurrency limit, queue position shown to user) | One heavy request currently blocks or crashes the single server | Engineering |
| 6 | **Secrets management**: all keys from environment or a secrets store; encrypt printer API keys; move `link.key` out of `data/` into a secret; rotate `ADMIN_TOKEN`; real moderator accounts instead of a shared token | Plain-text keys and a shared token are not acceptable with minors' data | Engineering + Ops |
| 7 | **Rate limiting and abuse controls** on every write route and on class-join guesses | Anonymous public endpoints | Engineering |
| 8 | **Legal and safety gates** (privacy policy, terms, COPPA/FERPA posture, takedown and reporting process, moderator staffing) | See section 4; owned by Trust, Safety & Legal | Kenji Watanabe |

### 2.2 Operations basics (Ops can set these up without app-code changes)

1. **Put the project under git** (private repo) and add `.env.example`. Right now there is no history to roll back to.
2. **Container image**: Dockerfile with Python 3.13, PrusaSlicer CLI, DejaVu fonts, non-root user. Needs a pinned `requirements.txt` (currently unpinned) and a lock file.
3. **Reverse proxy and TLS**: Caddy or nginx, automatic HTTPS, request body size cap, gzip, security headers (CSP, HSTS, `X-Content-Type-Options`).
4. **Health and metrics**: a `/healthz` endpoint (small Engineering ask), uptime monitor, error tracking (for example Sentry free tier), structured logs with no personal data.
5. **Backups**: nightly database dump plus a sync of user files to an off-site bucket; retention 14 daily and 8 weekly; **a restore drill before launch and then quarterly**. A backup that has never been restored does not count.
6. **Storage limits and cleanup** (starting proposal, Engineering to confirm what is feasible):
   - 25 MB per photo, 50 MB per mesh, as today.
   - About 250 MB of stored files per free user; build history of 5 per user as today (note: `MAX_BUILDS` should become per-user).
   - Class projects deleted with the class (already specified); inactive anonymous data purged after 30 days.
   - Expiring signed links already exist (2 hours), keep them.
7. **Environments**: local, staging (same container, separate data, fake seed data) and production. Never copy production child data to staging.
8. **CI**: run `tests/` on every change; build the container; block deploys on failure.
9. **PrusaSlicer licensing**: it is AGPL. Running it server-side as a separate CLI process is a common pattern, but legal should confirm the obligations before we host it publicly.
10. **Incident basics**: one page runbook (how to roll back, how to restore, who to call), a status note we can post, and a way to take the site to read-only mode.

## 3. Hosting options and rough costs

Assumptions (not measurements): early pilot of a few classrooms and maker clubs, roughly 50 to 500 monthly active users, under 20 GB of stored files in the first months, a handful of simultaneous slicing or editing jobs. Real numbers should replace these after a load test on staging.

Sizing guide: because meshing and slicing are CPU/RAM heavy, start with **at least 2 vCPU and 4 GB RAM** for the app plus worker, and move workers to their own machine if queue times grow.

| Option | What you get | Rough monthly cost (USD) | Pros | Cons |
|---|---|---|---|---|
| **A. One VPS, Docker Compose** (DigitalOcean Basic 2 vCPU / 4 GB is listed at $24/mo; 2 vCPU / 2 GB at $18/mo; 4 vCPU / 8 GB at $48/mo) | App, worker, SQLite or Postgres, Caddy on one box | $24 to $48 for the server, plus backups (DigitalOcean lists backups at 20% of the droplet price weekly, or 30% daily), so about $30 to $65 total | Simplest; predictable bill; full control (PrusaSlicer installs easily) | One machine = one point of failure; we handle patching |
| **B. Hetzner Cloud VPS** | Same layout as A | EU plans reported from about $6.5 (small) to about $42 (4 vCPU / 8 GB, per a third-party tracker); US (Ashburn) plans reported at about $20 to $37 for 2 to 3 vCPU. **Prices recently rose and sources disagree; verify before deciding** | Often the best price per CPU; EU data centers help with GDPR | Smaller US footprint; US schools may prefer US data residency; less hand-holding |
| **C. Fly.io Machines + volume + Managed Postgres** | Container deploy with a CLI, volumes, optional managed database | Fly's own example "small web app with Managed Postgres" is about $44/mo. A 2 GB shared machine is listed at $13.39/mo, a performance 2 GB at $33/mo, volumes $0.15/GB/mo. Expect roughly $50 to $100 for our needs | Easy deploys and rollbacks; managed Postgres means fewer backup chores | More moving parts to learn; CPU-heavy jobs need performance machines, which cost more |
| **D. Managed PaaS (Render, Railway, etc.)** | Git push to deploy | Not priced here; check current pricing pages | Least ops work | Heavy jobs and persistent disks tend to cost more; need to confirm PrusaSlicer fits |
| **E. Hyperscaler (AWS / GCP / Azure)** | Everything, including queues, KMS, WAF | Typically more than A to C for this scale, and egress fees add up | Best for compliance paperwork if a district asks | Complexity and cost out of proportion to a pilot |

**Object storage for user files and backups**: Backblaze B2 lists about $6.95 per TB per month, with free egress up to 3x stored data and free egress through partner CDNs including Cloudflare. For 20 GB that is well under $1/mo. Cloudflare R2 (zero egress fees) is another S3-compatible option; pricing not verified here.

**Other recurring costs to budget for** (rough, mostly unverified): domain name about $10 to $20 per year; transactional email (for sign-in links) free to about $20/mo at pilot volume; error tracking and uptime monitoring free tier to about $30/mo; a CDN/proxy such as Cloudflare free tier for caching and basic DDoS protection.

**Recommended path**
1. **Pilot (invite-only): Option A**, one 4 GB VPS, Docker Compose, SQLite (WAL) or small Postgres, Cloudflare in front, nightly off-site backups to B2. Realistic all-in budget: **about $40 to $80/month**, plus a one-time domain.
2. Move to **separate worker box and managed Postgres (or Option C)** once queue wait times or database load show up in monitoring, probably **$100 to $250/month**.
3. Revisit hyperscaler or district-specific hosting only if a school or district contract requires it.

Not included: moderator time and legal review, which are likely the **biggest real costs** for a children's platform (see sections 4 and 5).

## 4. Safety, privacy and legal gating (owned by Trust, Safety & Legal; listed here because it gates the launch)

ROADMAP.md already states these are REQUIRED before any public launch and are NOT done. Ops view of what must exist before opening beyond a private pilot:

- Privacy policy, terms of service and community guidelines reviewed by qualified counsel.
- A written posture on COPPA, FERPA and state student-privacy laws, including the school-facing data processing agreement, parental consent flow where needed, and a retention and deletion policy.
- A reporting and takedown process (including DMCA), a named person who reviews reports, target response times, and an escalation path for any child-safety report (zero tolerance, mandatory reporting where required).
- Age signals are self-declared today; decide what is acceptable for launch.
- Hosting facts counsel will ask about: where data lives, who has admin access, backup locations and retention, sub-processors (hosting, email, error tracking). Ops will keep an up-to-date list.

**Recommendation:** do not open public sign-up until these are done. A small invite-only pilot with a few teachers and adult makers, with no student data beyond nickname, is a reasonable first step *if counsel agrees*.

## 5. Phased roadmap

Durations are rough and depend on Engineering capacity; they are planning guesses, not commitments.

**Phase 0: Prep (about 1 week, mostly Ops)**
- Put code in a private git repo; pin dependencies; write Dockerfile and compose file; set up CI running `tests/`.
- Choose hosting (decision for Zach); create staging.
- Engineering prerequisites sent (section 7).

**Phase 1: Safe foundations (about 3 to 5 weeks)**
- Auth, sessions, database, object-storage abstraction, secrets cleanup, rate limits, upload hardening, `/healthz`, job queue.
- Backup automation and a first restore drill. Load test staging with realistic slicing and editing jobs.
- Legal review in parallel.
- *Exit test:* a stranger cannot read another user's private item, a crashed server loses no data, a restore works, and the heaviest job cannot take the site down.

**Phase 2: Closed pilot (about 4 to 6 weeks)**
- Invite-only: a few teachers, maker clubs and adult hobbyists. Feedback form and weekly review.
- Moderators trained; reporting tested end to end with real (adult) testers.
- Track: sign-up to first print, job failure rate, queue time, support questions, cost per active user.
- *Exit test:* no unresolved safety or privacy incident, backups verified, costs known.

**Phase 3: Limited public launch**
- Open sign-up with caps (for example a waitlist) and all legal documents live.
- Build Plates (groups) only after moderation tooling exists. Share-to-social and OAuth verification after Phase 3.
- Status page, support inbox, on-call rota (even if it is one person).

**Phase 4: Scale and polish**
- Separate worker pool, managed Postgres, CDN for thumbnails and downloads, accessibility and localisation, LMS sign-in (Google Classroom / Clever) once school demand is proven.

## 6. Launch checklist (go / no-go)

- [ ] Real auth live; cookie-only identity removed
- [ ] Database in use; JSON stores retired
- [ ] Per-user quotas and cleanup jobs running
- [ ] Upload scanning, EXIF stripping, rate limits on
- [ ] Heavy jobs run in a limited worker with a queue
- [ ] No secrets in `data/` or in git; admin token replaced by moderator accounts
- [ ] HTTPS, security headers, firewall (only 80/443 open)
- [ ] Backups automated **and restored once successfully**
- [ ] Monitoring: uptime, errors, disk, CPU/RAM alerts
- [ ] Privacy policy, terms, guidelines, DMCA and report process published (counsel-approved)
- [ ] Moderators named and trained; safety escalation path written down
- [ ] Rollback tested; read-only mode available
- [ ] Spend alert set at the hosting provider

## 7. Engineering prerequisites (sent to Haruto Tanaka)

1. Auth and sessions (email/passkey or magic link), CSRF, secure cookies; keep teen and child defaults.
2. Replace JSON stores with a database behind the existing small store functions; provide a one-time migration script.
3. Storage abstraction (local disk / S3-compatible) and per-user quotas; make `MAX_BUILDS` per user.
4. Job queue/worker for slicing, hollow, boolean, photo-to-mesh, with timeouts, memory caps and a per-user concurrency limit.
5. Upload hardening: MIME sniffing, EXIF stripping, re-encoding, rate limits, optional malware scan hook.
6. Secrets: read everything from env; encrypt printer keys; move `link.key` out of `data/`; moderator accounts replace `PHOTO3D_ADMIN_TOKEN`.
7. `GET /healthz` (no auth, no data) and structured logging without personal data.
8. Pin dependencies (`requirements.txt` is unpinned) and confirm the supported Python version.
9. Config via environment for host, port, base URL, data and output directories; no writes outside those directories.
10. A "read-only mode" switch.

## 8. Positioning one-pager (humble)

**ZEIM**

**One-liner:** A free place to turn a photo or a 3D file into something you can print, and to share and learn along the way.

**Who it is for:** students, teachers and hobbyists who are new to 3D printing or want fewer tools to juggle. Families and schools are welcome; the community is family-friendly by design.

**What it does today (still growing, parts are early):**
- Turns photos into printable lithophanes, reliefs and pop-art, with simple defaults for beginners and full settings for experts.
- Lets you open existing STL, OBJ and 3MF files and make basic edits (scale, cut, hollow, add a base, repair, add text), with undo.
- Hands your model to your own slicer or printer, so your files are never locked in.
- Lets you share projects with privacy controls (private by default).
- Includes Spark Lab lessons and classrooms for teachers, with join codes, nickname-only students, and no personal data collected from children.

**What we are not:** not a marketplace, no paid content, no adult content, no ads. We do not claim to replace the tools makers already love; we hope to be a friendly starting point that works alongside them.

**What we are still working on (said openly):** sign-in, a production-grade database, groups called Build Plates, more printer types, and independent safety and legal review before we open to everyone.

**How we want to grow:** by listening. Maker clubs, libraries and teachers first; small, honest pilots; shareable lesson and project pages; letting people export their work any time.

**Tone guide:** friendly, plain, a little curious. Say "we're learning" rather than "we're the best". Do not compare ourselves to other products. Label example content as examples. Never promise safety features that are not built yet.

**Short boilerplate (for forms and listings):** "ZEIM is a free, family-friendly 3D-printing starter: photo or file to print, with lessons for classrooms and a small community for sharing what you make. It is early and growing, and we welcome feedback."

---

## 9. Open decisions for Zach

1. Hosting: Option A (single VPS) for the pilot, yes or no? Preferred region (US vs EU)?
2. Who will be the named moderator(s) and on-call person for the pilot?
3. Is a private invite-only pilot acceptable before the legal review finishes, if it involves adults only?
4. Domain name and sender email address for sign-in links.
5. Budget ceiling for the first three months (hosting + tools); estimate above is $40 to $80/month, excluding legal.

## 10. Sources (read 2026-10-04)

- DigitalOcean Droplet pricing: https://www.digitalocean.com/pricing/droplets
- Fly.io resource pricing: https://fly.io/docs/about/pricing/
- Backblaze B2 pricing: https://www.backblaze.com/cloud-storage/pricing
- Hetzner (third-party price trackers, may be out of date): https://bestusavps.com/reviews/hetzner/ and https://servercostcalculator.com/providers/hetzner/plans/cpx21
