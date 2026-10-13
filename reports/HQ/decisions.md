# HQ decisions
- 2026-10-13: Zach decided PrusaSlicer licensing follows the MakerWorld model: ZEIM's own code stays PRIVATE; PrusaSlicer (AGPL-3.0) is used unmodified as a separate program called through its command line; ZEIM shares only PrusaSlicer's own source (attribution + upstream link on credits/footer). Nobody may modify, patch or link PrusaSlicer code into ZEIM. Repo visibility is not changed. (Team's reading, not legal advice.) Supersedes the 2026-10-12 "source must be available" note.
- 2026-10-12: Zach decided ZEIM launches with no lawyers. Legal pages use plain wording from common free templates, with no compliance claims. DMCA agent registration (small fee) waits for Zach's OK. PrusaSlicer AGPL: source must be available to users; repo visibility is Zach's call.
- 2026-10-12: Zach removed school features; no grades/school records held. No teacher tools, classrooms, class codes, assignments, quizzes or scores. ZEIM stays free and family-friendly; kids use it with their families.
- Free, family-friendly. No paid content, no NSFW. Humble positioning (no "better than" claims).
- Teens (13-17): Private only at launch; adults cannot follow teens; no public profile/project.
- Likes require account once auth exists; no dislike; example items show no invented counts; counts hidden for minors.
- Chat: disallowed language is blocked with "Chat doesn't allow that language. Please use appropriate language." No strikes/bans.
- Work order: safety Critical/High -> auth/DB/upload hardening -> accessibility -> Take-a-photo camera button -> Build Plates groups (last).
- Group name: Build Plates. Product name: ZEIM.
- Local only until Zach decides hosting, moderators, pilot, domain, budget.
- Escalate to Zach: money, public launch, legal commitments, minors' data, deletions.
- Send hub (Zach, iPhone/iPad/Creality K1/Creality Cloud/Shapr3D): order = download -> Web Share API (needs HTTPS) -> email-to-self LATER.
- Email-to-self: only to the signed-in account's own address, rate-limited, needs real accounts + mail provider (cost/setup = Zach decision). Never a typed-in address.
- Sending outside ZEIM (cloud/app/printer) is a separate explicit step chosen by the user. Minors' photo-based models are NOT sent outside ZEIM by default.
- Pop-art OBJ/3MF non-manifold edges must be fixed BEFORE Send ships. Hollow/Simplify must not report watertight success on bad meshes.
- Local HTTPS test option (Caddy internal cert) is approved for testing on Zach's devices; HOST env var for binding (default 127.0.0.1).
- Creality Cloud / Shapr3D integration status: unverified until Daichi's reports/integrations.md; label "untested" until Zach tries on real devices.

## Send-hub privacy (approved by Mr. Yami Kato, per Kenji's reports/send-privacy.md)
- Teens: Download of own builds only. (Per-class Send switch removed with school features, 2026-10-12.)
- Before Send ships: /f/<token> scoped to one file, 5-10 min; redact tokens in server.log; require public base URL in shared mode; share sheet uses logged-in download, never a link; generic 3MF object name; never bundle uploaded source (EXIF/GPS).
- Download stays primary (Web Share unproven on iOS). No direct-to-printer promise from hosted ZEIM. Encrypt printer API keys.
- Third-party terms (Creality, Dropbox, Google) remain unverified until full text is read.

## Filter messages for all free-text fields (Mr. Yami Kato)
- Language block message everywhere: "Chat doesn't allow that language. Please use appropriate language." (verbatim).
- Inline next to the field (not a vanishing toast); the box keeps what the user typed.
- Personal-info block is a second, separate message: "Please don't put names, phone numbers, emails or links here."
- Text-tool and other free-text inputs: server-side language + PII filter on create and later edits, with a length cap.

## TOP PRIORITY (Zach, 2026-10-04 4:50 PM): photo upload broken + no camera option
- Haruto: diagnose/fix upload with regression test; add "Take a photo" (capture=environment on phones, getUserMedia on desktop, strip EXIF/GPS). Ren Ishikawa verifies via real UI at phone size before "fixed".

- 2026-10-12 18:41 CT (auto-approved after 6h, reversible): resin 0.2 mm = Experimental opt-in only; Wildlife Calls no classroom-only hold (schools removed); phone tests via existing ngrok/local-https; printer pref = account + localStorage; Experienced/Newest labels confirmed.
