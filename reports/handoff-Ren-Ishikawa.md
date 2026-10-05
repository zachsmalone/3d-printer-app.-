# Handoff: Ren Ishikawa, Mesh & Slicer QA (2026-10-04)

## What I did
- First mesh printability audit of the ZEIM pipeline: /workspace/qa/mesh_audit.md (sent to Haruto).
  - High: pop-art OBJ/3MF non-manifold edges (since fixed: 0 of 22 cases failing on 97a63d6).
  - Medium: Edit "Hollow" leaves ~332 tiny void shells on vase-like inputs; Edit "Simplify" ignores keep_ratio and breaks the mesh. Both still open as of last test.
  - Low-Med: no output-size cap for extreme aspect ratios (10x1000 px = ~200 MB STL).
- Batch 1 UI QA (pinned copy of 97a63d6 on :8766, items 3 and QA-1 also on live :8765). Write-up appended to reports/engineering.md ("Batch 1 QA pass"), 87 screenshots in reports/qa_screens/batch1/.
  - PASS: photo start, HEIC/rotated JPEG, EXIF/GPS stripped, inline errors, Beginner/Expert build, no horizontal scroll at 320/375/390/768, stale model within Studio, 5-build cap, Edit text placement on all 6 faces, pop-art fix.
  - Bugs: QA-1 (Medium) Print opens wrong model across Studio/Edit tabs (shared S.current); QA-2..QA-6 (Low) see engineering.md.

## Unfinished
- Hollow and Simplify fixes and the aspect-ratio size cap: not retested.
- QA-1 to QA-6: Haruto queued fixes; not retested.
- Not tested: Send sheet (SEND-1, /sharetest), Creality K1 preset and Creality Print path, Send exports (format/size/watertight checks).
- Unverifiable without real devices: iOS Safari/Photos/iCloud HEIC, phone camera handoff, VoiceOver, iOS home indicator, K1 network send.
- Reviewer's extra test folders in outputs/ were never deleted (I held off, then did not get to it); only delete ones the Reviewer lists.

## Where files are
- Audit report: /workspace/qa/mesh_audit.md; audit scratch and generated meshes: /workspace/qa/ (gen_results__*.json, gen/<case>/, shapes_repro.png)
- Batch 1 scripts/raw JSON: /workspace/qa/b1/
- Screenshots: /workspace/photo3d/reports/qa_screens/batch1/
- Findings: /workspace/photo3d/reports/engineering.md
- Disk note: root filesystem hit 100% around 18:10 CT; /tmp/b1 (1.1 GB) and /tmp/freshvenv are not mine.
- No app code was edited by me.
