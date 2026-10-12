# ZEIM Education & Community Report

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


**Author:** Aiko Nakamura, Head of Education & Community · **Date:** 2026-10-04 (CT) · **Status:** DRAFT for Zach / Mr. Yami Kato / Haruto Tanaka
**Scope:** `/workspace/photo3d` (read-only review; Education did not edit app code). Companion files: `education-change-requests.md` (section 6 below, saved separately) and `education-lessons-draft.json` (draft lessons in the app's `LESSONS` schema).

> **Tone and honesty note.** ZEIM is young and many parts are scaffolds. Nothing here says ZEIM is better than any other tool; the research section is about what we can *learn* from others. I read the code and ran three read-only `GET` requests against the running server (`/api/config`, `/api/settings`, `/l/lithophanes`, `/api/showcase?tab=trending`). I did **not** drive the UI in a browser, did not run the test-suite, and have **not** tested any lesson with a teacher or a child. Treat the lessons as drafts that need a teacher's eyes.

## 0. Summary

**What is already thoughtful** (so we protect it): private-by-default visibility enforced server-side with 404 on denial (`app/community/privacy.py`); classroom students need no account or personal data and join with code + teacher password + nickname, with scrypt-hashed passwords and a wrong-guess limiter (`classrooms.py`); class projects never leave the class; student↔teacher messages are canned-only; a PG-13 language filter plus contact-info blocking runs on every free-text field (`safety.py`); `minor_safety` reports hide an item immediately; no dislikes anywhere; the Trending formula is documented and uses log-damping and decay; teen defaults are safer; muted-text contrast is fine (computed ≈ 6.4:1).

**Top findings (details in §2):**
1. **P0 — `/api/settings` is unauthenticated** (`app/api/settings.py`): any visitor, including a student, can change printers and `public_base_url`; the latter feeds the teacher's join-QR and slicer links, and a saved printer can be targeted by `/api/send`. Fine on one person's laptop, not on a shared school server.
2. **P0 — student photos:** raw uploaded bytes (EXIF intact) are stored as `outputs/<id>/source.<ext>` (`app/api/builds.py` ~208-210) and are **not** deleted when a student is removed or a class is deleted, although the README says class data is erased.
3. **P0 — class students can use the public Showcase** (browse, like, download strangers' content); only Spark Lab is "safe by construction".
4. **P0 — locked-out students:** identity is the browser cookie; a cleared cookie / different Chromebook means the nickname is "taken" and progress is lost; no seat reset.
5. **P0/P1 — no photo-consent step** at upload; and the lithophane lesson says "a pet or a face".
6. **P1 — UI built on `prompt()`/`confirm()`** (report reason typed as a code word, "type a number" to pick a build), a lesson panel that re-renders and scrolls on every tick, and almost no ARIA.
7. **P1 — likes / Trending for minors:** anonymous likes with public counts, invented counts on example items, teens may publish Public.
8. **Content gap:** three lessons only, one-question quizzes, no worksheets, no teacher-only prep/safety section, no print-queue workflow — and the teachers I found in public sources say the workflow around printers is the hard part, not groups.

**The five new lessons** (§3): (1) **Start here: Glow Card** (lithophane, ages 9+, teacher-led for 5-8); (2) **Height Detectives** (K-2, tactile relief); (3) **Name Tag Engineers** (grades 3-5, measuring in mm, Edit tools); (4) **Layer Cake Posters** (grades 6-8, pop-art layers + kind critique); (5) **Fit Check** (grades 9-12, measure/tolerance/redesign).

**Build Plates headline** (§4): *private-by-default, adult-moderated, school-linked groups first; no DMs; public hobby groups for adults come later.* MVP is a **Class Build Plate** (a teacher-owned shared board tied to an existing classroom) and a **Club Build Plate** (adult-run, invite-only), both with pre-moderated posts and canned reactions.

## 1. Questions about the brief (better ways I see — please challenge me)

1. **Is "Build Plates" the right next thing?** The brief asks for a groups spec, and I wrote one. But the public evidence (§5) suggests the pain for teachers is the *print workflow* (submit → review → approve → queue → print → get it back), and our own P0 list is about safety basics. I recommend **Engineering order: CR-1…CR-5 → CR-11 → class print queue (CR-13) → Class Build Plates**, not groups first.
2. **Mixing minors and hobbyist adults in one groups system is the highest-risk design choice we have.** I'd start with *school and club* plates only (adults who are known to a teacher or organiser), and keep adult-hobbyist plates separate until we have real accounts, age assurance beyond a self-declared date of birth, and human moderation capacity. The brief says "hobbyist groups"; I've specified them but marked them *later*.
3. **"Showcase / Trending / Likes for kids":** I'd question whether kids' work should ever enter popularity ranking. Better candidates: a *class-private gallery*, *teacher picks*, and challenges judged on stated criteria, not counts (CR-3, CR-10).
4. **"Lithophane as first project":** agreed, with one change — make the first lesson **design + predict + preview**, with printing as a teacher-run follow-up, because a print can take longer than a class period and printers are shared. A student should be able to finish the *learning* without waiting for plastic.
5. **"Five outlines":** I'd rather ship two or three polished lessons with teacher guide and tested timing than five untested ones. I wrote five as asked, but ranked them: lessons 1 and 4 can run on today's app; lessons 3 and 5 depend on Edit being reachable from Spark Lab (CR-8); lesson 2 needs a teacher-led setup.
6. **"Create your own specialist bot"** (in Mr. Kato's welcome message) — I have no tool to create agents, so this is **not done**; the parent agent/user would need to do it.

## 2. Review findings

Legend: **P0** fix before any real-class pilot · **P1** before wider pilot · **P2** next · ✅ exists · ◑ partial · ✗ missing. "CR-n" = change request in §6.

### 2.1 Spark Lab lessons (`app/community/education.py`, `app/api/learn.py`, `static/community.js`)
| Area | Status | Evidence / note | Pri |
|---|---|---|---|
| Lesson set | ◑ | 3 lessons: `first-print` (8+, 20 min), `intro-modeling` (9+, 25 min), `lithophanes` (8+, 25 min). Each has objective, steps, one quiz question, a "try" button, `teacher_notes`. | P2 |
| Clarity / reading level | ◑ | Short imperative steps; good analogies ("stacking thin sheets of paper"). No reading-level target, no pictures/diagrams, no glossary (slicer, G-code, layer). | P2 |
| Safety content | ◑ | `first-print` covers hot nozzle/bed, sleeves/hair, grown-up nearby; lithophane says LED only. Missing: who operates the printer, ventilation/placement, not opening the enclosure, cooling before removal, no student blades. Authoritative school guidance exists (§5 [WA DOH]). | **P1** (CR-8) |
| Photo/consent guidance | ✗ | `intro-modeling` teacher note says "no faces of others without permission", but the **lithophane** lesson step 2 recommends "a pet or a face"; no consent checkbox at upload (`index.html` ~272 is publish-only). | **P0/P1** (CR-5, CR-8) |
| Accuracy of teacher notes | ◑ | Lithophane note "2.4-4 mm lithophanes prints in about 1-2 hours" matches no preset (`autotune.py`: thin 0.6-2.4, standard 0.8-3.2, thick 1.0-4.0 mm) and I could not verify the time; community guides say slower speeds and finer layers lengthen prints (§5). | P1 (CR-8) |
| Pacing | ◑ | `minutes` per lesson, but print time is not part of the plan; no "what to do while waiting" step; `first-print` depends on a pre-sliced model. | P2 |
| Assessment | ◑ | One multiple-choice question per lesson, unlimited retries, no explanation on a wrong answer, answer index kept server-side (good). Completion = all steps ticked + quiz right (`_maybe_complete`). | P2 (CR-14) |
| Differentiation | ✗ | `age` field is a string like "8+"; no grade band, no teacher-led vs independent flag, no extension/support. | P2 (CR-8) |
| Teacher support | ◑ | `objective`, `teacher_notes` exist; teacher notes are rendered for **students** too (`<details>` in `openLesson`); no printable guide, no rubric, no worksheet. | P2 |
| Shareable lesson page | ✅ | `/l/<id>` server-rendered, no login, escapes HTML. | — |
| Lesson UI behaviour | ◑ | `openLesson()` re-renders the whole panel and calls `scrollIntoView` on every checkbox tick and after a correct quiz; focus is lost (`community.js`). | **P1** (CR-7) |
| Spark Lab "Try it" | ◑ | `try` only supports Studio modes; Edit-based lessons cannot deep-link. | P2 (CR-8) |
| Badges | ✅ | Emoji badges at completion; low-pressure, no leaderboard. Good. | — |

### 2.2 Classroom flow (`app/community/classrooms.py`, `safety.py`, `static/community.js`)
| Step | Status | Note | Pri |
|---|---|---|---|
| Teacher creates class | ✅ | Adult account only; password 4-40 chars; 6-char code from an unambiguous alphabet; QR encodes link only (never password). | — |
| Teacher identity | ◑ | Adult = self-declared DOB, cookie-bound, no password (`identity.py`). Clearing browser data loses the teacher account and its classes. | P2 (CR-15) |
| Student join | ✅ | Code + password + nickname (2-20 chars, filtered), no PII, 60-student cap, 5 wrong tries / 10 min. | — |
| Student re-join | ✗ | A nickname already used in the class is refused; a cleared cookie or another device strands the student; shared computers can merge students. | **P0** (CR-4) |
| Assign lessons | ✅ | Per class; stars on assigned lessons. No due dates. | P2 |
| Progress view | ◑ | Counts per student per lesson (✅ or n/total). No "stuck" sort, no export. A student's `need_help` request appears only as a plain notification. | P2 (CR-13) |
| Submit work | ◑ | Student submits a build snapshot (STL/3MF/thumb) to the class; picking the build is a `prompt("Type a number")`. | P1 (CR-6) |
| Teacher feedback | ◑ | Text only, 500 chars, language-filtered, no scores (good); entered with `prompt()`; student can report a feedback comment via API but the UI path is thin. | P1 (CR-6) |
| Student↔teacher messages | ✅ | Four canned requests; muted students can't send. Good, low-risk, and very simple for young children. | — |
| Moderation inside class | ◑ | Teacher can mute/remove; no teacher view of reports. Students cannot report a classmate's project (only teacher feedback). | P1 (CR-6, CR-11) |
| Printing in class | ✗ | Any session can reach Print → Send (`/api/send`) if a printer is saved; no teacher approval, no queue, no filament/time info. | **P0** (CR-1) / P2 (CR-13) |
| Data erasure | ◑ | Class delete erases progress + class projects, **not** students' builds/photos in `outputs/`. | **P0** (CR-2) |
| Student photos | ◑ | Stored unmodified incl. EXIF; extension taken from client filename (4 chars). Thumbs of class projects are private to class (good). | **P0** (CR-2) |
| Showcase from class | ✗ | Nothing prevents a class session from browsing/liking public Showcase. | **P0** (CR-3) |
| Legal | ✗ | COPPA/FERPA review not done (README says so). Context: the FTC's amended COPPA Rule had a compliance date of **April 22, 2026** and did **not** finalise the proposed school-authorisation provisions [Fed. Reg.] — so schools' consent arrangements stay governed by existing guidance. Needs counsel, not us. | decision |

### 2.3 Showcase / Trending / Likes (`app/community/catalog.py`, `app/api/community.py`)
| Topic | Status | Note | Pri |
|---|---|---|---|
| Visibility | ✅ | Private default; public items only in Trending; 404-on-deny; items from private owners never counted. | — |
| Likes mechanics | ◑ | One per session, toggle, no dislike, can't like own, public only. But **no account required** and no rate limit: counts are cheap to inflate by clearing cookies (README admits this). | P1 (CR-10) |
| Counts shown | ◑ | ♥ and ⬇ shown on every card. For kids this invites comparison; we have not decided a policy for minors. | P1 (CR-10) |
| Example data | ◑ | Seed items are labelled EXAMPLE, but show invented counts (e.g. 1,500 downloads) that also drive Trending order; may mislead teachers about "real" community size. | P1 (CR-10) |
| Trending formula | ✅ | Documented: `ln(1 + 3·likes + downloads) × (0.15 + 0.85·0.5^(age/21))`; popularity-biased by nature, damped by log and decay. | — |
| Teen publishing | ◑ | Teens default Private but may choose Public per project (README: "open decision"). A thumbnail of a lithophane is a recognisable image of the source photo. | P1 (CR-10) |
| Reporting | ◑ | Reasons exist; UI is `prompt()` with code words; no dedupe or rate limit; any visitor can trigger `minor_safety` auto-hide of any public item (fail-safe, but griefable). | P1 (CR-6, CR-11) |
| Moderation queue | ◑ | API-only, admin-token header; no UI, no reviewer, no SLA, no audit log (README says stub). | P1 (CR-11) |
| Search/personalisation | ◑ | Searches stored per session in `data/prefs.json` (viewable, disable, clear). Default **on**. For classroom sessions we would prefer off. | P2 |
| Public pages | ◑ | `/p/` and `/u/` have no `noindex`. | P1 (CR-9) |
| Following | ◑ | Opt-out works; scaffold only. Fine. | — |
| Guidelines | ◑ | Draft; includes photos-of-others and "moving young users to private channels" (good). Not legally reviewed. | decision |

### 2.4 Accessibility, inclusion, and tone
- ✅ `lang="en"`, labelled form fields in the Studio, visible focus outlines on inputs, good text contrast (computed).
- ◑ Only one `aria-` attribute in `index.html`, none in `community.js`; toasts and progress are not announced; emoji-only buttons; canvas viewer without text alternative; `prompt()` dialogs; small buttons. I have **not** run axe/Lighthouse or tested with a screen reader (CR-12).
- ✗ No localisation, no read-aloud/simplified text mode, no printable/offline lesson (ROADMAP lists these).
- ✅ Tactile relief is a natural inclusion path (lesson 2).
- Tone: copy is friendly and humble; "ZEIM is young and still growing" is good. Keep it.

## 3. Five new lesson outlines

Draft lessons in app format: `reports/education-lessons-draft.json`. All are **drafts**: untested with children, timings are estimates, and print times depend on your printer.

### 3.0 Shared guidance used by every lesson

**Photo guidance (consent, privacy, school-safe).** Offer these in this order:
1. *Best:* a **school-safe image pack** supplied by the teacher (originals, public-domain, or openly licensed with attribution): pets, plants, landscapes, objects, artwork.
2. A **student's own drawing or object photo**.
3. A **student's own photo of a pet/place/object** taken for the class.
4. **People:** under-13 students: **no photos of people at all** in this lesson series. Ages 13+: only yourself, or someone who said yes *and* (for school use) a teacher approved. Never a photo of another child unless the teacher holds the school's/guardian's permission. This is a classroom norm, not legal advice; check your school's photo policy.
5. **Never include:** home address, school name/logo, street signs or license plates, uniforms with names, anything that shows where someone lives or is at a given time. Tell students that photos from phones can carry location data; ZEIM should remove it on upload (CR-2) but students should not rely on that.
6. **Tell students:** "A lithophane is a recognisable picture. If it would be awkward on a classroom shelf for everyone to see, choose a different photo."

**Safety baseline for printing days** (teacher/adult-operated printer; see §5 for sources): printer placed away from desks, near a fire extinguisher, in a ventilated space — PLA preferred; students don't stand over a running printer, don't touch the nozzle/bed/motors, don't open an enclosure mid-print; wait for the part to cool (and for an enclosure to be left shut ~20 minutes after the print per the WA DOH page) before removal; no scrapers/blades for students; wash hands after; use LED tea-lights, never hot bulbs, behind lithophanes. Your school's own safety officer's rules win over this page.

**Alignment hints (no exact codes on purpose).** I'm not citing specific standard codes because I haven't verified them against your state's version. Look for: *NGSS Engineering Design (ETS1) performance expectations* for your grade band; *CCSS Math* domains named in each lesson; *ISTE Standards for Students* "Innovative Designer"/"Creative Communicator" (check the current wording); *state arts/technology standards*. Teachers should map to their own standards.

**Accessibility:** offer a tactile model where possible; read steps aloud; allow oral predictions; pair students by strengths; give text alternatives for the 3D view (name, size in mm).

---

### 3.1 ⭐ START HERE — Glow Card (lithophane intro)
- **Band:** grades 4-8 independently (ages 9+); teacher-led for ages 5-8 (K-3) with whole-class demo. *(Replaces/extends the current "Make a lithophane" lesson.)*
- **Time:** 45 min design + a separate teacher-run print (plan to test one print first; write the real time on the board).
- **Objectives:** choose a photo they have the right to use; predict where plastic is thick/thin from a photo's dark/light areas; compare the preview with the prediction; state "thick blocks light, thin lets light through".
- **Materials:** devices with ZEIM; class image pack (printed contact sheet helps); paper/pencil; LED tea-light; teacher-run printer; white or light PLA (community guides suggest white/silver filament tends to work best; test yours — §5 [ItsLitho]).
- **Steps:**
  1. *Photo choices (5 min):* teacher shows the do/don't list from §3.0; students pick from pack / own drawing.
  2. *Predict (7 min):* annotate a printed copy: circle where you think the plastic is thickest. Pair-share.
  3. *Build (10 min):* Studio → Lithophane → Beginner → Standard → Build. Read the "Auto-chosen settings" table together (it explains what and why).
  4. *Compare (8 min):* try Thin and Thick; note what changes in the preview. One-sentence conclusion.
  5. *Submit (5 min):* submit to class (private to class). Optional teacher comment.
  6. *Print + light (teacher-run, later):* teacher prints standing up (community guides recommend printing lithophanes upright with a brim and slow speeds, §5); students light it with an LED tea-light.
- **Safety:** printer is teacher-operated; hot parts; LED only; photo rules above.
- **Assessment:** prediction sheet + one-sentence conclusion; quiz ("Which choice is a good photo?"). Rubric (3 levels): chooses allowed photo / predicts using light-dark reasoning / explains thickness–light link.
- **Extensions:** 9-12 — measure brightness through different thicknesses with a phone's light sensor or camera and graph it (controlled variable: same LED, distance); K-2 — tactile relief only (lesson 3.2). Art — compare tonal range in drawings.
- **Alignment hints:** science practices (planning/carrying out investigations, constructing explanations), light & matter ideas; engineering design (define, model, test, improve); art (value/contrast); ISTE Innovative Designer.

### 3.2 Height Detectives (K-2, teacher-led)
- **Band:** K-2 (ages 5-7). **Time:** 30 min (+ pre-printed relief).
- **Objectives:** describe "tall" and "flat" parts of a relief by touch; connect a bold drawing to the raised shape.
- **Materials:** one pre-printed relief (teacher makes from a bold shape drawing), thick markers, white paper, one device for the teacher, scanner/phone for the teacher to capture 2-3 drawings (no names or faces).
- **Steps:** (1) touch-and-describe circle; (2) draw a bold shape; (3) teacher builds 2-3 drawings as Relief on the projector; (4) match drawings to shapes; (5) "what would a taller one look like?".
- **Safety:** nothing hot in student hands; printer off-limits; supervise small parts (no mouthing small prints).
- **Assessment:** oral — "show me the tall part"; quiz is teacher-asked, not on-device. **Extension:** compare two prints with different relief heights; discuss "why might a blind or low-vision friend like this?" (check with a vision specialist before presenting a real student's needs).
- **Alignment hints:** K-2 measurement/describing (math: "Measurement & Data", comparing attributes); engineering design K-2 level ("ask questions, make observations"); fine-motor/art.

### 3.3 Name Tag Engineers (grades 3-5)
- **Band:** 3-5 (ages 8-10). **Time:** 50 min + teacher-run print. **Needs:** Edit workspace reachable from Spark Lab (CR-8).
- **Objectives:** measure in mm and cm and convert; explain why a flat base helps a printed part stand or stick; change one variable at a time.
- **Materials:** rulers, devices, ZEIM Edit sample model.
- **Steps:** measure a pencil case in cm and mm → open the sample → Measure tool → scale to ~40 mm wide → Add base → add *initials* (not full names) → partner share. Quiz: 40 mm = 4 cm.
- **Safety:** same printing-day baseline; initials only on anything displayed.
- **Assessment:** exit ticket — "I changed ___ and ___ happened"; check correct unit conversion. **Extension:** estimate then measure how many tags fit on a 200 mm bed.
- **Alignment hints:** math measurement & unit conversion (grades 3-5 "Measurement & Data"); engineering design 3-5 level (test one change at a time); ELA speaking/listening for partner share.

### 3.4 Layer Cake Posters (grades 6-8)
- **Band:** 6-8 (ages 11-14). **Time:** 55 min. **Runs on the current app** (Pop-art mode).
- **Objectives:** explain simplifying an image into N flat layers; relate total height = layers × step; give specific, kind critique using "I notice / I wonder / What if".
- **Materials:** bold images (class pack/own art), devices, critique protocol card.
- **Steps:** choose image → predict layers/height → build 3, 4, 6 colours → check maths vs model details → partner critique → revise one setting. Quiz: 5 layers × 1 mm.
- **Safety:** printing-day baseline; critique rules (about the work, not the person); no student names on public pages; class-private only.
- **Assessment:** prediction vs result; critique rubric (specific, kind, useful). **Extension:** ratios of colours by area; compare halftone vs posterize; art history link to pop-art (teacher-chosen, non-trademarked examples).
- **Alignment hints:** math ratios/proportional reasoning & expressions; art (colour, value, composition); engineering design MS level (iterate from feedback).

### 3.5 Fit Check (grades 9-12)
- **Band:** 9-12 (ages 14-18). **Time:** 90 min over two sessions, two print cycles. **Needs:** Edit (boolean, measure, repair).
- **Objectives:** measure a real object; state a requirement with a tolerance; test, document, and justify one redesign with evidence.
- **Materials:** calipers or rulers, a safe object (pen cap, marker, USB stick), devices, teacher-run printer.
- **Steps:** define requirement → measure twice → model holder/cap (scale, base, boolean cut) → Repair + Measure → print and test → change ONE dimension and justify.
- **Safety:** printing-day baseline; no sharp tools; no safety-critical parts (nothing that holds weight over people, no food-contact claims, no electrical enclosures).
- **Assessment:** design notebook page with measurements, predictions, results; rubric on evidence-based revision. **Extension:** compare two printers/filaments' tolerances; write a short "user instructions" page. **Support:** provide a measured sketch to scale.
- **Alignment hints:** engineering design HS level (criteria/constraints, trade-offs, testing); measurement precision; technical communication; career/technical education.

---

## 4. Build Plates — feature spec (not built; DRAFT)

### 4.1 Purpose and principles
A **Build Plate** is a small, safe, interest-based group where makers share projects and learn from each other: a class, a school club, a library maker night, or (later) a hobby group such as "Lithophane Lab" or a printer-model group. Principles:
1. **Private by default; adults accountable.** Every plate has named adult moderators; plates containing minors must have ≥ 2 adult moderators.
2. **No DMs between strangers** (and none at all for minors in v1); no free-text chat in v1.
3. **Humble and useful:** we aim to bring useful parts together, not to out-rank other communities.
4. **Learning over popularity:** recognition by criteria, not counts.
5. **Everything free; no paid or NSFW content;** same language/contact filters as everywhere.

### 4.2 User stories
- **Student (nickname, in a class):** I see a shared board for our class; I add my project to it; I react with preset kind reactions; I can report something that feels wrong; I can see who is in the plate by nickname only.
- **Teacher:** I create a Class Build Plate in one click from my class; posts and comments wait for my approval (or auto-approve only canned reactions); I can freeze, archive, export, or delete the plate; I can run a challenge with criteria.
- **Parent/guardian (later):** I can see which plates my child belongs to (via a link from the school/teacher), what is posted under their nickname, and ask the teacher to remove it. I do not need a ZEIM account in v1; the teacher sends a read-only family link.
- **Club leader / librarian:** I run an invite-only plate for a club, approve members, and keep it private to the club.
- **Hobbyist (adult, later):** I join a public interest plate (e.g. a printer model), share a project with a real print photo, and ask questions; I can mute or hide topics I don't want.
- **Moderator:** I see a queue of reported posts and pending approvals with context and can hide, restore, warn, or remove a member; every action is logged.

### 4.3 Plate types and roles
| Type | Who can join | Visibility default | Minors | Moderation |
|---|---|---|---|---|
| **Class Plate** | Members of one ZEIM classroom (via class code) | Class-only | Yes (nickname) | Teacher; posts pre-approved |
| **Club Plate** | Invite by organiser | Invite-only | 13+ accounts with ≥ 2 adult mods; under-13 only via a school/club adult-run session | Organiser(s) |
| **Interest Plate (adult)** *(later)* | Public join request or invite | Listed but members-only content | **No** (18+ only) | Volunteer mods + staff escalation |
| **Interest Plate (all-ages)** *(later, maybe never)* | Join request | Members-only | 13+ only if ≥ 2 verified adult mods & safe-mode on | Mods + staff |

Roles: **Owner** (one adult), **Moderator** (adult), **Member** (adult or teen 13+), **Student member** (nickname-only, class-bound), **Guest/observer** (read-only family link). Owners can transfer ownership; a plate with <1 owner or <2 mods when minors are present is frozen until fixed.

### 4.4 Privacy and safety defaults
- Plates start **Private**; "listed" vs "unlisted" is the owner's choice; only adult-only Interest Plates may ever be publicly readable.
- **No DMs.** Replies are via comments on posts. For minors: comments are canned reactions + teacher-approved short comments only.
- **Reporting:** a visible Report button on every post/comment with plain-language reasons; `minor_safety` hides immediately (as today) and alerts staff; reports go to plate mods first then staff.
- **Identity:** nickname-only for students; adults use display names; no real names, no contact info (existing filters block email/phone/links).
- **Photos:** same photo-permission acknowledgement as uploads (CR-5); real-print photos for makes must not show faces/identifying backgrounds.
- **Age gate honesty:** self-declared DOB is bypassable (README) — so **adult-only plates are a policy, not a guarantee**; keep minors out of them by not sending minors to them at all (no listing, no search in their sessions).
- **Data:** leaving a plate removes the member's posts on request; deleting a plate deletes everything in it; exports for teachers; retention period to be set with legal.
- **Moderation transparency:** a plain "How we handle reports" page; stated target response times we can really meet (decide with Daichi/Operations).

### 4.5 Moderation
- Pre-moderation for Class Plates; post-moderation + report for adult Interest Plates.
- Language/contact filters on every text field (existing `safety.gate`).
- **No auto-hide after N reports** for non-safety reasons (false-positive risk, §5), except `minor_safety` which hides then gets human review.
- Strikes are *not* introduced (current policy: no strikes/bans in chat). Moderators can mute or remove members; staff can lock a plate. Appeals: simple form, human answer.
- Audit log of every moderator action.

### 4.6 Challenges (learning-first)
- A challenge has a **public rubric** (e.g. "uses at least 3 layers; includes a short note on what you changed") and a date range.
- Recognition: **"Teacher/Moderator picks"** and **badges for criteria met**, not rank by likes or downloads. No points redeemable for anything.
- Entries are class- or plate-private by default; showcase on the plate board only.
- Example starters: *Glow Card gallery walk* (class), *One Change* (same model, change one setting, tell us what happened), *Fit Check* (high school).
- Lessons we take from others (§5): vague/changing contest rules and opaque judging frustrate people; so publish rules up front and judge on stated criteria.

### 4.7 Data model sketch (JSON-file style as today; swap for DB later)
```text
plates:        {id, type, name, description, owner_uid, classroom_code?, visibility, minors_allowed, status(active|frozen|archived),
                created, rules_version}
memberships:   {plate_id, member_ref(uid | sid+nickname), role, joined, status(active|pending|removed|muted)}
invites:       {id, plate_id, code_hash, role, expires, uses_left}
posts:         {id, plate_id, author_ref, project_ref(showcase|class|build), text, status(pending|approved|hidden|removed), created}
reactions:     {post_id, member_ref, kind(canned: "nice idea","I learned something","great colours","how did you do this?")}
comments:      {id, post_id, author_ref, text|canned_kind, status, created}
challenges:    {id, plate_id, title, rubric[], start, end, status}
entries:       {challenge_id, post_id, criteria_met[], picked_by?}
reports:       {id, target_type, target_id, reporter_ref, reason, status, created, resolved_by?}
audit_log:     {ts, actor_ref, action, target, note}
```
Author references for students are nickname-bound, never real names.

### 4.8 API / UI sketch
```text
POST /api/plates                       {type, name, classroom_code?}      create (adult)
GET  /api/plates                       my plates
GET  /api/plates/{id}                  board (posts with status=approved) + my role
POST /api/plates/{id}/join             {code | invite}
POST /api/plates/{id}/posts            {project_ref, text?}  -> pending (Class/Club)
POST /api/plates/{id}/posts/{pid}/approve|hide|restore    (mods)
POST /api/plates/{id}/posts/{pid}/react {kind}               (canned only)
POST /api/plates/{id}/posts/{pid}/report {reason, details?}
POST /api/plates/{id}/members/{ref}/mute|remove|promote      (mods)
POST /api/plates/{id}/challenges       {title, rubric[], start, end}
GET  /api/plates/{id}/export           (owner) JSON/CSV
DELETE /api/plates/{id}                (owner) erase all
```
UI: top-nav "Build Plates" (name from `branding.SECTIONS["groups"]`); plate board = grid of project cards (thumb, title, nickname, reactions as icons without numbers for minors); right rail with rules + "Report"; moderator drawer with the pending queue. Teacher "Create a Build Plate from this class" button in Teacher tools.

### 4.9 MVP vs later
- **MVP (after CR-1…5, CR-11, CR-13):** Class Plate only: create from class; student posts a class project; teacher approves; canned reactions; report; archive/delete; export.
- **v1.1:** Club Plate with invites and ≥2-mod rule; challenges with rubric; family read-only link.
- **v2:** Interest Plates (adult-only) with join requests, real-print photos on makes, mod tools, appeals; LMS/roster tie-ins; localisation.
- **Not planned:** DMs, public minors' plates, follower counts for minors, points/rewards.

### 4.10 Success metrics (humble, checkable)
- % of Class Plates with ≥ 80% of students posting at least once in a unit.
- Teacher time to approve a post (median) and % approved same day.
- Reports per 100 posts, time-to-first-human-review, % `minor_safety` reviewed within our stated target.
- Teacher-reported usefulness (short survey, 5 questions) and "would you use again next term".
- Zero incidents of student personal info visible outside a plate (audit).
- *Not* used as success metrics: raw likes, downloads, time-on-site.

### 4.11 Open questions
1. Who is legally responsible for moderation in Club Plates run by libraries? Do we need an organiser agreement?
2. Are teachers allowed to approve content on behalf of guardians under their district's policy? (Counsel / districts.)
3. How do we verify adults beyond self-declared DOB — school email, domain allow-list, or a vouch from an existing verified teacher?
4. Do we allow teens (13-17) to join all-ages Interest Plates at all?
5. Retention and deletion periods; export format for schools.
6. Do canned reactions need translations from day one?
7. Should "Build Plates" stay the user-facing name (trademark clearance not done; branding is configurable in `app/branding.py`)?

---

## 5. Global research (education & community angle)

**Method and limits.** Public web sources only, gathered 2026-10-04. Each source is tagged **[F]** (I fetched and read the page) or **[S]** (I saw an excerpt in search results but did not read the whole page). Reddit pages could not be fetched directly (blocked), the Scratch pages did not render, and one NIOSH PDF timed out, so most community claims rest on search excerpts. Forum and Reddit posts are individual voices, not representative samples; I give **no statistics** because I found none I could verify, and I do not quote beyond short phrases that appear in the excerpts. Several sources are vendors describing their own products (SimplyPrint, ItsLitho, CREATE Education, Bambu Lab). Coverage is uneven: Tinkercad, Printables, Thingiverse, MakerWorld, Prusa forum and teacher threads are covered; **Cults3D, Shapr3D (beyond its education licence), Bambu/Orca/Prusa slicer-usability and r/functionalprint were only thinly or not verified**. Treat this as a starting point for conversations with real teachers, not as proof.

### 5.1 What teachers ask for and struggle with
1. **Join without email; nickname + class code.** Tinkercad Classrooms advertises onboarding "with a link or code" with "no emails required" [S: https://www.tinkercad.com/teachers]. Its guide describes students joining with a nickname and class code, teachers pasting a roster to generate nicknames, "Seats" with their own login codes, and classes up to 250 [S: https://images.tinkercad.com/jl5ii4oqrdmc/5v197WuuaqspGT81cG5tT6/81154785a527f1b42a32325487a30e44/tinkercad-guides_classrooms-Printable.pdf; https://www.tinkercad.com/help/classrooms/share-class-link-code]. Autodesk's children's privacy statement says students joining by nickname do not give personal data and cannot communicate with members other than the teacher [S: https://www.autodesk.com/company/legal-notices-trademarks/privacy-statement/childrens-privacy-statement]. *ZEIM's design is close to this; the gap is seat recovery and roster-created seats.*
2. **A safe default mode for classes.** The same Tinkercad guide says students start in "Safe Mode" by default: designs stay private, students cannot make designs public or search the Gallery, and the Gallery is limited to curated picks; teachers can toggle it per student or class [S: same PDF]. *This is the model for CR-3.*
3. **The workflow around the printers is the hard part.** A Prusa-forum post from someone helping a school with 100+ students describes print requests arriving by email/USB/shared folders, wanting one place to submit/review/approve, queue management near deadlines, filament tracking, restricting who may start prints, and linking student accounts, classes and deadlines to the queue [S: https://forum.prusa3d.com/forum/english-forum-general-discussion-announcements-and-releases/managing-a-school-3d-printing-lab-how-do-you-handle-student-print-requests-and-tracking/]. SimplyPrint's documentation describes teacher-led, approval-queue and quota-based modes [S: https://help.simplyprint.io/en/article/school-and-makerspace-workflows-from-teacher-led-to-student-led-printing-cfmow0/]. CREATE Education's guide suggests student "printer monitors", booking rotas, test prints, and planning extra days for printer errors [S: https://www.createeducation.com/wp-content/uploads/2024/09/3D-Printing-Classroom-Management-Guide.pdf]. *This supports CR-13 (print queue with approval) before groups.*
4. **Teach troubleshooting, not just printing.** A teacher in an r/TechnologyTeachers thread describes giving students a guide with troubleshooting and having them work in design cycles, and says students start with Tinkercad [S: https://www.reddit.com/r/TechnologyTeachers/comments/kqh3xg/what_struggles_do_you_have_when_teaching_3d/ — thread appears to be from the remote/hybrid-learning period; another poster guesses Chromebooks without mice may have been an obstacle]. A teacher blog (2016) describes small student groups each responsible for a printer, filament changes and troubleshooting [S: https://tweenteacher.com/2016/06/17/lessons-to-share-3d-printing-and-design-to-learn-reading-writing/]. *Supports a "why did it fail?" lesson as an extension and student roles that never involve hot parts.*
5. **Health and safety guidance exists and is specific.** Washington State's Department of Health page for schools says best practice is an enclosed printer exhausted outside, PLA as the preferred filament, printers away from student desks, near a fire extinguisher, safety training before use, no hovering over a running printer, no opening the cover mid-print, keeping the enclosure shut 20 minutes after printing, no sharp tools when avoidable (use painter's tape/glue-stick surfaces), cooling before removal, and handwashing [F: https://doh.wa.gov/community-and-environment/schools/3d-printers]. It also states a WAC rule requiring local exhaust ventilation in that state's schools [F, same page]. The page links a NIOSH guide I could not open [S: https://www.cdc.gov/niosh/docs/2024-103/pdfs/2024-103.pdf]. *Used in §3.0 and CR-8; rules differ by state/district — always defer to the school.*
6. **Educator verification is a real hurdle for tools.** Shapr3D's education licence is free for teachers but needs a school email, ID and proof of affiliation (with school-domain whitelisting) [S: https://support.shapr3d.com/hc/en-us/articles/12720247715868-Educational-license-eligibility]. *Lesson: keep our teacher onboarding light for now, but plan a verification path for groups with minors.*
7. **Beginners get overwhelmed by slicer settings.** There is a beginner post titled "Overwhelmed. Need help getting started w Orca slicer software." on r/3Dprinting [S: https://www.reddit.com/r/3Dprinting/comments/1vutz5n/overwhelmed_need_help_getting_started_w_orca/] (title only; I did not read the replies). *Low-confidence support for keeping ZEIM's Beginner mode and its "Auto-chosen settings" table.*

### 5.2 What students and families need (from the children's-privacy angle)
1. **US children's privacy rules moved in 2025-26.** The FTC's amended COPPA Rule was effective June 23, 2025 with a compliance date of April 22, 2026 for most provisions; the FTC said it was **not** finalising the proposed school/ed-tech definitions or a codified school-authorisation exception, and will keep enforcing in ed-tech under existing guidance; the amended definition of personal information adds biometric identifiers such as faceprints and facial templates [F: https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule]. *Takeaway for us: keep data minimal (nickname only), do not derive anything from faces, and get counsel before any under-13 launch. I am not a lawyer; this is not legal advice.*
2. **Kid-focused communities lean on filters, reports and clear guidelines.** Scratch's guidelines (as shown in a search excerpt) ask members to be respectful, give constructive feedback, keep personal information private, and report content [S: https://scratch.mit.edu/community_guidelines — page did not render for me; low confidence]. *ZEIM's Community Guidelines already cover this ground; plain-language wording for kids is the improvement.*

### 5.3 What makers ask for and complain about
1. **Spam, AI-generated or unprintable uploads and fake engagement hurt trust.** On Printables in 2026, users post about AI-generated or fake "makes", duplicates and suspicious accounts; a Prusa staff reply says reports "get reviewed in waves", that they have tools to find scammers and vote manipulation, and, in April 2026, that harassment is a "tug and war" they are reactive to, while asking people to keep reporting [S: https://www.reddit.com/r/prusa3d/comments/1vmqb8d/ai_generated_makes_on_printables/; https://www.reddit.com/r/printablescom/comments/1sh0zgn/dangerous_accounts/]. A staff post asks for feedback on handling AI models and asks users to report untagged ones [S: https://www.reddit.com/r/prusa3d/comments/1r4srum/stop_sharing_ai_generated_models/]; commenters there propose requiring real photos of the printed object [S, same URL]. A forum user says there are filters to exclude AI, political and NSFW content in search and settings [S: https://forum.prusa3d.com/forum/english-forum-general-discussion-announcements-and-releases/hiding-individual-users-on-printables/].
2. **Popularity-based rewards get gamed and frustrate creators.** A Bambu Lab staff post on MakerWorld points says download/print counts alone skewed rewards and describes points farming and download manipulation, and says the new system looks at originality, complexity and presentation, with the exact formula hidden [S: https://forum.bambulab.com/t/why-we-re-upgrading-our-points-system/172869]. Creators on the forum complain about low-effort uploads and uneven enforcement [S: https://forum.bambulab.com/t/makerworld-lack-of-quality-control-is-killing-the-platform/162794], and some describe contests as judged by "vibes", partly popularity-driven, or announced with vague rules [S: https://forum.bambulab.com/t/design-competitions/240058; https://forum.bambulab.com/t/bambu-labs-makerworld-contest-reform-is-desperately-needed/147284] — these are user opinions.
3. **Automated moderation can misfire and be weaponised.** A Thingiverse forum thread says an automated system flags items when several members report them (for theft or undeclared AI), a creator says they were targeted by a harasser, and a staff reply removed the flag and the harassing comments [S: https://forum.thingiverse.com/t/models-under-moderation/400]. Other threads complain of accounts "under moderation" with slow support [S: https://www.reddit.com/r/thingiverse/comments/sa95ix/your_account_is_under_moderation_and_can_no/]. *Support for: no auto-hide on report count, human review, fast clear appeals.*
4. **Reliability and openness matter.** Press and Reddit posts describe Thingiverse downtime, bugs and slow support over several years, and users moving files elsewhere [S: https://3dprint.com/252620/lets-kill-thingiverse/; https://www.reddit.com/r/3Dprinting/comments/pboa8c/why_is_thingiverse_so_shit/; https://www.reddit.com/r/thingiverse/comments/sa95ix/your_account_is_under_moderation_and_can_no/]. *Support for ZEIM's "never lock files in" ROADMAP principle and for simple, boring reliability before features.*
5. **Reports and private accounts are table stakes.** Printables' terms route complaints through a Report button or email, offer private accounts and have a Messenger [S: https://www.prusa3d.com/page/terms-of-service-of-printables-com_231249/]. *We differ deliberately on DMs for minors.*
6. **Lithophane craft knowledge is community-sourced and trial-and-error.** One lithophane vendor's guide (also sells filament) says: print upright, along the bed's Y axis, solid interior (99% infill or many walls), white/silver filament generally best, slow speeds (they suggest ~30-45 mm/s), fine layers (~0.12 mm; ~0.2 mm the coarsest acceptable), a brim not a raft, and a calibration print per filament; and notes it is "a trial & error process" [F: https://itslitho.com/itslitho-blog/slicer-settings-for-lithophanes-tweaking-to-perfection/]. *Implication for lessons: classes should test-print one first, and our "1-2 hours each" teacher note should not be stated as fact.*

### 5.4 Cross-cutting observations (my reasoning, not sourced claims)
- The sources agree on a pattern: **popularity metrics attract gaming; automated, count-based moderation attracts abuse; and the places that serve young people default to private, curated and teacher-moderated.** That fits where ZEIM has already landed; the remaining work is applying it consistently (class sessions + Showcase, minors + Trending).
- For schools, **throughput and approval of prints** looks more urgent than **social features**.
- A kind, specific critique protocol and criteria-based challenges address what makers complain about in contests (opaque judging) without needing counts.

### 5.5 Ideas table — Adopt / Adapt / Reject
| Idea | Seen in | Decision | Why (for ZEIM) |
|---|---|---|---|
| Nickname + class code, no email | Tinkercad | **Adopt** (already built) | Fits our no-PII design for under-13s. |
| Class "Safe Mode" default (private, no gallery search) | Tinkercad | **Adopt** | CR-3: Showcase off for class sessions unless teacher enables. |
| Teacher-created roster seats with login codes | Tinkercad | **Adapt** | Start with "reset seat" (CR-4); roster seats later; avoid collecting real names. |
| Teacher approval queue for prints; quotas | SimplyPrint, Prusa forum, CREATE | **Adapt** | Status-only queue first (CR-13); no remote printer control for students; quotas later. |
| Student "printer monitors" | CREATE, teacher blog | **Adapt** | As a teacher-assigned classroom role; never touching hot parts without adult supervision. |
| Test print first; plan spare days | CREATE, ItsLitho | **Adopt** | In lesson teacher notes; no invented timings. |
| School printer safety checklist | WA DOH | **Adopt** | Use in lessons; always defer to local rules/officer. |
| Curated "Staff favourites"-style gallery | Tinkercad | **Adapt** | "Teacher picks" per class/plate instead of a public popularity list. |
| Require real photos of prints | Printables community | **Adapt** | Optional "show your print" photo; no people/faces/backgrounds that identify; not required for kids. |
| AI/political/NSFW filters | Printables | **Adapt** | We have no NSFW; consider a simple "made with AI" provenance label if AI features appear; not now. |
| Report button + staff reply on reports | Printables | **Adopt** | Plain-language reasons, visible response targets we can meet (CR-6, CR-11). |
| Hidden scoring formula | MakerWorld | **Reject** | We keep our formula public (README); and avoid ranking kids' work. |
| Points / rewards for downloads or prints | MakerWorld | **Reject** | Invites gaming; ZEIM is free and not a rewards marketplace. |
| Contests judged by staff opinion, popularity-weighted | MakerWorld (user complaints) | **Reject** | Use public rubrics and criteria badges (§4.6). |
| Auto-flag after N reports | Thingiverse | **Reject** (except `minor_safety` → hide + human review) | Documented false positives and harassment-by-report. |
| DMs between users | Printables Messenger | **Reject for minors; later for adults only** | Grooming risk; canned messages instead. |
| Educator verification with ID/school email | Shapr3D EDU | **Adapt (later)** | Needed before groups with minors scale; keep MVP light. |
| Simple/beginner mode with explained defaults | slicer-beginner threads | **Adopt** (already built) | Keep the "Auto-chosen settings" table. |
| Kid-friendly guidelines & filters | Scratch (low confidence) | **Adapt** | Rewrite Guidelines in kid-readable form with examples. |
| Open file formats / no lock-in | Thingiverse complaints | **Adopt** (already ROADMAP) | Trust for teachers who may switch tools. |

---

## 6. Change requests for Engineering

(Also saved as `reports/education-change-requests.md`. Text below is identical.)


From: Aiko Nakamura (Head of Education & Community) · To: Haruto Tanaka (Engineering) · Date: 2026-10-04 (CT)
Status: DRAFT for review. Source: read-only review of `/workspace/photo3d` (no app code was edited by Education).
Full rationale, evidence and context: `reports/education.md`. Draft lesson content in the app's `LESSONS` schema: `reports/education-lessons-draft.json`.

How to read: **P0** = fix before any pilot with a real class on a shared/hosted server. **P1** = before a wider school pilot. **P2** = next. File/line references are from the code as of today and may move; each item says what to look for. Where I am unsure of the best implementation I say so — Engineering knows the code better; the *acceptance criteria* are what matter to us. Items that need a product/legal decision are marked **[decision]**.

---

### P0 — before any real-class pilot

#### CR-1. Lock down `/api/settings` and network-printer sending on shared servers
- **Why:** `GET/PUT /api/settings` (`app/api/settings.py`) take no `Actor`; any visitor, including a class student, can add/change printers and `public_base_url`. `public_base_url` is used to build the teacher's join-QR (`app/api/learn.py::room_qr`) and slicer links (`app/api/printing.py::base_url`), so changing it could point a class QR at another site. `POST /api/send/{bid}` (`printing.py`) then uses any saved printer, with `start=true` available.
- **What:** Add a deployment setting (e.g. `PHOTO3D_MODE=shared|local`, default `shared` unless explicitly local). In `shared` mode, `PUT /api/settings`, printer CRUD, and `POST /api/send/*` require the admin token or an adult teacher/owner account; class-student sessions (any `sid` in a classroom's `students`) always get 403 on these. `GET /api/settings` must not expose printer URLs to students.
- **Accept:** (a) test: a session that joined a class gets 403 on `PUT /api/settings` and `POST /api/send/{id}`; (b) a brand-new anonymous session in `shared` mode gets 403 on `PUT /api/settings`; (c) `local` mode behaves as today; (d) the join QR always encodes the configured base URL, which a non-admin cannot change.

#### CR-2. Student photo hygiene: strip metadata, safe extension, purge on leave/delete
- **Why:** `app/api/builds.py` (~line 208-210) writes the uploaded bytes unchanged to `outputs/<id>/source.<ext>` (EXIF such as GPS/camera info stays; extension comes from the client filename). `classrooms.remove_student()` and `classrooms.delete()` erase class projects and progress but **not** the students' own builds/source photos in `outputs/`, although the README says "all class data erased".
- **What:** (1) On photo upload, re-encode the image (e.g. Pillow, orientation applied, EXIF/ICC/GPS dropped) and save as PNG/JPEG chosen from the *sniffed* format, not the filename. Do this for the Edit-workspace photo path in `app/services/editproj.py` too. (2) On `remove_student` and `delete`, also delete every build/edit project whose `owner_sid` is that student (use `history.store.delete`). (3) Add a `delete_my_data` endpoint for class students (builds + progress + class projects) and a "Delete my stuff" button on the student banner. **[decision]** optional auto-expiry of class-student builds (e.g. 30 days after last activity) — Education suggests yes.
- **Accept:** test uploads a JPEG with GPS EXIF → stored `source.*` has no EXIF; filename `x.exe.png` or a JPEG named `.png` is stored with the correct extension; after `DELETE /api/classrooms/{code}` and `DELETE …/students/{sid}`, no `outputs/<id>` with that student's `owner_sid` remains; `tests/` pass.

#### CR-3. Showcase is off by default for class-student sessions (teacher can enable)
- **Why:** Class students are anonymous cookie sessions, but nothing stops them browsing the public Showcase, liking, downloading, or reading public descriptions written by strangers (`app/api/community.py::showcase*`). The README says Spark Lab is classroom-safe "by construction", which is true for Spark Lab but not for the rest of the app the student is sitting in.
- **What:** Add `showcase_enabled` (default `false`) to each classroom (`app/community/classrooms.py`; teacher toggle in `/api/classrooms/{code}/settings` and in Teacher tools). For a session that is a member of a class with it disabled: `GET /api/showcase*`, `/p/*`, `/u/*`, like, download, report-from-Showcase return 404 (or a friendly "Your teacher has turned this off"), and the Showcase nav item is hidden/disabled in `static/community.js`. When enabled, students get view-only (no likes) unless the teacher also enables likes.
- **Accept:** a student session in a default class gets 404/friendly-off for all Showcase routes and cannot like; after the teacher enables it, listing works; likes need a second toggle; test covers both states and that a non-class visitor is unaffected.

#### CR-4. Seat reset so a student who loses their browser/cookie can come back
- **Why:** Student identity is the `p3d_sid` cookie. `classrooms.join()` rejects a nickname already used in the class, so a student on a shared school laptop who clears cookies (or is on a different Chromebook next day) is locked out of their own nickname and loses progress/projects. Shared devices also mean two students can end up as one `sid`.
- **What:** Teacher button **"Reset seat"** per student (`POST /api/classrooms/{code}/students/{sid_prefix}/reset`): detaches the old `sid` from the nickname but keeps the nickname's progress/projects, and allows exactly one new join with that nickname (code + password + nickname) within e.g. 24 h. Also add a visible "I'm on a shared computer" join option that does not persist the cookie beyond the browser session (`max_age` unset for that case). **[decision]** longer term: teacher-pasted roster of nicknames with per-seat login codes (see research: Tinkercad "Seats").
- **Accept:** test: student A joins as "Fox", cookie dropped, new session cannot join as "Fox" (409 as today) until teacher resets the seat, then can, inheriting progress; the old session loses access; another student cannot take the seat.

#### CR-5. Photo-permission acknowledgement before upload and publish
- **Why:** The only consent prompt is `pub_ok` ("follows the Community Guidelines") in `static/index.html` ~line 272; the Guidelines mention photos of other people (item 5) but nothing is asked at the moment a photo is uploaded, and the lithophane lesson currently suggests "a pet or a face".
- **What:** (1) Studio and Edit photo drop zones show a one-line notice and required checkbox: "This is my photo/drawing or I have permission from everyone in it. No addresses, school names or license plates." (2) For class-student sessions the checkbox cannot be pre-ticked and the choice is stored in `meta.json` (`photo_ack: true`). (3) Publish dialog text names photo permission explicitly. (4) Optional (stretch): offer a built-in school-safe image pack (`static/imagepack/`, originals or public-domain with attribution file) behind a "Use a class image" button next to "Try a sample photo".
- **Accept:** cannot Build from an uploaded photo without ticking; `meta.json` records `photo_ack`; text appears in publish dialog; built-in sample/image-pack path does not require the checkbox.

---

### P1 — before a wider school pilot

#### CR-6. Replace `prompt()` / `confirm()` with accessible dialogs; give students a way to report
- **Where:** `static/community.js` uses `prompt()` for the Showcase report (reason typed as a code word such as `minor_safety`), details, teacher feedback, and "Which build? Type a number" (`submitToClass`), plus one `confirm()` for deleting a class.
- **What:** Use `<dialog>` forms with labelled radio buttons for reasons in plain language ("Something about a person or a child is not safe" → `minor_safety`, "Not family-friendly", "Mean or unkind", "Shares private info", "Copyright", "Something else"), a build picker with thumbnails for submit, a textarea for feedback with the 500-character counter. Add a **Report** button for class students on teacher feedback and on classmates' projects (`POST /api/classrooms/{code}/projects/{pid}/report`, goes to the teacher first, then to the moderation queue). Dialogs must trap focus, close on Esc, return focus to the opener.
- **Accept:** no `prompt(`/`confirm(` remain in `community.js`/`edit.js`/`app.js`; keyboard-only user can file a report; screen-reader labels present (checked with axe, see CR-12); existing tests still pass and a new test covers the class-project report route.

#### CR-7. Lesson panel re-renders the whole page on every checkbox and scrolls
- **Where:** `static/community.js::openLesson` — ticking a step calls `openLesson(id)` which rebuilds the panel and calls `box.scrollIntoView(...)` each time; a correct quiz answer does the same after 700 ms.
- **What:** Update only the changed step/progress bar, preserve scroll and keyboard focus, announce "Step 3 of 5 done" via an `aria-live="polite"` region; scroll into view only when the lesson is first opened.
- **Accept:** ticking steps by keyboard keeps focus on the same checkbox and does not move the page; a screen reader announces the progress change.

#### CR-8. Lesson content fixes now, schema extension next
- **Now (copy only, `app/community/education.py`):**
  1. `lithophanes` step 2: "a pet or a face" → remove "face"; use the photo guidance in `education.md` §3.1 (own photo/drawing/class image pack; no photo of another person without permission).
  2. `lithophanes` `teacher_notes`: "A class set of 2.4-4 mm lithophanes prints in about 1-2 hours each" matches neither the Standard preset (0.8-3.2 mm, `app/core/autotune.py`) nor a measured time. Replace with "test-print one on your printer first and write the real time on the board", and say the printer is operated by the teacher.
  3. Add safety steps to `first-print`: printer is operated by an adult; no hands near moving/hot parts; do not open an enclosure mid-print; wait for the print bed to cool before removal; students do not use scrapers/blades; printers away from desks and ventilated (see research, WA DOH). Use "ask your grown-up" wording consistently.
  4. `first-print` says "Open the Studio… pick Relief" while the `try` button opens a thin relief — fine, but state the printer is teacher-run.
- **Next (schema):** add optional fields to each lesson: `grade_band`, `audience` (`teacher_led` | `independent`), `prep`, `materials`, `safety`, `assessment`, `extension`, `alignment_hints`; render them on `/l/<id>` and in the lesson panel (teacher-only parts hidden from student sessions); allow `try.view = "edit"` so Spark Lab can open the Edit workspace (three draft lessons need it); allow multi-question quizzes with a short explanation per answer.
- **Drafts to paste in (after Education review with a teacher):** `reports/education-lessons-draft.json` (same keys as `LESSONS`; `answer` is the 0-based option index).
- **Accept:** lesson text matches the drafts; `/l/<id>` shows materials/safety for new fields; no lesson mentions faces as a recommended subject; quiz data validated by a test (answer index in range).

#### CR-9. `noindex` for user-generated pages
- **Where:** `app/api/learn.py::_page` (used by `/p/<id>` and `/u/<id>`) has no robots meta or header.
- **What:** Add `<meta name="robots" content="noindex,nofollow">` and `X-Robots-Tag: noindex` for `/p/*` and `/u/*` (keep `/l/*` lesson pages indexable). **[decision]** later, allow public adult creators to opt in to indexing.
- **Accept:** `curl -I /p/<id>` shows `X-Robots-Tag: noindex`; `/l/<id>` does not.

#### CR-10. Likes / Trending / teen publishing: safer defaults **[decision]**
- **Observed:** likes are one-per-cookie-session and need no account (`catalog.set_like`), counts are shown on every public card; Trending ranks by likes+downloads (documented, `trending_score`); example seed items show invented counts (e.g. 1,500 downloads); a teen (13-17) may publish *Public* per project (`privacy.check_level` only blocks the *default*).
- **What (each is a config flag in `app/config.py` so we can change our minds):**
  1. `LIKES_REQUIRE_ACCOUNT=true` and a per-session/IP rate limit (e.g. 30 likes/hour) on `/like`; same limit on `/report`.
  2. `SHOW_COUNTS_FOR_EXAMPLES=false` — example items show no like/download numbers (still labelled EXAMPLE) and sort by recency inside Trending.
  3. `TEEN_PUBLIC_ENABLED=false` for launch: accounts 13-17 can choose Private or Followers only; Trending/Free exclude under-18 creators' items until a human review process exists. (Education recommends flagging this to Yami/legal; the README already lists the teen-public question as "open decision".)
  4. `HIDE_COUNTS_FOR_MINORS=true`: do not show like/download counts on items by under-18 creators, and do not show the creator their own numbers as a ranking (they still see "your project was liked").
- **Accept:** tests per flag; defaults are the safe values; README "Likes"/"Trending" sections updated by Engineering to match.

#### CR-11. Moderation basics: dedupe, rate-limit, queue visible to a human
- **Where:** `app/community/moderation.py`, `app/api/community.py::mod_queue`.
- **What:** (a) one open report per (reporter, item, reason); (b) rate limit reports per session; (c) keep `minor_safety` auto-hide (good fail-safe) but record who reported and when, and add an audit log line for every hide/restore; (d) a minimal admin page `/admin/moderation` (token-protected) listing open reports oldest first with item preview and Hide/Restore/Dismiss; show "oldest open report age"; (e) for class-scoped reports, teacher sees them first. (f) Do **not** add "auto-hide after N reports" for non-safety reasons (research: this produced false takedowns elsewhere).
- **Accept:** duplicate report returns the existing id; 11th report in a minute is refused; admin page lists/acts on reports; audit entries written; tests.

#### CR-12. Accessibility pass with measurable exit criteria
- **Observed (not a full audit):** body text contrast passes (computed `#8b97ad` on `#0e1117` ≈ 6.4:1, `#e6eaf2` ≈ 15.7:1); only one `aria-` attribute in `static/index.html` and none in `community.js`; the 3D viewer is canvas-only; toasts have no live region; many teacher-tool buttons are emoji-only or small (`.btn.small`).
- **What:** run axe-core (or Lighthouse a11y) on Studio, Showcase, Spark Lab, Teacher tools, dialogs; fix critical/serious findings; add `aria-live` for toasts and progress; label icon buttons; ensure every dialog is keyboard-operable; give the viewer a text alternative (model name, size in mm, "triangles", watertight status) and a "reduce motion" respect (`prefers-reduced-motion`) if the viewer auto-rotates; confirm 200% zoom and touch targets ≥ 44 px on class pages. Add the axe run to `tests/ui_smoke.py`.
- **Accept:** zero critical/serious axe violations on the listed pages; keyboard-only walk-through (join class → open lesson → tick steps → quiz → submit build) passes; recorded in `reports/a11y.md`.

---

### P2 — next

#### CR-13. Teacher dashboard: needs-help first, print queue with approval, CSV export, due dates
- **Why (research):** teachers describe the workflow around printers (submit/review/approve, queue, deadlines, filament use) as the hard part (see `education.md` §5).
- **What (MVP):** (1) sort students with an unread `need_help` first and show a badge; (2) "Print queue" tab per class listing submitted projects with title, student nickname, model size (mm), estimated print time & filament if the slicer is available, and **Approve / Send back with a comment / Mark printed** — it records status only; no remote printer control for students; (3) CSV export of progress (nickname, lesson, steps, completed); (4) optional due date per assigned lesson (`assigned` becomes `[{id, due}]` — keep backward compatibility).
- **Accept:** teacher can approve/send back; student sees status ("waiting", "approved", "printed", or teacher comment) and the project stays class-private; CSV opens in a spreadsheet; tests.

#### CR-14. Quiz and teacher-note separation
- Teacher notes are currently shown to students inside a `<details>` in the lesson panel. Serve `teacher_notes`/`prep`/answers only to the teacher session (or behind a teacher toggle). Add short "why" explanations for wrong answers. Accept: student session API payload has no `teacher_notes`.

#### CR-15. Teacher account recovery **[decision]**
- Teachers are cookie-bound accounts without passwords (`identity.py`); clearing browser data loses the account and classes. Smallest step: a one-time **recovery code** shown at account creation (stored hashed) that re-binds a new browser to the account. Proper fix is real auth (already on the ROADMAP). Accept: a new browser can regain the teacher account with the code, and the old session loses teacher rights; code can be regenerated.

---

### Not requested yet (waiting on P0/P1)
Build Plates (groups). The spec is in `reports/education.md` §4. Please do not start until CR-1…CR-5 and CR-11 are done, because groups multiply every one of those risks.

---

## 7. Hansei (honest reflection)

**What was partial**
- **I read code; I did not use the product.** No browser walk-through, no screen-reader or axe run, no test-suite run, no real class on shared Chromebooks. Everything about "how it feels" for a nine-year-old or a busy teacher is inference. The only live calls were four read-only `GET`s.
- **Some tool output was truncated** (long files such as parts of `community.js`, `catalog.py`, `learn.py`). I re-read the parts I rely on (join, submit, feedback, likes, settings, upload, privacy), but I did not read every line of the UI code, `edit.js`, `viewer.js`, or the mesh-editing core, so I may have missed controls that already address something I flagged.
- **Claims about "no gating"** (class students reaching Showcase and `/api/settings`) come from reading route signatures, not from a test that proves it. Engineering should reproduce each P0 before acting; I would be glad to be wrong.
- **Research is thinner than the brief asked.** Mostly search excerpts, with only three pages read in full (WA DOH, Federal Register, ItsLitho); the Tinkercad material is search-excerpt only. Reddit was blocked; Scratch did not render; NIOSH timed out. I found no verified statistics, so I gave none. Cults3D, Shapr3D beyond licensing, the slicers' own UX, and r/functionalprint are essentially uncovered (I dropped an r/functionalprint claim because I could not verify the subreddit rules). Many sources are vendors or individual forum voices.
- **Lessons are drafts.** Not tested with children or a teacher; timings are guesses; I did not verify print times; standards alignment is deliberately domain-level because I did not verify exact codes. Three of the five lessons depend on features (Edit from Spark Lab; teacher-led setup) that don't exist yet.
- **Build Plates is a design on paper.** Role and age rules lean on a self-declared date of birth, which is bypassable; I said so, but the spec cannot fix that.
- **Not done from the delegation:** I could not create a specialist bot (no tool for it), and I cannot message Haruto or Mr. Kato directly — the parent agent must forward the change requests and status.

**What went wrong / what I'd do differently**
- I wrote the change-request file before finishing research and then cross-checked it afterwards. It happened to hold up, but the order was backwards; I would sequence research → hypotheses → requests.
- I pulled very large pages (the full Federal Register notice) to confirm three facts, which cost context and time; targeted searches first would have been better.
- I initially sketched the Build Plates spec as the centrepiece, because the brief did. The evidence I found pointed to print workflow and class safety defaults as higher value, so I reordered the recommendation; the report still gives groups a full spec, which may over-invest in the less urgent item.
- Some recommendations are judgement calls that reasonable people could dispute, notably **disabling Public for teens (CR-10)** and **hiding counts for minors**: they reduce a motivating feature. I'd test these with teachers and teens before locking them.
- I assumed the audience is mostly US schools (COPPA/FERPA, WA example). ZEIM may have users in other regions with different rules and safety norms.

**What I would change next**
1. Interview 3-5 teachers (different grade bands, one with Chromebooks only) and run one 45-minute Glow Card session with a pilot class before finalising any lesson.
2. Run axe-core and a keyboard/screen-reader pass; replace my "not measured" notes with real findings (CR-12).
3. Have Engineering reproduce the P0s on a throwaway copy of the data directory, and add the tests listed in the acceptance criteria.
4. Get counsel's view on teacher-consented use for under-13s, photo handling, retention, and whether "Build Plates" needs organiser agreements.
5. Measure what teachers do (time to set up a class, time to approve a print) before building more social features.
6. Cut the lesson list to the two or three best after testing, and write one proper teacher guide with a printable worksheet and rubric.

*End of report.*
