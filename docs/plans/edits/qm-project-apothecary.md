# The records this work eventually owes

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/qm, branch `project/apothecary` |
| **State** | stub |
| **Depends on** | Photo → shapes → words → placed scenes → links; Twenty controls of its own become none |
| **Graduates to** | six new `adr/DRAFT-*.md` plus one in-place rewrite |
| **Verified** | `project/apothecary` cloned and read. Two records present, both Proposed, both unnumbered. `namespace-guard.yml` and `check_one_pr.py --per-base 'project/*'` read in full. The branch does not carry `records/DRAFT-one-executable-walkthrough.md`, which `main` does. |

## What
Six drafts, referenced by title because numbers are assigned at ratification:
the photo-derived shape provider seam · photo-derived geometry carries no scale ·
a word is a registered, reusable Assembly node · scene links as first-class edges ·
rad host integration for apothecary · photographs stay on the machine that took
them.

Plus one **in-place rewrite**, which is the cheapest high-value item here:
`adr/DRAFT-constitution-adoption-scope.md` is `Proposed`, so it is rewritten as
though the final position were always held. It gains a service inventory (empty,
verifiably — rad's §5 is the model), a risk register, size-smell thresholds for
the control plane, and the quarterly-upstream-scan gap named as a gap.

## Why now
Three of the eight obligations in `project-seed/adr/README.md` are undischarged
for apothecary today — service inventory, control-plane instance record, risk
register — and this feature line makes all three material. A hosted detector is a
§6 service; a detector is precisely where a seam grows into an engine; and
provider abandonment is a risk with nowhere to be written down.

## Seam
Mechanically constrained, and the constraint is not a matter of taste:
`namespace-guard.yml` runs on `pull_request: branches: ['project/**']` and fails
any path outside `adr/` that differs from `main`. Nothing org-level can ride on
these PRs.

`check_one_pr.py` returns the base name as the slot when it matches
`--per-base 'project/*'`, so `project/apothecary` holds its own slot — concurrent
with a `main`-based PR and with anything in the rad repo, but **serial with
itself**. Plan for four sequential PRs on that base, or cut records to fit.

Every PR: `check_pr_base.py --base project/apothecary --head <branch>` with the
output pasted; `gh pr create --draft`; no review requested; assignee is the
person who asked; no co-author trailer naming an unmonitored address.

## Open questions
- **The head-branch namespace is genuinely undefined.** `qm/README.md` names five
  namespaces and none of them describes a branch *heading toward*
  `project/<name>`: `propagate/` is main→project, `perspective/` is perspectives,
  `workspace/` never merges, and `project/` is refused as a head by
  `check_pr_base.py`. `evolve/<slug>` is the only survivor and fits poorly. Ask
  before pushing; if `evolve/` is the answer, that is a one-line addition to the
  table worth proposing.
- Whether to propagate first. The branch does not carry P12
  (`DRAFT-one-executable-walkthrough.md`), which is directly on point for a
  feature whose deliverable is "analyse a photo, look at the result". Citing it
  from this branch would cite a document not at its own pin.
- How much of the scene-document defect belongs here versus in apothecary's own
  issue tracker — see `features/scene-document-validation.md`.
