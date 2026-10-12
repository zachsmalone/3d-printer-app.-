# ZEIM slicer research — Perplexity to Mr. Yami Kato

Date: 2026-10-12. Scope: issue #2 data/loader and the slicer portion of issue #3. This is not Claude's slicer implementation. No engines or printers were run during this research.

## Recommendation

Recommend PrusaSlicer CLI for the first prototype: it explicitly supports CLI use, loads INI configuration and exports G-code, and Creality publishes K1 configuration downloads for PrusaSlicer. This is an engineering recommendation, not proof that the resulting G-code works on Zach's printer. Sources: https://github.com/prusa3d/PrusaSlicer ; https://manpages.debian.org/unstable/prusa-slicer/prusa-gcodeviewer.1 ; https://wiki.creality.com/en/software/creality-print/three-party-platform

Evaluate OrcaSlicer next for its built-in K1 machine profile. That profile explicitly declares Klipper flavour, a 220 x 220 printable bed, 250 mm printable height, a 0.4 mm nozzle and START_PRINT/END_PRINT macros. It inherits fdm_creality_common: the single file is not a complete standalone resolved preset. Source: https://github.com/OrcaSlicer/OrcaSlicer/blob/main/resources/profiles/Creality/machine/Creality%20K1%20(0.4%20nozzle).json

## Comparison

| Engine | Licence evidence | CLI flags | K1 fit / limits |
| --- | --- | --- | --- |
| CuraEngine | AGPL-3.0 repository label; command-line source says AGPLv3 or higher. https://github.com/Ultimaker/CuraEngine ; https://github.com/Ultimaker/CuraEngine/blob/main/src/communication/CommandLine.cpp | `-j` JSON definitions, `-l` model, `-o` output, `-s key=value` overrides; `CuraEngine help` for the installed build. https://github.com/Ultimaker/CuraEngine/blob/main/src/communication/CommandLine.cpp ; https://github.com/Ultimaker/CuraEngine/wiki/Building-CuraEngine-From-Source | Creality offers K1 Cura configurations, but direct use of that GUI configuration with CuraEngine was not verified. https://wiki.creality.com/en/software/creality-print/three-party-platform |
| PrusaSlicer | AGPL-3.0. https://github.com/prusa3d/PrusaSlicer | `--export-gcode`, `--load profile.ini`, `--output output.gcode`. https://manpages.debian.org/unstable/prusa-slicer/prusa-gcodeviewer.1 | Manufacturer-supplied K1 configuration download available. Actual configuration contents, fast-print quality and hardware compatibility still need smoke tests. https://wiki.creality.com/en/software/creality-print/three-party-platform |
| OrcaSlicer | GNU AGPL version 3; optional Bambu networking plugin uses non-free libraries. https://github.com/OrcaSlicer/OrcaSlicer | `--load-settings`, `--load-filaments`, `--slice 0`, `--export-3mf`; CLI settings use hyphens. https://www.orcaslicer.com/wiki/cli/cli_mode | Upstream K1 machine profile exists and inherits a common preset. Documentation's example exports sliced 3MF, not a raw .gcode file. Raw G-code extraction/export workflow remains unverified here. https://github.com/OrcaSlicer/OrcaSlicer/blob/main/resources/profiles/Creality/machine/Creality%20K1%20(0.4%20nozzle).json ; https://www.orcaslicer.com/wiki/cli/cli_mode |

Illustrative Prusa invocation (not executed):

```sh
prusa-slicer --export-gcode --load k1.ini --output output.gcode model.stl
```

The installed binary's help and pinned version are authoritative for supported flags. The argument example is supported by the packaged manual above; input profile validation and model containment are separate tasks.

## Data contribution and provenance

- `app/data/printers/creality_k1.json`: sourced manufacturer capabilities plus explicitly labelled upstream profile settings. Advertised 600 mm/s is not a material printing default. Manufacturer: https://www.creality.com/support/creality-k1-3d-printer
- Retraction 0.8 mm at 40 mm/s, deretraction 40 mm/s and Z-hop 0.4 mm are machine profile values, not TPU-specific calibrations. Upstream blob SHA reviewed: 11edd6f0723641fe0ccd1ed5e55894ffdced759f. Source: https://github.com/OrcaSlicer/OrcaSlicer/blob/main/resources/profiles/Creality/machine/Creality%20K1%20(0.4%20nozzle).json
- PLA and PETG temperatures are general Prusa recommendations, not K1-tested presets. https://help.prusa3d.com/article/pla_2062 ; https://help.prusa3d.com/article/petg_2059
- TPU temperatures specifically describe Prusament TPU 95A, not all TPU. https://help.prusa3d.com/article/prusament-tpu-95a-material-guide_899653
- Speeds use explicitly labelled typical volumetric-flow ranges: PLA 12–20, PETG 8–15, TPU 2–5 mm^3/s. These are not linear mm/s speeds or a measurement of the K1 hotend. https://help.prusa3d.com/article/max-volumetric-speed_127176

Unverified K1 material-specific linear speeds and retraction are omitted. Nozzle material is omitted because the manufacturer lists hardened steel while the upstream K1 profile says brass. Sources: https://www.creality.com/support/creality-k1-3d-printer ; https://github.com/OrcaSlicer/OrcaSlicer/blob/main/resources/profiles/Creality/machine/Creality%20K1%20(0.4%20nozzle).json

Each numeric setting has its own `sources` list, unit and provenance note. The loader retains provenance, rejects malformed/unsourced settings, does not invent defaults and does not invoke an engine. URL checks validate syntax only, not the truth or accessibility of a cited page.

## Acceptance and handoff

Follow Zach's latest requested path `app/data/printers/materials.json`, rather than issue #2's original `app/data/materials.json`. Follow his omission rule rather than adding unknown numeric defaults or null settings. Notes explicitly document omissions. Reference material ranges are not executable, calibrated slicer presets.

Run `python -m pytest -q tests/test_printer_profiles.py`. Focused tests exercise schema, URL provenance requirements, positive finite values, ranges, duplicate JSON keys, path allowlisting and fresh load results. The full ZEIM suite remains for Yami's build line.

Claude must still choose and pin an engine, map reference data into its native profile format, ensure printable-volume containment, smoke-test headless operation, retrieve estimates, enforce job ownership/resource limits and conduct printer validation. No endpoint or slicing changes are included here.

AGPL deployment/distribution compliance and the effect of any integration on ZEIM need licence review; running a subprocess is not asserted to remove obligations. Licence evidence is in the table, not a legal opinion.

## Remaining issue #3 scope

Hosting prices, US legal-help programs, and ZEIM domain availability/cost are not researched in this report. Keep issue #3 open; this PR addresses only its slicer subsection.
