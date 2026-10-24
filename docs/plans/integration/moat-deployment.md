# Deploying anything to the cluster

| | |
|---|---|
| **Kind** | integration |
| **Repo** | quaternionmedia/moat |
| **State** | stub |
| **Depends on** | Selecting a real detector |
| **Graduates to** | a deployment-and-provenance record |
| **Verified** | See `edits/moat.md` — same reading, same session. |

## What
Held. The chart-plus-Application pattern is understood and documented in
`edits/moat.md`; nothing is built until a detector exists that needs to run
somewhere other than a laptop.

## Why now
Explicitly not now. The trigger is a selected detector that cannot run locally.

## Seam
`charts/groot/templates/` for the Argo `Application`, `charts/<name>/` for the
chart, Traefik plus cert-manager for ingress.

## Open questions
- Everything in `edits/moat.md`'s open questions, unchanged.
