# (REA) (ArtCraft): provenance, not bundled product engines

## REA

The investigation used [morluto/rea](https://github.com/morluto/rea), pinned at
[`rea-agents@6.5.0`](https://github.com/morluto/rea/releases/tag/rea-agents-6.5.0),
through the reverse-engineering skill's lockfile-checked launcher.
REA is a research/verification tool here, not a runtime dependency, mesh kernel,
printer controller or component of the shipped workbench bundle.

Evidence is classified as follows:

- **Observed behavior, REA:** declared browser scenarios against public Tinkercad,
  Shapr3D and ugee pages in the earlier pass; retained complete records locally.
- **Blocked REA captures:** MakerWorld, Printables, Thingiverse and MyMiniFactory
  initially returned Cloudflare challenges. Those records do not prove app behavior.
- **Supplementary observed behavior:** a separate cloud browser viewed selected
  public pages on those four platforms. These are not relabeled as REA evidence.
- **Integration observation:** this branch adds a fresh bounded scenario against
  the actual ZEIM `/workbench/` route. Its identity and coverage are recorded in
  `evidence-manifest.json`.

The public branch records Evidence IDs and SHA-256 file identities, not raw third-party
DOM, thumbnails, screenshots, credential/storage data or machine-specific capture paths.
Complete evidence files remain in the task workspace. An evidence digest documents
identity; it is not a claim that the omitted raw evidence can be reconstructed from Git.

## ArtCraft

Source-assisted architecture reference:
[storytold/artcraft](https://github.com/storytold/artcraft), commit
`d4e4ac69bbd93d237eaf5d0260bc6a5ff3a5e373`.

Consulted `frontend/apps/artcraft/app/src/pages/MainApp.tsx` and the
`PageScene` entry point. The relevant pattern is a persistent tool shell with
tab-specific content and shared interaction surfaces. The source documents lazy
editor loading and the 3D engine's lifecycle.

ZEIM's workbench is a new, independently written implementation, not an ArtCraft fork.
No ArtCraft source, logos, media, API services, authentication, license bypasses or
competitor application bundles are copied into this branch. ArtCraft's dual
MIT/Apache-2.0 notice does not license unrelated third-party assets or services.

## Dependency notices

The shipped code uses Three.js (MIT), Lucide (ISC) and self-hosted Manrope (OFL).
Full license texts are committed under `static/perplexity-workbench/licenses/`.
esbuild (MIT) is development tooling; the separate pinned package lock records its version.

## Verification boundaries

This is not a recovered or verified reconstruction of a competitor app.
No screenshot is treated as proof of recovered CAD behavior. No logged-in competitor
flows, unknown binaries, private data, hardware, purchases or production deployments
were used. The browser-local workbench does not call REA or ArtCraft as a backend.
