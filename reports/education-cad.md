# CAD in education, and what "CAD" means for ZEIM
Author: Aiko Nakamura (Education & Community) · Date: 2026-10-04 · Status: DRAFT for HQ review
Scope: research and planning only. I did not edit app code. Nothing here has been tested with a teacher, a child, or an iPad.

**Source tags.** **[R]** = I opened and read the page in full with a fetch tool. **[S]** = only a search-result excerpt/summary was seen; the page was not opened. **[C]** = I read ZEIM's code. **[X]** = I ran a short scratch script against `app/core/meshedit.py` on generated meshes (not through the UI, not on a real lithophane). Statements marked *(my inference)* are not sourced. No numbers below are invented; where a source gives none, I say so.

---
## 0. Short answer
1. **CAD-lite belongs in grades ~5–12, after the lithophane first project,** as "change the thing you already made" (add a stand, a hole, initials, a fit test). Real classrooms commonly start with shape-building CAD (Tinkercad) and move to sketch-and-extrude / parametric CAD around ages 14+ [R: PrintLab interview; R: Oak National Academy]. K–2 should stay hands-on and teacher-led *(my inference; K–8 Tinkercad lesson exists [S], but I recommend no student CAD below grade 3)*.
2. **Near term, "CAD" for ZEIM = mesh editing plus a few small, honest additions** (start from a shape, add/subtract shapes, text anywhere, stand/foot preset, clearance test). Most pieces already exist in Edit [C][X].
3. **Long term, parametric CAD (sketch, constraints, extrude, STEP) is a different, much bigger product** (different geometry kernel, solver, data model). I recommend **interoperability, not building a CAD,** for at least the next planning horizon: export clean STL/3MF/OBJ, import Shapr3D/Tinkercad exports, and revisit STEP only after real demand.
4. **Shapr3D on iPad:** its own help page lists **STL (reference only)** among importable 3D mesh formats; **OBJ and 3MF appear only under export** [R]. So **STL is the safe handoff to Shapr3D;** don't promise OBJ/3MF import.

---
## 1. Where CAD-lite fits in education

