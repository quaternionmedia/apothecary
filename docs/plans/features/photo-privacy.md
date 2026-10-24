# What a photograph contains that a scene does not

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | the proposed local-only rule (`../proposals/runs-and-stays-local.md`) |
| **Graduates to** | photographs stay on the machine that took them (project) and a personal-data record (org) |
| **Verified** | Searched the whole qm corpus by filename and content: no org-level privacy, PII, personal-data or biometric record exists. `DRAFT-open-license-exclusion-and-upstream-remediation.md` §6 read in full — it governs provider replaceability and says nothing about data. Since 2026-09-20 this project has its own: the draft *Personal data stays on the device, by construction* in `governance/qm/adr/`, enforced by `apothecary/stays_local.py`; the org-level record is still the gap. |

## What
Photographs of a workshop, a garage or a home contain people, addresses, licence
plates and equipment inventories. The derived `Detection` contains none of that —
it is a handful of normalized polygons. The gap between those two facts is where
the decision lives: where an ingested photo is stored, for how long, and what
leaves the machine.

**The proposed local-only rule answers this without a photo-specific decision.**
If the software stores nothing off the machine and needs no outside service, a
photograph cannot leave, and an implementation that transmits one is not a
candidate at all rather than a candidate requiring extra scrutiny.

That is a simplification worth taking. What it does *not* do is close the wider
gap: no rule anywhere says what information may leave, for any project that does
send data somewhere. This page stays open for that reason.

## Why now
Before the first photograph is ingested, not after. This is the cheapest possible
moment to decide it and the most expensive one to defer.

## Seam
The Protocol boundary is also the egress boundary, which is convenient: a
provider either reads a local file or it does not.

## Open questions
- A project record cannot bind `looksatphotos` or any sibling. Closing the gap
  org-wide is `edits/qm-main.md`, gap 1.
- Retention. "Until the site is discarded" and "never written to disk at all" are
  both defensible and imply different code.
- EXIF. Location and device data ride along in the file and nothing currently
  strips them.
