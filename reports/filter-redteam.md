# ZEIM language / PII filter — red-team report

| | |
|---|---|
| Requested by | Kenji Watanabe (Head of Trust, Safety & Legal) |
| Author | Filter Red-Team Tester |
| Date | 2026-10-04 (all times CDT) |
| Target | `app/community/safety.py` + `app/community/wordlists/`, and every API path that calls it |
| Method | Black-box probing by importing the module with the project `.venv` (`PYTHONPATH=/workspace/photo3d`) and, for the path audit, FastAPI `TestClient` against throw-away `PHOTO3D_OUT` / `PHOTO3D_DATA` dirs under `/tmp`. No server on 8765 or 8798 was started or touched; no app code was edited. |
| Content rule | No slurs or explicit text appear below. Abusive test strings were generated at run time from the app's own word lists and are shown masked (`f***`) or by category. A few benign-but-edgy strings (e.g. "butt joint", "sex education class") are quoted because they are the false positives. |

> **Read this first — the code moved while I tested.** `safety.py` was 251 lines when I started. Between ~16:36 and ~16:38 other agents patched it (now 256 lines, sha256 prefix `7499ee21dfd8`: `MAX_SCAN_CHARS = 2000`, bounded e-mail regex, HTTP 413 `too_long`) and also `classrooms.py`, `links.py`, `builds.py`, `edit.py`, `community.py`, plus a new `textcap.py`. The big sweeps (sections 3–6, 8) ran on the **original** `safety.py` (word logic is unchanged in the patch, so those numbers should still hold, but I have **not** re-run them on the patched file). The path audit (section 7) and the performance re-check ran on the **patched** tree. Please re-run `filter_redteam.py` after the next merge; the project is not a git repo, so I could not pin a commit.

---

## 1. Executive summary

The filter does what the README promises for *obvious* input (whole-word matching, plain leetspeak, spaced letters, accents, fullwidth/"fancy" Latin, triple-stretched letters, plurals/-ing/-ed). It is **easy to bypass** with anything else, and it **blocks a surprising amount of ordinary maker and school vocabulary**. It has **no minor-safety logic** beyond a few list phrases. Individually most gaps are known limits of word lists (the README says so); a few are plain bugs that are cheap to fix.

**Numbers (this run)**

| Area | Result |
|---|---|
| Evasion transforms tested | 84 transforms × 295 abusive words from `en`/`extra` (14 "stem" words, 281 others), plus 13 transforms × 529 list phrases, plus per-language sweeps for 9 languages |
| Benign inputs | 305 maker/school/name/number strings → 69 blocked: **45 genuine over-blocks**, 24 policy-debatable (anatomical terms, slang-looking names, Nazi-history) |
| Dictionary sweep (top ~57–60k words each of en/es/fr/de) | en 351 flagged (**54 are plainly ordinary words or names**), es 209, fr 225, de 188 (many ordinary words, not individually counted) |
| PII / contact | 151 cases → **110 not caught** (email 15/26 missed, phone 22/33, link 24/35, handle/username 33/40, address & personal-info 16/17) |
| Minor-safety phrases | 105 grooming/solicitation patterns → **95 not caught** (10 caught, all by exact list phrases) |
| Languages with no list | 13 probe strings in ja/zh/ko/el/ar/hi/vi/id/tl/romaji → **0 blocked** |
| Path audit | 12 text-input paths checked; all but 2 now go through the gate; error shapes inconsistent |

### Top findings

| # | Sev | Finding |
|---|---|---|
| **F-01** | **High** | The CC-BY licence text file in `wordlists/` is **loaded as a word list** (`WL.glob("*.txt")`). Ordinary words `material`, `information`, `rights`, `license`, `conditions`, `agreements`, `warranties`, `designated` and ~290 licence phrases are now "profanity". A showcase description "Material: PLA …" is rejected with 422 (verified through the API). |
| **F-02** | **High** | The "glued stem" check concatenates **all tokens of the whole message** and substring-matches stems, so it fires across word boundaries: "a bit cheap", "rabbit chair", "habit change", "mini game(s)" are blocked. De-duplicating doubled letters in the stems also makes **Niger / Nigeria / shenanigans / minigames** match. |
| **F-03** | **High** | **Homoglyphs: 0 %** blocked. Swapping letters for Cyrillic/Greek lookalikes (all 295 words, all 529 phrases, all nine languages) is never caught; even a single swapped character beats it ~99 % of the time. Same for small-caps and negative-squared/regional-indicator letters. |
| **F-04** | **High** | **One inserted character defeats 86 % of words** (all but the 14 "stem" words): zero-width space/joiner, soft hyphen, tag/variation selectors, or a visible `. - _ * / space emoji` in the middle. "Self-censored" forms (`f*ck`, `f#ck`) beat 99 %. Vowel-dropping, reversal and ASCII-art leet (`ph`, `|<`, `()`) beat ~99 %. |
| **F-05** | **High** | **Contact-info rules are narrow**: "name at gmail dot com" (the case you asked about) and 14 other e-mail obfuscations pass; **spelled-out phone numbers pass in every language I tried**; `,` `/` `_` separators and 7-digit local numbers pass; only 10 TLDs count as links (`.xyz .ru .co.uk .info .be .gl` pass; "example dot com" passes); a bare `@handle`/`u/name`/`name#1234` passes; only 8 platform names are recognised, and only when followed by another word. No street-address, school, age or location detection at all. |
| **F-06** | **High when chat/DMs ship, Med today** | **No minor-safety pattern layer.** Of 105 grooming-style probes (asking age/location/school, "are you alone", moving to another app, "snap me", "don't tell your parents", requests for pictures) only 10 exact-phrase variants are blocked; any rewording, typo, or Unicode trick passes. ZEIM has no free chat today (canned messages only), which is why I rate it Med now — but titles, descriptions, tags, teacher feedback and display names are all free text that other people read. |
| F-07 | Med | Non-English lists are applied to **all text**: everyday words such as `hard`, `stake`, `gotten`, `finger`, the names `Peter`, `Anita`, `Regina`, `Pitt`; German `nicht`, `bitte`, `weniger`; Spanish `martillo` (hammer), `comer`; French `balle` (ball) are blocked. (Which language list each word comes from is inferred from file names.) |
| F-08 | Med | Phone regex blocks maker numbers: dates/times (`2026-10-04 12:45`), versions, temperature lists, G-code-ish lists, coordinates, prices, "1 2 3 … 10". |
| F-09 | Med | Link/handle regexes block ordinary text: `it.Me`, `good.App`, `ok.Gg` (sentence typos), **"snap fit", "snap together", "snap off"** (maker terms), and any sentence that mentions Discord/Instagram/TikTok/Snapchat followed by a word. |
| F-10 | Med | Unlisted languages (ja, zh, ko, el, ar, hi, vi, id, tl): no coverage; the CJK code path is dormant because no list contains CJK entries. Transliterated Russian 4 %. |
| F-11 | Med | Path gaps/inconsistencies: profile link-out **handles are not language/contact-filtered**; error shape differs (400 `{"detail"}` vs 422 `{"code","message","context"}` vs 413); nickname regex blocks homoglyph/ZW tricks but lets `-`-split names through. |
| F-12 | Med | Stretching: only runs of **3+** identical letters are folded; doubling every letter (every letter repeated) beats 73 %. |
| F-13 | Low (was High) | Long-text CPU blow-up in `scan` (quadratic): 50 000-char word = 44 s, 100 000 chars + `@` = 175 s, 20 000-char e-mail regex = 6.5 s, each pinning the GIL. **Mitigated in the current tree** (2000-char cap, 413). Verified: 2001+ chars refused in 0 ms; 2000 chars scan in 12 ms. |
| F-14 | Low | Emoji unhandled (innuendo, rude-gesture and threat emoji pass); the one emoji entry in `en.txt` can never match. |
| F-15 | Low | Policy/UX: "Are you alone on that printer…" blocked by a list phrase; anatomical terms, `sex education`, `Nazi Germany` (history project) blocked; mild words like `hell/damn/crap` explicitly allowed — confirm this is the intended PG-13 line. |

