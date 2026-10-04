# Education review of design.md T7 and T8 (classroom realism and reading level)

**Author:** Aiko Nakamura, Head of Education & Community · **For:** Sakura Mori (Design) · **Date:** Sun 2026-10-04 (CT) · **Status:** DRAFT, desk review
**Read:** `reports/design.md` T7, T8 (plus D6, D6b, D14, D20, D31, R6), `reports/education.md`, and the current copy and code in `static/index.html` (Print and Join dialogs), `static/app.js` (`showBuild`, `openPrint`), `static/community.js` (`openTeacher`), `app/api/printing.py` (print hint), `app/community/classrooms.py` (join limiter). Nothing was edited.

## 0. Bottom line

T7 and T8 point the right way. I would keep both and change these things:

1. **T7's Print dialog must be different for a class student.** "Send to my printer" and "Open in my slicer app" make no sense for a student on a school Chromebook. For class sessions the primary action should be **Send to my teacher**. Plain "Save the file" is second. This also matches CR-1 and CR-13 in my change requests (students never start printers; teacher approves).
2. **T8's Safety tab must only say what is true today.** Several lines in T8 ("no public sharing from a class") are not yet true for the whole app, because CR-3 (Showcase reachable by class students) is open. An empty "No reports" list would also mislead, because students have no way to report yet (CR-6). A reassuring panel that is wrong is worse than no panel.
3. **Join instructions must work when the QR does not.** Many school devices cannot scan a QR code. The page needs a big, typeable address and a 6-character code.
4. **T7 has no "not ready" copy.** The design only writes the green state. Students need a calm, actionable message for a model with holes.
5. **Both tickets need a "what happens to students already in the class?" answer** before "New class code" and "Reset password" ship.

## 1. Reading level

### 1.1 How I measured (and why you should not over-trust it)
I wrote a small Flesch-Kincaid grade script (`/workspace/scratch/fk.py`: sentence split on . ! ? : ; and newlines; heuristic syllable counter; FK = 0.39·words/sentence + 11.8·syllables/word − 15.59). It is **not** a validated tool (I did not run textstat or a published implementation; it is not installed). Limits:
- UI strings are 3 to 20 words. FK on tiny strings is unstable (it even goes negative) and only measures sentence length and syllables.
- FK **cannot see jargon.** "Triangles", "watertight", "slicer", "G-code", "brim" are short words, so they look easy but a 9-year-old does not know them. For this review, the vocabulary check below matters more than the number.
- The scores below are a rough guide. A real check needs 5 to 10 children reading the strings aloud (not done).

### 1.2 Current copy (scores are approximate)
| String | FK grade (approx.) | Real problem |
|---|---|---|
| Result bar: "282,108 triangles · 1 body · ✔ watertight" | ~11 for the pill line | Jargon. Not grade-level, but vocabulary a 10-year-old has never met. |
| Print hint ("Deep links need the slicer installed on the SAME computer as your browser… Public base URL… Links are signed…") | ~9 | Adult/admin text; also "deep links", "signed", "Public base URL". Not for students at all. |
| Print dialog labels ("Slice to G-code", "Infill %", "Brim mm", "Supports") | scores ~4 | Easy words, wrong audience. Hide from Beginner. |
| Join dialog help ("No account needed. Use a nickname — not your real full name.") | ~1 to 2 | Good. Keep nearly as is. |
| Teacher help ("Students join with the class code (or the QR / link below) + your password + a nickname…") | ~5 | Fine for teachers; the `+` signs read like code. |
| Design's proposed Safety wording ("nickname-only, class-private projects, no chat — canned messages only, language filter…") | ~8 | "canned", "nickname-only" are insider words. Teachers will understand, but "canned" is odd; say "ready-made". |

### 1.3 T7 as proposed
- "10.6 × 8.1 cm, 0.3 cm thick": fine for grades 4+ (kids know cm). The `×` sign is a grade 3 to 4 idea; I would write words. Also **I could not verify which axis is width/height** from `size_mm` for every mode (code shows `x × y × z`). Engineering should confirm the order before we label it "wide / tall / thick".
- "Ready to print ✔": grade 1 to 2, good. Tooltip "no holes in the model": ~grade 2, good, but **tooltips do not work on touch devices or for keyboard users**; put it in visible small text (see T5/T6).
- **"Download for printing (3MF)"**: "3MF" is jargon to a child. Keep "3MF" in small grey text or the "Other formats" menu for the teacher.
- "Open in my slicer app": "slicer" is a word only makers know. T7's own "done when" says the child shouldn't see "triangle, body, G-code, infill, brim", but "slicer" and "3MF" should be added to that list.
- "Download file to give to a grown-up/teacher": fine words, but see §3 (the handoff itself does not work well on shared devices).

