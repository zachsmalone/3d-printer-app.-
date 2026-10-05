# ZEIM free-model library: legal and safety review (v0.1 DRAFT)

Reviewer: Kenji Watanabe (Trust, Safety & Legal). Written 2026-10-04 (CT). Read-only review; nothing in `library/` or the app was changed.

> **Kenji is not a lawyer. This is a risk review, not legal advice, and nothing here says the library "complies" with any licence or law.** Items marked **needs counsel** must be read by a lawyer before launch. **UNVERIFIED** = I could not confirm it from a primary source.

## 1. What I checked, and what I did not

**Read (2026-10-04):** `library/manifest.json` (195 kept entries, 24 quarantined, `verified_on` 2026-10-04), `manifest.md`, `ATTRIBUTION.md`, `verification_evidence.json` (GitHub API licence/README evidence, Commons API licence + artist records, hash checks, NASA and 3DBenchy quotes), `library/originals/source/*.py` (descriptions and category of each ZEIM Original), and the live NASA guidelines page <https://www.nasa.gov/nasa-brand-center/images-and-media/> (fetched today).

**Checked by me:** every entry's id, title, category, licence id, licence/evidence URL, flags, notes and credit line (keyword and eye review of titles and descriptions for trademarked characters, logos, weapons, mature or hunting items, brand lookalikes); my own counts (licences: CC0 65, NASA 60, CC BY 26, Unlicense 16, CC BY-SA 15, public domain 13 = 195, all match the manifest summary); a rough single-angle render of three NASA-related models (Hubble 25th medallion, Astronaut 1, Astronaut glove).

**NOT checked:** the shape of the other ~190 models (I read names, not geometry); whether any file contains hidden text, logos or insignia inside the mesh; the licence files themselves beyond the manifest's quoted evidence (I trust, but did not re-fetch, the GitHub/Commons/Smithsonian evidence); the Smithsonian Open Access terms; whether any "own work" uploads on Commons are actually copied from elsewhere; whether file contents match their descriptions; whether the quarantined folders are safe (they are hidden, not reviewed). A human visual pass over all 195 previews is still needed before launch.

## 2. Quarantine check (24, must stay hidden)

Per `quarantined[]`: 2 x 3DBenchy (repo has no licence file; older copies BY-ND; the 3DBenchy.com page now says CC0 1.0 / public domain; re-admit only after counsel/Zach confirm the licence evidence), 4 x JRodrigoTech (BY-SA 3.0 vs 4.0 unresolved), 18 x `commons-*` stray folders with no manifest/source record (e.g. Big Ben, Gateway Arch, Space Needle, Shanghai Tower, Moai: **also real-world landmarks/buildings, see 6**). **Hide all 24.** The kept 195 contain none of them (I checked the ids).

## 3. NASA items (60): third parties, endorsement, insignia

**Which 60:** 47 from `nasa/NASA-3D-Resources` on GitHub (`nasa-*`) and 13 NASA models on Wikimedia Commons (`license_id: public-domain-us-gov`): `commons-agena-target-vehicle-agena-carbajal`, `commons-aqua-b-aqua-13`, `commons-astronaut-astronaut1`, `commons-astronaut-glove-astronautglove`, `commons-cassini-3d-model`, `commons-clementine-clementine-v01`, `commons-cloudsat-a-cloudsat1-composite`, `commons-cubesat-1-ru-generic-1ru-genericcubesat`, `commons-dawn-3d-model`, `commons-deep-impact-epoxi-68`, `commons-geotailsat`, `commons-mars-exploration-rover-nasa`, `commons-triana-concept-3d`. Counts verified: 47 + 13 = 60.

**What NASA says** (fetched today from the page above): NASA content "used in the rendition of 3-dimensional models ... generally are not subject to copyright in the United States"; may be used for educational or informational purposes; "NASA should be acknowledged as the source"; used "in a factual manner that does not imply endorsement". It also says "NASA occasionally uses copyright-protected material of third parties with permission ... those images will be marked identified as copyright protected with the name of the copyright holder. NASA's use does not convey any rights to others to use the same material." And at the top: "**The NASA Insignia, Logotype, identifiers, and imagery are not in the public domain**", and use of the Insignia, Logotype and identifiers "is protected by law". The page has a separate section on commercial use (no implied endorsement of goods or services) and on identifiable persons and current NASA employees (publicity). It has a note about AI use that does not apply here.