Severity scale: **High** = defeats the stated purpose or breaks core maker use; **Med** = meaningful gap or frequent annoyance; **Low** = edge case / hygiene.

---

## 2. Scope, corpus and caveats

* **Abusive corpus**: 295 single words (ASCII, ≥4 letters, not allow-listed, baseline-detected) read from `en.txt` + `extra.txt` at run time; 529 multi-word phrases from all lists; non-English entries per language file. Rates below are **over that subset** only.
* "Stem" words (14) are the ones that contain a `stems.txt` entry; they get extra protection (substring match), so they behave very differently from the other 281. The table shows both.
* PII/minor-safety expectations are **my reading of Kenji's brief**, not necessarily the product's documented scope (the README only promises phone numbers, e-mail and links). Where that matters I say so.
* ZEIM has no live chat — "chat" below means any free text others can read.

---

## 3. Evasion results (language filter)

`rate` = share of baseline-detected words still **blocked** after the transform (higher is better). "non-stem" = the 281 words without a stem. Full table (84 rows) in `filter-redteam-results.json` → `sweeps.transforms`.

### 3.1 Passed correctly (≥ 98 % blocked)

spaced letters (`x y z`) and the same with `. - _ , / *` between **every** letter (100 %); stretched vowels / first / last letter ×3+ (100 %); leet digits (98 %) and symbols (99 %); `1`→`i`/`l` leet (100 %); fullwidth Latin, math bold/double-struck, circled, parenthesised, squared Latin (all 100 %, via NFKD); combining accents and 3-mark zalgo on every letter (100 %); NBSP/ideographic space between letters (100 %); bidi-override wrap (100 %); upper/alternating case, plural/-ing/-ed/-er/-y (≈100 %); `big-XYZ` hyphen to another word (100 %); phrases joined with hyphen/underscore/dot (100 %); non-English: spaced letters 100 %, leet 97–100 %, inflection 100 %.

### 3.2 Findings