### 1.4 Targets I recommend
- Student text: **grade 4 to 5**, max ~12 words per sentence, no unexplained maker words. If a maker word is needed ("layer"), show it with a one-line meaning. 
- Teacher text: **plain adult English, grade 7 to 9 is fine**, but short, scannable, with the action first. Teachers read on the move.
- Avoid text in tooltips only. Avoid `+`, `/`, `·` as grammar.

## 2. Suggested rewritten copy

Scores are from my script (rough; see §1.1). I include them only so you can see the target was met, not as proof it is easy to read.

### 2.1 Student: Beginner result (T7)
| Where | Suggested text | FK ~ |
|---|---|---|
| Size line | "It is 10.6 cm wide and 8.1 cm tall. It is 0.3 cm thick." *(confirm axis order first)* | <2 |
| Ready (green) | "Ready to print! Your model has no holes, so a printer can make it." | ~2 |
| Not ready (**missing in T7**) | "This one has a problem. It has holes, so it may not print well. Tap **Fix it**, or ask your teacher." | <1 |
| Main button (class student) | "Send to my teacher" | — |
| Main button (home user) | "Save my print file" *(small grey: "3MF")* | ~1 |
| Other formats menu | "Other file types (for experts)" | — |

"Fix it" needs a real target in the Edit tool (Design/Engineering to decide). If there is no one-click fix yet, say "ask your teacher" only and do not show a button that goes nowhere.

### 2.2 Student: Print dialog, Beginner (T7)
Title: **"Get ready to print"** (not "Print this build").

Class student (three choices, in this order):
1. **Send to my teacher.** "Your teacher will check it and print it."
2. **Save the file.** "Keep it safe. Give it to a grown-up who runs the printer."
3. *(only if a printing app is detected for the logged-in user, never in class mode)* **Open in a printing app.** "Only use this if a printing app is on this computer."

Always visible, small: "Only a grown-up starts the printer."
Collapsed: **"More options for experts"**: layer height, infill, brim, supports, G-code, network printer, "Start print immediately".

Home / non-class Beginner: same, with option 1 replaced by "Send to my printer" *only if* a printer is set up; otherwise hide it (do not show an empty drop-down with "No printers configured — add one in Settings").

### 2.3 Student: Join a class (D20 plus T8 join page)
| Field | Suggested text |
|---|---|
| Help | "You do not need an account. Pick a nickname. Do not use your real name." |
| Code | "Class code: 6 letters and numbers from your teacher" |
| Password | "Class password: your teacher will tell you" (add Show/Hide) |
| Nickname | "Your nickname: a made-up name, like Blue Fox" + **Suggest a name** button |
| Wrong code or password | "That code or password did not work. Check it, or ask your teacher." |
| Too many tries | "Too many tries. Wait a few minutes, then ask your teacher." *(current server text is already close: "Too many wrong passwords. Wait a few minutes and ask your teacher.")* |
| Nickname taken | "Someone already has that nickname. Try another one. If it is yours, ask your teacher." *(ties to CR-4 seat reset)* |

### 2.4 Teacher: setup and Safety tab (T8)
Setup help (replaces the long paragraph): 
> "Students need three things: the class code, the class password, and a nickname they make up. They do not need accounts. Say the password out loud or write it on the board. It is not in the QR code or the link."

Safety tab, **only the lines that are true when it ships** (gate each line on the matching Engineering change):
> **What is on for your class**
> - Students use nicknames only. No names, emails or accounts.
> - Class projects can only be seen by your class.
> - Students cannot chat. They can send four ready-made messages to you.
> - Words that are not school-friendly are blocked in titles and comments.
> - *(only after CR-3)* Students cannot open the public Showcase unless you turn it on.
>
> **What ZEIM cannot do**
> - The word filter can miss things.
> - We cannot see photos before a student uses them.
> - A grown-up should watch the class, as with any website.
>
> **Reports and blocks** 
> *(until students can report, CR-6)* "Students cannot report a problem yet. Please watch for upsetting pictures or words."
> *(after CR-6/CR-11)* a list: who, what, when, with Hide / Keep / Contact us.

Tab actions:
| Button | Text |
|---|---|
| Reset password | "Change class password. Students already in your class can stay. New students need the new password." *(Engineering must confirm this is the behaviour)* |
| New class code | "Make a new class code. The old code stops working. Students already in your class can stay." *(same)* |
| Mute | "Mute: this student can still learn, but cannot send quick messages." (design already has this idea; good) |
| Remove | "Remove **Blue Fox** from **Period 3**? Their saved work will be deleted. You cannot undo this." |
| Delete class | "Delete **Period 3**? This erases 24 students and 31 projects. You cannot undo this." + "Type the class name to continue" + "Download progress first" link if CR-13 CSV exists |

