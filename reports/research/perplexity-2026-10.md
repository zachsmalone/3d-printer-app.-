# ZEIM research — Perplexity to Mr. Yami Kato

Reviewed 2026-10-12. Issue #3. Research plus an offline budget calculator; no purchases, deployments, legal representation or printer tests. Claude owns slicer implementation.

## Slicer recommendation

Recommend PrusaSlicer CLI for the first prototype, then evaluate OrcaSlicer for its native K1 profile. This is engineering judgement, not a hardware-tested result. Creality publishes K1 Prusa/Cura configuration downloads: https://wiki.creality.com/en/software/creality-print/three-party-platform

| Engine | Licence | CLI | K1 support and limits |
| --- | --- | --- | --- |
| CuraEngine | AGPL-3.0 repository label; source says AGPLv3 or higher. https://github.com/Ultimaker/CuraEngine ; https://github.com/Ultimaker/CuraEngine/blob/main/src/communication/CommandLine.cpp | -j JSON definitions, -l model, -o output, -s key=value. https://github.com/Ultimaker/CuraEngine/blob/main/src/communication/CommandLine.cpp | Creality offers Cura configurations; direct engine loading of the GUI configuration is unverified. https://wiki.creality.com/en/software/creality-print/three-party-platform |
| PrusaSlicer | AGPL-3.0. https://github.com/prusa3d/PrusaSlicer | --export-gcode, --load profile.ini, --output output.gcode. https://manpages.debian.org/unstable/prusa-slicer/prusa-gcodeviewer.1 | Creality provides a K1 configuration download; contents, performance and actual output require testing. https://wiki.creality.com/en/software/creality-print/three-party-platform |
| OrcaSlicer | GNU AGPL version 3; optional Bambu networking plugin uses non-free libraries. https://github.com/OrcaSlicer/OrcaSlicer | --load-settings, --load-filaments, --slice 0, --export-3mf. Documentation example exports sliced 3MF; raw G-code workflow remains unverified here. https://www.orcaslicer.com/wiki/cli/cli_mode | Upstream K1 profile declares Klipper, 220x220x250 printable volume, 0.4 mm nozzle and START_PRINT/END_PRINT. It inherits fdm_creality_common, so it is not a complete resolved standalone preset. https://github.com/OrcaSlicer/OrcaSlicer/blob/main/resources/profiles/Creality/machine/Creality%20K1%20(0.4%20nozzle).json |

Illustrative command, not executed: `prusa-slicer --export-gcode --load k1.ini --output output.gcode model.stl` (manual above). Pin the engine and check installed help. Validate profile inheritance, printable-volume containment, output format and estimates separately. AGPL deployment/distribution obligations need legal review; subprocess use is not asserted to remove obligations.

## Three pilot hosting options under $80/month

Assumption: one small FastAPI service and 20 GB persistent app data. Subtotals exclude taxes, domain, separately priced backups, databases, workers and unassessed transfer. VM disks are shared with the OS/app; reserve headroom. No plan is benchmarked for slicing concurrency.

| Option | Resources | Monthly base subtotal | Source |
| --- | --- | --- | --- |
| DigitalOcean Basic Regular | 1 vCPU, 2 GiB RAM, 50 GiB SSD | $12, bundled persistent disk | https://www.digitalocean.com/pricing/droplets |
| Vultr Cloud Compute Regular Performance | 1 vCPU, 2 GB RAM, 55 GB disk | $10, bundled disk | https://www.vultr.com/pricing/ |
| Render Hobby + 1 CPU / 2 GB service | Paid service with 20 GB persistent disk | $0 workspace + $25 compute + 20 x $0.25 disk = $30 | https://render.com/pricing ; https://render.com/docs/disks |

Recommendation: DigitalOcean if an operator can manage the VM and backups; Render if managed deployment warrants the higher base cost; Vultr is the cheaper listed VM alternative. These are judgement calls, not measured performance claims. Verify region/availability and checkout before selection.