**Risks and my recommendations**

1. **Third-party contributor material (possible, not shown).** The GitHub items' flag admits the contributing NASA centre is not stated per file, and NASA warns some site content is third-party. Eight Commons items carry a long list of contributor names/centres instead of one creator (`commons-agena-target-vehicle-agena-carbajal`, `commons-aqua-b-aqua-13`, `commons-astronaut-astronaut1`, `commons-astronaut-glove-astronautglove`, `commons-clementine-clementine-v01`, `commons-cloudsat-a-cloudsat1-composite`, `commons-cubesat-1-ru-generic-1ru-genericcubesat`, `commons-deep-impact-epoxi-68`); their credit line says only "by NASA", which may hide individual contributors (for example named JPL artists). Action: **SHOW with label** "NASA content, generally not subject to US copyright; not endorsed by NASA", and keep the contributors text on the detail page for the 8. Whether "generally" is enough for a hosted service, and whether it holds outside the US, is **UNVERIFIED / needs counsel**.
2. **Endorsement.** Never write or imply NASA approves ZEIM or the models. The standard's NASA variant already says so (attribution-standard 1.3, 2.4). No NASA logos, "worm", "meatball" or seal on cards, headers, Spark Lab or launch copy; the word "NASA" only as factual source credit. Do not use these models in anything that looks like a NASA-branded product or sponsorship.
3. **Insignia inside models.** I did not inspect geometry. The **Hubble 25th anniversary medallion** (`nasa-hubble-25th-anniversary-medallion`) shows "HUBBLE 25" lettering in a rough render; whether it contains NASA or other agency marks is **UNVERIFIED**. Action: **HIDE until a human checks it**, together with any model whose surface might carry lettering or patches (astronaut items below are lower risk: the render shows no marks, but only from one angle).
4. **Identifiable persons.** `commons-astronaut-astronaut1` and `commons-astronaut-glove-astronautglove` appear generic (no face or name tag seen in the render, one angle only). NASA's page says a name tag or historical context can make an astronaut identifiable in photos; these are 3D models, not photos, but a human check is cheap. SHOW with label after a look.
5. **Commercial wording.** NASA treats commercial use differently (ZEIM is free, but users may sell prints; that is the user's use, not ZEIM's). Include the NASA variant line in downloads (done in `credit_full`).
6. **Credit line wording for Commons NASA items** says `by NASA`; keep, but add "contributors listed on source page" where `contributors_note` exists.

## 4. CC BY-SA 4.0 items (15): share-alike impact (**needs counsel**)

