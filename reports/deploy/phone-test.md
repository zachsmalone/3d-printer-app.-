# Phone-test address (iPhone camera test) - pointer

Status: PREPARED, NOT SWITCHED ON. Everything here is UNTESTED on real iOS and untested through a real tunnel.

Full runbook: `deploy/iphone-test/RUNBOOK.md` (test log: `deploy/iphone-test/TEST-NOTES.md`).

Go-live gate (all must be true before starting):
1. Haruto confirms in HQ: signed-link fix and camera work are done.
2. Kenji's `reports/safety-reverify-1.md` passes.
3. Zach has agreed (he has said yes in principle).

Start:  `reports/deploy/iphone-test/start.sh --haruto-confirmed`   (auto-shutoff 120 min by default, `--max-minutes N`)
Stop:   `reports/deploy/iphone-test/stop.sh`   (also runs the log check and removes the passcode and URL files)
Log check on its own: `reports/deploy/iphone-test/check-logs.sh`

The passcode and URL are saved in 0600 files in the run folder and never printed. Mr. Yami Kato sends them to Zach in a private DM, never in a group chat or a repo file.

Known blocker (confirmed 2026-10-04 by a probe): this box cannot open a working tunnel. Outbound port 7844 (used by cloudflared) is blocked, and other no-account tunnels fail too. Run the test from Zach's own computer or ask for egress to be opened. See iphone-test/RUNBOOK.md.