### 1.1 What classrooms actually do (progression)
| Stage | What it is | Evidence | Typical band |
|---|---|---|---|
| A. Shape-building ("constructive solid geometry") | Combine/subtract simple shapes: boxes, cylinders, spheres | Oak National Academy defines CSG as "creating 3D models by combining simple shapes like cubes (boxes), cylinders, and spheres" and calls Tinkercad "easy to use and accessible, especially for beginners" [R](https://www.thenational.academy/teachers/programmes/design-technology-secondary-ks4/units/systems-approach-to-design-sustainable-futures/lessons/fusion-fundamentals) | A Tinkercad lesson plan is listed as grades 5–12 (US), 6h30 [R](https://www.tinkercad.com/lessonplans/create-a-solar-powered-invention); another Tinkercad tool-design lesson lists K–8 [S](https://www.limitlessspace.org/wp-content/uploads/2024/02/Tinkering-a-Tool-in-Tinkercad.pdf) |
| B. Sketch + extrude | Draw 2D profile, push/pull to 3D | A UK teacher: Tinkercad in Years 8–9, Autodesk Fusion Years 10–13; "we focus on the importance of sketching in Fusion and the Extrude command as there is so much students can achieve with just these" [R](https://weareprintlab.com/blog/advancing-3d-cad-skills-in-uk-design-and-technology-classrooms/) | UK Year 10 ≈ age 14–15 *(my conversion; the page gives year groups, not ages)* |
| C. Parametric / constraints | Editable dimensions and rules; assemblies, drawings | Oak: Fusion is "sketch based… parametric modelling, giving users more control" and adds assemblies/technical drawings [R](https://www.thenational.academy/teachers/programmes/design-technology-secondary-ks4/units/systems-approach-to-design-sustainable-futures/lessons/fusion-fundamentals). Onshape's teacher blog describes a ~9-week "Intro to CAD" course covering part modeling and design for manufacturing [S](https://www.onshape.com/en/blog/using-cad-support-project-based-learning-engineering-classroom). CADclass sells a Tinkercad→Fusion/Onshape/SolidWorks sequence "for grades 5 through university" [S](https://www.cadclass.org/) | Upper secondary / CTE |

Two further observations from the same sources: the teacher advises "it's best to use Tinkercad only across select areas of the curriculum… instead of starting with Fusion" and notes students "overwhelmed by the interface at times" need "another route into CAD" (he suggests scanning) [R, PrintLab interview]. A Reddit thread asks how to "graduate from Tinkercad", with replies pointing to Fusion, Onshape and FreeCAD, but that is anecdote, not evidence [S](https://www.reddit.com/r/3Dprinting/comments/1d1pj0b/how_can_i_graduate_from_tinkercad_to_a_proper_3d/).

### 1.2 What Tinkercad Classrooms does that teachers seem to value
- "no emails required"; onboard students "with a link or code"; "review student work in a class gallery"; Google Classroom integration; curriculum and PLTW/PrintLab/MakerBot resources linked [R](https://www.tinkercad.com/teachers). (The page showed untranslated placeholder keys, so wording of some headings could not be read.)
- A class link is "easier as the student only has to click it, rather than type in the 9 digit Class code" [S](https://www.tinkercad.com/help/classrooms/share-class-link-code). A third-party (school-support) guide says Safe Mode is on by default, keeping student designs private and hiding gallery search/comments [S](https://help.mytsi.org/v2/knowledge-base/how-to-use-tinkercad-classrooms/). I have not read Tinkercad's own Safe Mode page.
- *(my inference)* ZEIM's classroom (code + password + nickname, class-private, teacher approval) is already close to this model. That is a reason to **interoperate** with Tinkercad classes rather than compete with them.

### 1.3 Teacher pain points that touch CAD (not just ZEIM)
| Pain point | Source |
|---|---|
| Printing is slow; bottlenecks; plan extra days for printer errors; finalise models before printing | "Managing 3D printing in school can be challenging… manufacturing process is relatively slow, which can lead to bottlenecks" [S](https://www.createeducation.com/wp-content/uploads/2024/09/3D-Printing-Classroom-Management-Guide.pdf) |
| Failed prints often come from designs "not optimised for 3D printing", e.g. holes in the model; budget for failures; the same model can take 11 minutes or 5 hours depending on size | [S](https://assets.ctfassets.net/pc40tpn1u6ef/file-132734/c03c69cc417f688bdf823fc0842cd999/PrintLab_-_3D_Printing_Guide_for_Teachers.pdf) |
| Files arrive by email; no way to catch "a 14-hour monster" or off-task parts; need submit → review → approve/deny/send back | SimplyPrint school workflow article describes teacher prints / approve / quota tiers [R](https://help.simplyprint.io/en/article/school-and-makerspace-workflows-from-teacher-led-to-student-led-printing-cfmow0/) (a vendor page, so it shows what a vendor says teachers need, not a survey) |
| Accounts and devices: set up accounts before the lesson; Chromebooks and a basic mouse | Oak "Teacher tip" [R]; PrintLab interview [R] |
| Vocabulary load: one school teaches "up to 30 key terms" for Tinkercad | [R, PrintLab interview] |
| Shared print-queue habits: shorter prints are more reliable; batching made whole batches fail | [S](https://weareprintlab.com/blog/managing-high-volume-3d-printing-for-student-projects/) |

**What this means for ZEIM:** CAD-lite is only useful if it ends in a *printable* object quickly (repair, size in mm, base, hole check) and flows into the teacher print queue (already CR-13 in `education.md`). The "print-ready checks" matter more than modelling power.

### 1.4 Shapr3D in education, and the iPad workflow
- **Free education licence:** "educational version of Shapr3D Pro" for students, teachers, faculty at accredited institutions with a valid school email; 365 days, renewable; non-commercial; "currently available only in select countries"; approval within 3 business days; "Multi-seat licensing is not available, but we can offer a bulk license" [R](https://www.shapr3d.com/education). School domains can be whitelisted for faster approval; this needs a signed institutional document [S](https://support.shapr3d.com/hc/en-us/articles/11868036819868-Educational-license-email-whitelist-guide).
- **Platform:** iPadOS 17 or later, "preferably with Apple Pencil" [R, education page].
- **Plans (matters for Zach):** Shapr3D Basic is "limited up to 2 projects only" for import; export on Basic is "low-resolution STL, and 3MF formats only" [R](https://support.shapr3d.com/hc/en-us/articles/7874523890076-Supported-file-types).
- **Import path on iPad:** open a project, tap Import, choose Files, pick the file, set the unit [R](https://www.shapr3d.com/content-library/open-your-stl-files-in-shapr3d-the-ultimate-guide) (article date reads "January 1, 2021", so the UI may have changed; the 2025 help page below is newer).
- **Formats (help page updated Dec 9, 2025) [R]:** import 3D = X_T/X_B, STEP, IGES, **STL (for reference only)**, SHAPR, SLDPRT, SLDASM; images; DWG/DXF sketches. Export 3D = SHAPR, X_T/X_B, STEP, **3MF**, IGES, **OBJ (with colors)**, **STL**, GLB, USDZ. (The App Store listing, a search excerpt, also lists import without OBJ/3MF [S](https://apps.apple.com/us/app/shapr-3d-cad-modeling/id1091675654).)
- **What an imported STL can do:** Shapr3D's own guide says an imported mesh "cannot be edited"; "most of the modeling tools are locked"; only Booleans and Move/Rotate/Mirror/Scale; to change it you "reverse engineer" by sketching over it [R, same article].
- **Not found:** I did not find what Shapr3D requires for under-13 students. Not claimed either way.

*(my inference)* A school with iPads and a Shapr3D edu licence is a natural fit for grades 10–12 only; for younger students, an account tied to a school email is likely a barrier. ZEIM should not depend on Shapr3D.

---
## 2. What "CAD" means for ZEIM

### 2.1 Near term: mesh editing (what exists today) [C]
Edit works on one triangle mesh made from an uploaded STL/OBJ/3MF or photo, non-destructively (operation list replayed from the original). Verified by reading `app/core/meshedit.py` and `static/edit.js`, and by scratch runs [X] for items marked X.

| Capability | Exists? | Notes |
|---|---|---|
| Move / rotate / scale, numeric, mm / cm / in | Yes | Scale by factor or target size; keep proportions |
| Mirror X/Y/Z | Yes | Mirrors the whole model; no mirrored *copy* |
| Drop to bed, centre | Yes | |
| Measure two points | Yes | Click on model; touch behaviour on iPad not tested |
| Cut / split with a plane | Yes | Known gap: can leave open meshes (engineering.md) |
| Hollow (wall, drain hole) | Yes | Voxel-accurate to about one voxel |
| Base / brim (outline, rect, round) | Yes [X] | A 3 mm rect base added under a 60×3×80 mm upright card gave a watertight 80×23×83 mm solid |
| Add / subtract / intersect box, cylinder, sphere | Yes, but only *as a tool on an opened model* | Numeric centre and size; no standalone "new shape" start; needs watertight input |
| Text emboss/deboss, DejaVu fonts | Yes, **with limits** | Text is placed on the **flat bounding-box face**. [X] On an upright card with a foot, deboss on "front"/"back" removed **zero volume** (text floated in air); "top" cut only the card's edge. Emboss "top" on a flat 50×20×3 tag worked (watertight, +39 mm³) |
| Repair, simplify | Yes | |
| Multi-object scene, colours/materials on 3MF import | **No** | Objects fuse into one mesh; roadmap item |
| Drag handles, face/edge select, snapping | **No** | Roadmap |
| Language filter on text-tool content | **Not seen** | [C] `app/api/edit.py` filters the project *title* only. I did not find the same gate on `text` op content, and a model can later be published. Needs confirmation from Engineering/Kenji |

### 2.2 Near-term proposals (labelled **PROPOSAL**; Engineering decides; sizes are my rough guesses)
Effort: S = days, M = 1–2 weeks, L = a month+. These are relative guesses, not estimates from Engineering.

| # | Proposal | Why (education) | Effort | Risk |
|---|---|---|---|---|
| N1 | **Start from a shape** (new Edit project from box / cylinder / sphere with size in mm) | Needed for any "make something from nothing" lesson; today primitives exist only as boolean tools | S (primitive code exists in `meshedit.primitive`) | Low |
| N2 | **Shape presets** in the Add/Subtract tool: "hanging hole", "slot", "peg", with a plain-language label | The current form asks for Center X/Y/Z and sizes, which is heavy for grade 3–5 | S | Low |
| N3 | **Text anywhere**: choose a plane/height or "on top of the last added shape", not only the bounding-box face | Fixes the verified limitation; enables "initials on the stand" | M | Medium (orientation bugs) |
| N4 | **Stand/foot preset** for upright cards (rotate 90°, drop, wider foot with optional slot) | Natural follow-up to Glow Card [X: rotate+drop+rect base works] | S–M | Low; stability must be tested with real prints |
| N5 | **Clearance test strip** generator (peg + holes at several clearances) | Fit Check lesson; teachers' failed-print worry | M | Low–medium; results vary by printer, so lesson says "measure yours" |
| N6 | **Always-visible size in mm** and a "ready to print?" checklist (watertight, size, thin walls) | Fewer failed prints [S above] | S–M | Low |
| N7 | **Multi-object scene** (several parts, move separately) | Real assemblies, symmetry by copy | L | Medium–high |
| N8 | Filter/gate text-tool content like other user text | Safety | S | Low |
| N9 | Touch pass on Edit (measure, numeric fields) for iPad | Zach uses iPad | M | Unknown until tested (Sakura's iOS pass) |

### 2.3 Long term: parametric CAD (what it would take)
Sketch on a plane, dimensions/constraints, extrude/revolve/fillet, a history tree where you change a number and the model rebuilds, and STEP in/out.
- **Different data model.** ZEIM Edit is mesh-based (trimesh + manifold3d). CAD works on exact curved surfaces (B-rep) via a geometry kernel. Shapr3D says it runs on Siemens Parasolid [S](https://www.shapr3d.com/download/ipad) [S, App Store listing also names the D-Cubed sketch engine]. This is a commercial kernel; I did not research its licence cost.
- **An open option exists in the browser:** OpenCascade.js reads/writes STEP via WebAssembly; the docs say the full build ships ≈9.1 MB compressed and a custom build ≈2.4 MB compressed [R](https://ocjs.org/docs/getting-started/file-size) [S, STEP bindings: https://ocjs.org/docs/getting-started/configure-bundler]. That shows STEP in a browser is *possible*; it does not show it is *easy*. I did not evaluate quality, licence, or iPad Safari performance.
- **Needs a 2D constraint solver, sketch UI, feature history, fillet/chamfer, and good touch UX.** Prusa's own tips say a parametric approach "helps immensely" for iterating tolerances [R](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135). That is the pull; the cost is the point.
- **Rough size:** many person-months for a usable first version, plus ongoing bug load. *(my inference, not an Engineering estimate.)* Risk: high. It would compete with free tools that already exist for schools (Tinkercad; Onshape's free Student/Educator plans [R](https://www.onshape.com/en/education/plans); Shapr3D's education licence [R]).
- **Honest alternative:** a very small **2D-sketch → extrude** (rectangle, circle, text, polygon → height) is a plausible stepping stone without a B-rep kernel (shapely + extrusion already used for base/text [C]). It would still be a mesh, with no constraints and no STEP. I'd call it "mesh-based sketch-extrude", not CAD.

### 2.4 Recommendation on scope
1. **Now:** N1, N2, N6, N8, then N3/N4 (all mesh-level). Ship nothing parametric.
2. **Interoperate:** keep STL as the bridge to Shapr3D, with 3MF/OBJ as "may not import" notes; accept Shapr3D/Tinkercad exports in Edit (already STL/OBJ/3MF). Shapr3D can export STL/3MF/OBJ [R], which Edit can open, so the round trip works on paper; **untested**.
3. **Later (only if teachers/Zach ask):** mesh-based sketch-extrude; then a STEP *export* spike (read-only evaluation of OpenCascade.js).
4. **Reject for now:** a full parametric CAD, a block-coding CAD, or a Tinkercad-style drag editor in v1 (see table in §4).

---
## 3. CAD-lite lesson outlines (DRAFT; untested with teachers or children)
All build on **Glow Card** (`education.md` §3.1). Shared rules from §3.0 there still apply: no photos of people for under-13s; printing is teacher-operated; "initials only". Each notes **what works today** vs **needs a proposal**.

### L1. Glow Card Stand: "Will it stand up?" (grades 3–5 teacher-led, 5–8 independent) — 45 min
- **Objective:** predict, then test, what makes a flat card stand; change one thing (foot width) and observe.
- **Steps:** open the Glow Card in Edit ("Edit this") → rotate it upright → Drop to bed → Add base (rectangle, try 10 mm vs 20 mm margin) → Measure the foot → prediction sheet → teacher prints one or two → test with a gentle tap.
- **Works today?** Yes for the foot [X on a generated card; not on a real lithophane build]. Initials on the foot **wait for N3**; do not put initials on the picture face (it blocks light and the current tool can't reach other faces anyway [X]).
- **Safety/consent:** photo rules from §3.0; LED tea-lights only; printer teacher-operated; stand stability is a classroom demo, not load-bearing.
- **Assess:** prediction vs result; one sentence "A wider foot ___ because ___".

### L2. Name Tag Level 2: "Add a hole, add your initials" (grades 3–5) — 50 min + print
- **Objective:** work in mm, use subtract to make a hanging hole, use text for *initials only*.
- **Steps:** teacher-supplied tag file (or N1 shape) → scale to 50 mm wide → subtract a 5 mm cylinder near an end → emboss initials (≤3 letters) on top → Measure → submit to class.
- **Works today?** Subtract and emboss on a flat tag work [X: watertight, hole removed ≈59 mm³]. Starting from nothing needs **N1**; until then the teacher provides the blank.
- **Safety/consent:** initials only, no names, handles, phone numbers; hole must clear the text. **Flag:** text-tool content isn't filtered today [C]; until N8 ships the teacher approves each tag before it is submitted for printing.
- **Assess:** exit ticket "I changed ___ and ___ happened"; correct mm↔cm conversion.

### L3. Fit Check with tolerances (grades 8–12) — two sessions, two print cycles
- **Objective:** state a requirement with a tolerance; test clearances; justify a redesign with evidence.
- **Steps:** measure a safe object → predict clearance → model socket holes at several clearances (e.g. start from Prusa's guidance of 0.2 mm for accurate fits and "at least 0.3 mm" for movable parts [R](https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135); your printer may differ) → print → measure → pick one value and defend it.
- **Works today?** Partly. [X] Subtract-cylinder at hole diameters 10.0/10.4/10.8 mm stayed watertight. A matching peg needs **N1** or a teacher-supplied file; the strip itself is **N5**.
- **Safety:** no safety-critical or food-contact parts; no sharp tools; nothing that holds weight over people.
- **Assess:** notebook page: measurement, prediction, result, one change with reason; rubric on evidence. Prusa also warns circles may print as polygons and thin walls under one nozzle perimeter don't print [R, same page], which is a good discussion item.

### L4. Bridge to real CAD: "Design in another tool, finish in ZEIM" (grades 9–12, optional; iPad/Shapr3D or Tinkercad)
- **Objective:** know the difference between a mesh (STL) and a CAD solid; export, open, repair, size and print.
- **Steps:** class compares shape-building vs sketch-extrude using Oak's keyword set (CSG / parametric / parameter) [R] → students design a small holder in the school's CAD tool → export **STL** → open in ZEIM Edit → Repair + Measure → submit to teacher. Shapr3D students may instead import a ZEIM STL as a *reference* and sketch over it (reverse-engineering), per Shapr3D's guide [R].
- **Works today?** ZEIM side yes (STL/OBJ/3MF import) [C]. Tool side depends on school accounts and licence; **not tested**.
- **Safety/consent:** no third-party account may be created for a student under 13 without the school's authorization; Kenji to review before this lesson is offered. Remember Shapr3D's edu licence is "non-commercial" and country-limited [R].
- **Assess:** short write-up: "Which stage (shape-building, sketch, parametric) did you use, and what did you give up?"

K–2: no student CAD. Keep "Height Detectives" (tactile relief). *(my inference)*

---
## 4. Recommendations

### 4.1 Adopt / adapt / reject
| Idea | Call | Reason |
|---|---|---|
| Teach shape-building CAD first, sketch-extrude later | **Adopt** | Matches the school progression above [R] |
| Tinkercad-style class link + nickname, no emails | **Already adopted** (ZEIM classes use code + password + nickname) | [R Tinkercad teachers] |
| Safe Mode idea: students can't publish, teacher decides | **Adopt** (CR-3 in `education.md`) | Same idea, third-party description [S] |
| Link out to Tinkercad / Shapr3D / Onshape as "next steps" in Spark Lab | **Adapt** (plain link, no integration, no ZEIM account sharing) | Free alternatives exist; honest positioning |
| Start-from-shape, presets, text anywhere, stand preset, clearance strip (N1–N6) | **Adapt** | Small, mesh-level, serve first-project follow-ups |
| Multi-object scenes (N7) | **Later** | Large; needed for real assemblies |
| Mesh-based sketch-extrude | **Later**, decide after N-items are used | Not CAD; useful stepping stone |
| Full parametric CAD (constraints, B-rep, STEP) | **Reject for now** | Very large; free tools exist; ZEIM is photo→print first |
| Tinkercad-style drag editor | **Reject for v1** | Big UI build, touch work; Tinkercad already free for classes |
| Direct integration/account link with Shapr3D | **Reject** | Nothing public found in what I read; file handoff is enough |
| Claim "imports into Shapr3D" for OBJ/3MF | **Reject** | Not in Shapr3D's import list [R] |

### 4.2 Open questions
- **Zach:** Which Shapr3D plan are you on (Basic, Pro, education)? Basic limits import to 2 projects and export to low-res STL/3MF [R]. Do you want to design in Shapr3D and finish/print in ZEIM, or the reverse?
- **Zach:** Is "CAD design" mainly about students making simple things (initials, stands, holders), or professional parametric work?
- **Engineering (Haruto):** Confirm N1–N9 sizing; is text-tool content gated by the language filter? Can a "new project from shape" reuse `primitive()`? Does any Edit tool (measure, numeric fields) work on iPad Safari?
- **Design (Sakura):** How should the Add/Subtract form look for grade 3–5 (presets, no X/Y/Z)? Touch targets for the measure tool?
- **Trust (Kenji):** Text on models published to Showcase; any guidance on third-party CAD accounts for under-13s; photo rules for L1.
- **Ops (Daichi):** Does the integrations research confirm Shapr3D's formats and say anything about Creality Cloud import? I used only Shapr3D's pages.

---
## 5. Hansei (what is partial or unverified)
- **Public sources only; no teacher interviews.** Grade bands are inferred from lesson listings and UK year groups (my conversion). Nothing says what a typical US grade 3 student can do in Tinkercad.
- **Many sources are [S] only.** In particular CADclass, Onshape's blog, the Create Education and PrintLab PDFs, Tinkercad Safe Mode (third-party), and the Shapr3D App Store listing. I did not open those pages.
- **Vendor pages (SimplyPrint, PrintLab, CADclass, Onshape) are marketing-adjacent.** They show what vendors say, not measured teacher data.
- **The Shapr3D STL guide may be dated** (shows January 1, 2021). The 2025 help page is the stronger source. Shapr3D plans/prices change; I did not read pricing. I did not test any file in Shapr3D, and I have no iPad.
- **My scratch runs [X] used generated boxes,** not real lithophanes, and did not go through the web UI. They show the *tool logic*, not classroom usability. A foot's real stability is unknown until printed.
- **Effort and risk sizes are my guesses,** not Engineering's. The "very large" size of parametric CAD is reasoning, not a measured estimate.
- **I could not find** under-13 terms for Shapr3D, any public Creality Cloud import path (outside my scope), or Tinkercad's current age rules.
- **Mistake caught:** my first scratch run used the wrong rotate parameters and rotated nothing; I corrected it and re-ran before reporting.
- **What I'd change next:** interview two real teachers about the progression; read Tinkercad's own help for Safe Mode and age; test L1 on a real print; ask Sakura to review the Add/Subtract form wording.
