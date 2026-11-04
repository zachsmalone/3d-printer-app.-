# FEAT3: Bambu / Prusa cloud sync (status, queues, history)

Status: research only. Not built, because every route found needs either a partner agreement or an
unofficial/undocumented API. Per the brief: no scraping, no unofficial auth.

## Bambu Lab
- There is no self-service public cloud API for third-party apps. Bambu offers integration through its SDK /
  partner programme, Bambu Connect, and the `bambu-connect://` URL scheme.
- Since the 2025 firmware updates, starting prints and control need Bambu's authorisation. LAN "Developer Mode"
  skips that but turns off cloud features; it is a local path, not cloud sync.
- Community libraries that log in to Bambu's cloud use undocumented endpoints. Not used.

## Prusa
- PrusaLink (local, on the printer) has a documented API (spec published under AGPLv3, digest auth). It is a
  LAN path, so it has the same reachability problem as FEAT2 and fits the local connector there.
- Prusa Connect (cloud) has an OpenAPI description for its mobile API, but no published terms permitting
  third-party apps to log in with a user's account. Using it without permission is a terms risk.

## Decisions needed (Zach)
1. Apply to Bambu's developer/partner programme? This is the only honest route to Bambu cloud data.
2. Write to Prusa asking whether third-party use of the Connect API is allowed, and on what terms.
3. Meanwhile, the FEAT2 local connector could read PrusaLink and Bambu LAN (Developer Mode) status locally,
   with the user's consent and their own access code.

No code changes. No cloud credentials are requested or stored.
