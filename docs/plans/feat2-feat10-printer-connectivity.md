# FEAT2 / FEAT10: send to printer and a print queue

Status: planning doc + simulator tests. Nothing here is hardware-tested. The download path stays.

## What already exists

- `app/services/printers.py` uploads, starts, reads status and pauses/resumes/cancels for OctoPrint and
  Moonraker (Klipper), and has a Bambu LAN path.
- Results are honest: an upload is "accepted"; a start is only "confirmed" when the printer's own status says it
  is printing. Every message says "Not Hardware-tested on a real printer yet."
- `HARDWARE_VERIFIED_TYPES` is empty.
- On production, direct control is off unless `ZEIM_PRINTER_DIRECT=1` (default: unset = off), because a server that
  dials any printer address is an SSRF risk. This is the default-off flag for FEAT2; no new flag was added.
- New: `tests/test_feat2_printer_simulator.py` runs send, start, status and pause against local Moonraker and
  OctoPrint simulators (7 tests). Simulators prove the request shapes, not the printer.

## Why the live site cannot send to a home printer today

1. zeimapp.com runs in a data centre. A K1 at `http://192.168.x.x:7125` is on Zach's home network; the server
   cannot reach it, and should not try.
2. The browser could reach it, but zeimapp.com is https and the printer is http. Browsers block that
   request as mixed content. Moonraker would also need CORS set for zeimapp.com.

So FEAT2 on the live site needs one of these. **Decision needed (Zach).**

| Option | How | Pros | Cons |
|---|---|---|---|
| A. Local connector (recommended) | A small program on a computer at home (or on the printer) pairs with the account, polls zeimapp.com over https for jobs and talks to the printer on the LAN | No inbound ports; works with mixed content; enables the FEAT10 queue | New program to build, sign and support; pairing and token design |
| B. Moonraker's own remote access | Use Moonraker's documented remote options or a tunnel the user sets up | No ZEIM program | Setup is hard for beginners; exposes the printer if done wrong |
| C. Self-hosted ZEIM on the LAN | Run ZEIM at home; `ZEIM_PRINTER_DIRECT=1` there | Works now with the existing code | Not the live site |

## FEAT10: queue

A queue that starts the next job when the printer is free needs something that is always connected to the
printer and can see "standby/complete" and that the bed is clear. Only option A gives that. Starting a print
on a bed that still has a part is a real hazard, so a queue must ask a person to confirm the bed is clear
before each auto-start unless the printer has an ejection system. Build after option A exists.

## What Zach must test on the K1 (in order)

Run a self-hosted ZEIM on the same network (option C) with `ZEIM_PRINTER_DIRECT=1`.

1. Settings → printer → Creality K1. Address `http://<K1-IP>:7125` (Moonraker, not Fluidd on 4408).
   Press Test. Expect "reachable". Note the firmware version on the K1 screen.
2. Slice the 20 mm calibration cube. Send **without** start. Check the file appears in the K1's file list.
   The K1 must not start.
3. Send **with** start, standing next to the printer. Expect "accepted"; then the status should
   change to printing with the right filename. Note how long it took.
4. Status card: compare nozzle/bed temperatures and progress with the K1 screen.
5. Pause → check the printer pauses. Resume → it continues. Cancel → it stops and parks.
6. Wrong address and printer powered off: expect a clear "could not reach printer" message, no crash.
7. Report pass/fail per step with times. Only after all pass: add `"moonraker"` to `HARDWARE_VERIFIED_TYPES`
   in its own PR.

OctoPrint and Bambu stay unverified until someone tests them on real hardware.
