# ZEIM Claim Process (v0.1 DRAFT, design only)

Owner: Kenji Watanabe (Trust, Safety & Legal). Written 2026-10-04 (CT). Part of `reports/attribution-standard.md` (section 9 summarises this file).

> **Kenji is not a lawyer. This is a proposed process, not legal advice.** Lines tagged **needs counsel** must be read by a lawyer before launch. **UNVERIFIED** = not confirmed from a primary source.
>
> **What ZEIM promises until counsel approves this: only (1) a temporary *hold* when a claim is complete on its face, and (2) a *human review*. ZEIM does not yet promise any specific legal outcome, timeline set by law, or "DMCA compliance".**
>
> **Haruto / Engineering: do NOT build the claim form, the hold switch or the claim queue until Kenji's process is approved by Zach (via Mr. Yami Kato).** This file only lists what the form will need.

Zach's rule: **a takedown needs proper proof. A bare "that's mine" removes nothing.** Zach's tone: honest, honorable, grateful, never hostile to either side.

Settled by Zach (2026-10-04): acknowledge a report within **2 business days**; decide within **10 business days**; **pause (hold) on a proper report**. Still open with Zach: a **ZEIM-owned** claims mailbox (a role address, not anyone's personal email) and the **repeat-infringer policy** (section 8; thresholds below are proposals).

---

## 1. Three kinds of report (they are handled differently)

| Kind | Example | Evidence needed | Hold? |
|---|---|---|---|
| **A. Safety or privacy** | a child in danger, a photo of a person, personal info, minor-safety | none to start | **Immediate hide**, no evidence needed (existing guideline; do not weaken) |
| **B. Credit correction** | "my name is spelled wrong", "please credit my profile" | light: a link that shows the claimant controls the named profile/page | No hold; fix the credit within 2 business days |
| **C. Ownership / rights claim** ("this is mine", "you can't host this") | copyright, trademark, "not licensed to you" | **proper proof (section 2)** | Hold only under the rule in section 3 |

A bare statement ("this is mine", "remove this") in kind C is **acknowledged and answered with what is needed; nothing is hidden**.

## 2. Required evidence (kind C)

Claimant must give **identity + a clear identification of the work + evidence of ownership or authority + good-faith statements**. Evidence is weighed, not just counted.

| Evidence | What counts | Weight |
|---|---|---|
| **Link to the original listing** | a public page of the work that is **dated earlier** than the ZEIM upload (GitHub repo/commit, Printables/Thingiverse/Cults page, Wikimedia file page, personal site, museum page) and visibly names the claimant | strong |
| **Original project files** | the editable source (CAD/slicer project: `.f3d`, `.step`, `.scad`, `.blend`, project `.3mf` with history) that rebuilds the work; we compare shape/hash/structure | strong |
| **Dated drafts / work-in-progress** | screenshots, renders or files with dates (version history, cloud-file history, commit log) showing the work evolving | medium (screenshots are easy to fake; need two or more dated, consistent items) |
| **Licence / permission document** | the rights holder's written licence or the authority letter when the claimant is an agent | strong (agent claims: required) |
| **Registration or trademark number** | a registered copyright or trademark record that matches | medium (shows ownership of *a* work/mark; reviewer still checks it is *this* work) |
| **Claimant identity** | full name (or organisation), role, contact email we can verify (a link we send must be clicked), and for an organisation an address on its domain or a signed letter | required |
| **Identification of the ZEIM item** | its page link/id and the exact file(s) | required |
| **Good-faith statement** | "I believe in good faith that this use is not authorised by the owner, its agent or the law" | required; wording **needs counsel** |
| **Accuracy and authority statement, under penalty of perjury** | statement that the information is accurate and the claimant is the owner or authorised to act | **wording and whether it is required: needs counsel** (this is a legal-notice formality; do not invent it) |

Not enough on their own: an unsupported statement; a screenshot with no date; a link to the claimant's *own page created after* the ZEIM upload; "I saw it somewhere"; a claim about a CC0/public-domain item with no evidence that the dedication was made by someone else (that is a different argument: see 6, "licence challenge").

## 3. When a HOLD is applied, and when we wait for evidence

**Hold = temporarily hidden from public lists, search and downloads; the owner still sees it with a "paused for review" badge; nothing is deleted.** Not a finding that anyone did wrong.

| Rule | Condition | Action |
|---|---|---|
| **H0 (no change)** | kind C intake is incomplete, or is a bare assertion | Item stays visible. Auto-reply lists what is missing. Claim stays open **14 calendar days** for evidence (proposal, Zach to approve), then closes as "insufficient"; the claimant may file again with proof. |
| **H1 (hold)** | intake complete (all required fields) **and** at least one *strong* item, or two consistent *medium* items, with a date earlier than the ZEIM upload | **Hold now** (within the 2-business-day acknowledgement), human review starts. |
| **H2 (hold, third-party library item)** | claimant is the creator named on the item's own source page and shows control of that page/account (e.g. the GitHub owner), or is the named organisation | Hold on complete intake; faster review. |
| **H3 (immediate hold, no evidence needed)** | kind A (safety/privacy), or a credible claim that the item contains personal data or an identifiable photo | Hide immediately; review next business day. |
| **H4 (reviewer discretion)** | incomplete claim but a reviewer sees a serious risk (for example a clearly copied trademarked logo or character in plain sight) | Reviewer may hold with a written reason in the log; the reason is *the risk seen by us*, not the claimant's say-so. |

Rate/abuse guards (section 7) apply before H1. A claim is never held for the sole reason that the claimant is persistent or loud.

## 4. Human review

Every claim is decided by a **person**, never automatically. v1 reviewer: Kenji or a delegate named by Mr. Yami Kato; **a second person approves any permanent removal that the uploader disputes** (two-person rule, proposal). A reviewer must not review a claim about their own work.

### 4.1 Reviewer checklist

1. Identity verified (email link clicked; organisation domain or letter checked).
2. Claimant's evidence dated **before** the ZEIM upload (compare to `created` in the item record).
3. Same work? Compare geometry/structure, not just title. Note differences; check for a *remix chain* (maybe both are remixes of a third work).
4. Licence check: does the claimant's own page offer the work under a licence that allows our use (CC0/CC BY/BY-SA)? If so the claim may be a *credit* issue (kind B), not a takedown.
5. Is the ZEIM copy credited to the claimant under the licence's terms? If not, fix the credit and say so.
6. Uploader response read (counter-notice, section 5) and its evidence weighed the same way.
7. Any trademark, character, logo or person's likeness issue? (different standard: **needs counsel** for borderline cases)
8. Minor involved on either side? Apply section 9 before sending anything.
9. Decision picked from 4.2, reason written in plain words (no personal data).
10. Remixes/children of the item checked and handled (hidden or re-credited).
11. Audit entry written (section 10). Notices sent from the templates (section 11).

### 4.2 Decision outcomes

| Outcome | Meaning | Effect |
|---|---|---|
| **Rejected / insufficient** | evidence does not show the claim | hold lifted; item restored; claimant told why and may re-file with more |
| **More information needed** | specific question to claimant or uploader | hold stays up to 10 more business days; then decide on what we have |
| **Credit corrected** | the claimant is right about credit, not about removal | credit/licence line fixed on page, files and downloads; hold lifted |
| **Licence corrected** | licence on ZEIM was wrong or unsupported | corrected, or item hidden if the true licence is not one we host (NC/ND/unknown) |
| **Upheld: removed** | claim shown | item deleted (files, previews, caches, search, signed links) and children handled; **counts toward repeat-infringer rule only if "validated"** (section 8) |
| **Escalated to counsel** | borderline, high-stakes or legal-notice formalities | stays on hold; Zach/counsel decide |

## 5. Counter-notice (uploader's reply)

* The uploader is told **what was claimed (summary), what was held, how to reply, and the date** (a *summary only*, see minors rule in 9). Their reply form asks: own-words explanation; evidence in the same categories as section 2 (original files, dated drafts, link to original or licence); a statement that the item is theirs or properly licensed; whether they agree to be contacted for questions.
* **Reply window: 10 business days** from the notice (proposal for Zach). No reply = decision is made on the claimant's evidence alone.
* **Decision within 10 business days of the uploader's reply or of the window closing** (matches the accepted "decide within 10 business days" target; Zach to confirm it applies per step).
* Neutral outcome if both sides have evidence and we cannot tell: the item stays **held, not published**, and both are told; escalate to counsel (we do not decide ownership disputes).
* **Formal DMCA counter-notification** (statutory content, a statement under penalty of perjury, consent to jurisdiction, the 10-14 business-day restoration timing, forwarding rules) **needs counsel**. Until counsel approves this wording, ZEIM does **not** claim to run a statutory counter-notice process; it runs the human review above.

## 6. Other special cases

* **Licence challenge**: someone says a CC0/CC BY item was licensed by a person who did not own it (typical for GitHub repos and uploader-declared Wikimedia items). Treat as kind C: the claimant must show they own the work or are authorised.
* **Claimant is the named creator of a third-party item and asks for credit changes or removal**: for CC BY the licence says the credit information must be removed on request "to the extent reasonably practicable" (CC BY 4.0 s.3(a)(3), read 2026-10-04). Removal of credit alone is always honoured; removal of the *work* needs the licence analysis above (the licence is irrevocable for copies already shared: s.2(a)(1), s.6(c) lets a licensor stop distributing, so a polite "stop distributing" request from the true licensor is normally honoured by us). **needs counsel** on exact consequences.
* **Trademark or character complaints**: same intake, but the question is "does it use a protected mark or character", not "who made the shape". **needs counsel** for anything not obvious.
* **Cross-claims** (A says B stole; B says A stole): both held; counsel.

## 7. Protection against false or abusive claims

* **Terms of Service clause** (wording **needs counsel**): knowingly false claims are not allowed and may be refused and the claimant blocked; whether and what legal liability applies for knowing misrepresentation (US law has a provision for this in the DMCA, 17 U.S.C. section 512(f): UNVERIFIED, I have not read it) is **needs counsel**. Do not threaten legal action in our templates.
* **Rate limits** (proposal): 3 open claims per claimant at a time; 10 new claims per claimant per 30 days; 5 per network address per day; a claim needs a verified email before it is queued.
* **Claimant strikes**: a claim closed as **bad faith** (reviewer finding: forged/misdated evidence, claiming others' work as theirs, harassment) = strike 1 warning; strike 2: 90 days blocked from filing; strike 3: permanently blocked from filing (appeal to Kenji). An honest mistake or "insufficient evidence" is **not** a strike.
* **No retaliation tools**: claimant never gets the uploader's identity, class or age.
* **Targeting patterns**: if one claimant files against many items of one uploader, a reviewer looks at the pattern before any more holds.

## 8. Repeat-infringer handling (open with Zach; **needs counsel**)

A repeat-infringer policy is generally expected by US law for platforms that want the DMCA safe harbour (17 U.S.C. s.512(i): UNVERIFIED, not read by me; **needs counsel**). Only **validated** outcomes count: "Upheld: removed" where the uploader either did not reply in the window or the reviewer found their evidence insufficient. **A claim, a hold, or a rejected claim never counts.**

| Validated findings (rolling 12 months, per uploader account) | Proposed action |
|---|---|
| 1 | Item removed, friendly note, link to the licence picker guide |
| 2 | Uploading paused 30 days; must re-confirm the rights checkbox with a short quiz; item(s) already live stay unless claimed |
| 3 | Uploading ended for that account (appeal to Kenji; review in 14 days). Learning features and downloads stay. |

Under-18: no suspension by silent automation: the classroom teacher (class students) or the account's guardian contact (teens: UNVERIFIED how reached today, no guardian contact exists in the code) is informed first; consequence is "uploading paused" only. Zach to decide whether these numbers are right.

## 9. Minors (uploader under 18)

* ZEIM today: no accounts under 13; teens (13-17) are Private only (no public items); class students use nicknames in classrooms, and Showcase is off for class students (commit `8fc9f0a`, read 2026-10-04). So a public item from a minor is rare at launch, but a claim can still arise (class projects shared to the teacher, teen privately shared links, library-style uploads later).
* **Notices go to the classroom teacher** (for class students) **or to the account in-app** (teens); we never email a minor, never publish their name, age, class or school to the claimant, and never reveal that the uploader is a minor.
* **Hold only; no permanent removal of a minor's item without a teacher/guardian response or the end of the reply window.** A minor's counter-notice goes through the teacher.
* The claimant receives only: "the item has been held for review" and, at the end, the outcome. If a statutory counter-notice would require giving the uploader's name/address to the claimant, that conflicts with this rule: **needs counsel** (it is why we promise only hold + review for now).
* The claim record uses the item id and an internal hash of the account, never the nickname/username in exported logs.

## 10. Audit log (minimum data)

One record per claim, kept separately from the item: `claim_id`, `received_at`, `kind` (A/B/C), `item_id`, `claimant_ref` (internal id; contact kept in a separate store), `evidence_types` (list, no files), `hold_applied_at`, `rule` (H0-H4), `reviewer_id`, `decision`, `decision_reason` (plain words), `decided_at`, `notices_sent` (template ids + dates), `counter_received_at`, `strike_effect`. **Not stored in the log:** evidence files, emails, uploader username, minors' data, IP (keep rate-limit counters hashed and short-lived).

Retention (proposal, **needs counsel**): evidence files and claimant contact deleted 90 days after the claim closes; the one-line audit record is kept 3 years; if litigation or a legal request is possible, counsel decides.

## 11. Notice templates (short, gracious)

1. **Received (claimant), incomplete**: `Thank you for writing. To look into "{title}" we need a little more: {missing list}. Nothing has been changed yet. We hold requests open for 14 days, and you are welcome to send what you have. We appreciate your care for your work.`
2. **Received (claimant), complete**: `Thank you. Your request is complete, so we have paused "{title}" while a person reviews it. This is not a finding about anyone. We will write by {date}.`
3. **To the uploader (hold)**: `Hello. Someone asked us to check "{title}", so it is paused for now. Please send us where it came from (original files, drafts, or a link). You have until {date}. We will read it carefully and fairly.` (Minor: sent to the teacher; wording: `A student's project in your class "{title}" ...` with no names.)
4. **Outcome: restored**: `Thank you for your patience. After review, "{title}" is back. We could not confirm the claim. If you have more to show us, please write again.`
5. **Outcome: credit corrected**: `Thank you, {creator}. We have corrected the credit on "{title}" to: {credit line}. We are grateful for your work and sorry for the mistake.`
6. **Outcome: removed**: `We have removed "{title}" and the copies made from it. We are sorry for the trouble and thank you for telling us.`
7. **More information**: `We looked at your reply and have one more question: {question}. We will decide within 10 business days after we hear back.`
8. **Escalated**: `This one needs a closer look, so "{title}" will stay paused while we get advice. We will write again as soon as we can.`
9. **Bad-faith warning (claimant)**: `We could not match the details you sent to the work. Please check them. Requests that give wrong information may be refused in future.`

Tone: kind, specific, no blame, no legal threats, no promise of a legal result.

## 12. What Engineering needs later (fields, do **not** build yet)

**Intake form** (public page `/report-ownership`, no account required): kind (A/B/C chooser); ZEIM item link or id; what is claimed (copyright / trademark / not licensed to you / credit wrong / privacy); claimant full name or organisation; role (owner / agent / depicted person); contact email (verified by link); organisation website (optional); authority letter (agents; upload, small PDF/PNG, scanned for size/type); link to original listing; dated evidence (up to 5 files or links, size-capped; stored private); original project files (optional; hash + small preview only); how the ZEIM item differs or matches (free text, filtered); good-faith statement (checkbox + exact counsel-approved wording); accuracy/authority statement (counsel-approved wording: **needs counsel**); "I understand a bare claim removes nothing and false claims may be refused" (checkbox); anti-spam (rate limits, honeypot; no Google captcha without a privacy check).

**Staff side**: queue by age; hold/restore buttons (one action logs everything); reviewer checklist as required fields; decision picker (4.2); template picker; two-person approval for permanent removal; purge job (files, previews, caches, search, `/f/` links, history copies, children); retention timers; claimant-strike table.

**Tests for later**: bare claim changes nothing; complete claim with a strong item holds within the target; hold hides from list, search, direct download, signed link, and shows owner badge; minor uploader notice goes to teacher only; claimant never sees uploader identity; rate limits trip; audit record holds no personal data; purge removes every copy.

## 13. Hansei

* I have not read US DMCA section 512, any counter-notice rules, or non-US law; every legal formality above is a placeholder for counsel.
* Time targets other than 2 / 10 business days (14-day evidence wait, 10-day reply window, strike numbers, retention) are my proposals.
* There is no guardian contact or claims mailbox in the code today; the "teen notice" path is unspecified until accounts have an email/guardian model.
* Evidence-weight table is my judgement, not a standard; reviewers will need practice and a second opinion on hard cases.
