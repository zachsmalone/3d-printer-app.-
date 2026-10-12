# Handoff: Spark Lab Curriculum Writer (2026-10-04)

> **Superseded in part (2026-10-12):** Zach removed the school aspect of ZEIM. Teacher tools, classrooms, class codes, assignments, quizzes, scores, grades and any school records described below are NOT part of ZEIM and will not be built. ZEIM stays free and family-friendly; kids use it with their families. Learning lessons/videos that keep no scores still apply. See reports/HQ/board.md.


## What I did
- Zach asked for a teacher/parent guide for ZEIM. I asked him who it is for (classroom teachers, parents, or both) and the age range. He had not answered yet.
- In the Hq2 room I collected facts for the guide. No guide file has been written.

## Facts gathered for the guide (as given by teammates; not independently verified)
- Hosting (Ren Okabe): ZEIM runs only on the local computer, nothing is pushed anywhere. Data lives in `data/` and `outputs/`. Printer keys are stored unencrypted, so treat a copy of `data/` as private. Other computers on a shared network could reach the app until the localhost-only default lands. No public address or pilot date should be promised.
- Filter (Filter Red-Team Tester): call it "a basic safety net", never "protection". It is not reliable against evasions or personal details (`reports/filter-redteam.md`). Teachers should supervise chat and remind students not to share names, emails or addresses.
- Pop-art (Ren Ishikawa, `/workspace/qa/mesh_audit.md`): use STL for now. OBJ/3MF multi-color layers are broken until a fix is verified. Hollow and Simplify may report success on a bad mesh.
- Send features (Yami's decisions in `HQ/decisions.md`): sending outside ZEIM is a separate user choice. Photo models by minors/students are not sent out by default. Email-to-yourself goes only to the account's own address and comes later. Mark everything "coming soon" or "untested" until verified, including Creality K1 and the share sheet.
- Accessibility (`reports/accessibility.md`): several keyboard-only paths are broken today, so classroom steps should not rely on them.

## Unfinished
- The guide itself: audience, age range, outline, and content were not started.

## Files
- Only this note. I changed no app code.
