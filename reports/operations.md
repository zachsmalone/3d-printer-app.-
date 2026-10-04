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
| **B. Hetzner Cloud VPS** | Same layout as A | EU plans reported from about $6.5 (small) to about $42 for a CPX32-class 4 vCPU / 8 GB plan per a third-party tracker (Ren Okabe could not confirm this against Hetzner's own page and reads the EU CX33 as about EUR 9; treat all Hetzner figures as UNVERIFIED); US (Ashburn) plans reported at about $20 to $37 for 2 to 3 vCPU. **Prices recently rose and sources disagree; verify before deciding** | Often the best price per CPU; EU data centers help with GDPR | Smaller US footprint; US schools may prefer US data residency; less hand-holding |
| **C. Fly.io Machines + volume + Managed Postgres** | Container deploy with a CLI, volumes, optional managed database | Fly's own example "small web app with Managed Postgres" is about $44/mo. A 2 GB shared machine is listed at $13.39/mo, a performance 2 GB at $33/mo, volumes $0.15/GB/mo. A 4 GB performance-2x machine is $66/mo and Managed Postgres Basic is $38/mo, so expect roughly $105 or more with a database (corrected 2026-10-04 after Ren Okabe's review; earlier draft said $50 to $100) | Easy deploys and rollbacks; managed Postgres means fewer backup chores | More moving parts to learn; CPU-heavy jobs need performance machines, which cost more |
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


---

## 11. Global research (Operations & Growth angle)

Author: Daichi Hayashi · Added 2026-10-04 · Status: DRAFT for Zach / Mr. Yami Kato. Sections 1 to 10 above are unchanged.

**Why this section exists.** Mr. Yami Kato asked each department to read what makers, teachers, students and parents say about the tools they already use, and to adopt, adapt or reject ideas with reasons. This is the Ops/Growth view: reliability, hosting, lock-in, moderation, school privacy, onboarding, pricing and community growth. We are learning from others here. Nothing below says ZEIM is better than anything else.

**How to read the evidence labels.**
- **[Pattern]** seen independently in two or more sources.
- **[Single]** one forum post, comment or blog. Treat it as a hint, not a finding.
- **[Official]** a company's own page or a regulator's document.
- **[Vendor]** a company describing its own product. It shows what they believe schools want, not proof that schools want it.
- Sources are numbered S1 to S27 in 11.12. I fetched S1 to S23 myself. S24 to S27 I could only see as excerpts returned by the search tool, because the pages were blocked to my fetcher. They are marked low confidence.

**What I could not get (said plainly).**
- Reddit pages (r/3Dprinting, r/functionalprint, r/teachers, r/makerspaces) returned "blocked by network security" when I fetched them, so I have **no direct r/teachers, r/makerspaces or r/functionalprint evidence**. Teacher voices below come from blogs, help pages and vendor pages, which are weaker.
- The Printables contest page and the Cults3D FAQ and policy page were blocked by bot checks.
- I did not find an ISTE page I could fetch and read. I did not use ISTE.
- Most sources are English-language and hobby-platform-heavy. The mix leans toward vocal complainers, since people post when annoyed. The Hansei section (12) returns to this.

### 11.1 Reliability, outages and cloud dependence

**What people say**
- **[Pattern]** Bambu Lab's cloud and MakerWorld have had visible outages. On 2025-10-28 a forum thread filled up with users in the US, Canada, UK, Netherlands and Switzerland reporting MakerWorld and cloud printing down. One wrote that it was "a good time as any to learn how to use my SD card"; another said "this is why the cloud system is idiotic" (S1). A third-party Bambu site describes two MQTT outages on 2026-07-20 that blocked print starts for about two hours, an AWS-related disruption on 2026-07-24, and shorter timeouts on 2026-09-27. Per that site, Bambu's post-mortem blamed one faulty node and promised multi-region deployment (S2). Those S2 dates and durations are relayed from Bambu's status page by a third party that says it did not reproduce them.
- Prints already running kept going; only starting new jobs failed (S2). That is a useful design lesson: keep the critical path short.
- S2 also recounts a 2023 Bambu incident where, after recovery, queued commands fired on their own and some idle printers started unattended prints. It is secondhand, but it matters for ZEIM if we ever "send to printer" from a queue.
- **[Single, low confidence]** Thingiverse had an outage on 2025-01-09. One commenter said the site "is down once every month or two"; another quoted a claim of "bad infrastructure choices" with a temporary fix (S24, excerpt only). A blog calls Thingiverse "notoriously slow and prone to errors", with upload failures (S10, [Single] opinion).
- **[Official]** Printables' terms say the service may not always be available and is not a data store: "PRINTABLES does not serve as data storage" (S7, terms dated 2022).

