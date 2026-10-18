# ZEIM hosting options

## Status

Draft comparison. Prices and provider capabilities below have not been verified against current provider documentation. All cost ranges are preliminary estimates, not quotes.

## Deployment requirements

ZEIM's proposed deployment needs a Python FastAPI service, a background worker capable of running PrusaSlicer, persistent storage for uploads and generated files, HTTPS, and backups. Exact resource requirements need workload testing.

## Options

| Provider | Proposed setup | Preliminary monthly compute estimate (unverified) | Storage and backup options to verify |
|---|---|---|---|
| Hetzner | Cloud VPS | EUR 4-15+ | Persistent volumes, snapshots, and separate object storage |
| DigitalOcean | Droplet + Spaces | USD 6-24+, excluding Spaces | Droplet backups/snapshots and Spaces object storage |
| Vultr | Cloud Compute | USD 6-24+, excluding object storage | Snapshots and object storage |
| AWS | EC2 + S3 | USD 10-30+, highly configuration-dependent | S3 versioning, EBS snapshots, and AWS Backup |

These estimates exclude potentially material storage, backup, bandwidth, tax, database, and operational costs. They do not imply that the lowest-priced plan can handle ZEIM's slicing workloads.

## Provisional recommendation

Evaluate DigitalOcean first for a straightforward single-server deployment with separate object storage. Compare Hetzner as a cost-focused alternative. Consider Vultr as another VPS option and AWS when its broader services justify additional configuration. These are provisional judgments, not benchmarked conclusions.

Run FastAPI and the slicing worker as separate processes or containers. Begin resource testing around 2 vCPU / 4 GB RAM, but treat this only as an unverified test configuration. Measure peak memory, slicing duration, and concurrency before choosing a production plan.

## Backup plan to validate

- Back up metadata separately from the application server.
- Keep source uploads and generated assets in durable storage.
- Verify versioning, retention, and recovery costs.
- Test restores before launch.

## Provider sources for verification

- https://www.hetzner.com/cloud
- https://www.digitalocean.com/pricing/droplets
- https://www.digitalocean.com/pricing/spaces
- https://www.vultr.com/pricing/
- https://aws.amazon.com/ec2/pricing/
- https://aws.amazon.com/s3/pricing/
- https://www.prusa3d.com/page/prusaslicer_424/
- https://fastapi.tiangolo.com/

## Open checks

Verify current regional pricing, available instance specifications, PrusaSlicer compatibility and licensing obligations, database requirements, expected storage growth, and concurrent slicing performance before committing to a provider.