Render Hobby includes 5 GB monthly bandwidth, then $0.15/GB. Illustrative 105 GB transfer adds $15, making its compute/disk/egress subtotal $45. Persistent disks require a paid service, are available to one instance and prevent zero-downtime deployments. Store persistent files under the mount rather than the ephemeral filesystem. https://render.com/pricing ; https://render.com/docs/disks

The calculator uses a dated price snapshot, not a complete bill predictor. Unknown transfer rates for the VM options remain null and produce an exclusion warning rather than an invented zero charge. OS/app reserve, extra monthly costs and annual domain amortisation are caller inputs, not provider quotes.

## Free/low-cost US legal-help routes

1. WashU Entrepreneurship Clinic: local first contact for Zach in St. Louis; free legal assistance for qualifying entrepreneurs/organizations. Apply through the official intake page. Acceptance, current availability, children's-privacy expertise and filing charges remain unknown. https://law.washu.edu/academics/clinical-programs/entrepreneurship-clinic/
2. UMKC Entrepreneurial Legal Services and Intellectual Property Clinic: serves Missouri/Kansas entrepreneurs unable to afford market-rate services. St. Louis eligibility, exact fee arrangement, intake and privacy expertise require confirmation; do not promise free representation. https://law.umkc.edu/academics/clinics/entrepreneurial-legal-services-clinic.html
3. USPTO Law School Clinic Certification Program: directory of participating pro bono patent/trademark clinics. Confirm geographic eligibility and acceptance with a clinic. This is an IP referral, not confirmation of COPPA/FERPA expertise; government fee waivers are unverified. https://www.uspto.gov/learning-and-resources/ip-policy/public-information-about-practitioners/law-school-clinic-1

Proposed intake brief: free school/family maker app; account ages, nickname classroom identities, uploads/photos/models, teachers' feedback, logs, hosting, sharing and moderation. Ask counsel to review consent, notices, retention/deletion, school agreements, trademark clearance and AGPL obligations. Do not provide real children's data as an intake example.

FTC guidance flags a 2025 COPPA Rule amendment and limits school-authorised consent to school-benefit use without another commercial purpose. Counsel must assess ZEIM against the current rule and actual data flows. Free access does not establish an exemption. This report is not legal advice or compliance clearance. https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions

## ZEIM domain ideas, pricing and availability

Candidate ideas: zeim.com, zeimmaker.com, makezeim.com, zeim.org and zeim.app. All exact-name availability and trademark clearance remain UNKNOWN. No name has been reserved or purchased.

Porkbun lists standard non-premium .com registration and renewal at $11.08/year. This is a TLD list price, not a quote for any candidate above; a registered, reserved or premium name may be unavailable or cost more. Other TLD checkout prices should be reconfirmed rather than assumed from a promotional headline. https://porkbun.com/products/domains ; https://porkbun.com/about/domain-cost-calculator

Attempts to retrieve registry RDAP records for these .com names failed; retrieval failure is not proof of an unregistered/available name:
- https://rdap.verisign.com/com/v1/domain/zeim.com
- https://rdap.verisign.com/com/v1/domain/zeimmaker.com
- https://rdap.verisign.com/com/v1/domain/makezeim.com

Proposed next check: live registrar search for makezeim.com and zeimmaker.com, followed by trademark screening before purchase. This is naming judgement, not an availability claim. Exact-name availability is an outstanding issue #3 verification gap.

## Code and test handoff

- app/data/research/pilot_hosting.json: dated, sourced hosting prices and explicit unknowns.
- app/research_budget.py: Decimal-based offline calculator; disk capacity/headroom checks, egress when known, domain amortisation and strict under-budget comparison. Does not provision resources.
- tests/test_research_budget.py: 17 focused pytest cases passed in an isolated temporary package; full ZEIM suite not run.

Run tests: `python -m pytest -q tests/test_research_budget.py`
Run default comparison: `python -m app.research_budget`

This research branch leaves K1 loader/profile files and Claude's slicer untouched. Yami's build line reviews and runs the full suite before merge. Keep unknown domain availability, clinic acceptance/privacy scope, checkout prices and workload performance explicit; do not describe them as verified.
