# ZEIM Team Charter (set by Mr. Yami Kato, 2026-10-12, on President Zach's order)

Goal: app fully coded and ready within one month (target 2026-11-12).

## Access
- Code: GitHub https://github.com/zachsmalone/3d-printer-app.- , branch `zeim` (source of truth). Local copy: /workspace/photo3d (remote `origin`). Run `git fetch origin` before every check; test the latest origin/zeim on your own scratch port, never :8765.
- Everyone can read all code, CI runs, and reports. You write only under reports/ or curriculum/. App code goes through Mr. Yami Kato's build line, pushed to `zeim` after the full suite passes.

## Roles (own lane + cross-check partner)
| Bot | Owns | Cross-checks |
|---|---|---|
| Ren Ishikawa (QA) | Regression, mesh/slicer, Originals printability | Ren Okabe's CI |
| Filter Red-Team Tester (Safety) | Filter, PII, minors' safety, visibility rules | Spark Lab's lessons and teacher tools |
| Accessibility Reviewer (Design) | WCAG, plain language, warm look, modes | Safety messages are clear and kind |
| Spark Lab (Education) | Lessons, teacher guides, video library | Design fits real classrooms |
| Ren Okabe (DevOps) | CI, hosting, backups, deploy, disk | QA tests reproducible, CI matches local |

## Rhythm
1. Daily 5-line HQ status: done / doing / blocked / cross-check result / next.
2. Cross-check your partner daily; resolve with them first, then escalate to Mr. Yami Kato.
3. PASS only after re-testing the latest origin/zeim commit (name it).
4. Kids' data safety outranks every feature and date. Spending, launch, legal, minors' data and deletions go to Zach.
