# ZEIM / Spark Lab video library (2026-10-04)

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


Data: `reports/education-video-library.json` (25 entries). Written by the Spark Lab Curriculum Writer. No app or static files were touched.

## READ THIS FIRST
**Nobody has watched these videos end to end.** I cannot watch video. I checked links and metadata only, so a teacher must preview every video before class. I did not check for adult language, ads shown during playback, comment sections or what YouTube recommends next. Titles and "why it helps" lines rest on the page title and description, and the notes say where I could not see more.

## Method
1. Found candidates with WebSearch and YouTube's public search-results page.
2. For each one, fetched YouTube oEmbed (`/oembed?url=...&format=json`) and the watch page over HTTP.
3. Kept an entry only if both returned HTTP 200, playability was OK, and the oEmbed title and channel matched the watch-page title and owner name.
4. `duration_seconds_or_null` is the `lengthSeconds` value in the watch-page player data. Every kept entry had one, so none is null.
5. Read titles and descriptions for sponsorship, affiliate links, superlative claims, "better than" claims and unclear sources. Matching words are listed in each entry's `notes`.
6. Fetched with Python HTTP requests (same as curl), not literal `curl`. Discovery also used YouTube's search page. Transcripts were not available, so spoken content is unchecked.

## Counts
- Distinct videos fetched: 52. Kept: 25. Failed verification: 0 (one near-miss, a trailing space in a channel name, was matched after trimming).
- Per topic: CAD basics 5; printing basics 4; printer safety 4; lithophanes 4; measuring/tolerance 4; layers/slicing 4. Total runtime is about 2 h 53 min.
- Excluded for quality, 13: affiliate, sponsor or promo links (5), clickbait or hype (2), vendor marketing (3), blank or unclear source (3).
- Not selected, 14: duplicates, surplus or very short clips.

## Caveats
- **Embedding allowed: unknown for all.** Each entry also records `playableInEmbed` from page data, but I did not test an iframe. Link out until someone tests embedding.
- **Safety videos are adult-oriented.** Use them to brief teachers or older students. The ZEIM rule stands: an adult operates the printer.
- **Shapr3D (vl-16):** this is professional CAD. Its help-center text says it is licensed monthly or annually. I did not check free-tier limits.
- **Lithophanes:** vl-12 uses a web converter. Don't upload students' photos to any converter unless the school approves it. vl-11 is a student-made video, not the museum's.
- Videos can be removed or edited, and the "Content not watched" caveat applies to every `verify_method`. Re-run the check before each term.
- Suggested age bands and durations are guides only. The ages are my judgment from titles and descriptions.