Items: `3dracers-racer-buggy`, `3dracers-racer-muscle-car`, `3dracers-racer-pickup-truck`, `commons-catenoid`, `commons-cercles-villarceau`, `commons-costa-minimal-surface`, `commons-courbe-de-viviani`, `commons-h-lico-de`, `commons-hennig-reuleaux-tetrahedron`, `commons-hyperbolic-paraboloid`, `commons-osiris-rex`, `commons-sphericon`, `commons-surface-de-boy`, `commons-surface-henneberg`, `commons-telescope`. Breakdown: 3 `3dracers-*` (GitHub, Marco D'Alia / 3DRacers), 12 Wikimedia Commons maths/space items. Licence text: <https://creativecommons.org/licenses/by-sa/4.0/legalcode.en> (read 2026-10-04): adapted material may be shared only under the same licence or a "BY-SA Compatible License" (a list Creative Commons approves), the adapter must include the licence text or link, and no extra terms or technical measures that restrict the rights.

Impact on ZEIM (my reading, **needs counsel**):

* **Download as-is:** fine with credit. SHOW with chip "Share-alike".
* **Edit / Make remix, then Share/Publish:** the result must be offered under CC BY-SA 4.0 (or compatible). The Edit tool must force the licence picker to BY-SA for any child of these items and the validator must block other choices (attribution-standard 2.3). Private edits and downloads for personal use are not "sharing", but whether a **download of an edited file that the user then shares elsewhere** puts any duty on ZEIM beyond keeping the credit and licence notice in the file is **needs counsel**.
* **Combining** an SA item with a CC BY-SA item under another version or a non-compatible licence: blocked (attribution-standard 2.3).
* **ZEIM's own licence for derivatives:** ZEIM cannot put its own terms (ToS, "ZEIM may use anything uploaded", "no commercial use") on top of an SA derivative: that would be an "additional or different term". The ToS grant to ZEIM (host/display) must be compatible with BY-SA for these items. **needs counsel.**
* **ZEIM Originals licence (CC BY 4.0, Zach 2026-10-04) vs SA parents:** an Original must never be derived from an SA item (it would then have to be SA). The provenance line already says designed from scratch; keep it.
* **Collections/bundles** ("classroom pack" zips with SA + other items): may be a collection, not an adaptation, but this is exactly the kind of line a lawyer should draw. **needs counsel.**
* Slicer output (G-code): whether G-code from an SA model is "adapted material" is unclear; **UNVERIFIED / needs counsel**. Do not claim either way.
* `commons-osiris-rex` (BY-SA, uploader-declared) depicts a NASA spacecraft; the 3D file is by a Commons user, so NASA's PD statement does not apply to it. Keep it as BY-SA with the creator credit.

## 5. Commons public-domain items (13 maths + 13 NASA): uploader-declared risk

Maths PD items: `commons-compound-of-five-octahedra`, `commons-compound-of-five-tetrahedra`, `commons-compound-of-ten-tetrahedra`, `commons-concertina-cube`, `commons-disdyakis-dodecahedron`, `commons-final-stellation-of-the-icosahedron`, `commons-menger-sponge-2`, `commons-rhombic-triacontahedron`, `commons-snub-cube`, `commons-snub-dodecahedron`, `commons-trefoil-knot`, `commons-truncated-cuboctahedron`, `commons-truncated-dodecahedron`. Their licence is "Public domain" as declared on the Commons file page; the verification record says the Commons API returned that licence and the file SHA-1 matches. That proves **what Commons says**, not that the uploader had the right. Risks: wrong or over-broad PD claims, derivative geometry of a protected design (rare for polyhedra, which are mathematical objects), and later correction by Commons. 13 of these use the **file page as the "licence URL"** (there is no licence text to link): acceptable for display, but the licence link on cards should read "Public domain (declared on Wikimedia Commons)". The creator names include a messy string (`Jim.belk (STL file: MichaelFrey)`). Recommendation: **SHOW with label** "Public domain per Wikimedia Commons; tell us if this is wrong"; add them first to any takedown watch list. Counsel: whether relying on uploader-declared PD is acceptable for a service that hosts the file is **needs counsel**.

## 6. `azdle/printables` OpenSCAD warning (13 items)

What the repo README says (quoted in `verification_evidence.json`, GitHub `azdle/printables`): *"I've dedicated all these works to the public domain using the CC0 dedication, you may do anything you wish with them. However, note that some models may depend on third-party code not made available under CC0 terms, you must still abide by the terms of the third party licences when distributing."* The 13 items: `azdle-aa-battery-tower`, `azdle-aaa-battery-tower`, `azdle-cord-hanger`, `azdle-floater`, `azdle-honeycomb-tile`, `azdle-honeycomb-tile-1x1`, `azdle-honeycomb-tile-1x4`, `azdle-hook-bracket`, `azdle-l-bracket`, `azdle-marker-rack`, `azdle-mason-jar-net-cup`, `azdle-rack-rail-mount-3mf`, `azdle-suction-cup-soap-dish`. (12 carry the manifest flag; `azdle-rack-rail-mount-3mf` has the same note.)

My reading: the STL files themselves are covered by the repo CC0 dedication (the manifest says so); the warning is about the **OpenSCAD source libraries** some designs are built with. ZEIM hosts STL/3MF, not source, so the exposure is small, but it is the creator's own caveat, so we must not describe them as "100% CC0 with no strings". Actions: keep the licence note visible on detail pages ("repo author notes that some models used third-party libraries under other licences"); do **not** host or link `.scad` source from this repo; Engineering must not "parametrise" these via OpenSCAD in Make. Which of the 13 use which library: **UNVERIFIED** (not checked). **needs counsel** only if we ever add the source files.

## 7. Printer tags are guesses

The manifest says "printer values are unverified guesses" and every entry has `printer_guess: true` with a note: 134 `both`, 40 `fdm`, 21 `resin` (resin = scans guessed "fine organic detail"; nine are marked "larger than a typical resin build volume"). They come from size, shape and category rules, **not from a test print or slicing**. Rules for the UI: show as "Suggested: FDM / Resin / Both (unverified)"; never "FDM ready" / "resin ready" claims; never block a download by tag; the claims table (Haruto) must list this as **untested**. Of the 195, **76 are view-only** (not watertight; 32 are Smithsonian textured scans) and must show "view only" rather than a print tag.

## 8. Family-friendly and lookalike review

**Method:** read all 195 titles, categories, notes; keyword scan for weapon, hunting, predator, skull, bomb, alcohol, adult, character and brand words (list in my notes: gun, weapon, sword, knife, blade, hunt, call, skull, rocket, Batman, Mario, Pokemon, Disney, Marvel, Star Wars, Lego, Nintendo, Minecraft, logo, NASA, insignia, beer, wine, vape, dragon, astronaut). **Not done:** looking at the meshes. Result by title/description only:

* **Weapons / mature / drugs / adult:** none found in the 195. (Smithsonian history items: a bully-beef can opener, a patent-model refrigerator and motor, a stereoscope, a stoneware jug, a saxophone: none is a weapon.)
* **Trademarked characters / logos:** none obvious. Low-risk name or brand echoes, for a human to look at: `3dracers-racer-muscle-car` and `3dracers-racer-pickup-truck` (generic cartoon cars, but a "muscle car" silhouette can echo real models: trade dress risk **UNVERIFIED**); `thomo-zigbee-case-cap`, `thomo-zigbee-case-cup` ("ZigBee" is a name owned by an industry body: use it only factually, add the trademark line); `xarfa-white-feather-fountain-pen` (name "White Feather" is the creator's project name; needs non-printed ink parts); `drlex0-funny-flexi-octopus` (the author says it is inspired by, not a remix of, another flexi octopus; commonly copied shape, low risk); `framedog-*` (a robot project name); `osbock-droobot-*` ("Droobot" is the creator's name for it); `commons-soccer-ball` (generic ball, CC BY by Microsoft; no logo expected, not inspected). Also `commons-hatch-frame-v335...` and `commons-handle-selector-knob-v11...` (Apollo 11 hatch parts, CC0, "by NASA and Smithsonian Institution" in the title: keep the factual credit, no endorsement).
* **Pets and small parts:** `cat-toy-cat-treat-ball-half-a`, `cat-toy-cat-treat-ball-half-b` (treat dispenser for cats: not food-safe/pet-safe guaranteed; label "not tested for food or pet safety"). Small parts (chess pieces, polycubes, tiles) are choking hazards for small children: add one fit note "small parts; not for children under 3" to games/puzzles and the toy items (wording **needs counsel**).
* **Real-world landmarks and cultural objects:** the 18 quarantined `commons-*` items (landmarks such as Big Ben, Gateway Arch, Space Needle, Shanghai Tower, Moai) are hidden anyway; if later re-admitted, check design/architecture rules per country (**needs counsel**, **UNVERIFIED**). Smithsonian cultural-heritage objects (`si-stoneware-jug-created-by-thomas-commeraw-...`, `si-alto-saxophone-owned-and-played-by-charlie-parker-...`) are CC0 on Smithsonian's own terms; show the respectful credit and a note that the real object is in the collection. A person's name in a title is fine as factual provenance, not a product endorsement.
* **Fossils / animals:** natural-history scans (skeleton, shell, fish, mammoth): fine for schools. No human remains seen by title. **Not verified visually.**
* **Game/predator-call items:** none in the free library. They are in the **ZEIM Originals** (section 9).

## 9. ZEIM Originals family check (37 STL on disk of 39 defined; 45 planned)

Source: `library/originals/source/m_*.py`; provenance in `source/build.py` says designed from scratch procedurally with no tracing of any character/logo/franchise (that is the team's statement; I have not independently verified originality: **needs counsel**, and a human visual review is still needed).

| Category (count in source) | Items | Recommendation |
|---|---|---|
| **Wildlife Calls (12)** | `mallard-style-duck-call`, `goose-flute-call`, `crow-caw-call`, `doe-bleat-can-call`, `open-reed-predator-call` (titled "Distress Call"), `deer-grunt-tube`, `teal-peep-whistle`, `bobwhite-slide-whistle`, `owl-hooter-whistle`, `elk-bugle-tube-kit`, `turkey-diaphragm-frame-set`, `turkey-friction-pot-call` | **HIDE until cleared for classrooms and under-13.** Reason: hunting and game-calling use (duck, goose, deer, elk, turkey, predator-distress), "use lawfully" notes, mouth-contact items (diaphragm frames: "adults only"). Suggested for Zach: show to adult/13+ accounts with a label, but never in Spark Lab, classrooms, or default Showcase for minors. Optional exemption for Aiko/Zach to consider: the three bird-whistle toys (`owl-hooter-whistle`, `bobwhite-slide-whistle`, `teal-peep-whistle`) as "bird whistles" in a separate category. Local hunting/game-call laws vary: **UNVERIFIED / needs counsel** if marketed as hunting gear (we do not market them so). |
| Comic Book Art (3) | `pow-comic-burst-plaque`, `launch-day-comic-panel`, `bubble-helmet-explorer-bust` (defined, no STL yet) | **SHOW with label after human lookalike check**: "POW!" is a common word; the explorer bust (round bubble helmet, star chest badge) must be checked against existing characters; the source itself says a human visual check is still advisable. |
| Toys & Articulated (3) | `wiggle-gator`, `flower-fidget-spinner`, `horn-dino-band-popper` (defined, no STL yet) | `wiggle-gator`, `flower-fidget-spinner`: SHOW. **`horn-dino-band-popper` (rubber-band launcher): HIDE for classrooms/under-13 until Zach decides** (projectile toy, eye-safety note in its own `use` text). |
| Useful Items (6) | `tree-stump-pen-cup`, `dino-phone-stand`, `cable-pebble-holder`, `whale-tail-wall-hook`, `wave-book-stand`, `fish-bottle-opener` | SHOW. `fish-bottle-opener` (opens crown-cap bottles): **HIDE in classrooms** as alcohol-adjacent (conservative; judgement call for Zach). `whale-tail-wall-hook` is "untested at ~1 kg": keep the untested label (don't claim load capacity). |
| Figures & Desk Art (4) | `chubby-penguin-scarf`, `sleepy-loaf-cat`, `ember-baby-dragon`, `octo-buddy` | SHOW. Run a name/lookalike check on "Ember" (dragon) and the penguin-with-scarf (many commercial penguins exist): **UNVERIFIED** originality of expression. |
| Outdoor Mechanisms (7) | `telescoping-lantern-mast`, `field-kit-box-spring-latch`, `trail-tool-fob` (no blades), `pocket-sundial-compass-plate`, `cam-cleat-guyline-tensioner`, `spring-gate-bottle-neck-clip`, `rain-guard-bird-feeder` | SHOW. `spring-gate-bottle-neck-clip`: "drinking bottle or flask" is fine. Add no-load-rating-claim notes (spring latch, tensioner; not tested for safety use). |
| Containers (2), Desk Art (1), Wall Art (1) | `turtle-trinket-jar`, `pumpkin-trinket-jar`, `twist-vase-pen-pot`, `sunrise-waves-plaque` | SHOW. Label "not food safe" where the source says so. |

Licence for all Originals: CC BY 4.0 with credit to ZEIM, **pending counsel** (attribution-standard section 1.5 and 6). Authorship and copyrightability of procedurally generated works, and which legal entity is the licensor, are **needs counsel**.

## 10. Category table (action at launch)

Actions: **HIDE** = not shown in public lists, search or classrooms until cleared; **SHOW + label** = shown with the stated label; **SHOW** = shown with the standard credit line.

| Category (count) | Action | Reasons / labels |
|---|---|---|
| Quarantined (24) | **HIDE** | licence unclear (6) or no source record (18); landmarks to review |
| `space/astronomy` (71), of which NASA (47 GH + 13 Commons + `commons-osiris-rex`, `commons-telescope`, `commons-satelite-dish-large`, Smithsonian astro scans/prints) | **SHOW + label** (NASA lines 3.1-3.2); **HIDE** `nasa-hubble-25th-anniversary-medallion` until insignia check | third-party content possible; no endorsement; insignia; contributors for 8 |
| `school/STEM` (48): maths surfaces (Commons PD / BY-SA / CC0), polycubes (Unlicense), FrameDog, Smithsonian-related | **SHOW**; BY-SA ones **SHOW + label** "share-alike" | uploader-declared PD for 13; creators unverified |
| `tools/practical` (19): azdle (13, CC0 + OpenSCAD note), DrLex0 boxes, thomo, Xarfa pen | **SHOW + label** | azdle: "some models used third-party libraries"; ZigBee trademark line; pen: needs ink parts |
| `nature` (14), `nature (fossils)` (7): Smithsonian CC0 scans | **SHOW + label** "view only, museum scan" (32 of 33 Smithsonian are textured scans) | Smithsonian name is credit only |
| `toys` (9): 3DRacers BY-SA (3), DrLex0 octopus, cat treat ball (2), droobot (2), soccer ball | **SHOW + label**: BY-SA share-alike; "not tested for pet/food safety"; small-parts note | possible trade-dress echo on the cars |
| `games/puzzles` (8): chess (6 CC0), tetracubes, monomino | **SHOW** + small-parts note | |
| `calibration/test prints` (7): ibell CC BY | **SHOW** | credit required (CC BY) |
| `art` (6): DrLex0 hex vases CC BY | **SHOW** | credit required |
| `history/tools` (6): Smithsonian CC0 scans | **SHOW + label** "view only"; respectful credit | museum objects |
| ZEIM Originals: Wildlife Calls (12) | **HIDE for classrooms and under-13**; adult/13+ SHOW + label only if Zach agrees | hunting/game-call use, mouth contact |
| ZEIM Originals: `horn-dino-band-popper`, `fish-bottle-opener` | **HIDE in classrooms** until Zach decides | projectile toy; alcohol-adjacent |
| ZEIM Originals: other 7 categories | **SHOW + label** "CC BY 4.0, pending counsel" (do not launch publicly until counsel confirms) | provenance + lookalike check outstanding |

## 11. Open questions for Zach and counsel

1. **Counsel:** is "generally not subject to copyright in the US" from NASA's page enough to host and let users sell prints of NASA-based models (inside and outside the US)? Third-party NASA contributors?
2. **Counsel:** CC BY-SA and ZEIM: forced SA on edited children, ToS grant compatibility, bundles, G-code.
3. **Counsel:** acceptability of relying on uploader-declared Commons PD/CC licences (50 Commons items) and repo-level GitHub licences (creators unverified for 162 of 195).
4. **Counsel:** Originals: licensor entity, copyright in procedurally generated/AI-assisted works, CC BY 4.0 irrevocability and commercial reuse (CC BY allows commercial use by anyone).
5. **Zach:** Wildlife Calls hidden for classrooms/under-13 (and whether the three bird whistles are exempt); `horn-dino-band-popper`, `fish-bottle-opener`.
6. **Zach/Aiko:** small-parts wording for toys and puzzles; "not for children under 3".
7. **Engineering/Kenji:** human visual pass over all previews (insignia, lettering, lookalikes) before launch; fix the 13 file-page licence URLs and 8 contributor credits.
8. 3DBenchy (2 quarantined): re-admit only on counsel/Zach confirmation of the CC0 evidence.

## 12. Hansei

* I reviewed text, not meshes; hidden logos or lettering cannot be ruled out. My render test covered three models from one angle.
* My keyword list is mine; a missed word means a missed item. I did not run an automated image-similarity or trademark search (no tool, no database).
* The NASA reading is of one page fetched today; I did not read NASA's merchandise or brand guidelines, nor the Smithsonian terms.
* "Wildlife Calls" recommendation is a safety/school-fit judgement, not a legal finding; hunting-related law was not researched.
* Counts are from the manifest as of 2026-10-04 ~19:35 CT; it may change.