**Recommendation: ADAPT.** Publish a simple public status page, write a short plain-language post-mortem after any incident, and make the server-down path survivable: a user should still be able to download a file they already built. Never let a queued job reach a physical printer automatically after an outage; require a human confirm. *Owner: Ops (status page, post-mortems, read-only mode runbook); Engineering (confirm-before-send, downloads independent of heavy jobs).*

### 11.2 Account lock-in and vendor control

**What people say**
- **[Pattern]** Closed or semi-closed ecosystems provoke strong reactions. In January 2025 Bambu announced an authorization firmware change. Third-party tools lost direct access unless routed through Bambu Connect, and Ars Technica reported strong pushback (S3). Bambu's own follow-up said misinformation was circulating and conceded "our communication might have contributed to the confusion". It then added an optional Developer Mode and said users could stay on older firmware (S4). Bambu also told The Verge it would never put printer functions behind a subscription and would always allow firmware rollback, per S3.
- Bambu's stated reason included load and abuse: "peaks of up to 30 million unauthorized requests per day" (S3, quoting Bambu). Public services attract automated traffic; we should plan rate limits early (this matches section 2.1 #7).
- **[Single]** A MakerWorld user wrote of losing downloads when models get deleted elsewhere, and: "If you lose the net, and want to print something, too bad???" (S8).
- **[Official]** Printables' terms say content may be damaged or deleted without liability, and that Free Licences are irrevocable after publication (S7).

**Recommendation: ADOPT.** Make "your files are yours" a tested feature, not just a sentence in the one-pager: one-click download of everything (originals, meshes, G-code, project settings) in open formats, plus plain-language data-retention text. Say what happens to class work when a teacher leaves (see 11.5). *Owner: Engineering (export-all), Design (wording), Ops (retention text with Trust & Safety).*

### 11.3 Model import/export and file formats

**What people say**
- **[Pattern]** Format friction is real and was acknowledged by platforms. MakerWorld added automatic STL generation from 3MF print profiles "addressing community feedback", initially for new uploads only (S9). A user in the same thread worried auto-generated profiles could mislead, citing a model that detached from the bed (S9, [Single]). In S8 a logged-in user reported that neither the STL nor the 3MF download button did anything after a number of downloads, which looked like a per-account limit ([Single]).
- **[Official]** PrusaSlicer's own first-print guide warns that opening a 3MF can bring its own printer, filament and print settings and replace the user's (S22). PrusaSlicer imports 3MF, STL, OBJ, STEP and SVG (S22). Printables lists STL, 3MF, OBJ and AMF as accepted 3D formats (S7).
- **[Single]** One commentary lists weak 3MF support as a Thingiverse shortcoming (S10).
- **[Single]** A Shapr3D forum user says the free-plan export is so coarse "I can sadly count the triangles" when opening it in a slicer (S12).

**Recommendation: ADOPT** for "offer STL and 3MF, never a degraded export"; **ADAPT** for "tell people when a 3MF carries its own settings". Photo-to-print outputs should be full resolution for everyone. *Owner: Engineering (formats), Design (small notice text).*

### 11.4 Moderation and reporting speed

