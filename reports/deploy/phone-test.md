# Phone-test address (iPhone camera test) - pointer

Status: ngrok replaces Cloudflare (this computer only passes TLS on port 443; ngrok works). Everything here is UNTESTED on real iOS. Whether it is switched on right now is stated by whoever started it; check `reports/deploy/iphone-test/TEST-NOTES.md`.

Full runbook: `deploy/iphone-test/RUNBOOK.md` (test log: `deploy/iphone-test/TEST-NOTES.md`).

Go-live gate (confirmed by Mr. Yami Kato on 2026-10-04: Haruto Batch 1 live, Kenji re-check passed, Zach agreed):
1. Haruto confirms in HQ: signed-link fix and camera work are done.
2. Kenji's `reports/safety-reverify-1.md` passes.
3. Zach has agreed (he has said yes in principle).

Start:  `reports/deploy/iphone-test/start.sh --haruto-confirmed`   (auto-shutoff 120 min by default, `--max-minutes N`)
Stop:   `reports/deploy/iphone-test/stop.sh`   (also runs the log check and removes the passcode and URL files)
Log check on its own: `reports/deploy/iphone-test/check-logs.sh`

The passcode and URL are saved in 0600 files in the run folder and never printed. Mr. Yami Kato sends them to Zach in a private DM, never in a group chat or a repo file.

Needs Zach's ngrok authtoken in `/workspace/tools/.ngrok-authtoken` (0600). `stop.sh` shreds it; Zach should rotate it after the test.
On the iPhone: ngrok's free plan shows a warning page once ("Visit Site": tap it), then Safari asks for user `zach` and the passcode. UNTESTED on real iOS.
Why not Cloudflare: its tunnel needs port 7844, blocked from this computer. See iphone-test/RUNBOOK.md.