| ID | Input class (masked) | Expected | Actual (blocked) | Sev | Suggested fix |
|---|---|---|---|---|---|
| E-1 | Cyrillic lookalikes for latin letters, all letters (`f***`-style words) | block | **0/295** words, 0/529 phrases, 0 % in es/fr/de/it/pt/nl/tr/pl | High | Preprocess with the Unicode **confusables skeleton** (UTS #39, see §9) before matching; also flag mixed-script tokens in names/titles. |
| E-2 | One Cyrillic/Greek lookalike in the word | block | 2/295 (Cyr), 3/295 (Grk); stem words 14 % | High | same as E-1 |
| E-3 | Small-caps letters; negative-squared, negative-circled, regional-indicator letters | block | 0/295 each | Med | confusables / extra fold table (these have no NFKD mapping) |
| E-4 | Latin-extended lookalikes (`ł ø đ ı ħ`) | block | 13/295 (4 %); non-stem 2 % | Med | confusables skeleton |
| E-5 | Zero-width space / joiner / non-joiner / word joiner / BOM / LRM in the **middle** of a word | block | 52/295 (18 %); non-stem 13.5 % | High | Strip `Default_Ignorable_Code_Point` + `Cf` characters (UTS #39 skeleton step 2) **before** tokenising. |
| E-6 | Soft hyphen, variation selector, Mongolian VS, tag char, invisible separator, grapheme joiner, enclosing circle, Hangul filler mid-word | block | 5–52/295 | High | same as E-5 (these are not `combining()` > 0, so the accent stripper does not remove them) |
| E-7 | Same invisible char between **every** letter | block | 295/295 | — | (passes only because tokens become single letters) |
| E-8 | One visible separator mid-word: space, `.`, `-`, `_`, `/`, `*`, emoji | block | 52/295 (18 %); non-stem 13.5 % | High | After normalising, also test each *adjacent token pair/triple* joined without separator when the separator is punctuation (not whitespace), and test whole-token letter strings after removing non-letters. |
| E-9 | "Self-censored" vowel replaced by `*`, `#`, `_` | block | 5/295 (2 %); stem words 14 % | High | Same as E-8 plus wildcard-vowel match (`f*ck` → regex over list). Most common real-world form. |
| E-10 | Vowels dropped; word reversed | block | 4/295; 2/295 | Low | vowel-skeleton for long list entries; reversal is rare—optional |
| E-11 | ASCII-art leet (`ph`, `\|<`, `()`, `vv`, `\|)`) | block | 2/295 all-letters; 21/295 single char | Med | broaden `_LEET`: multi-char tokens (`ph`→f, `vv`→w, `\|<`→k, `()`→o) and `(`→c, `<`→c |
| E-12 | Every letter doubled (each letter repeated) | block | 80/295 (27 %); non-stem 27 % | Med | Fold *all* repeated letters (not just ≥3) in a second pass, compare against squeezed list (accept Scunthorpe risk, protect with allowlist). |
| E-13 | One mid-word letter doubled | block | 52/295; non-stem 15 % | Med | same as E-12 |
| E-14 | Word glued to a prefix/suffix/digits/CamelCase (`superXYZ`, `XYZhead`, `XYZ123`, `xxXYZxx`) | block | 14–19/295; non-stem **0–2 %** (stem words 100 %) | Med | Compound split using the list as a dictionary, restricted to long (≥5) entries to limit false positives; or move more entries into `stems.txt` (but see F-02). |
| E-15 | Suffixes `-ness`, `-ish`, `-ly` | block | 14–19/295 | Low | add suffixes (`ness`, `ish`, `ly`, `ful`) to `_SUFFIXES` for entries ≥5 letters |
| E-16 | Multi-word phrases run together (no spaces) / ZWSP in each word / Cyrillic lookalikes / leet / hyphen-underscore-dot joins | block | glued 3 % / ZWSP in each word 1 % / Cyrillic 0 % (leet digits 62 %; hyphen/underscore/dot joins 100 %) | High | phrase check should run on the same normalised stream as words (E-1, E-5, E-8) and also on a no-space version for long phrases |
| E-17 | Emoji as a word (innuendo, rude gesture, threat emoji) | policy | all pass; list contains one emoji entry which never matches | Low | decide policy; load emoji entries as literal substrings (tokeniser uses `\w`, so they are dropped at load) |
| E-18 | Russian: Latin transliteration; Cyrillic word typed with Latin lookalikes; ZWSP mid-word | block | 4 % / 2 % / 2 % (baseline Cyrillic 100 %, spaced 100 %) | Med | translit fold for the ru list; confusables (E-1) |
| E-20 | Japanese, Chinese, Korean, Greek, Arabic, Hindi, Vietnamese, Indonesian, Tagalog, romaji (13 hand-written common-profanity / "die" probes) | block | **0/13** | Med | Add lists. The `scan_language` CJK substring path exists but `_NOSPACE_SCRIPT` finds 0 CJK entries in the shipped lists. Check what extra languages the upstream LDNOOBW project offers (I believe more exist but did **not** verify). Needs native-speaker review. |

---

## 4. False positives

### 4.1 Passed correctly (236 of 305 benign strings)

`Class project`, `Classroom organiser`, `Assess your print quality`, `Assembly instructions`, `Bass guitar stand`, `Compass holder`, `Passion project`, `Analysis of failed prints`, `Cucumber slicer`, `Cockpit canopy`, `Scunthorpe`, `Penistone`, `Middlesex / Sussex / Essex`, `Hancock bridge`, `Peacock feather lamp`, `Shiitake`, `Titanic`, `Dickens`, `Hitchcock`, `Fukushima`, `Bangkok`, `Lake Titicaca`, `Wankel engine`; print bed, nozzle, infill, retraction, stringing, brim/raft, hot end, hotend, extruder, filament, support, belt tensioner, lead screw, bowden, spool holder, glass bed, hardened nozzle, `ball bearing`, `nuts and bolts`, `naked eye`, `shaft collar`, `kill switch`, `abort print`; `Hell yeah`, `Damn, the print failed`, `Crap, I ran out of filament` (allow-listed on purpose); identity-affirming strings ("my friend is gay", pride-flag stands) pass; short foreign look-alikes (`Gift`, `Kind`, `Bad`, `Sein`, `Mist`, `Kot`) pass; numeric strings that are not phone-shaped (`150 x 150 x 150 mm`, `G1 X10.5 Y20.25 Z0.2 F1500`, `1,234,567 grams`, `Year 2026 week 40`) pass.

Note the policy inconsistency: `Holocaust memorial model` and `Slave trade history` pass while `Nazi Germany history project` is blocked.

### 4.2 Genuine over-blocks (45) and policy-debatable (24)

| ID | Input class (benign) | Expected | Actual | Sev | Suggested fix |
|---|---|---|---|---|---|
| FP-1 | Words in the **licence file** loaded as a list: `material(s)`, `information`, `rights`, `license(s)`, `licensor`, `conditions`, `agreements`, `warranties`, `designated`, + 289 phrases (e.g. "terms and conditions") | pass | blocked; API: description "Material: PLA, 0.2 mm layers. More information in the README. License: CC BY." → **422** | **High** | Load only an explicit list of files, or move the licence to `LICENSES/` or rename to `.md`. Add a test that fails if any `*.txt` in the dir is not in an expected set. |
| FP-2 | Cross-word concatenation (§F-02): "a bit cheap/chilly/chunky", "rabbit chair", "habit change tracker", "bit chip holder", "mini game(s) tokens" | pass | blocked (422 via API for "Rabbit chair", "Mini game tokens", "A bit chunky …") | **High** | Restrict the glued-stem test to (a) a single token, or (b) a run of ≤1-char tokens (already joined), never across words; do not squeeze stems. |
| FP-3 | Place names / vocabulary hit by squeezed stems: Niger, Nigeria, Nigerian(s), shenanigans, minigames | pass | blocked ("Map of Niger and Nigeria" → 422) | **High** | as FP-2; add `niger`, `nigeria`, `nigerian`, `shenanigans`, `minigame(s)` to `allow_words.txt` immediately. |
| FP-4 | Everyday words from other languages' lists: `hard`, `stake(s)`, `gotten`, `finger(s)`, `harder`, `hardy`, `spicy`, `spices`, `scatter`, `inferno`, `information(s)`; names `Peter(s)`, `Anita`, `Regina`, `Pippa`, `Pitt`, `Moses`, `Frances`, `Gerber`, `Butters`, `Cummings`; German `nicht`, `bitte`, `weniger`, `reiniger`; Spanish `martillo`, `comer`; French `balle` | pass | blocked ("hard" tag → 422; "Print is hard but I've gotten better" → 422; "Peter Piper", "Civil rights march"[via `rights`], "Cummings desk sign") | Med | Apply each non-English list only when text is in that language (locale / simple language-id), **or** drop entries that are common words in the English top-20k (wordfreq/other frequency list) unless in `extra.txt`. Add frequent given names/surnames to the allowlist. |
| FP-5 | Maker terms: `butt joint`, `butt weld`, `nipple fitting`, `hard stop` | pass | blocked | Med | allow-phrases: "butt joint", "butt weld", "nipple fitting", "hard stop", "hard drive" … (list-driven; owners can extend) |
| FP-6 | `snap fit`, `snap-fit`, `snap together`, `click and snap`, `snap off`, `snap the two halves` | pass | **blocked as a social handle** (platform name + word) | Med | Require handle-like token (digit, `_`, `.` or `@`) or an intent word ("my", "add", "username", "id") before treating `snap`/`insta`/… as an account reference; allow `snap fit/in/together/off`. |
| FP-7 | Platform mentions in normal sentences ("I love Instagram reels", "Discord bot project for class", "Snapchat vs Instagram essay", "WhatsApp is popular", "Kik is a game") | policy | blocked as contact info | Low | Decide: block *sharing an account*, not *naming a product*. Message wording currently says "contact details or links". |
| FP-8 | Sentence-boundary typos that look like domains: `it.Me`, `print.Dev`, `good.App`, `hello.Org`, `this.Tv`, `Ok.Gg`, `Version 2.io` | pass | blocked as links (`.me .dev .app .org .tv .gg .io`) | Med | Run the URL regex on **original-case** text and require a lowercase TLD, or require no space-less capitalised word after the dot; keep `www.`/scheme rule as is. |
| FP-9 | Numbers: `2026-10-04 12:45`, `1234567890 layers`, `v1.2.3.4.5.6.7`, `200 210 220 230 240` (temps), `0.2 0.2 0.2 …`, coordinates, `3.14159265358979`, `1 2 3 … 10`, serial `12 34 56 78 90`, price lists | pass | blocked as phone numbers | Med | Tighten `_PHONE`: after stripping separators require 10–15 digits **and** a recognised shape (NANP `\d{3}[- .]\d{3}[- .]\d{4}`, `+cc …`), exclude decimals and dates (`\d{4}-\d{2}-\d{2}`), and exclude runs where most groups are 1–3 digits with a repeated unit. Prefer "digits ≥ 7 in a 15-char window with ≤ 1 non-digit between" for the *obfuscated* case only. |
| FP-10 | Bird / nursery / tool names (robin, small songbird, bastard file), `Spic and span` | pass | blocked | Low | allow-phrases |
| FP-11 | `Are you alone on that printer or sharing?` | pass | blocked by phrase "are you alone" | Low | Keep (it is a deliberate grooming phrase) but consider context words (printer, machine, task) → allow-phrase. |
| FP-12 | Anatomical terms (science class), `sex education class`, `Nazi Germany history project`, `Dick`/`Moby Dick` as names/titles, `Dyke Road`, joke-name lookalikes, short slang words in German/French/Spanish that are also ordinary words or names | policy | blocked | Low/policy | Product decision. For a kids' maker app blocking is defensible; for school use consider a teacher-managed per-class allowlist. |

**Dictionary sweep** (top ~60k words each, wordfreq): `en` 351 flagged — 54 are plainly ordinary words/names (`hard harder hardy information rights conditions material(s) license(s) peter finger(s) gotten stake(s) nigeria nigerian(s) niger moses spicy spices pitt frances anita regina scatter inferno shenanigans minigames cummings butters gerber designated agreements warranties …`); the rest are mostly genuine profanity or sexual terms, with a few ambiguous ones I did not classify (details, masked, in the JSON). `es` 209, `fr` 225, `de` 188 flagged; a manual skim shows many ordinary words (examples above) but I did not label them exhaustively.

---

## 5. PII / contact-info results

Context: `scan_contact` = four regexes (`_EMAIL`, `_PHONE`, `_URL`, `_HANDLE`) on **lower-cased, un-normalised** text (no NFKD, no invisible-char stripping, no homoglyph folding).

### 5.1 Passed correctly (41 of 151 cases, two of which are "must pass" controls)

Plain e-mail; `(at)(dot)` and `[at][dot]` forms; `name @ gmail . com`; fullwidth `＠`; U+FE6B small at-sign; `name+tag@sub.domain.co.uk`; IDN domains; mixed/upper case; ZWSP inside the local part; `mailto:`. 10-digit US numbers with `- . ( )` and spaces, `+1 …`, UK mobile, `+44`, fullwidth/Arabic-Indic/math-bold digit strings (`\d` matches all Unicode digits). `https://`, `www.`, upper-case scheme, homoglyph in scheme, `.com .net .org .ly`, Discord invite, IPv4 (also with spaces), maps link. Handles: `snap: name`, `my snap is name`, `insta name`, `kik name`, `discord name#1234` (platform name first, one of the 8 covered).

### 5.2 Findings

| ID | Input class | Expected | Actual | Sev | Suggested fix |
|---|---|---|---|---|---|
| P-1 | E-mail with words: "name at gmail dot com", "name AT gmail DOT com", `{at}{dot}`, `<at><dot>`, "at gmail" (no dot), "dot" only, `name-at-gmail-dot-com`, `arroba`/`arobase` forms, "gmail: name", "g mail", "my hotmail is …" | block | **allowed (all 15 missed variants)** | High | Normalise first, then rewrite tokens `at/(at)/[at]/{at}/<at>/arroba/arobase/@` and `dot/(dot)/[dot]/punto/point/.` to symbols, collapse spaces, then run e-mail/URL regexes. Also flag provider names (`gmail`, `hotmail`, `outlook`, `yahoo`, `icloud`, `proton`) + a handle. |
| P-2 | `name@gmail` (no TLD); ZWSP inside the TLD (`gmail.c​om`) | block | allowed | Med | invisible-char strip (E-5); allow TLD-less when provider name present |
| P-3 | Phone, **spelled-out digits** ("five five five one two three …", dashes, upper-case, "oh" for zero, "triple five", mixed digits+words, Spanish/German/French words) | block | **allowed** (all 9 variants) | High | Map number words (en/es/fr/de at least: also `oh`, `zero`, `double`, `triple`) to digits, then look for ≥7–10 digits in a short window. Roblox documents exactly this bypass family (see §9). |
| P-4 | Phone separated by `,` `/` `_` `·`, letters (`5a5a5…`), emoji, ZWSP, keycap emoji digits, leet-letter digits | block | allowed | High | Strip every non-digit between digit groups when the digit count is ≥10 (after number-word folding), within a bounded window; handle keycap (`\d\ufe0f?\u20e3`). |
| P-5 | 7-digit local numbers ("call 555-1234") | block | allowed (regex needs ≥10 chars) | Med | add `\d{3}[- ]\d{4}` when preceded by call/text/number/phone words |
| P-6 | Links: `.co.uk .ru .xyz .info .de .uk .be .gl .link .site .online .cc .to` | block | allowed (only `com net org io gg me ly tv app dev`) | High | Replace the TLD list with the **IANA TLD list** (or at least top ~100 + ccTLDs) but require a *lowercase*, space-free `label.tld` form, and a following `/` or end/space, to limit FP-8. |
| P-7 | Links written as words/obfuscated: "example dot com", `example (dot) com`, `example . com`, `example。com`, `example．com`, `example[.]com`, `hxxps://…`, ZWSP before TLD, Cyrillic `o` in `.com` | block | allowed | High | same normalisation as P-1/P-4 |
| P-8 | Other schemes / hosts: `ftp://`, `javascript:`, `data:`, `localhost:8765`, "tinyurl com abc", "search for X on youtube channel Y" | block | allowed | Med | add `\b[a-z][a-z0-9+.-]*:` schemes and `localhost`; for XSS-ish schemes also reject at render time |
| P-9 | Bare handles: `@name`, `follow me @name`, `u/name`, `name#1234`, `IG @name`, `username: name` | block | allowed | High | `(^|\s)@[\w.]{3,}`, `\bu/\w{3,}`, `\w{3,}#\d{4}`, and `username|user name|id|handle` + token |
| P-10 | Platforms not in the list: YouTube, Twitter/X, Facebook/FB, Roblox, Minecraft, Steam, Twitch, Reddit, WeChat, Skype, Signal, Viber, LINE, FaceTime, gamertag; abbreviations `sc`, `ig`, `fb` | block | allowed | High | extend list; match platform + (`:`, `@`, `is`, `me`, `my`, `add`, `follow`) + token. Roblox's open-sourced model uses the categories "asking for PII / giving PII / directing off-platform" (see §9) — adopt that taxonomy. |
| P-11 | Platform names obfuscated: ZWSP, homoglyph, leet (`d1scord`), `s.n.a.p`, `s n a p`; 13+ chars between platform and token | block | allowed (one long-gap case blocked) | High | normalise (E-1, E-5), de-leet, collapse single-letter runs in `_HANDLE` too |
| P-12 | "Add me on snap", "snap me", "whatsapp me", "dm me", "text me", "pm me" | block | allowed | High | see §6 (off-platform intent), these are the *most common* real phrasing |
| P-13 | Street address ("42 Oak Street", "17 Maple Ave"), PO box, ZIP, UK postcode, city+state, "I live in <town>", school + town, GPS coordinates, what3words, plus code | block | allowed (only a maps *link* was blocked) | High | Add: `\b\d{1,5}\s+\w+(\s\w+){0,3}\s+(st|street|ave|avenue|rd|road|blvd|ln|lane|dr|drive|ct|way)\b`, US ZIP+state, UK postcode regex, lat/long pairs, "I live (in|at|on)", "my school is/I go to". Expect FPs ("Main Street USA diorama" must still pass—test). |
| P-14 | Self-disclosed age/name/birthday/"home alone" ("I am 11 years old", "My name is … and I am 11", "my birthday is …", "I'm home alone") | block (my reading of the brief; README does not promise it) | allowed | Med | Minecraft's partner servers filter numbers incl. ages (§9); add `\b(i'?m|i am)\s+\d{1,2}\b` and "my name is" patterns for under-18 contexts. |

---

## 6. Minor-safety patterns

The filter has **no grooming/contact-solicitation logic** other than 23 exact multi-word entries in `extra.txt` (e.g. "how old are you", "where do you live", "what school do you go to", "are you alone", "send pics" — the 10 cases that passed). I tested 105 phrasings in 5 classes; every reworded, abbreviated, mis-spelled, leetspoken, homoglyph or ZWSP-split variant passed.

| ID | Input class | Expected | Actual | Sev | Suggested fix |
|---|---|---|---|---|---|
| M-1 | Asking age/personal info: "what is your age", "asl / a/s/l / age?", "what grade are you in", "when is your birthday", "are you a boy or a girl", "do you have a boyfriend", "hw old r u", other languages ("wie alt bist du", "quel âge as-tu") | block | 5/21 blocked (only exact "how old are you" + spacing/leet variants) | High (latent) | regex family `how|what|hw` + `old|age|grade|birthday` + `you|u|ur|your`, abbreviations (asl, a/s/l), per-language; run on normalised text (E-1, E-5, E-8) |
| M-2 | Asking location/identity: "where are you from", "what city/town/state", "what is your address / zip / last name / real name", "which school are you at", "where r u", leet / ZWSP variants | block | 3/21 blocked | High (latent) | same approach; fold `u/ur/r`, 1-character typos; add school/city question templates |
| M-3 | Moving off-platform: "let's talk on discord", "add me on snap", "**snap me**", "message me on whatsapp", "find me on roblox", "dm/pm/text/call/email me", "give me your number", "do you have snapchat", "let's go private", "this chat is monitored, talk elsewhere", obfuscated `s n a p`, `sn4p`, `sn\u0430p`, `snaaaap` | block | **0/27** | High (latent) | intent patterns (verb: add/message/find/hit/dm/pm/text/call + `me` + platform) and generic "somewhere else / private / another app" phrases; treat *any* platform mention with `me`/`my`/`add` as off-platform intent. Roblox treats "directing users off platform" as its own label with a deliberately low threshold (§9). |
| M-4 | Secrecy / isolation: "don't tell your parents/teacher", "our little secret", "keep this between us", "are your parents home", "is anyone home", "delete this message", "no one has to know" | block | 1/15 blocked ("are you alone") | High (latent) | add phrase patterns (with `dont/don't/do not`, curly apostrophe, `ur/your`), `parents|mom|dad|teacher` + `home|know|find out` |
| M-5 | Pictures/meeting/rewards: "send me a pic/photo of yourself", "show me your face", "turn on your camera", "video chat", "what are you wearing", "you're so cute", "come to my house", "meet me after school", "I'll buy you robux / send a gift card", "can we meet in person" | block | 1/21 blocked ("send pics") | High (latent) | same; add reward-for-contact patterns |
| M-6 | Benign class talk that must pass ("Where do I find the infill setting?", "What age group is this lesson for?", "Can you send me the STL file in class?", "Let's meet at the printer after lunch") | pass | 8/9 pass; "Are you alone on that printer…" blocked | Low | see FP-11 |

**Why "latent":** ZEIM currently has canned messages only (`CANNED`), so there is no stranger-to-child free text channel. Free text that others *do* read: display names, class names, nicknames, project/Showcase titles, descriptions, tags and teacher feedback. These patterns become **High** the moment comments, DMs or any chat arrives, so the pattern layer should land before that feature, not after. Context-free regexes will always miss paraphrases — Roblox's own write-up says exactly this (§9).

---

## 7. Where the filter is (and isn't) applied — input-path audit

Tested on the **patched** tree (~16:38–16:44) via `TestClient`; `lang`/`contact` = the same `safety.scan`. "Evasions" column shows which of my standard evasion strings (homoglyph, mid-split `-`, obfuscated e-mail, `.xyz`, bare `@handle`, "snap me") still got through (`✓`=blocked, `✗`=accepted).

| Path | Field | Gate | Plain abusive | Evasions | Notes |
|---|---|---|---|---|---|
| `POST /api/me/signup` | `display_name` (≤40) | `filter_only` → 400 `{"detail"}` | ✓ | homoglyph ✗, split ✗, obfuscated mail ✗, `.xyz` ✗, `@handle` ✗, snap me ✗ | No rename endpoint found, so a display name is only checked once. |
| `PUT /api/me/links` | handle for tiktok/instagram/reddit/patreon | **none** — only `^[A-Za-z0-9._-]{2,30}$` | **accepted** | accepted: abusive word, 10-digit number, `kid.gmail.com`, `@name` | Shown on profile (adults) as "link-outs". Non-ASCII refused by the regex, so homoglyph is blocked incidentally. **Med** (F-11). |
| `POST /api/classrooms` | class `name` (≤60) | `filter_only` → 400 | ✓ | homoglyph ✗, split ✗ | e-mail/phone ✓ |
| `POST /api/classrooms/join` | `nickname` | regex `^[A-Za-z0-9 _-]{2,20}$` + `filter_only` → 400 | ✓ | homoglyph ✓ (regex), ZWSP ✓ (regex), split with `-` ✗ | Best-protected path because the charset is ASCII-only. |
| `POST /api/generate` | `title` form field | now `filter_only`/`gate` → 400 | ✓ | — | Filename-derived default title now passes through `_safe_title` (falls back to "Untitled"). I did **not** see the pre-patch behaviour. A false positive on a filename silently becomes "Untitled". |
| `POST /api/edit/new` | `title`, uploaded filename | `filter_only` → 400 for title; filename sanitised | ✓ | — | same note |
| `POST /api/showcase` | `title` (≤80), `description` (≤500), each `tag` (≤8) | `gate` → **422** `{"code","message","context"}` | ✓ | same ✗ list as signup | Tags non-string / string input now 400. |
| `POST /api/classrooms/{c}/projects` | `title` (≤60) | `gate` → 422; empty title falls back to the build title (now sanitised) | ✓ | homoglyph ✗, split ✗ | |
| `POST /api/classrooms/{c}/projects/{p}/feedback` | teacher `comment` | `gate` → 422 | ✓ | homoglyph ✗, split ✗, obfuscated mail ✗, `.xyz` ✗, snap me ✗ | Teachers are adults, but the comment is shown to a child. |
| `POST /api/showcase/{id}/report`, feedback report | `details` (≤1000) | none | n/a | — | moderator-only; fine, but moderators see raw PII/abuse. |
| Messages / requests | canned only | n/a | — | — | Good design: no free text. |
| Not built / not found | "Build Plate" (hobbyist group) names, usernames beyond `display_name`, comments, DMs | — | — | — | `branding.py` has the name, no endpoint exists yet. **When Build Plates ship, their names/descriptions must be wired to `safety.gate` from day one.** |

Other path observations

* **Error shape/status is inconsistent**: `filter_only` callers (signup, class name, nickname, build/edit titles) return 400 `{"detail": "<message>"}`; `gate` callers return 422 `{"code","message","context"}`; over-length now returns 413 or 400 depending on caller. Clients must special-case each (README says "the sender sees exactly: …"). Suggest one `ChatBlocked → JSON` handler registered app-wide.
* Filter runs on **create** only; the data already stored is not re-scanned when the lists change (e.g. after fixing F-01 or adding words). A periodic re-scan job for public items would close that.
* Everything is server-side; I did not test the browser UI, share pages (`/p/{id}`) or how titles are escaped on render.

---

## 8. Robustness / performance

| Input | Original `safety.py` | Patched `safety.py` |
|---|---|---|
| 10 000 chars, one word | 1.5 s | refused (`too_long`) in 0 ms |
| 50 000 chars, one word | **43.9 s** | refused in 0 ms |
| 20 000 chars, no `@` (e-mail regex) | 6.3–6.5 s | refused |
| 20 000 chars `a.` repeated (URL regex) | 5.9–7.2 s | refused |
| 30 000 chars + `@` | 14 s | refused |
| 100 000 chars + `@` | **174.6 s** | refused |
| 20 000 fullwidth chars | 6.9 s | refused |
| 200 000 chars of spaced prose | 2.3 s | refused |
| 2 000 chars of one word (cap) | — | 12 ms |

The same issue is documented as **S-02** in `reports/safety.md`; the current cap and bounded `_EMAIL` look correct. Residual: Work is still superlinear on a long single token, but at 12 ms for the 2 000-char maximum it is not a concern. No crashes on the odd inputs I tried (empty, NUL, replacement char, emoji runs, newlines).

---

## 9. Global research (public web, pages actually fetched on 2026-10-04)

I only cite pages I opened with the fetch tool. Where a vendor publishes no technical detail I say so instead of guessing. I could not open the Reddit thread about Printables rejecting profanity in model titles (blocked), so I make no claim about Printables' title filter.

| # | Source (fetched) | What it says (summary, not quotation) | Relevance to ZEIM | Rec. |
|---|---|---|---|---|
| R-1 | Roblox, "Safety Tools and Policies" — https://about.roblox.com/safety-tools | Built-in chat filters block discriminatory speech, extremism, violence, sexual content and also catch **requests to move off the platform** and requests/shares of personal information; a "rephrasing" feature rewrites profanity; repeated attempts trigger a warning, then temporary blocks/suspensions; age checks gate chat. | Confirms that "off-platform" and PII are treated as first-class categories next to profanity — the gap in §5/§6. ZEIM's README promises **no strikes**; warning-then-block is escalation, rephrasing needs UX work. | **Adapt** (adopt the three categories; keep "no strikes", add teacher-visible counts only) |
| R-2 | Roblox engineering post, "Open Sourcing Roblox PII Classifier" (Nov 2025) — https://about.roblox.com/newsroom/2025/11/open-sourcing-roblox-pii-classifier-ai-pii-detection-chat | Says PII detection "can be bypassed" by industry-standard tools; lists bypass families (character-level manipulation such as diacritics/odd spellings, spelling letters out, NATO-style alphabets, implicit references to a platform without naming it); blocks all detected PII by default for younger users; used **human and LLM red-teaming** and fed misses back into training. Reports 98 % recall at 1 % FPR on its *own* English test set (vendor figures, not independently verified). | Same bypass families I found (§3, §5). Their red-team loop = what this harness should become. | **Adapt** (copy the practice — labelled bypass corpus, regression-tested; not the model) |
| R-3 | Hugging Face model card, `Roblox/roblox-pii-classifier-v2` — https://huggingface.co/Roblox/roblox-pii-classifier-v2 | Context-aware classifier (XLM-RoBERTa-Large, ~0.6 B params) with three labels: asking for PII, giving PII, **directing users off-platform**; evaluates the message **with surrounding conversation**; claims 189 languages; suggests per-label thresholds (off-platform deliberately low). | Good label taxonomy for ZEIM's rule layer. Running a 0.6 B model inline is heavy for a small self-hosted app, and I did not check the model licence. | **Adapt** taxonomy now; **reject** inline model for the pilot; revisit as an *offline/batch* second check once there is chat |
| R-4 | Minecraft, "How to Stay Safe Online" (2017 article) — https://www.minecraft.net/en-us/article/minecraft-multiplayer-server-safety | Official chat filter word lists expanded over time; partner servers add filters for **e-mail addresses and numbers including phone numbers and ages**; private messaging removed on partner servers "to allow more thorough moderation"; child accounts default to communication blocked until a parent allows; mute/block/report in the pause menu. | Supports canned-only/no-DM stance and an **age-number filter** (P-14). Article is old; current Mojang policies may differ. | **Adopt** (no private channels; filter ages/numbers) |
| R-5 | Scratch Help Center, "Updates to the Filter System" — https://mitscratch.freshdesk.com/en/support/solutions/articles/4000228373-updates-to-the-filter-system | Comment filter shows a message explaining *why* a comment was blocked, tells users how long they are muted, and has a built-in form to **report filter mistakes**. | ZEIM shows one fixed message; false positives (§4) are frequent and users cannot say so. | **Adapt** (add "this looks wrong" button feeding an allowlist review queue; keep the fixed wording for abuse) |
| R-6 | Scratch Wiki, "Community Guidelines" (summary of the official guidelines) — https://en.scratch-wiki.info/wiki/Community_Guidelines | Personal info not to be shared: real last names, phone numbers, addresses, **hometowns, school names**, e-mail, usernames/links to social media, video-chat apps, sites with private chat. Violations → alert, then temporary block. (The official page itself rendered empty to my fetch tool, so I rely on this wiki summary.) | Gives a ready scope list; compare with §5.2 P-13 (hometown/school missing in ZEIM). | **Adopt** as scope checklist |
| R-7 | Tinkercad Help, "Share class link / code" — https://www.tinkercad.com/help/classrooms/share-class-link-code | Teachers can create **Class Seats**: logins made by the teacher, no student e-mail; under-13 social sign-ins get a **random username** (teacher can edit display names); class codes can be regenerated. | If nicknames are teacher-assigned or randomly generated (e.g. "Blue Otter 42") the nickname filter becomes nearly unnecessary and homoglyph/split attacks vanish. | **Adopt** (default random nickname; teacher may edit) |
| R-8 | Tinkercad Blog, "TinkerTips: Safe Mode" — https://www.tinkercad.com/blog/tinkertips-safe-mode | New class members are in **Safe Mode** by default: limited Gallery view, **cannot make designs Public**, cannot change their screen name; teacher turns it off per student/class. | ZEIM's classroom projects are already classroom-private; model the same defaults for any future public/comment features. | **Adopt** (restrictive default for class members) |
| R-9 | Printables, "Messenger rules" (Prusa KB) — https://help.prusa3d.com/article/printables-com-messenger-rules_335533 | Human-readable rules (no harassment, hate, sexual objectification, spam, advertising); enforcement by moderators up to permanent ban. Reader comments on the page report an account disabled by an **automated spam classifier** with no obvious appeal path. | Shows the cost of opaque automation (false positive → lost account). No technical filter detail published. | **Adapt** (publish rules + an appeal contact; never auto-ban) |
| R-10 | Thingiverse forum guidelines — https://forum.thingiverse.com/guidelines | Civility rules enforced mainly by **user flags** ("if enough flags accrue, action will be taken automatically or by a moderator"); moderators do not pre-screen posts. | Reactive only; not suitable for under-18 audiences on its own. The flag-threshold auto-hide idea is what ZEIM already does for `minor_safety` reports. | **Reject** as primary model; **adopt** flag-threshold auto-hide for other report reasons |
| R-11 | MakerWorld Community Guidelines (updated 2026-04-27) — https://makerworld.com/en/community-guidelines | Category-based policy (harassment, doxxing/personal info, a "Minor Safety — zero tolerance" section, spam/"redirect users off-platform"), enforcement ladder and an appeal route. No word-filter details published. | Good policy template to align `COMMUNITY_GUIDELINES.md` with; says nothing about technical filtering. | **Adapt** (policy structure + appeal; not a technical source) |
| R-12 | Wikipedia, "Scunthorpe problem" — https://en.wikipedia.org/wiki/Scunthorpe_problem | Catalogues false-positive incidents (surnames, towns, "bone", "summa cum laude", clbuttic substitution); names the standard workaround: **allow-lists of known false positives**. | ZEIM's allow-list approach is right; F-01/F-02/F-07 show the lists are not tested against real vocabulary. | **Adopt** (add a regression corpus of names/places/maker terms, run in CI) |
| R-13 | Unicode UTS #39 "Security Mechanisms" — https://www.unicode.org/reports/tr39/ | Defines the confusables **skeleton**: NFD, remove Default_Ignorable code points, map each char to its prototype; mixed-script detection; says results are for comparison, not display; warns the data can over-match. | Directly fixes E-1…E-6 (homoglyphs, invisibles). Use the skeleton **only for matching**, never to alter stored text. | **Adopt** |
| R-14 | FTC, "Children's Online Privacy Protection Rule: A Six-Step Compliance Plan" — https://www.ftc.gov/business-guidance/resources/childrens-online-privacy-protection-rule-six-step-compliance-plan-your-business | Personal information includes name, home address (street and city), online contact info incl. IM/video-chat identifiers, phone numbers, screen names that function as contact info, geolocation; "collect" includes letting kids make information public through open chat/posting **unless reasonable measures** delete "all or virtually all" PI first. | The filter is part of such "reasonable measures" for under-13 class users. Measured PII miss rates (§5) are therefore a **compliance** input, not only a quality metric. **Not legal advice — flag for counsel** (your item #1). | **Adopt** (track filter recall as a launch gate; counsel to decide the bar) |

Not found / not verified: published word-filter internals for Thingiverse, Printables or MakerWorld; Tinkercad's comment-filter behaviour (a search summary said comments are disabled in Safe Mode, but the page I opened does not say so, so I do not rely on it); any Roblox/Minecraft false-positive rates.

---

## 10. Suggested fix order

1. **Today (list/regex only, no design work):** remove the licence file from the list glob (F-01); delete the cross-word stem test or restrict it to a single token and stop squeezing stems (F-02); allow-list Niger/Nigeria/shenanigans/minigames; add a test that fails when a non-list `.txt` is in `wordlists/`.
2. **This week:** one `normalise()` used by language *and* contact scans: NFKD → strip Default_Ignorable/Cf → UTS #39 confusables → fold leet/ASCII-art leet → map number words and `at/dot` words (§3, §5). Re-run this harness; target ≥ 95 % on E-1…E-9 and P-1…P-10.
3. **Before any chat/comments/DM ships:** pattern layer for M-1…M-5 using Roblox's three labels (R-2/R-3); teacher-visible flag counts (no strikes); "report a filter mistake" button (R-5); default random nicknames (R-7).
4. **Next:** language-aware list activation (FP-4), tighter `_PHONE`/`_URL` (FP-8/9), ungated `/api/me/links` handles (F-11), unify error shape, re-scan job when lists change.

---

## 11. What passed, in one paragraph

Whole-word matching and the allowlist hold up well on classic Scunthorpe cases and on 3D-printing vocabulary (236/305 benign strings pass); spaced/dotted/dashed letters, digit and symbol leetspeak, stretched vowels, accents/zalgo, fullwidth and "fancy" Latin blocks, and inflections are reliably caught in English and eight other languages; ASCII phone numbers, plain/`(at)(dot)` e-mails, scheme/`www`/common-TLD links and IPv4 addresses are caught; the classroom nickname regex neatly shuts out homoglyph and zero-width tricks; the new 2 000-char cap closes the CPU-exhaustion hole; the filter never crashed on odd input; and all class messaging is canned, which removes the largest category of risk.

---

## 12. How to reproduce

```bash
cd /workspace/photo3d
export PYTHONPATH=/workspace/photo3d
# main harness: evasion sweeps, list integrity, languages, dictionary sweep, 573 fixed cases, performance (~6–8 min)
.venv/bin/python reports/filter_redteam.py        # -> reports/filter-redteam-results.json (words masked)
# path audit via TestClient with throw-away PHOTO3D_OUT/DATA (~5 s)
.venv/bin/python reports/filter_redteam_paths.py  # -> reports/filter-redteam-paths-results.json
```

* Dictionary sweep needs `/tmp/rt_corpus_{en,es,fr,de}.txt` (built with `wordfreq` in `/tmp/rtvenv`; not part of the app venv). Without them that section is skipped.
* The scripts take abusive English inputs from the app's own lists at run time; they do contain a few mild non-English profanity probes and some name/place look-alikes in the benign set. Treat the script and JSON files as internal.
* The original `safety.py` was not saved; I can only point to the sha256 of the patched one (`7499ee21dfd8…`). The 8798 temp instance was not needed.

---

## 13. Hansei (reflection)

**What I could not cover**

* **The real UI.** Everything here is API/module level. I did not drive the browser, so client-side filtering, escaping on render (`/p/{id}` share pages, Showcase cards) and UX of the error message are untested.
* **Context.** The filter sees one string at a time; I did not test attacks spread over several messages/fields (e.g. half a phone number in the title, half in a tag) or repeat-attempt behaviour.
* **Languages.** Beyond the shipped lists I used 13 hand-picked probes with no native-speaker review; "0/13" is a signal, not a measurement. My other-language false-positive impressions come from my own skim of flagged words.
* **Images, file contents, 3MF/STL metadata, EXIF** (names or text inside uploads) — out of scope, but real channels.
* **Severity and "expected".** Several expectations are mine (age/"I'm home alone" disclosure, platform mentions, anatomical terms). Kenji/counsel may decide differently; I tried to separate policy from bugs, but the line is judgment.

**What I probably got wrong or over-claimed**

* The code changed under me (patches at ~16:36–16:38). The main sweeps ran on the original file and the path audit on the patched one; I did not re-run everything on the final tree, and I did not keep a copy of the original — someone should verify F-13's "mitigated" claim with their own run.
* My corpus is only 295 words (14 stem, 281 other). The "86 % bypass" figure is for that subset; list entries that are multi-word, foreign, <4 letters or non-ASCII were handled in separate, smaller sweeps. The "word order swapped" and "filler word between" rows in the phrase sweep are not meaningful attacks and should be ignored.
* "54 of 351 flagged words are benign" is my eyeballing of a wordfreq top-60k list that itself contains slang and profanity; the real false-positive rate on kids' actual text is unknown. I have no corpus of real student/teacher text.
* Some of my "should be blocked" PII probes (e.g. `username: name`) would also match innocent text; I did not measure the false-positive cost of the fixes I suggest, and several suggested regexes are sketches, not tested code.
* A few process slips: my first full run was wasted on a script bug (licence file in the integrity loop), and one early path-test label wrongly blamed the nickname regex for a filter block (fixed in the script).

**What I would change next time**

1. Pin a commit (or copy the tree) before testing, and agree a freeze window with engineering.
2. Build a labelled, versioned corpus (benign maker/school text × attack variants × languages) so precision and recall are reported together and can gate CI.
3. Add a native-speaker pass for the top three non-English languages the product claims to support, and an educator pass over the false-positive list.
4. Drive the real UI (and the 8798 instance) for a smaller end-to-end set, including how blocked text is displayed.
5. Ask counsel what recall bar the filter must hit for the under-13 classroom flow (FTC "reasonable measures", §9 R-14) so that severity can be tied to a requirement rather than my opinion.
