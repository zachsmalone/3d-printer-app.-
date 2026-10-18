# NCMEC escalation procedure (CSAM reports)

**This document is a procedure, not legal advice.** It describes what ZEIM does when a report
involves suspected child sexual abuse material (CSAM). ZEIM is an 18+ site; CSAM is illegal,
and U.S. law (18 U.S.C. § 2258A) requires reporting it to NCMEC's CyberTipline.

## The rule

Suspected CSAM is **never** handled like ordinary moderation content:

1. **Do not share, forward, or re-upload the material anywhere** — not to another moderator, not
   to a chat, not to email. The report context and preserved evidence stay on the server.
2. **Do not tip off the account holder.** No "we removed your item because..." message.
3. **Preserve first, then escalate, then report — all within 24 hours.**
4. **Do not delete the account or content** while law enforcement may need it. ZEIM's normal
   rules ("accounts and data are never deleted") happen to be the correct CSAM behavior too.

## Step-by-step

### 1. Secure the report (automatic)

Every report already records the reporter's IP, user agent, and timestamp
(`app/community/moderation.py: report(ip=..., user_agent=...)`). Reports with reason
`minor_safety` hide the item immediately. The report lands in the admin queue
(`GET /api/moderation/queue`).

### 2. Preserve the evidence (admin)

```
POST /api/moderation/report/{report_id}/preserve
```

This copies the item's files and the report context into `DATA/preservation/<report_id>/`
(directory mode 700, files mode 600, never served by any route). Preservation happens BEFORE any
escalation decision.

### 3. Escalate (admin)

```
POST /api/moderation/report/{report_id}/escalate-ncmec   {"note": "why"}
```

This marks the report `escalated_ncmec` and writes a CRITICAL audit entry. **It does not submit
anything anywhere** — the next step is a human action, deliberately.

### 4. File the CyberTipline report (human, within 24 hours)

The operator (Zach) signs in at https://report.cybertipline.com and files the report:

- include the preserved files (upload per the CyberTipline's CSAM report flow),
- include the reporter's IP + user agent + timestamps from the preservation sidecar,
- keep the CyberTipline report number in the escalation note (`escalate-ncmec` again, or the
  admin log) so the paper trail connects.

If you cannot access the CyberTipline for any reason, call NCMEC at 1-800-843-5678 for guidance.

### 5. Cooperate, keep records, do not destroy

Preserve the evidence for at least 90 days (18 U.S.C. § 2258A preservation expectation) and longer
if law enforcement asks. Keep the audit trail intact — `GET /api/moderation/audit` is the record of
who decided what and when.

## Why no automated hash-matching yet

PhotoDNA/CSAI-Match class integrations require agreements with those providers and cost money;
ZEIM's launch posture is: humans review every report (the default image-moderation hook already
requires human review of print photos), preservation + escalation are built, and the CyberTipline
filing is a documented human step. Hash-matching remains on the roadmap as budget allows.

## What is deliberately NOT built

- No auto-deletion of accounts (preservation requires the records).
- No auto-submission to NCMEC (wrong or delayed automated reports are worse than a human filing).
- No forwarding of content to third parties of any kind.
