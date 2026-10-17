# ADULTS-ONLY POLICY — DRAFT

> **DRAFT — NOT LEGAL ADVICE — DO NOT PUBLISH AS-IS.**
> Working draft for lawyer review. Original text; `[BRACKETED]` items are owner
> decisions. Sources checked October 17, 2026 (see Sources).

## 1. The rule

**[SITE NAME]** is for adults only: you must be at least **18 years old** to
create an account or use the Service. There are no exceptions, no school or
minor features, and no family-sharing mode. This rule exists for two reasons:

1. **Safety obligations scale with the audience.** A service that can be
   accessed by minors attracts children's-safety duties — under the UK Online
   Safety Act, for example, services likely to be accessed by children must
   assess risk to children and use age assurance for certain harmful content,
   duties enforceable since July 25, 2025. An adults-only design is the
   operator's chosen response to that risk; **[LAWYER: assess whether it is a
   sufficient response for a service of this content mix — this draft takes no
   position.]**
2. **Moderation reality.** The Service hosts user-generated 3D models and
   photos. An adults-only community with a strict no-NSFW content rule is a
   far smaller moderation problem than an all-ages one. **[LAWYER: this draft
   takes no position on how content categories map to legal exposure.]**

## 2. How the gate works (implementation)

- **Signup**: date of birth is required, and accounts with an under-18 date of
  birth are refused (**[confirm the signup flow actually rejects them — see
  engineering notes]**).
- **Stated everywhere**: the 18+ rule appears in the Terms, at signup, and in
  the community guidelines shown before first publish.
- **Enforcement, not just declaration**: if we learn an account holder is under
  18 — from their own statements, a report, or a takedown request — we close
  the account and delete their personal information, subject to the
  legal-preservation exceptions in the Privacy Policy (Privacy Policy §6).
- **No interest in verification theater**: we do not collect government IDs for
  age verification. A date-of-birth gate plus active enforcement is the current
  design choice; **[LAWYER: assess whether any target market's law requires
  more for a service of this type and content mix — e.g. UK rules on "highly
  effective age assurance" — and whether the no-NSFW content rule changes
  which duties attach. This draft takes no position on sufficiency.]**

## 3. No NSFW content, for anyone

The adults-only gate is not permission for adult content. Sexual content,
nudity, and pornographic uploads are prohibited for all users (Terms §4) and
removed when identified. This is deliberate: it keeps the Service out of the
most heavily regulated content categories while keeping the community
comfortable for hobby printing.

## 4. Minors who slip through

If a minor creates an account despite the gate, the account is closed and
their personal information is deleted, subject to the legal-preservation
exceptions in the Privacy Policy. Because we do not knowingly collect
children's data, we do not design the Service for children — the applicability
and response for a discovered minor account under the U.S. children's-privacy
statute is **[LAWYER: a review item — do not assume scope or outcome from this
draft.]**

---

## Sources (checked October 17, 2026)

- UK Government, Online Safety Act collections (children's duties since
  July 25, 2025; age-assurance expectations):
  https://www.gov.uk/government/collections/online-safety-act
- UK Online Safety Act 2023 s.35 (children's access assessment — a provider
  may conclude children cannot normally access the service where age
  assurance is in place):
  https://www.legislation.gov.uk/ukpga/2023/50/part/3
- FTC, Children's Privacy (COPPA) business guidance:
  https://www.ftc.gov/business-guidance/privacy-security/childrens-privacy
- Ofcom, approach to implementing the Online Safety Act (children's access
  assessments, proportionality):
  https://www.ofcom.org.uk/siteassets/resources/documents/online-safety/information-for-industry/roadmap/ofcoms-approach-to-implementing-the-online-safety-act
