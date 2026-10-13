# ZEIM Originals: "Simulated" and "Test-printed" badges

Every ZEIM Original card shows one honest badge:

| Badge | What it means |
|---|---|
| **Simulated** (default) | Checked on a computer only: shape checks plus a slicer preview with a generic 0.4 mm profile (see `reports/qa/originals-and-regression-2026-10-12.md`). It means the check was **done**, not that every check passed. Treated as an untested print. |
| **Test-printed** | The ZEIM team logged a **real print** of that file. The card names the printer that was logged and the date, and says whether it was also checked to work (for example, a call that makes its sound). |

Nothing says "tested on a K1" unless a K1 print was actually logged.

## Logging a real print (server admin only)
Needs the admin token (`PHOTO3D_ADMIN_TOKEN`), sent as the `X-Admin-Token` header.

```
POST /api/moderation/originals/zo-<slug>/prints
{"printer": "Creality K1", "printed_on": "2026-10-14", "result": "worked", "notes": "PLA, 0.2 mm, brim 5 mm"}
```
- `result`: `worked` (printed and did its job), `printed` (printed fine, function not checked yet), or `failed`.
- Only `worked` / `printed` turn the badge into **Test-printed**. A `failed` print keeps **Simulated** and says a test print failed.
- The date can't be in the future; the printer name is required.

A wrong entry is **retracted**, not deleted (it stays in the record but no longer counts):
```
POST /api/moderation/originals/prints/<entry id>/retract   {"reason": "logged on the wrong model"}
GET  /api/moderation/originals/prints                      (the full log)
```
The log lives in `data/originals_prints.json`.
