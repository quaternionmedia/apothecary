# Selecting a real detector

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | stub |
| **Depends on** | Photo → shapes → words → placed scenes → links; the proposed local-only rule (`../proposals/runs-and-stays-local.md`) |
| **Graduates to** | a record on qm `project/apothecary`, citing the seam record |
| **Verified** | `records/DRAFT-build-the-seam-buy-the-engines.md`, `DRAFT-open-license-exclusion-and-upstream-remediation.md` §1 and §6, and `DRAFT-house-stack.md` §2–§3 read in full. |

## What
A third `ShapeProvider` implementation that actually recognises shapes. Nothing
on the current branch selects one, and that refusal is deliberate — the seam is
the deliverable.

## Why now
When `NaiveProvider`'s output stops being good enough to demonstrate the
pipeline. Not before: a detector chosen to make a demo look better is a detector
chosen without the ordering rule below.

## Seam
**The proposed local-only rule removes most of the field before these apply.** A
candidate must run on the user's own machine with the network off. That excludes
every hosted vision service outright — obligation 3 below stops being a test a
candidate can pass and becomes a disqualification.

What remains: a hand-written detector, or an openly-licensed model fetched once
and run locally thereafter. Whether that one-time fetch is permitted is item 2 in
`../CONCERNS.md` and is unanswered.

Four obligations any candidate must discharge, in this order:

1. **P4's ordering rule** — ask which engine should own this upstream before
   defaulting to the seam. Detectors are named explicitly in that record as
   components to select rather than write.
2. **Open-license §1** covers model weights *and their toolchains*, and refuses
   restricted "open-weights" — no waivers, no opt-ins. A local model needs a
   licence audit before it can land.
3. **Open-license §6** covers hosted inference: a service inventory row plus the
   ownability test — if this provider withdrew, re-priced, or refused service
   tomorrow, is the response a configuration change or an engineering project?
   Only the first is acceptable.
4. **House-stack §2–§3** — a component imported into seam code needs an org-level
   record; one reachable only across a protocol seam is an engine selection.

## Open questions
- The **size smell**: any image decoding, filtering, or pixel-level operation
  appearing inside `apothecary/` means the seam has become an engine. That is a
  revision trigger, not a style note.
- Under local-only, `features/photo-privacy.md` stops being a gate on this and
  becomes a statement of something the general rule already guarantees.
- Poor accuracy is explicitly acceptable. The local-only proposal says slow and
  yours beats fast and borrowed, so a visibly worse detector that runs offline is
  the intended outcome, not a compromise to apologise for.
