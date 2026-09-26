# A looksat service as the third provider

| | |
|---|---|
| **Kind** | integration |
| **Repo** | quaternionmedia/looksat* + quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | looksatphotos, looksatvideos, and what unknown means |
| **Graduates to** | a clause in the detector-selection record |
| **Verified** | Nothing. The repositories were not reachable; see the depends-on stub for the exact probes. |

## What
A `looksat*` service implementing `ShapeProvider` across the Protocol — the third
implementation, and the one that makes the seam's replaceability test something
other than theoretical.

## Why now
This is the shape P4's "build the seam, buy the engines" doctrine actually wants:
a detector that is *selected*, running behind a protocol boundary, rather than
written into apothecary. If these services exist, they are the answer to
`features/detector-selection.md`'s first obligation.

## Seam
`ShapeProvider`. Nothing else changes — which is the entire argument for having
built the seam first.

## Open questions
- Existence, first. Everything else is downstream of one `gh api` call.
- **A provider reached over the network is disqualified** by the proposed
  local-only rule unless item 1 in `../CONCERNS.md` resolves permissively. If
  `looksat*` turns out to be a service rather than a library, it may not be usable
  here at all — which would be a real loss and should be argued rather than
  absorbed quietly.