### 2.5 Teacher: printable Join instructions page (T8)
Layout I would want taped to a wall or handed to a substitute, **A4/Letter, black and white safe**:
> **Join our class on ZEIM** 
> 1. Open this web page: **zeim.example/join** *(huge, typeable)*  — or scan the picture
> 2. Type the class code: **K7M4QX**
> 3. Type the class password: _________________ *(teacher writes it, or says it)*
> 4. Pick a nickname that is **not** your real name.
> Stuck? Put your hand up. Do not share your password.
> *(small, bottom, teacher-only)*: "No camera on the computer? Type the web address. Teacher: students who lose their seat can be reset in Class setup."

Notes: today's link is `/#join/CODE`. A `#` link is hard to type; ask Engineering for a short `/join` page that has a code box (the `#join/CODE` link keeps working for the QR).

## 3. Classroom-realism issues (for T7 and T8)

Everything below is reasoning from how classrooms generally work and from reading the code. **I have not observed a class, run the app on a Chromebook, or interviewed a teacher.** No quotes or statistics are used.

| # | Issue | Why it matters | Suggested edit |
|---|---|---|---|
| 1 | **Shared devices.** `localStorage.level` (Beginner/Expert) is per browser profile (app.js:4). If students share a profile, one student who flips to Expert changes it for the next. The Beginner/Expert switch is also available to every student. | A "Beginner" result that the next child can switch off defeats T7. | Class setting "Keep everyone in Beginner" (teacher toggle), applied to class-student sessions server-side. Without this, T7 is advice, not a guarantee. |
| 2 | **Download handoff on shared/locked devices.** "Download file to give to a grown-up" puts a file in the shared Downloads folder (or is blocked / wiped at logout on managed Chromebooks, which I cannot verify for any particular school). Filenames: I saw `photo3d_<id>.<ext>` (builds.py:235) and the result bar links `/files/<id>/model.<ext>`; likely all students' files end up named alike, so a teacher cannot tell whose is whose. *(not verified in a browser)* | Thirty files called `model.3mf` on a shared machine is a mess. | Make "Send to my teacher" the primary route (it exists as submit-to-class; picker needs T3). If a file is saved, name it `nickname-title.3mf`. |
| 3 | **Adult-run printer.** T7 says "Send to my printer". `POST /api/send` can start a print (CR-1). | A child must never start a printer in a school room; the teacher must see and approve. | In class mode hide printer sending completely; "Send to my teacher" only. Teacher side: approval/queue (CR-13), "Only a grown-up starts the printer" line shown. |
| 4 | **Time pressure (about 45 minutes, 30 students).** Teacher setup has to take about 2 minutes, then the first student must be in within one more. | Teachers will not read a Safety page mid-lesson. | Create class in one step with a **generated password** ("blue-fox-47": readable, no symbols, easy to say) and a visible Show/Copy. Put "Print join sheet" as the first button after create. Safe defaults are on without any toggle to find. |
| 5 | **30 children typing a password at once.** The limiter keys on (student session, code) in `classrooms.py` (line 36, 82), so a whole school behind one network address is probably not locked out together. *(I read it; did not test.)* Mistyping is still the #1 problem. | A 2-minute join becomes 10. | Show/Hide password; do not force upper-case on the password; accept the code in lower case (the field only *looks* upper-case via CSS, `text-transform`; I did not verify the server uppercases it). Autofocus the next field after 6 characters. |
| 6 | **QR codes at school.** Some school devices have no usable camera, cameras are often disabled, and young children find QR hard. The QR also uses the server's configured base URL (CR-1), so a wrong `public_base_url` would give a QR that goes nowhere or somewhere else. | The "recommended" join method (R6) may fail for the youngest and for shared desktops. | Keep QR, but make the big typeable address the main line; a teacher "Test the link" button that opens the join page; show the exact address printed on the sheet so a teacher notices a wrong one before 30 children do. |
| 7 | **School network/filters.** A school may block the site, or a web filter may block `localhost`/odd ports/new domains. | Class day stops with no recovery. I cannot verify any school's filter. | In the teacher setup, a one-line note "If the page is blocked, ask your school's IT person to allow <domain>" with the domain filled in. Do not promise it will work everywhere. |
| 8 | **Substitute teachers.** The teacher account is bound to one browser cookie (identity.py; education.md CR-15); there are no co-teachers (design R6 defers them). A sub on another computer cannot open "Teacher tools" at all. | The class cannot be run if the regular teacher is away. | Printable sub plan (join sheet + the lesson's step list + "what to do if a student is locked out") that works **without** teacher login. Keep teacher tools out of reach of an unattended logged-in laptop: confirm-type-the-class-name for Delete; the destructive buttons (Remove/Delete) visually apart from Mute. |
| 9 | **Locked-out students.** A student who clears cookies or changes Chromebook gets "nickname taken" (CR-4). Neither T7 nor T8 mentions the fix. | This is the most likely daily interruption. | Add **Reset seat** next to Mute/Remove in the Students tab. Add the student-side message in §2.3. |
| 10 | **Consent and photos.** The lithophane first project starts with a photo. Safety tab line "what ZEIM cannot do" says ZEIM does not check photos. The Result screen has no mention of whose photo it was. | A teacher may think the Safety tab covers photo permission. It does not. | Add one line in Safety: "Students should use their own pictures, class pictures, or pets and places. No photos of other people without permission. Check your school photo rule." Link to my photo guidance (education.md §3.0). The upload-time tick box is CR-5 and should be built before the Safety tab claims anything about photos. |
| 11 | **Parent/guardian consent and legal.** Safety tab cannot say "COPPA-safe". Legal review is not done (README; education.md §2.2). | Overclaiming to a teacher could be a real problem. | Never use words like "safe", "COPPA", "compliant" in T8 headings. Say "What is on" and "What ZEIM cannot do". A "For parents and teachers" page is R11 in design.md (agree) but needs counsel. |
| 12 | **Accessibility inside the class.** Tooltips for "watertight" (T7) fail on touch/keyboard; emoji-only status (✔/✖) carries meaning by colour and symbol only. | Students with low vision, screen readers or colour-blindness. | Write the status as words ("Ready to print", "Needs a fix") with the icon as decoration; visible helper text, not tooltip. |
| 13 | **Teacher panel reading load.** One long modal today. Tabs help, but the Students tab must stay the default after Setup, since that is what a teacher uses all lesson. | Teachers glance, they don't read. | Default tab: **Students** once the class has any student; badge on tab for unread help requests. Safety is checked once, not daily. |
| 14 | **"Teacher tools" versus student view of teacher notes.** Teacher notes are currently shown to students (CR-14). | A Safety tab in the same modal could end up visible to students if a student shares a device with a teacher session. | Do not render Setup/Safety content for a non-teacher session; check server-side. (Engineering call.) |

## 4. Specific edits I would make to the tickets

**T7**
- Add to "done when": no "slicer", "3MF", "G-code" in the Beginner view; the **not-ready** state has copy and an action.
- Add: in a class session, the Print dialog shows only "Send to my teacher" and "Save the file" (no printer sending).
- Add: tooltips are not the only place that meaning appears.
- Add a line: Beginner mode in a class is set by the teacher, not the student.

**T8**
- Rename the Safety tab "What's on" (or keep Safety with the two sub-headings in §2.4); avoid the word "safe" in the sentence that answers the teacher's question.
- Every line in the Safety tab needs a matching Engineering change before it appears (CR-3 for Showcase; CR-6/CR-11 for reports; CR-4 for seat reset).
- Specify what happens to joined students on "New class code" and "Reset class password".
- Add **Reset seat**, **Print join sheet**, generated password, and a typeable join address to scope.
- "Done when" currently says a teacher can answer "is this safe for my students?" on one screen. I would soften it to: "a teacher can see what is on and what is not, and hand out access, in under 3 minutes."

## 5. What I could not verify
- No real teacher, child, or school IT person was consulted. Everything about classroom behaviour is reasoning, not observation. 
- No browser run: I did not open the Print dialog, join dialog or teacher modal. I read their code and markup.
- My readability numbers come from a home-made script (not a standard library) on very short strings; treat as rough.
- Not checked: which dimension is which in `size_mm`; whether the server upper-cases the class code; the actual download filename the browser gives for the result-bar links; how managed Chromebooks treat downloads or QR scanning; any particular school's web filter; whether "New code"/"Reset password" would keep existing students (code not written).
- I did not read the whole of `design.md` beyond the sections named above and the table rows I cite.

## 6. Hansei
- I started with the design's wording and tried to improve it; a better first step would have been writing what the teacher does minute by minute (setup, join, assign, print day) and checking each ticket against that timeline. I did this only in the head, not on paper.
- I leaned on FK because it is easy to compute, then found it misses what actually blocks children (vocabulary). I should have built a jargon list first and treated FK as secondary.
- My Safety tab wording is a first draft; it needs a teacher's reading and counsel's eyes before it is shown to a real school.
