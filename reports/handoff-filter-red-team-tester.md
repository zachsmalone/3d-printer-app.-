# Handoff: Filter Red-Team Tester (2026-10-04)

## What I did
- Red-teamed the ZEIM language/PII filter and swept the user-input paths. No app code was edited. Testing used module import and temp dirs only; ports 8765 and 8798 were not touched.
- Report: `/workspace/photo3d/reports/filter-redteam.md` (6 High, 6 Med, 3 Low). It has findings with input class, expected, actual, severity and fix. It also has a Global research section (14 fetched pages, each with adopt/adapt/reject) and a Hansei section.
- Summary sent to Kenji Watanabe and to the Hq2 room.

## Top findings
1. A CC-BY licence file is loaded as a wordlist, so ordinary words are blocked.
2. Cross-word stem matching causes false positives (e.g. "rabbit chair", "Nigeria").
3. Normalisation is inconsistent: Cyrillic lookalikes, a single invisible character or separator, and `f*ck`-style masks mostly get through.
4. PII recall was low (41 of 151 caught): obfuscated email, spelled-out phones, bare @handles and street addresses were missed.
5. Minor-safety probes mostly got through (95 of 105). This is latent until free chat exists.
6. Path inconsistencies: profile link handles are unfiltered and error shapes differ across endpoints.

## Unfinished
- Numbers mostly come from the pre-patch `safety.py`. Other agents patched it around 16:36-16:38 on 2026-10-04, and I did not re-run everything. The repo was not pinned at that time.
- Kenji's request still open: after Haruto reports the filter patches landed on HQ/board.md, re-run the word/evasion sweeps and the path audit on the same commit. Report before/after numbers and new false positives in filter-redteam.md.
- Kenji's request still open: post a one-line STATUS to HQ/board.md. I did not do this.
- Design checks for the Send features (not tested): "email to yourself" should only go to the signed-in account's address and be rate-limited; sending to external clouds or printers should be an explicit user step, off by default for kids' accounts.
- Kenji's decided PII bar: block obfuscated email, phones (including spelled-out), bare @handles and URLs/domains anywhere other people can read; street addresses best-effort; minor-safety phrases deferred until free chat exists.

## Files
- `/workspace/photo3d/reports/filter-redteam.md` (not yet committed; Ren Okabe offered to commit it)
- Test scripts: see the "reproduce" note inside the report.
