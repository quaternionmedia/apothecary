# Where a detector would run, if one is ever selected

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/moat |
| **State** | stub |
| **Depends on** | Selecting a real detector |
| **Graduates to** | a deployment-and-provenance record, if it ever happens |
| **Verified** | moat cloned and read: 16 charts plus standalone chart dirs. No nvidia device plugin, no `runtimeClassName: nvidia`, no Coral/TensorRT/OpenVINO — grep returns nothing. No object-storage chart, no PostgreSQL/MySQL/Redis chart. No `AGENTS.md`, no `governance/qm`, no `adr/`; listed under `org.unmanaged_named`. |

## What
If a detector is ever selected and needs to run somewhere other than a laptop,
moat is where. The pattern is one chart dir under `charts/<name>/` plus one
`Application` template in `charts/groot/templates/` — Argo CD app-of-apps,
`syncPolicy.automated` with selfHeal and prune.

Ingress is Traefik as default class with cert-manager issuing via
`letsencrypt-production`, hostnames `<service>.harpo.me`. Storage is
`proxmox-data-xfs`/`proxmox-data` block classes, or the MinIO already running
in-cluster and consumed as an S3 endpoint by both tempo and loki
(`endpoint: minio.minio`) — note those credentials are committed in cleartext.
`charts/frigate` is the existing object-detection precedent in this cluster, and
`charts/jellyfin`'s `/dev/dri` hostPath is the only hardware-acceleration
pattern present.

## Why now
**Blocked, not merely deferred.** Under the proposed local-only rule, running a
detector on the cluster is only permissible if "your machine" means "any machine
you own on your own network" rather than "the machine the software runs on".
That is item 1 in `../CONCERNS.md` and is unanswered, so this page waits on a
decision rather than on a schedule.

Everything below still holds if the answer goes the permissive way.

**Also not now, deliberately.** Shipping a container image flips apothecary's
licence-gate path from dependency-manifest to SBOM-per-image, opens a service
inventory it does not have, and triggers P8's deployment-and-provenance
obligation. That is a much larger commitment than a laptop-local slice needs.
Record it as a revision trigger on the adoption record and stop.

## Seam
`minio.minio` is the obvious S3 seam for photo storage if it ever leaves the
machine — which `features/photo-privacy.md` argues it should not, so the seam is
noted rather than recommended.

## Open questions
- moat carries no governance artifacts at all. A service landing here would need
  the full eight-step fork from `handbook/forking-a-project.md` first.
- GPU is entirely net-new. `/dev/dri` passthrough is the only precedent, and it
  is a QSV/VAAPI pattern rather than an inference one.