**What people say**
- **[Official + Single]** On Printables a community manager replied to a user about fake accounts: "we are catching and banning fake accounts like these, but sometimes it can take a couple of days", called it "a bit of a cat-and-mouse situation", and asked users to use the report function (S6, Oct 2025). A Report button or an email address is the official channel (S7).
- **[Pattern]** Complaints about low-quality or fake uploads appear in more than one place: spam accounts and AI renders on Printables (S6, one user's opinion), and AI-generated models slipping past a "no AI" tag on Cults3D because uploaders simply do not tag them (S26, excerpt only, [Single]).
- **[Official]** Thingiverse says AI is used only to flag firearm designs and "a human will always be the one to decide if something should be removed" (S11).
- **[Single, low confidence]** Anonymous user reports about Thingiverse describe accounts put under moderation without explanation and unanswered support email (S27, excerpt only). I could not verify them.

**Recommendation: ADAPT.** Take the shape: a report button on every shared item, a published target response time, automated flags with a human making the final call, and clear messages to the person affected. Keep everything private by default and keep Build Plates closed until moderators and tooling exist (as in section 5, Phase 3). Target times and staffing are for Trust & Safety to set; I have not estimated moderator cost (see 12). *Owner: Trust & Safety (policy, targets, reviewers); Engineering (report button, queue); Ops (staffing plan after pilot data).*

### 11.5 Child safety and privacy for school use

**What people say**
- **[Official]** Tinkercad's classroom model is the closest comparison. Teachers create a class; students join with a class code and a teacher-set nickname and no email or account; Safe Mode is on by default (designs private, no gallery search, no comments); the teacher can edit and delete student work (S14, S15, S16). Autodesk's children's statement (effective April 2026) says no personal data is collected from a student merely by joining a classroom, describes a kidSAFE COPPA certification, says it acts as a FERPA "school official", and says children's data is deleted or de-identified after 24 months of inactivity (S16).
- **[Official]** Autodesk says "one of the biggest hurdles to using Tinkercad with their students is simply getting everyone logged in. Email verification, lost passwords, confusion over sign-in options" (S15). That is the reason for nickname seats.
- **[Official, dated 2021]** An older help page said student data in a class seat is "owned by the teacher" and deleting the teacher account permanently deletes the classes (S14). The newer guide says a "graduate" process now exists (S15), but I did not open that process page. The lesson: define now what happens when a teacher leaves, and tell them up front.
- **[Official]** The U.S. FTC's amended COPPA Rule took effect 2025-06-23 and its general compliance date was 2026-04-22 (already passed). The FTC did not finalize its proposed ed-tech and school-authorization provisions, citing a possible conflict with FERPA changes (S17). For services that age-screen visitors, the definition requires age information to be collected "in a neutral manner that does not default to a set age or encourage visitors to falsify age information" (S17, proposed wording that the FTC adopted with an added clarification). The Rule's definition of personal information also now lists biometric identifiers such as "facial templates" and "faceprints" (S17). That is relevant to photo upload features, which counsel should assess. This is not legal advice, and I did not inspect how ZEIM handles photos.

**Recommendation: ADOPT** nickname class seats, Safe-Mode-style defaults, teacher-controlled deletion and a short teacher-facing "what we collect" page. **ADAPT** the age screen (ours is a self-declared date of birth; Kenji should check it against the neutral-screening language). *Owner: Trust & Safety (policy, counsel), Education (teacher wording), Engineering (defaults and deletion), Ops (sub-processor list).*

### 11.6 Onboarding and first-print friction

**What people say**
- **[Pattern]** Teachers and school IT say the first prints fail for mundane reasons. A 2025 teacher blog says one of her biggest mistakes was not giving students enough practice time before printing, that a pre-print checklist "improved the quality" and reduced "spaghetti" failures, and that she slices files herself and limits prints to 8 hours so she can supervise (S18). A school IT knowledge base says printers "require significant technical knowledge and regular maintenance" that the school must provide (S20, undated). A 2015 Edutopia piece says to attend prints, combine small parts into one job, and settle how students submit and how work is approved (S19, dated but consistent). A vendor blog notes that, on shared school printers, bed-level drift is common and students often blame the design (S21, [Vendor], July 2025).
- **[Official]** PrusaSlicer's guide for a first print says to use a standard profile (0.15 or 0.20 mm), that defaults are "fine" for a first print, and to check the first layer in preview before starting (S22).

**Recommendation: ADAPT.** Give every first print a one-page preflight (printer ready, first layer check, print time shown, size warning) and a "my print failed" flow that helps tell design problems from printer problems. Show print time clearly before send, and warn above a teacher-set limit (such as 8 hours). *Owner: Education (checklist and lessons), Design (flow), Engineering (time estimate, warnings).*

### 11.7 School print workflow: review, queue and quotas

**What people say**
- **[Vendor]** SimplyPrint (a paid print-management product) sells a "print approval workflow": students submit, a teacher approves, denies with a reason, or sends back; it also shows print time, material and cost and offers quotas. Its own example is catching "the 14-hour print, the wrong material, or the model that was never going to come off the bed" (S23). This is a vendor page, so it shows what one company believes teachers need.
- **[Single]** The teacher in S18 and the author of S19 both describe a manual version of the same idea.

**Recommendation: ADAPT**, small. A teacher "review before download or send" step for class projects, with a visible comment and a reason when a project is sent back. Do not build quotas or accounting now. *Owner: Education (requirement), Engineering (if it fits), Design.*

### 11.8 Cost and pricing surprises

**What people say**
- **[Pattern within one thread]** In a Shapr3D forum thread (Dec 2025 to Jul 2026), several users say the pricing leaves hobbyists out (one quotes about €362 a year with tax, S12), that the free tier "feels more like a Demo", and that novices start on free tools such as Tinkercad (S12). Shapr3D's help page says every modeling tool is free but high-quality export and unlimited projects are paid, and that students and educators get free Pro access (S13).
- **[Single, low confidence]** Cults3D sellers report payout friction and a fee they say rose to about 35% after a payment-provider fee; the commenters' numbers are unverified and the page was excerpt-only (S25).
- **[Official]** MakerWorld introduced a limit of 5 downloads for anonymous users to encourage sign-up (S9). A user who was logged in said downloads stopped after fewer than 10, and a MakerWorld responder asked for the username and suggested a CAPTCHA pop-up had failed (S8, [Single]).

**Recommendation: ADOPT** transparency: a "what is free and why there are limits" page that states file-size, storage and job limits and explains that they exist to keep the service running. **REJECT** any approach where the free tier produces deliberately degraded files. ZEIM has no paid content (by design), so marketplace-style fees are out of scope. *Owner: Ops (limits page), Design (wording), Engineering (quota messages).*

### 11.9 Community growth tactics

**What people say**
- **[Pattern]** Reward systems drive growth but also gaming. Printables runs design contests and a points scheme (S7). The Printables forum has complaints about unclear judging criteria, no feedback from judges, bias toward accounts with large followings and disqualification without explanation (S5, a 2023 post plus later replies). One veteran forum user says the site's gamification pushed quantity over quality, and the same user repeats it in 2025 (S5, S6; partly one voice). The Printables terms prohibit duplicate uploads and artificial inflation of likes (S7). MakerWorld pays points based on downloads, and users in the thread discuss how counts are calculated (S9).
- **[Single]** A Printables poster says MakerWorld "has introduced a mandatory real picture of the printed model" to reduce fakes (S6). I did not verify that, so I am not relying on it.
- **[Single]** The Shapr3D thread (S12) argues that a clear path from free beginner tools to bigger tools earns loyalty; one user says they teach novices on Tinkercad first.
- Teachers' groups value showing work: S18 recommends celebrating prints in newsletters and sharing pictures with families.

**Recommendation: ADAPT** small, teacher-led seasonal challenges with a written scoring rubric and feedback to every entrant, showcased in a family-friendly way. **REJECT** points for download counts, follower-weighted rankings and prizes tied to quantity. If we ever ask for photo proof of a print, tell people to crop out faces and strip metadata first. *Owner: Education + Ops (challenges), Trust & Safety (photo rules), Design.*

### 11.10 Top 5 for ZEIM now

1. **Make "your files are yours" real**: export-all in open formats, plus a plain data-retention statement (11.2, 11.3). Owner: Engineering + Ops.
2. **Status page, post-mortem habit and read-only mode**, and no auto-send of queued jobs to a printer after a restart (11.1). Owner: Ops + Engineering.
3. **Classroom-first privacy defaults**: nickname seats, private by default, teacher-controlled deletion, a stable class link (not only a code to re-type), and a counsel check of the age screen (11.5). Owner: Trust & Safety + Education.
4. **Report button with a published response target before anything is public** (11.4). Start the pilot with adults and teachers only. Owner: Trust & Safety + Ops.
5. **First-print preflight and visible limits**: one-page checklist, print-time warning, and a "what is free and why" page (11.6, 11.8). Owner: Education + Design + Ops.

**Idea to try cheaply, not to commit yet:** a teacher review step for class projects (11.7). It needs a short conversation with real teachers first.

### 11.11 Things I would challenge (questioning welcome)

About **Mr. Yami Kato's principles**:
- **Melting-pot research is a start, not proof.** Public posts over-represent people who are annoyed and under-represent quiet satisfied users and non-English speakers. Two of my sources are vendors, some are old (S5 from 2023, S7 terms from 2022, S19 from 2015, S14 from 2021), and I could not read Reddit at all. I suggest we treat these as hypotheses and talk to **five to ten real teachers or club leaders** before building any of them.
- **Nemawashi among department heads only** risks an echo chamber. Please add outside voices (teachers, a parent, a library or club lead) to the consultation step, with Kenji deciding what we can ask of children and of schools.
- **"Hansei after each deliverable"** is good. I suggest a short dated log file so lessons carry over, instead of living in each report.

About **my own plan above**:
- **Auth for "adults and teens" (section 2.1 #1)** should say explicitly that students in a class never need an email address, because login friction is the main complaint in S15.
- **Retention (section 2.2 #6)** proposes purging inactive anonymous data after 30 days. School terms have long breaks, so work could vanish over a summer. Align retention to the school calendar, with counsel.
- **Section 8 claims "your files are never locked in".** I have not tested every export path in the app. Until Engineering confirms export-all, soften that line or mark it as a goal.
- **"Build Plates"** is the group name. In slicer vocabulary a build plate is the physical print bed, and in S1 a user uses the phrase for plates inside a slicer project. This may confuse search and support. This is my inference, not a finding; a quick test with five teachers would answer it.
- **Budget (section 3)** lists one VPS but section 2.2 #7 asks for a staging environment. The $40 to $80 range may not include staging. Worth checking.

### 11.12 Sources (fetched and read 2026-10-04 unless noted)

Fetched and read in full or in the relevant part:
- S1 Bambu Lab forum, "MakerWorld down on EU right now" (2025-10-28): https://forum.bambulab.com/t/makerworld-down-on-eu-right-now/204279
- S2 BambuHub, "Bambu Cloud Down? How to Keep Printing Anyway" (third-party site, updated 2026-10-02): https://bambuhub.net/articles/bambu-cloud-down
- S3 Ars Technica, Bambu authorization control article (2025-01-21): https://arstechnica.com/gadgets/2025/01/bambu-lab-pushes-a-control-system-for-3d-printers-and-boy-did-it-not-go-well/
- S4 Bambu Lab blog, "Updates and Third-Party Integration with Bambu Connect" (2025-01-20): https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect/
- S5 Prusa forum, "Dear printables. We need to talk about design contests" (2023, replies to 2024): https://forum.prusa3d.com/forum/english-forum-general-discussion-announcements-and-releases/dear-printables-we-need-to-talk-about-design-contests/
- S6 Prusa forum, thread on accounts without print photos (Oct to Nov 2025): https://forum.prusa3d.com/forum/general-discussion-user-experience-ideas/is-there-any-way-to-ban-all-accounts-that-dont-have-at-least-a-single-actual-printout-photo-proof/
- S7 Printables Terms of Service (version dated 2022-08-01): https://www.prusa3d.com/page/terms-of-service-of-printables-com_231249/
- S8 Bambu Lab forum, "Can't download files" (MakerWorld, Sept to Oct 2024): https://forum.bambulab.com/t/cant-download-files/96364
- S9 MakerWorld Release Note 0724 (2024-07-25): https://forum.bambulab.com/t/makerworld-release-note-0724/89536
- S10 3D Printed, "Is Thingiverse Dead?" (2025-07-26, commentary): https://www.3d-printed.org/is-thingiverse-dead/
- S11 Tom's Hardware, Thingiverse AI firearm detection (2025-07-26): https://www.tomshardware.com/3d-printing/3d-printing-companies-turn-to-ai-to-block-production-of-ghost-guns-we-spoke-with-thingiverse-about-its-new-ai-driven-ghost-gun-detection-strategy
- S12 Shapr3D community, "Cheaper subscription for non professional users" (2025-12 to 2026-07): https://discourse.shapr3d.com/t/cheaper-subscription-for-non-professional-users-home-users/40034
- S13 Shapr3D Help Center, subscription plans (updated 2026-05-05): https://support.shapr3d.com/hc/en-us/articles/7871961422364-Shapr3D-subscription-plans
- S14 TSI Support, "How to use Tinkercad Classrooms" (page dated 2021-02-22): https://help.mytsi.org/v2/knowledge-base/how-to-use-tinkercad-classrooms/
- S15 Autodesk, Official Guide to Tinkercad Classrooms (PDF, undated): https://images.tinkercad.com/jl5ii4oqrdmc/5v197WuuaqspGT81cG5tT6/81154785a527f1b42a32325487a30e44/tinkercad-guides_classrooms-Printable.pdf
- S16 Autodesk Children's Privacy Statement (effective April 2026): https://www.autodesk.com/company/legal-notices-trademarks/privacy-statement/childrens-privacy-statement
- S17 U.S. Federal Register, FTC COPPA Rule amendments (2025-04-22): https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule
- S18 Enhancing Enrichment, "10 Tips for Using a 3D Printer with Elementary Students" (2025-01-06, one teacher's blog): https://enhancingenrichment.com/2025/01/06/10-tips-for-using-a-3d-printer-with-elementary-students/
- S19 Edutopia, "Year One With a 3D Printer: 17 Tips" (2015-06-29, dated): https://www.edutopia.org/blog/year-one-with-3d-printer-vicki-davis
- S20 K12 school IT knowledge base, "3D Printers" (undated): https://www.k12mt.com/kb/3d-printers
- S21 SelfCAD blog, bed-leveling problems in schools (2025-07-28, vendor): https://www.selfcad.com/blog/3d-printer-bed-leveling-problems-in-schools-causes-and-fixes
- S22 Prusa Knowledge Base, "First print with PrusaSlicer (3.0.0)": https://help.prusa3d.com/article/first-print-with-prusaslicer-3-0-0_1079761
- S23 SimplyPrint, print approval workflow (vendor): https://simplyprint.io/features/print-queue/approval

Seen only as search-tool excerpts (direct fetch blocked), low confidence:
- S24 r/thingiverse, "Thingiverse currently down (9/1/25)" (2025-01-09): https://www.reddit.com/r/thingiverse/comments/1hx0xsg/thingiverse_currently_down_9125/
- S25 r/cults3d, "Will the hyperwallet suck up revenue from creators?" (2025-12 to 2026-01): https://www.reddit.com/r/cults3d/comments/1phdkxp/will_the_hyperwallet_suck_up_revenue_from_creators/
- S26 r/cults3d, "AI moderation" (Oct 2025): https://www.reddit.com/r/cults3d/comments/1oa8s52/ai_moderation/
- S27 Outagedown, Thingiverse user reports (anonymous): https://outagedown.com/web/thingiverse.com

---

## 12. Hansei (honest reflection on this report)

**What is weakest or unverified in sections 1 to 10**
- **Hosting prices.** Hetzner figures came from third-party trackers that disagree. DigitalOcean, Fly.io and Backblaze figures were read from their pages on one day and can change. Option D (Render, Railway) was not priced at all.
- **Traffic and users are guesses.** The 50 to 500 monthly active users and the "handful of simultaneous jobs" are assumptions I labelled but did not test.
- **No load test and no performance inspection.** I described the app from its structure (single process, JSON files, subprocess slicing) but never ran it under load or profiled it. The "at least 2 vCPU and 4 GB" sizing is a reasoned guess, not a measurement.
- **Moderation cost is not estimated.** I said moderator time and legal review are probably the biggest costs, but I gave no hours or range. I have no data yet, and this research did not supply any.
- **Budget gaps.** The $40 to $80 range probably leaves out a staging environment, and may under-count monitoring, email and a restore drill.
- **Phase durations** (weeks per phase) are guesses without named owners or Engineering sign-off.
- **No availability target.** I did not define an uptime goal or consider school hours. For classrooms, an outage during a lesson is costlier than one at night. That is my inference, not a measured fact.
- **Research limits (this section).** I could not read Reddit, so there is no direct r/teachers, r/makerspaces or r/functionalprint evidence. Several sources are vendors or old. Everything is English. Several findings are single posts. I labelled these, but the overall picture still leans on vocal complainers.

**What I would change next time**
- Measure before recommending: run a one-hour test on a throwaway VPS with a few concurrent slicing and editing jobs, then size the server from the result.
- Get real quotes and re-read the pricing pages on the day of the decision.
- Talk to five to ten teachers and club leaders before writing recommendations about them, and ask Kenji what we may ask and how.
- Put moderation first in the cost model, using time-per-report and reports-per-100-users measured in the pilot instead of guessing.
- Keep a decision log (what, why, who agreed, date).

**Next small Kaizen steps** (each can be checked)
1. Put the project in a private git repo and record the starting commit. *Done when `git log` shows it. Owner: Ops.*
2. Run the throwaway-VPS load test and write the results (CPU, RAM, queue time) as a half-page note. *Owner: Ren Okabe with Engineering.*
3. Re-check Hetzner prices on the live provider page and replace the third-party numbers in section 3. *Owner: Ops.*
4. Add a staging line and a monitoring/email line to the budget. *Owner: Ops.*
5. Draft a one-page public "limits and data promise" page for Kenji and Education to review. *Owner: Ops with Design.*
6. Book short calls with five teachers or club leaders and ask about login, first print, and what they would need from us to try a pilot. *Owner: Education (Zach to approve who we contact).*
7. Ask Haruto Tanaka to confirm which export formats and "send to printer" paths exist today before we repeat the "never locked in" line. *Owner: Ops asks, Engineering answers.*

*Hansei on this Hansei:* I added the research without being able to touch app code or user data, which is the right boundary, but it also means these recommendations are untested against what ZEIM actually does. I would rather say that than guess.
