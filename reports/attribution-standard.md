# ZEIM Attribution & Credits Standard (v0.2 DRAFT)

Owner: Kenji Watanabe, Head of Trust, Safety & Legal. v0.1 written 2026-10-04 (CT); **v0.2 2026-10-04 evening**.
Status: draft for Mr. Yami Kato / Zach. Engineering builds it, Design (Sakura) designs the page, Daichi puts the wording in README/ROADMAP/launch copy.

> **Kenji is not a lawyer. This document is a working standard, not legal advice, and nothing in it says ZEIM "complies" with any law or licence.** Every line tagged **needs counsel** must be read by a qualified lawyer before public launch. Every line tagged **UNVERIFIED** is something I could not confirm from a primary source on 2026-10-04.

Zach's principle: *be honest, honorable and respectful of others' work, in the spirit of gratitude.* In practice: when someone offers a model for free use, we credit them properly, visibly and every time, even when the licence would not force us to (CC0, public domain). We make it easy for them to ask us to change or remove their work, and we answer kindly.

### What changed in v0.2 (Zach's decisions, 2026-10-04)

| # | Decision | Where in this file |
|---|---|---|
| D1 | **ZEIM Originals are licensed CC BY 4.0, credit to ZEIM, pending counsel confirmation before launch.** Exact strings are in 1.5. | 1.2, 1.5, 6, 7.1 |
| D2 | **Creator credit goes to the account USERNAME. The username is the only public identity. Email is private** (stored in account info, never shown; public only if the user explicitly opts in). Child/teen usernames must not be real names (existing nickname rules apply, cited in section 8). | 1.1, 1.2, 3.2, 6, 7.1, 8 |
| D3 | **NC and ND licences stay hidden in v1.** Response targets accepted: acknowledge within **2 business days**, decide within **10 business days**, **pause (hold) on a proper report**. | 2.1, 2.2, 5.2 |
| D4 | Claims need **proper proof**; a bare "that's mine" removes nothing. Process designed in `reports/claims-process.md` (summary: section 9). | 5, 9 |
| Open | **Still open with Zach:** (a) a **ZEIM-owned** takedown/claims mailbox (a role address, not Zach's personal email); (b) the **repeat-infringer policy** (thresholds in claims-process.md section 8 are proposals only). | 5.1, 9 |

Other changed pieces: section 0 re-audited on the **verified** manifest (195 kept, 24 quarantined); data-file fields now follow the names already in `library/manifest.json`; new sections 8 (identity) and 9 (claim process); `reports/library-legal-review.md` (NASA, share-alike, Commons, OpenSCAD, family-friendly review).

---

## 0. What I audited (verified library manifest) and what it means

Source: `library/manifest.json` (`verified_on` 2026-10-04), `manifest.md`, `ATTRIBUTION.md`, `verification_evidence.json`, `library/_quarantine/`. Per-entry results: **`reports/attribution-audit.csv`** (195 rows, regenerated for v0.2). The deeper licence/safety review is in **`reports/library-legal-review.md`**. Nothing in `library/` was edited.

### 0.1 Field coverage (195 kept entries; 24 more are quarantined)

| Wanted field | Manifest key (now) | Have | Lack | Notes |
|---|---|---|---|---|
| credit line (card) | `credit_line` | 195 | 0 | e.g. `"Soccer ball" by Microsoft · CC BY 4.0` |
| credit text (detail/embed) | `credit_full`, `credit_text` | 195 | 0 | |
| creator | `creator` | 195 | 0 | **162 of 195 are `creator_verified: false`** (taken from repo owner / Commons uploader as declared); 33 true (all Smithsonian) |
| creator profile URL | `creator_url` | 193 | **2** (Wikimedia Commons items) | |
| source URL | `source_url` / `source_page_url` | 195 | 0 | |
| licence id / name / URL | `license_id`, `license_name`, `license_url` | 195 | 0 | `license_url` is a **file page** for 13 Commons public-domain items and a **NASA guidelines page** for 60 NASA items (no licence text exists to link) |
| licence evidence | `license_evidence_url` | 195 | 0 | github.com 112, commons.wikimedia.org 50, si.edu 33 |
| provenance | `provenance` | 195 | 0 | |
| printer tag | `printer`, `printer_guess` | 195 | 0 | **all 195 are marked unverified guesses** (134 both, 40 fdm, 21 resin) |
| fit note | `fit_note` | 103 | 92 | filled mainly for non-watertight items |
| status | `status` | 195 | 0 | all `ready`; 76 are `view_only` (not watertight; 32 are Smithsonian textured scans) |
| NC / ND / unlicensed | n/a | 0 present | n/a | none in the kept set |
| `creator_username`, `license_confirmed` | **new in v0.2** | 0 | 195 | not needed for third-party records; needed for community uploads and Originals (7.1) |

### 0.2 Licence mix (kept set)

| `license_id` | Count | Attribution legally required? | Status |
|---|---|---|---|
| `cc0-1.0` | 65 | No (we credit anyway) | OK |
| `public-domain-us-gov` (NASA: 47 GitHub + 13 Commons) | 60 | No; NASA asks to be acknowledged, no endorsement, no insignia | OK with NASA label (see library-legal-review.md) |
| `cc-by-4.0` | 26 | **Yes** | OK once credit renders |
| `unlicense` | 16 | No | OK |
| `cc-by-sa-4.0` | 15 | **Yes + share-alike** | OK with share-alike rules (2.3); **needs counsel** on effects |
| `public-domain` (Commons, uploader-declared) | 13 | No | OK with label "per Wikimedia Commons" |
| **Total** | **195** | | |

### 0.3 What must stay hidden

* **Quarantined (24, hide):** 2 x 3DBenchy (repo has no licence file; older copies BY-ND; 3dbenchy.com now says CC0; re-admit only after counsel/Zach confirm), 4 x JRodrigoTech (BY-SA 3.0 vs 4.0), 18 x `commons-*` stray folders with no source record (this closes the "20 folders not in the manifest" gap from v0.1).
* **Single items to hold for a human look:** `nasa-hubble-25th-anniversary-medallion` (lettering; insignia not checked).
* **Not print-ready:** 76 view-only (label "view only", no print tag claim).
* **ZEIM Originals:** `library/originals/` has 37 STL + preview PNGs on disk (39 defined in `source/`, 45 planned) and **still no `manifest.json`**. Each needs `provenance`, `printer`, `fit_note`, the shared licence line (now CC BY 4.0, section 1.5), `license_confirmed`. Family-friendly flags (Wildlife Calls etc.) are in library-legal-review.md section 9.

### 0.4 Top 5 gaps (v0.2)

1. **Downloads still carry no credit** (`to_3mf()` writes only `Title`/`Application`; STL/OBJ nothing); no "changes made" recorded; no `/credits` page.
2. **No Originals manifest** and no `license_confirmed` (counsel) gate; Originals' authorship (procedurally generated) and the licensor entity are **needs counsel**.
3. **No username concept in the app**: accounts have a free-text `display_name` (not unique, not format-restricted); credits need `creator_username` (section 8).
4. **162 of 195 creators unverified**; 13 Commons licence URLs are file pages; NASA third-party contributor risk (8 items list contributors).
5. **No claims intake, hold switch or takedown mailbox**; `COMMUNITY_GUIDELINES.md` says only "use Report". Mailbox and repeat-infringer policy are open with Zach.

---

## 1. Credit line format (TASL)

Creative Commons recommends attribution include **T**itle, **A**uthor, **S**ource and **L**icence, plus a note if the work was changed, and says to credit the author the way the author asks (pseudonym is fine). Source: <https://wiki.creativecommons.org/wiki/Best_practices_for_attribution> (read 2026-10-04). The same page warns that putting attribution **only** in metadata fields is a pitfall, so ZEIM always shows it on the page **and** embeds it in the file.

CC BY 4.0 section 3(a) (read 2026-10-04 at <https://creativecommons.org/licenses/by/4.0/legalcode>) lists what to retain: creator identification, copyright notice if supplied, a notice referring to the licence, a notice referring to the disclaimer of warranties, a link to the material where reasonably practicable, an indication if modified (and previous modifications), and the licence text or link. 4.0 allows doing this "in any reasonable manner based on the medium", e.g. by link.

### 1.1 Rules for the strings

* **Third-party creators** are credited as they published themselves (name, pseudonym or handle on their source page). Never replace it with a real name we guessed.
* **ZEIM community creators are credited by their ZEIM USERNAME only** (Zach D2). The username is the only public identity. **Never** put a real name, email, date of birth, age, class, school or account id in a credit string, file, filename, header or the public data. Email is private account information, shown only if the user explicitly opts in (section 8.3).
* Where the account has no public profile (teens are Private only; class students use class nicknames and Showcase is off for them), the credit is shown only to those allowed to see the item; if it ever becomes visible beyond that, it shows the username, never a real name.
* If an account is deleted, or a creator asks for removal of their credit, the credit becomes `a ZEIM maker`. CC BY 4.0 section 3(a)(3) says that if the licensor requests, you must remove the credit information "to the extent reasonably practicable" (read 2026-10-04). Credit for a **third-party licence** does not disappear because a ZEIM user deletes their account: remix chains keep the original creator's credit.
* Always include the licence **name and link**. Use canonical links from section 2.
* Never claim more than we know: if the creator is only the repo owner, say "published by" (Benchy style), and keep `creator_verified: false` internally.
* "Credit appreciated" is for CC0/PD; never write "required" for CC0.
* The '@' prefix is **not** used in stored credit strings: the app's free-text filter blocks `@handle` patterns (`app/community/safety.py`, `_HANDLE_AT`), so usernames are shown as plain text, with a link to the profile only when the profile is public.
* Quote straight `"` in plain files; avoid emoji in embedded strings.

### 1.2 Card (short, one line, max about 90 characters; link target = detail page)

Template: `"{title}" by {creator} · {license_short}[ · remix by {remixer_username}]` where `{creator}` is the third-party creator as published, or the ZEIM `creator_username`, or `ZEIM` for Originals.

| Case | Exact example string |
|---|---|
| CC0 | `"Chess Bishop" by Olivier Wagener · CC0 1.0` |
| CC BY | `"Octagonal vase-mode box" by Alexander Thomas · CC BY 4.0` |
| CC BY-SA | `"Racer buggy" by Marco D'Alia / 3DRacers · CC BY-SA 4.0 · share-alike` |
| Public domain (NASA) | `"Apollo 11 landing site terrain" · NASA · Public domain` |
| Smithsonian CC0 | `"1903 Wright Flyer" · Smithsonian Institution, National Air and Space Museum · CC0 1.0` |
| Unlicense | `"Polycube 1 (monocube)" by possibly-wrong · Unlicense (public domain)` |
| ZEIM Original | `"Sleepy Loaf Cat" by ZEIM · CC BY 4.0` (exact strings in 1.5) |
| Remix (user) | `"Racer buggy" remix by mika_maker · based on "Racer buggy" by Marco D'Alia · CC BY-SA 4.0` |
| Community upload (username) | `"Desk Fox" by mika_maker · CC BY 4.0` |
| Creator removed credit / deleted account | `"Desk Fox" by a ZEIM maker · CC BY 4.0` |
| Minor (if visible at all) | username only, same format; never a real name (section 8.2) |
| HOLD / not ready | no card in public lists (see section 7 `status`) |

If the line is too long: keep creator and licence, truncate the title with an ellipsis and give the full text as the card's accessible name/tooltip. Never drop the creator or licence to fit.

### 1.3 Detail page (full, visible without clicking anything)

Rendered block (each underlined word is a link):

```
"Octagonal vase-mode box" by Alexander Thomas (GitHub: DrLex0)
Source: https://github.com/DrLex0/print3d-customizable-vase-mode-box
Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
Changes: none made by ZEIM.
Provided as-is, with no warranty (see licence).
Retrieved by ZEIM on 2026-10-04. Wrong, missing or want it removed? Tell us: [Report / credit correction]
```

CC0 / public domain variant:

```
"Chess Bishop" by Olivier Wagener (GitHub: 0x3b29)
Source: https://github.com/0x3b29/3D-Printable-Chess
Licence: CC0 1.0, dedicated to the public domain (https://creativecommons.org/publicdomain/zero/1.0/)
Credit is not required, but we are glad to give it. Thank you, Olivier.
```

NASA variant:

```
"Apollo 11 landing site terrain", NASA 3D Resources
Source: https://github.com/nasa/NASA-3D-Resources
Rights: NASA 3D model content is generally not subject to copyright in the United States (NASA Media Usage Guidelines).
ZEIM is not affiliated with and is not endorsed by NASA. Do not use NASA insignia.
```

Share-alike addition (BY-SA only): `Share-alike: if you change this model and share it, you must share your version under CC BY-SA 4.0 or a compatible licence.`

Remix / modified addition (section 3): `Changes: Modified by ZEIM user mika_maker on 2026-10-05 (changes: scaled to 120%, added text "MIA" in Edit).`

ZEIM Original addition: see 1.5 (full block).

### 1.4 Downloads (embedded)

A downloaded file must still tell its story after it leaves ZEIM. Embedding is **in addition to** the page, never instead (CC pitfall above).

**Canonical embedded text** (`credit_full`, plain ASCII, one paragraph, no newline inside fields):

```
"Octagonal vase-mode box" by Alexander Thomas (GitHub: DrLex0). Source: https://github.com/DrLex0/print3d-customizable-vase-mode-box. Licence: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/. No changes made by ZEIM. Provided as-is, no warranty. Downloaded from ZEIM.
```

**3MF** (read from the 3MF Core spec, <https://github.com/3MFConsortium/spec_core/blob/master/3MF%20Core%20Specification.md>, 2026-10-04): predefined `<metadata>` names include `Title`, `Designer`, `Copyright`, `LicenseTerms`, `ModificationDate` (and `Description`, `Application`). Proposed mapping, in the `<model>` element:

```xml
<metadata name="Title">Octagonal vase-mode box</metadata>
<metadata name="Designer">Alexander Thomas (GitHub: DrLex0)</metadata>
<metadata name="Copyright">Alexander Thomas; licensed CC BY 4.0</metadata>
<metadata name="LicenseTerms">CC BY 4.0 https://creativecommons.org/licenses/by/4.0/</metadata>
<metadata name="Description">{credit_full}</metadata>
<metadata name="ModificationDate">2026-10-05</metadata>   <!-- only if modified -->
<metadata name="Application">ZEIM</metadata>
```

Custom metadata names (e.g. `zeim:source_url`) need a namespace prefix per the spec's extension rules: **UNVERIFIED**, check section on extensibility before using; the predefined names above are enough. Values must be XML-escaped (the current `to_3mf()` already uses `escape()`). Slicers may drop or ignore metadata on import (UNVERIFIED), which is why the page and README-credit.txt exist.

**STL (binary)**: 80-byte header. By long-standing convention it is free text; it is not formally standardised and some tools overwrite it (UNVERIFIED which). Rules: ASCII only, **do not start with `solid`** (some readers then guess ASCII STL and fail), pad with spaces, truncate with `...`. Budget about 75 chars:
`ZEIM|Chess Bishop|Olivier Wagener|CC0-1.0|creativecommons.org/publicdomain/zero/1.0/` is 82 chars, too long, so use the short form:
`ZEIM | Chess Bishop | O. Wagener | CC0-1.0 | zeim item chess-chess-bishop`
and put the licence link in the filename and README. **ASCII STL** has only `solid <name>` (no standard comment syntax): put a short `solid chess-bishop_by-olivier-wagener_cc0` and nothing else; do not invent comments.

**OBJ**: `#` comment lines at the top are legal; write `credit_full` as 1-3 comment lines.

**Filename**: `{slug}_by-{creator-slug}_{license_id}.{ext}`, e.g. `chess-bishop_by-olivier-wagener_cc0-1.0.stl`, `racer-buggy_by-marco-dalia_cc-by-sa-4.0.stl`. Max 100 chars, strip non-ASCII to `-`.

**Zip / "Download with credit"** for any multi-file download, any 3MF/STL/OBJ of a CC BY or CC BY-SA item, and any remix: include `README-credit.txt`:

```
THANK YOU TO THE CREATOR
Title:    Octagonal vase-mode box
Author:   Alexander Thomas (GitHub: DrLex0)
Source:   https://github.com/DrLex0/print3d-customizable-vase-mode-box
Licence:  CC BY 4.0  https://creativecommons.org/licenses/by/4.0/
Changes:  None made by ZEIM.
Notice:   Provided as-is, no warranty. Licences are the creator's, not ZEIM's.
If you share this model or something made from it, please keep this credit with it.
Downloaded from ZEIM on 2026-10-05. Wrong credit or want it removed? [takedown contact: PLACEHOLDER]
```

Single-file downloads of CC0/PD items may be plain (still embedded header + filename). **Never put uploader photo EXIF/GPS, student names or real names in any credit string** (see `send-privacy.md`).

### 1.5 ZEIM Originals: credit line and licence line (Zach D1: CC BY 4.0, credit to ZEIM)

**Status: CC BY 4.0 is Zach's decision; counsel must confirm before public launch** (data flag `license_confirmed: false` until then; the launch validator fails while it is false). Open **needs counsel** points: (a) which legal entity is "ZEIM" the licensor; (b) authorship and copyrightability of procedurally generated designs (the Originals are built by code in `library/originals/source/`); (c) **CC BY allows commercial reuse by anyone** (Zach should know), and **CC licences are irrevocable for copies already shared** (CC BY 4.0 s.2(a)(1); s.6(c) lets the licensor stop distributing, not recall); (d) no Original may be derived from a share-alike item.

The **one shared licence line** (identical on card, detail page, download README, 3MF `LicenseTerms`, STL header, OBJ comment):

```
Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Credit: ZEIM.
```

**Card (short):**

```
"Sleepy Loaf Cat" by ZEIM · CC BY 4.0
```

**Detail page (full):**

```
"Sleepy Loaf Cat" by ZEIM (https://{zeim-site}/credits#originals)
Source: https://{zeim-site}/originals/sleepy-loaf-cat
Licence: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
Changes: none.
Provenance: Designed from scratch by ZEIM; no tracing or adaptation of any character, logo or franchise.
Provided as-is, with no warranty (see licence).
How to credit this model if you share it: "Sleepy Loaf Cat" by ZEIM, CC BY 4.0, https://{zeim-site}/originals/sleepy-loaf-cat
```

(`{zeim-site}` = the real address once Zach chooses a domain; **do not ship the literal placeholder**.)

**Embedded text (`credit_full`, one line, ASCII):**

```
"Sleepy Loaf Cat" by ZEIM. Source: https://{zeim-site}/originals/sleepy-loaf-cat. Licence: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/. Provided as-is, no warranty.
```

**3MF metadata:** `Title` = Sleepy Loaf Cat; `Designer` = ZEIM; `Copyright` = ZEIM; licensed CC BY 4.0; `LicenseTerms` = `CC BY 4.0 https://creativecommons.org/licenses/by/4.0/`; `Description` = `credit_full`. **STL header (<= ~75 chars, not starting `solid`):** `ZEIM | Sleepy Loaf Cat | ZEIM | CC-BY-4.0 | zeim item sleepy-loaf-cat`. **Filename:** `sleepy-loaf-cat_by-zeim_cc-by-4.0.stl`.

**Remixes of an Original:** the remixer must keep the credit to ZEIM, the licence link, and a statement of changes (CC BY 4.0 s.3(a)(1)(B)); chain display as in 3.3: `Based on "Sleepy Loaf Cat" by ZEIM (CC BY 4.0) -> remixed as "Sleepy Loaf Hat" by mika_maker (CC BY 4.0)`.

**Do not launch publicly with this string until counsel confirms.** Internal builds may show a visible `Pending counsel review` chip on Original pages.

---

## 2. Licence table (what ZEIM may host)

Canonical texts (read 2026-10-04 unless noted): CC BY 4.0 <https://creativecommons.org/licenses/by/4.0/legalcode>; CC BY-SA 4.0 <https://creativecommons.org/licenses/by-sa/4.0/legalcode.en>; CC BY-NC 4.0 <https://creativecommons.org/licenses/by-nc/4.0/legalcode.en>; CC BY-ND 4.0 <https://creativecommons.org/licenses/by-nd/4.0/legalcode.en>; CC BY-NC-SA 4.0 <https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en>; CC0 1.0 <https://creativecommons.org/publicdomain/zero/1.0/> (link from manifest; text not re-read by me today: UNVERIFIED); Unlicense <https://unlicense.org/> (UNVERIFIED, not re-read).

### 2.1 Tiers

| Tier | Licence | Host in ZEIM v1? | Download | Edit / remix | Share edited copy | What it requires (summary, from the legal code) | Link |
|---|---|---|---|---|---|---|---|
| A | **CC0 1.0** | Yes | Yes | Yes | Yes | Nothing required. ZEIM credits anyway. | creativecommons.org/publicdomain/zero/1.0/ |
| A | **Public domain** (NASA, Commons PD, Benchy if cleared) | Yes | Yes | Yes | Yes | Nothing legally required; NASA: acknowledge source, no endorsement, no insignia; third-party content inside NASA material is possible. | NASA: nasa.gov/nasa-brand-center/images-and-media/ (from manifest, UNVERIFIED) |
| A | **Unlicense** | Yes | Yes | Yes | Yes | Include the Unlicense text/notice if substantial portions are copied (UNVERIFIED, not re-read). | unlicense.org |
| A | **CC BY 4.0** | Yes | Yes | Yes | Yes, with credit | Keep creator, copyright notice, licence notice, disclaimer notice, link to source if practicable; **indicate if modified** and keep earlier modification notes; include licence text or link. No implying endorsement (s.2(a)(6)). Don't add terms or technical locks that restrict others (s.2(a)(5)(B)). | creativecommons.org/licenses/by/4.0/ |
| A | **CC BY-SA 4.0** | Yes | Yes | Yes | Yes, **only under CC BY-SA 4.0 or a CC-approved BY-SA compatible licence** | Everything in CC BY plus: adapted material must be shared under the same licence (or a "BY-SA Compatible License" listed at creativecommons.org/compatiblelicenses) and must include the Adapter's License text/link; no extra terms or technical measures that restrict it. | creativecommons.org/licenses/by-sa/4.0/ |
| B (hold) | CC BY 3.0 / BY-SA 3.0 | Only after counsel | as 4.0 | as 4.0 | version-specific | 3.0 and 4.0 differ (e.g. 3.0 requires title; 4.0 makes it optional per the CC attribution page). Mixing versions in a remix needs counsel. | creativecommons.org/licenses/by-sa/3.0/ (UNVERIFIED) |
| C | **CC BY-NC 4.0** (and NC-SA) | **Hidden in v1 (Zach decided 2026-10-04)**; may be revisited after counsel | personal / classroom only, labelled | Yes (adaptations allowed) | non-commercial only; NC-SA also needs same licence | NonCommercial means "not primarily intended for or directed towards commercial advantage or monetary compensation"; file-sharing exchange with no payment is NonCommercial (s.1). ZEIM is free with no payments, which helps, but ZEIM cannot promise what a user's school, club or sale does with a print, and a future ad or sponsor model could change the analysis. **needs counsel** before any NC item is shown. | creativecommons.org/licenses/by-nc/4.0/ |
| D | **CC BY-ND 4.0** (and NC-ND) | **Hidden in v1 (Zach decided 2026-10-04)** | view / download of the unchanged file only | **Edit locked** | **Never share a modified copy** | ND 4.0 lets you "produce and reproduce, but not Share, Adapted Material": private adaptations only; sharing a modified version is not allowed. Whether scaling or format conversion counts as "adapted" is unclear (4.0 s.2(a)(4) allows only the technical modifications needed to exercise the rights): **needs counsel**. | creativecommons.org/licenses/by-nd/4.0/ |
| X | No licence / "all rights reserved" / custom / unknown / "free for personal use" | **No** (3rd-party). Allowed only for the user's **own** upload as private or view-only (section 6) | no | no | no | Without a licence we have no permission. | n/a |

### 2.2 Tiers C and D: hidden in v1; handling rules if enabled later (so Engineering can build the flag now)

* **NC**: show a visible chip `Non-commercial`; the card line adds `· NC`; Download dialog says "Free to print for yourself, family and class. Not for sale." Block any ZEIM feature that sells or advertises (none exist). Hide from any future sponsored/featured placement. Counsel to confirm classroom and school-fundraiser use.
* **ND**: chip `No changes`; the **Open in Edit** button is disabled with the message `The creator asks that this model isn't changed, so Edit is switched off for it.` Studio/Make never use it as input. If counsel allows private adaptation, Edit may open with Share/Publish disabled instead.
* **v1 (decided by Zach):** NC and ND are **hidden** (`status: hold`, never listed, not offered in the upload licence picker). None are in the library today (0 of 195 kept).

### 2.3 Mixing licences (remix of more than one source)

* All sources Tier A and none SA -> the remixer picks any licence ZEIM offers, but credit for every source stays.
* Any source SA -> the remix must be offered under that SA licence (or compatible). If two sources are SA under **different** licences or versions -> block publishing, **needs counsel**.
* Any source ND/NC/unknown -> block publishing of the remix.
* A remix never *loosens* the licence of a source (e.g. cannot publish a BY-SA remix as CC0).

### 2.4 NASA, Smithsonian, Wikimedia, GitHub specifics

* **NASA** (47 items): the manifest says NASA says content is "generally" not subject to copyright in the US; some NASA site content contains third-party material; the 3D Resources repo README says "free and without copyright". Keep the three notes: acknowledge NASA as source; no implied endorsement; no insignia/logos. A NASA logo or "meatball" in a model would be a trademark/insignia issue regardless of copyright. Whether NASA's guidance holds outside the US is **UNVERIFIED / needs counsel**.
* **Smithsonian** (33 items): labelled CC0 under Smithsonian Open Access. Terms page not re-read by me (UNVERIFIED). Smithsonian name and logo are not licensed by CC0; use the name only as credit text.
* **Wikimedia Commons** (30 items): licence and creator are what the uploader declared; Commons can have mistakes (UNVERIFIED rate). Link the file page; accept takedowns quickly.
* **GitHub repos**: licence is repo-level; a LICENSE file does not prove the person who pushed owns every file (101 creators unverified). A repo with no licence file is **not** usable (Benchy case is held for that reason).

---

## 3. "Changes made" and remix chain

### 3.1 When it triggers

Any time a user (or ZEIM tool) changes the **shape or content** of a model that came from the library, Showcase or another user: Edit workspace (scale, rotate, mirror, cut, split, merge, hollow, simplify, repair, add text/emboss, base/stand, drill), Make tab parameter forks of a shared design (if it is derived from a shared model rather than a ZEIM-authored generator), and Studio builds that use another user's *photo-derived* model as input (not expected). Pure format conversion with no change to geometry (STL -> 3MF) is recorded as `format conversion` only. Whether uniform scaling is "a technical modification" or an "adaptation" is a legal question: record it anyway, label it, **needs counsel**.

### 3.2 Auto-generated notes (Engineering writes them; the user cannot delete them)

Format: `Modified by ZEIM user {display} on {YYYY-MM-DD} (changes: {list}).` Display = the ZEIM **username** (section 8), or `a ZEIM maker` when the creator asked for credit removal or the account is deleted (never a real name).

| Edit action | `changes` token | Example text in the list |
|---|---|---|
| Scale | `scale` | `scaled to 120%` |
| Rotate / mirror | `rotate`, `mirror` | `rotated 90 degrees about Z`, `mirrored left-right` |
| Cut / split / trim | `cut` | `cut flat at 12 mm height` |
| Hollow | `hollow` | `hollowed with 2 mm walls` |
| Simplify | `simplify` | `reduced triangle count by 50%` |
| Repair | `repair` | `repaired holes in the mesh` |
| Text tool | `add_text` | `added text "MIA" (text passed the language filter)` |
| Merge | `merge` | `combined with "Base plate" by ZEIM` |
| Format only | `format` | `converted from STL to 3MF (no shape change)` |

Full examples:

* `Modified by ZEIM user mika_maker on 2026-10-05 (changes: scaled to 120%, added text "MIA").`
* Credit withdrawn / deleted account: `Modified by a ZEIM maker on 2026-10-05 (changes: hollowed with 2 mm walls).`
* Multiple edits by different people keep **earlier notes** (CC BY 4.0 s.3(a)(1)(B): "retain an indication of any previous modifications"):
  `Changes: (1) mika_maker, 2026-10-05: scaled to 120%. (2) ren_makes, 2026-10-07: hollowed with 2 mm walls.`

The text is stored in `changes[]` (data file), shown on the detail page, written into 3MF `Description`/`ModificationDate`, STL header (short form `...|MODIFIED`), OBJ comments and README-credit.txt.

### 3.3 Remix chain

* Data: `remix_of: ["library-id" | "upload-id", ...]` (parents), resolved to a chain on display.
* Detail page shows the **whole chain**, nearest parent first:
  `Based on "Racer buggy" by Marco D'Alia / 3DRacers (CC BY-SA 4.0) -> remixed as "Racer buggy XL" by mika_maker (CC BY-SA 4.0).`
* Card shows the **original creator and licence** plus `remix by mika_maker` (section 1.2). The remixer never replaces the original creator.
* Depth > 3: collapse middle links on cards; the detail page lists all.
* If a parent is later removed (takedown), the child is **hidden too** until reviewed, and the remixer is told kindly (templates 5.5).
* The remix's licence is picked from the allowed set computed by section 2.3; the picker greys out illegal choices with a short reason.

---

## 4. Credits / Attribution page spec (`/credits`)

Linked from the footer on every page. Haruto builds it from **one data file** (e.g. `app/data/credits.json`); Sakura designs it; copy can be edited without code. Version number + "Updated {date}" at top. No analytics on this page.

### 4.1 Sections, in order

1. **Thank you** (gratitude statement, draft in 4.3).
2. **Creators we are grateful to**: auto-built from the library manifest and approved community uploads: third-party creators as published (links to `creator_url` if any); community creators by **username** only (opt-out available; never email); what they made (count + link to filtered catalog), licence. Alphabetical; no ranking. Under-18 usernames are not listed on the page (a single line "and the young makers who share with us").
3. **ZEIM Originals** (anchor `#originals`): the in-house designs, who made them (names the team agrees to publish), the shared licence line from 1.5 (CC BY 4.0, shown with a pending-counsel chip until confirmed) and "how to credit ZEIM": `"{title}" by ZEIM, CC BY 4.0, {url}`.
4. **Open-source tools and libraries** (table in 4.2): name, version, licence, link. Version and licence **read from installed package metadata at build time**, not typed by hand; a `reviewed:true/false` flag per row; any row with a blank licence shows "check upstream" and fails the build check.
5. **Standards, fonts and data we build on**: 3MF, STL, OBJ formats; DejaVu fonts (Edit text); photo/mesh libraries.
6. **Testers and friends**: opt-in names or first names only (adults); never minors or class students.
7. **Teachers and schools**: opt-in, with permission recorded by Aiko's team; never children's names.
8. **Trademarks and non-affiliation** (4.4).
9. **Report a credit, ask for a change or removal** (contact placeholder; section 5).

### 4.2 Open-source licence list (proposed, from this box)

Read on 2026-10-04 with `importlib.metadata` in `/workspace/photo3d/.venv` and from `/usr/share/doc/*/copyright`. "Metadata says" = what the installed package declares; I did **not** read each upstream licence file, so every row is **UNVERIFIED against upstream** until Engineering's build step records `reviewed:true`. Versions match `constraints.txt`.

| Component | Version | Licence per package metadata | Notes |
|---|---|---|---|
| FastAPI | 0.142.2 | MIT | web framework |
| Starlette | 1.7.0 | BSD-3-Clause | |
| Pydantic / pydantic-core | 2.13.5 / 2.46.5 | MIT | |
| Uvicorn | 0.54.0 | BSD-3-Clause | |
| httpx | 0.28.1 | BSD-3-Clause | |
| python-multipart | 0.0.32 | Apache-2.0 | |
| cryptography | 43.0.0 | Apache-2.0 OR BSD-3-Clause | |
| trimesh | 5.1.1 | MIT | mesh loading and checks |
| manifold3d | 3.5.4 | Apache-2.0 (classifier only; licence field blank) | mesh boolean/Make generators |
| fast-simplification | 0.2.0 | MIT | |
| NumPy | 2.5.3 | BSD-3-Clause family (metadata gives only a copyright line + BSD classifier) | |
| SciPy | 1.18.1 | BSD family (same) | |
| scikit-image | 0.26.0 | BSD (classifier; licence field is "Files: *", i.e. a multi-file text) | |
| Shapely | 2.1.2 | BSD-3-Clause | |
| networkx | 3.7 | BSD-3-Clause | |
| rtree | 1.4.1 | MIT | |
| mapbox_earcut | 2.1.0 | **blank in metadata** | check upstream (I believe ISC: UNVERIFIED) |
| Pillow | 12.3.0 | MIT-CMU (HPND style) | |
| pillow-heif | 1.8.0 | BSD-3-Clause | bundles libheif in its wheel: libheif is LGPL (UNVERIFIED) and the wheel's bundled-library notices must be listed: **needs counsel / Engineering to read the wheel's license files** |
| Matplotlib | 3.11.2 | Matplotlib licence (PSF-based) | used for text outlines |
| fonttools | 4.65.0 | MIT (UNVERIFIED, not in my query) | |
| lxml | 6.1.3 | BSD-3-Clause | |
| segno | 1.6.6 | BSD (classifier) | QR codes for classrooms |
| three.js r160 | bundled in `static/vendor/three.module.min.js` | MIT (header: "Copyright 2010-2023 Three.js Authors, SPDX MIT") | `OrbitControls.js` is from the three.js examples (MIT, header has no licence line: UNVERIFIED) |
| DejaVu fonts | Debian `fonts-dejavu-core` | Bitstream Vera licence + public-domain DejaVu changes (from `/usr/share/doc/fonts-dejavu-core/copyright`) | glyph outlines end up inside users' text models; the font licence allows use, but it forbids selling the font itself and requires keeping the notice with copies of the font (UNVERIFIED reading) |
| Python | 3.13 | PSF licence | |
| **PrusaSlicer** (system package) | **2.9.2+dfsg-1 (Debian)**, installed at `/usr/bin/prusa-slicer`, also `apt-get install`ed in the Dockerfile | **AGPL-3** for the main code per `/usr/share/doc/prusa-slicer/copyright`; bundled parts under GPL-2+, GPL-3+, AGG, and icons by Mark James under **CC BY 3.0** (credit due if the icons are shipped) | **see 4.2.1** |
| Dev/test only | pytest 9.1.1 (MIT), Playwright 1.63.0 (Apache-2.0) | not shipped; list on Credits only if we want to |

Not yet checked: any infrastructure Ren's deploy kit uses in production (for example the proxy and tunnel tools under `reports/deploy/`). If it runs on the live service or is redistributed, add it. **UNVERIFIED.**

#### 4.2.1 PrusaSlicer and the AGPL: **needs counsel**

Facts (read from this box and the repo): the app shells out to the `prusa-slicer` command-line program as a separate process (`app/services/slicer.py` looks for it on PATH; per README and Dockerfile comments). The Dockerfile installs the Debian package into the image, which means any Docker image we publish would **distribute** PrusaSlicer. ROADMAP already says "PrusaSlicer is AGPL, review if distributing/hosting".

What I can say honestly: AGPL-3 has obligations around providing source (and the network-use clause for *modified* versions). Whether running an unmodified PrusaSlicer as a command-line subprocess from a hosted web app, or shipping it inside an image, creates obligations for ZEIM's own code is a legal question I am **not able to answer**. Proposed safe steps pending counsel, all cheap: (1) list PrusaSlicer with its version and licence on /credits and link its source (<https://github.com/prusa3d/PrusaSlicer>) and Debian's source package; (2) never modify it without telling us; (3) do not bundle its icons or UI assets; (4) if we ship an image, include the licence texts and a "how to get the source" note; (5) keep the integration swappable (user-installed slicer, or OrcaSlicer/other). Name "PrusaSlicer" and "Prusa" only to describe compatibility (4.4).

### 4.3 Gratitude wording (draft, confident, warm, honest)

> **Thank you**
>
> ZEIM stands on the shoulders of people who share generously. Every model here was made by someone who chose to offer it for others to print, learn from and enjoy, and we are proud to show their names beside their work.
>
> We thank the makers whose designs you can print today, the museums and space agencies that open their collections to everyone, the open-source teams whose tools power every build, the teachers who bring ZEIM into their classrooms, and the testers who found what we missed. We climb one step at a time, and we are grateful for every hand along the way.
>
> If we credited something wrongly, or you would like your work changed or removed, tell us. We will listen, act promptly and thank you for it.

Rules: no "best/better than" lines here; no "compliant/certified/approved" wording; no names of people who did not agree to be named; "free to use" (not "free forever") until Zach decides.

### 4.4 Trademark and non-affiliation line (draft; **needs counsel** before launch)

> Creality, Creality K1 and Creality Cloud, Shapr3D, Prusa and PrusaSlicer, Bambu Lab, OctoPrint, Thingiverse, Printables, NASA, the Smithsonian, Wikimedia and other product and organisation names are trademarks or names of their respective owners. ZEIM mentions them only to say what works with what or where a model came from. ZEIM is not affiliated with, endorsed by or sponsored by them. NASA does not endorse ZEIM.

Also: ZEIM's own name and logo - **trademark clearance has not been done** (per `app/branding.py` and README); that is a separate **needs counsel** item. Do not use any third party's logo, mascot or character names in model titles or tags unless we hold rights (matches Originals provenance rule).

---

## 5. Removal / takedown route

Targets accepted by Zach 2026-10-04 (acknowledge 2 business days, decide 10 business days, pause on a proper report). Everything else on the policy side is a proposal; legal mechanics are **needs counsel**. Claims need proper proof (section 9).

### 5.1 Contact point

* Page `/report-credit` (credit corrections) and `/report-ownership` (ownership claims; form fields in claims-process.md section 12, **not to be built until the process is approved**), plus a "Report" button on every card and detail page, plus a monitored mailbox: **`[CLAIMS MAILBOX: OPEN - Zach to set a ZEIM-owned role address; NOT Zach's personal email]`**. Shown on /credits, in README-credit.txt and in the footer. No page may ship with this placeholder text (QA test D4).
* Credit corrections need only a link showing the requester controls the named profile. Ownership claims need **proper proof** (section 9).

### 5.2 Process (targets accepted by Zach, 2026-10-04)

| Step | Rule |
|---|---|
| Report types | Safety/privacy: **hide at once**. Credit correction: fix, no hold. Ownership claim: **hold only when the claim is complete on its face** (section 9, rules H0-H4); a bare "that's mine" changes nothing. |
| Acknowledge | Within **2 business days** (accepted). Auto-reply in 5.5. |
| Pause | A proper report **pauses (holds)** the item: hidden from public lists, search and downloads; the owner still sees it with a "paused for review" badge; nothing is deleted. |
| Decide | Within **10 business days** (accepted): restore, correct credit, replace, or remove. |
| Credit fix only | Within 2 business days of a confirmed creator request, correct credit across card, detail page, file metadata and README (regenerate downloads). |
| Remixes | If a parent is removed, children are hidden until reviewed (section 3.3). |
| Record | Minimal audit record (claims-process.md section 10). No usernames of minors, no student names, no evidence files in the log. |
| Minors | A minor's work is never named to a claimant; notices go to the classroom teacher or the account in-app (section 9 / claims-process.md section 9). |

### 5.3 Legal mechanics - **needs counsel**

* **US DMCA**: the 17 U.S.C. section 512 safe-harbour system relies on a designated agent registered with the US Copyright Office. The directory is at <https://www.copyright.gov/dmca-directory/> (page reachable 2026-10-04; I did not read the rules). Registration, renewal, who the agent is (a person or organisation), the exact notice and counter-notice fields and the statutory restoration timeline are **needs counsel**. Do not claim "DMCA compliant" anywhere.
* **Counter-notice**: the uploader may reply with evidence; timing, statutory content, penalty-of-perjury wording, jurisdiction consent and restoration timing are all **needs counsel** (claims-process.md section 5). Until counsel approves, ZEIM promises only a **hold plus human review**, not a statutory process.
* **Repeat infringers**: **OPEN with Zach**. Proposal only (claims-process.md section 8): count *validated* findings only; 1 = removal + note, 2 = uploading paused 30 days, 3 = uploading ended (appeal to Kenji). For under-18s and classes involve the teacher/guardian first. **needs counsel.**
* **Non-US rights** (for example Japan or EU): **UNVERIFIED / needs counsel**.
* **Terms of Service**: an uploader grant (licence to ZEIM to host, display and let others download as chosen) and a "you have the right to upload this" warranty must be in the ToS. **needs counsel** to write.

### 5.4 Takedown hygiene

Removing = hide + delete file + delete previews/cached thumbnails + remove from search + keep a one-line audit record. Mirrors, history entries and "recent builds" copies must be purged on the same rule (as for student deletion in CR-2).

### 5.5 Gracious reply templates (short)

1. **Acknowledgement to reporter (only when a hold was applied; for incomplete claims use claims-process.md templates 1-2)**: `Thank you for telling us. We have paused "{title}" while we look into it, and we will write to you again by {date}. We take other people's work seriously, and we are grateful you helped us get this right.`
2. **To the uploader (item paused)**: `Hello {name}, someone asked us to check "{title}", so we paused it for now. It is not a punishment; we just want to be sure the credit and licence are right. You can reply with where it came from or edit the credit, and we will take a quick look.`
3. **To a creator: credit corrected**: `Thank you, {creator}. We have corrected the credit on "{title}": {new credit line}. If anything else is wrong, please tell us. We are grateful for your work.`
4. **To a creator or rights holder: removed**: `We have removed "{title}" and everything made from it. We are sorry for the trouble, and thank you for letting us know.`
5. **To a remixer whose parent was removed**: `The model "{title}" is based on a design that has been removed at its creator's request, so your remix is paused. Thank you for sharing it; you may be able to republish it as an original or with a different base.`
6. **Declined complaint (needs counsel before use)**: `Thank you for writing. We looked carefully at "{title}" and it appears to be shared under {licence}. If you have more information, please send it and we will look again.`

Tone: warm, plain, no legal threats, no blame, no promise we cannot keep.

---

## 6. Community uploads (when sharing opens)

Required on every share/publish, enforced **server-side** (not just in the form):

1. **Rights confirmation** (checkbox, not pre-ticked), exact text: `I made this myself, or I have the right to share it, and I chose its licence below. I understand ZEIM will show my username as the creator.` Stored with timestamp and version of the text (no extra personal data).
2. **Where it came from** (required one-line `provenance`): `I designed it`, `I made it from my own photo`, `Based on {link} by {creator} ({licence})`. If "based on" then it is a remix: licence rules in 2.3 apply.
3. **Licence picker (required, nothing pre-selected)**: `CC0 (public domain)`, `CC BY 4.0`, `CC BY-SA 4.0`, and `Private (only me)` / `Class only`. Each option has a one-line plain-language explanation and a link to its deed. NC and ND are **not offered** in v1 (Zach decided).
4. **Photo-derived models**: only for photos the uploader took or has permission to use; no photos of identifiable people without consent (see send-privacy.md). A lithophane of someone else's artwork or a famous character is not "yours": Report route applies. Photo EXIF/GPS never shipped (existing rule).
5. **Creator label**: the account **username** only (section 8); never a real name or email; no links in free text (existing filter). Credit is withdrawn to `a ZEIM maker` on request.
6. **Moderation**: items are hidden until the automated checks pass (mesh check, text filter, licence fields complete); the report button is on every shared item; pause (hold) on a proper report, with proof required for ownership claims (section 9).

**Default if the licence is unset** (my proposal; **needs counsel**): the item cannot be published. It stays **`Private (only me)`**. Why not "All rights reserved, view only, no download" as the default: that would still *display* someone's work publicly, which needs an express display grant in the Terms and, for a child's work, a parent/teacher decision; Private needs neither. The creator may *choose* `All rights reserved, view only, no download` as an explicit option only after counsel confirms the ToS grant works (Edit and download both off, no remix).

For **Originals** the licence is fixed by Zach: **CC BY 4.0, credit to ZEIM**, pending counsel (section 1.5). It must be identical on the card, detail page, download and 3MF/STL metadata.

---

## 7. Checklist for Engineering and QA

### 7.1 Data file fields (one record per model; same fields for library, Originals and uploads)

Names below follow `library/manifest.json` (already present on all 195 kept entries) so Engineering can extend it rather than rename it. **Public data (JSON served to browsers, `/credits`, search index, downloads) must never contain: email, date of birth, real name, age, class/school, raw account id, IP.**

| Field | Type | Required | Rule / example |
|---|---|---|---|
| `id` | string | yes | stable slug, `chess-chess-bishop` |
| `title` | string | yes | as given by the creator |
| `creator_kind` | enum | yes (new) | `third_party`, `zeim_original`, `community` |
| `creator` | string | yes | third party: as published (`Olivier Wagener (GitHub: 0x3b29)`); Originals: `ZEIM`; community: **copy of `creator_username`** |
| `creator_username` | string | community: yes (new) | the account username (section 8); the **only** public identity; empty for third-party and Originals |
| `creator_url` | url or empty | no | third-party profile link (https only); community: the ZEIM profile path **only if the profile is public**; never a mailto |
| `creator_verified` | bool | yes | false for repo-owner/uploader-declared (162 of 195 today) |
| `creator_contact_public` | bool | community (new) | default **false**; true only if the user explicitly opted in to show a contact email; the email itself is **not** in this record (kept in private account info) |
| `source_url` | url | yes (3rd-party) | page where it can be found, pinned if possible. Originals/uploads: ZEIM item page |
| `license_id` | enum | yes | `cc0-1.0`, `public-domain`, `public-domain-us-gov`, `unlicense`, `cc-by-4.0`, `cc-by-sa-4.0`, `private`, `class-only`; anything else (including NC/ND/unknown) = blocked. ZEIM Originals use `cc-by-4.0` |
| `license_confirmed` | bool | Originals: yes (new) | false until counsel confirms (section 1.5); launch validator fails while false |
| `license_name` | string | derived | from a fixed table, e.g. `CC BY 4.0` |
| `license_url` | url | yes except private | **from the fixed table**, not free text; see 2.1 |
| `license_evidence_url` | url | yes (3rd-party) | LICENSE file or file page |
| `share_alike` | bool | derived | true for BY-SA |
| `credit_line` | string | derived | short card form (1.2) |
| `credit_full` | string | derived | detail/embedded form (1.4) |
| `changes` | list of {who, date, token, text} | yes (may be empty) | section 3.2; `who` = username or `a ZEIM maker` |
| `remix_of` | list of ids | no | section 3.3 |
| `provenance` | string | yes | Originals: how/by whom it was made and "not copied from any character, logo or franchise"; community: section 6.2 |
| `printer`, `printer_guess` | enum, bool | yes | `fdm`, `resin`, `both`; `printer_guess` true until tested (label "Suggested") |
| `fit_note` | string | Originals yes | small parts / needs supports |
| `rights_confirmed_at` | datetime | uploads | with text version |
| `status` | enum | yes | `ready`, `hold` (licence unclear), `not_ready` (mesh/fields failing), `paused` (reported), `removed` |
| `status_reason` | string | when not ready | shown to staff only |
| `audience` | enum | yes (new) | `all`, `13plus`, `adult`; `classroom_ok` bool. Used to hide categories (for example Wildlife Calls) from classrooms and under-13 (library-legal-review.md) |
| `retrieved` | date | 3rd-party | `2026-10-04` |

**Validator (shows nothing public unless all pass):** all required fields non-empty; `license_id` in the allowed table; `license_url` equals the table value; `credit_line` re-derives from the fields; `status == ready`; mesh is watertight (or flagged view-only); no NC/ND/unknown; every parent in `remix_of` is `ready`; Originals have `license_confirmed == true` before public launch; **public JSON passes an "identity scan"**: no field matches an email regex, no `creator` equals a known real-name field.

### 7.2 QA test list (Filter Red-Team Tester / QA)

| # | Test | Expected |
|---|---|---|
| A1 | Open every `ready` card in Showcase/Catalog | each shows creator + licence short text; no card without both |
| A2 | Detail page for a CC BY, a BY-SA, a CC0, a NASA, a Smithsonian, an Original item | matches the examples in 1.3; links go to the table URLs; licence link opens canonical text |
| A3 | The 6 HOLD items and the 20 manifest-less folders | not listed, not searchable, direct URL 404/"not available", not in sitemap/search |
| A4 | Remove `creator` / `license_id` / `credit_line` from a test record | item disappears from public lists; validator names the field |
| A5 | Put an NC / ND / `unknown` licence on a test record | blocked, never shown |
| A6 | Download 3MF of a CC BY item | unzip, read `3D/3dmodel.model`: `Title`, `Designer`, `Copyright`, `LicenseTerms`, `Description` present and escaped; opens in PrusaSlicer without error |
| A7 | Download STL, OBJ | binary STL header is the short credit, does **not** begin with `solid`, still loads; OBJ has `#` credit lines; filename follows 1.4 |
| A8 | Zip / "download with credit" | contains `README-credit.txt` with title, author, source, licence, changes |
| A9 | Credit strings with `"`, `<`, `&`, `'`, long names, Japanese kana, emoji, newline injection | escaped/neutralised everywhere (HTML, XML, header); no script injection on /credits or cards |
| A10 | Long title/creator | card truncates title, never creator/licence |
| B1 | Edit: scale, add text, hollow on a CC BY item | detail page and new download gain `Modified by ZEIM user ... (changes: ...)`; earlier notes preserved on a second edit |
| B2 | Edit a BY-SA item then publish | remix licence forced to CC BY-SA 4.0; picker blocks others |
| B3 | Mixed remix (BY-SA + unknown) | publish blocked with a kind explanation |
| B4 | Remixer is a minor/class student | credit shows `a ZEIM maker`; no real name in page, file, zip |
| B5 | Remove a parent item | child hidden; remixer message uses template 5.5 #5 |
| C1 | /credits renders from the data file | footer link on all pages; page loads logged-out; edit the data file wording, page changes without code change |
| C2 | Open-source list | versions/licences equal `pip`/`importlib.metadata`; a blank licence (mapbox_earcut) fails the build check or shows "check upstream" |
| C3 | Trademark line present; Creality, Shapr3D, Prusa/PrusaSlicer used only factually; no "approved/compliant/certified/official partner" text anywhere | grep the whole UI/README |
| C4 | Accessibility of /credits and credit chips | headings, link names (not "click here"), contrast, 44 px targets, keyboard path |
| D1 | Report "not mine" on a community item | hidden from public lists and downloads at once; owner sees "paused"; ack shown |
| D2 | Report type minor-safety | still hides instantly (existing behaviour; do not regress) |
| D3 | Takedown purge | thumbnails, previews, history, search, signed `/f/` links stop serving the item |
| D4 | Contact placeholder | visible on /credits and in README-credit.txt; build fails if it still reads PLACEHOLDER when `PHOTO3D_PUBLIC_LAUNCH=1` (or the launch checklist item is open) |
| E1 | Upload with no licence chosen / unticked rights box | cannot publish (server-side, not just the UI); stays Private |
| E2 | Originals validator | every Original has `provenance`, `printer`, `fit_note`, the shared licence line; non-watertight ones (Haruto listed two) stay out of Showcase as "not ready" |
| E3 | Same licence line on card, detail page, download, 3MF `LicenseTerms`, STL header | all identical (diff test) |
| F1 | Community item credit uses `creator_username` | card, detail, 3MF `Designer`, STL header, README-credit.txt, filename all show the username, no `@`, no real name/email |
| F2 | Public JSON/HTML/search index scan | no email address, DOB, raw account id; `creator_contact_public` false by default |
| F3 | User opts in to show contact email (when that exists) | shown only on their profile, only adult accounts, never in credit strings or downloads; opt-out removes it everywhere within one refresh |
| F4 | Username rules (section 8.2): spaces, dots, `@`, Unicode look-alikes, reserved words (`zeim`, `admin`, `nasa`, `official`), duplicates with different case, profanity, contact info | rejected with the standard messages; nothing stored |
| F5 | Rename a username | credit lines regenerate on next view; old downloads keep the old name (expected); no real-name leak via history |
| F6 | Delete account / withdraw credit | credit becomes `a ZEIM maker` on cards/pages; third-party credits in remix chains unchanged |
| G1 | Originals credit strings (1.5) | exactly match on card, detail, `LicenseTerms`, STL header, README, filename; `license_confirmed false` blocks the public-launch build |
| G2 | NC/ND/unknown in the licence picker or import | not offered / rejected |
| H1 | Bare ownership claim ("this is mine") | auto-reply asks for proof; **nothing hidden**; claim closes after 14 days if no evidence |
| H2 | Complete claim with strong dated evidence | item held within 2 business days; hidden from list, search, direct URL, signed links; owner sees "paused" |
| H3 | Claimant/uploader privacy | claimant never sees uploader username/age/class; notices for a minor go to the teacher |
| H4 | Rate limits and claimant strikes | 4th open claim refused; bad-faith finding records a strike |

---

## 8. Creator identity: usernames and email (Zach D2)

### 8.1 What the app does today (read-only, `app/` at HEAD `375f9c4`)

* **Accounts (13+)**: signup takes `display_name` and `dob` only (`app/community/identity.py`, `signup()`; route `POST /api/me/signup` in `app/api/community.py`). The name is trimmed, capped at 40 characters, and passed through `safety.filter_only(name, "Display name")` = the **language filter + personal-info filter** (email, URL, phone, address, `@handle`, social-platform handles; `app/community/safety.py`). **There is no username field, no uniqueness check, no character whitelist, no reserved names, and no email is collected** (I found no email field in `identity.py`; DOB is stored only after the age checks pass). Under-13: no accounts (`MIN_SIGNUP_AGE = 13` in `app/config.py`).
* **Teens (13-17)**: Private only; no public profile or project; adults cannot follow teens (HQ decisions).
* **Class students**: no account; join with a **nickname**: regex `^[A-Za-z0-9 _-]{2,20}$` (`app/community/classrooms.py`, `NICK`), unique per class (case-insensitive), same language + personal-info filter, error text `Nickname must be 2-20 letters/numbers. Do NOT use your real full name.` Showcase is off for class students (commit `8fc9f0a`).
* **Gap:** nothing in the code detects a *real name* (I searched `app/` for "real name" and name lists and found only the warning text above; UNVERIFIED that no other check exists). A child can type "Mia Tanaka" and pass.

### 8.2 Username standard (proposal; Engineering to build, **needs Zach approval** for the under-18 pieces)

1. **One field, `username`**, unique case-insensitively, 3-20 characters, `[A-Za-z0-9_-]` (no spaces, no dots, no `@`). Reuse the same language + personal-info filter on create and on rename. Reserved/impersonation block-list: `zeim`, `admin`, `moderator`, `support`, `staff`, `official`, `teacher`, `nasa`, `smithsonian`, names of credited creators and platforms.
2. **Under-18 (teens, class students):** username must not be a real name. Because that cannot be detected reliably: (a) default suggestion is a generated nickname (adjective + animal + number); (b) the field shows the existing warning `Do NOT use your real full name.`; (c) free-form choice allowed but passes the same filters; (d) teacher/admin can force a rename; (e) the report route covers "this looks like a real name". Existing nickname rules (regex above) stay the minimum for class nicknames.
3. **Rename** allowed (rate-limited); credits derive from the *current* username; previously downloaded files keep the old string (documented). Keep a private history for abuse handling; never show it.
4. **Public identity = username only.** No real name, no email, no DOB, no age band shown or stored in public data (7.1).

### 8.3 Email

* Email (when accounts get one) is **private account information**: never in public JSON, credit strings, filenames, logs (existing log redaction), or shared links.
* **Opt-in public contact** (adults only, off by default, explicit consent text, easy to switch off): shows a contact email on the creator's *profile page* only, never inside credit lines or downloads. Spam and harassment risk is real: advise a separate address. Teens and class students: never.
* Email may be used by ZEIM only for the account and for claims notices to that account; not for marketing without separate consent. Privacy-policy wording and any children's-data duties: **needs counsel**.

---

## 9. Claim process (summary; full design in `reports/claims-process.md`)

Zach's rule: **takedown only with proper proof; a bare "that's mine" removes nothing.** Until counsel approves, ZEIM promises only a **temporary hold** and a **human review**, not specific legal outcomes. **Haruto must not build the claim form, hold switch or queue until Kenji's process is approved.**

| Topic | Rule (details in claims-process.md) |
|---|---|
| Kinds | A safety/privacy: hide at once. B credit correction: fix, no hold. C ownership/rights claim: proof required |
| Evidence (C) | claimant identity (verified email, organisation letter for agents); the item; **dated** link to the original listing, original project files, dated drafts/screenshots, licence/authority letter; good-faith statement; accuracy/authority statement (**wording needs counsel**) |
| Hold rule | H0 incomplete or bare: no change, auto-reply lists what is missing, open 14 days. H1 complete + strong (or two consistent medium) dated evidence: **hold** within the 2-day acknowledgement. H2 claimant is the named creator on the item's own source page: hold on complete intake. H3 safety/privacy: immediate hold. H4 reviewer discretion for serious visible risk, reason logged |
| Review | A person decides; checklist (identity, dates, same work, licence allows our use, credit fix vs removal, remixes, minors); outcomes: rejected, more info, credit corrected, licence corrected, upheld-removed, escalated to counsel; second person approves disputed permanent removals |
| Counter-notice | uploader told a summary, may reply with evidence within 10 business days; we decide within 10 business days; **statutory counter-notice mechanics and timing: needs counsel** |
| False claims | ToS clause (needs counsel), rate limits (3 open per claimant, 10 per 30 days), claimant strikes only for **bad faith** (3 = blocked) |
| Repeat infringers | count **validated** findings only; proposal 1 removal, 2 paused 30 days, 3 uploading ended; **OPEN with Zach; needs counsel** |
| Minors | notices go to the classroom teacher or the account in-app; no personal data to claimant; hold only, no permanent removal without teacher/guardian response or window end; **conflict with statutory counter-notice identity rules: needs counsel** |
| Audit log | claim id, dates, kind, rule, reviewer, decision, reason, templates sent; no evidence files, emails, usernames of minors, IPs |
| Legal formalities | DMCA designated agent registration (<https://www.copyright.gov/dmca-directory/>, I did not read the rules), penalty-of-perjury wording, counter-notice timing, jurisdiction: **all needs counsel** |
| Open with Zach | ZEIM-owned claims mailbox (not Zach's personal email); repeat-infringer thresholds |

---

## 10. Hansei (what I could not verify, and what I may have wrong)

* I did not read the Smithsonian Open Access terms, CC0/Unlicense texts, CC 3.0 licences, NASA merchandise/brand guidelines or US DMCA section 512. I read CC BY 4.0 in full and the quoted passages of BY-SA/BY-NC/BY-ND 4.0, CC's attribution best-practices page, the 3MF core spec's predefined metadata table, the 3DBenchy.com licence page and (for the library review) NASA's media-guidelines page, all on 2026-10-04.
* I re-audited the **verified** manifest (195/24) at about 19:35 CT; it may change. I did not re-fetch the evidence behind the "verified" flags: I trust, not re-proved, the manifest's own hash and API checks.
* 162 of 195 creators are as-declared; I checked no creator against a second source. I read titles, not meshes, for the family-friendly review (library-legal-review.md section 1).
* STL-header behaviour in slicers, 3MF custom namespaced metadata, and whether slicers keep `LicenseTerms` on import were not tested. Open-source licence rows are from package metadata, not upstream files; `mapbox_earcut` is blank; `pillow-heif` bundled libraries need reading; PrusaSlicer AGPL consequences (including our Dockerfile) are **needs counsel**.
* I found no real-name detection in the code (section 8.1), but a search can miss things. Username rules are my proposal; under-18 handling needs Zach.
* The 14-day evidence wait, 10-day reply window, claimant strikes, retention periods and the repeat-infringer numbers are my proposals. DMCA details, ToS and privacy wording, AGPL, ND/NC, non-US law, COPPA/FERPA, trademark clearance of ZEIM/Make/Originals names, the Originals' authorship and licensor entity, and every "ZEIM Original is CC BY 4.0" statement are **needs counsel**.
* Nothing here says ZEIM is "compliant" with anything, and the Credits page must not either.
