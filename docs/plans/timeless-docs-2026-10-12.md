# The documentation, brought under "durable text states what is true"

*Begun on 2026-10-12. The rule is the governance record *Durable text
states what is true, not how it came to be*
(`governance/qm` records, `DRAFT-durable-text-states-what-is-true.md`;
Proposed in qm#136): durable text states what is true now and what to do
with it, for a reader who was not there -- present tense, no internal
history, no ornament -- and a repository's existing text is swept area by
area, each passage sent to one home. This plan is the sweep's triage for
apothecary: what each area holds, where each passage goes, and the order.
It is dated and about the sweep, so the rule's own §4 exempts it.*

## Decided with the owner

Asked one at a time on 2026-10-12:

- **A passage's homes** are the record's own: a short fact stays inline in
  the present tense; an explanation moves to the reference pages in
  `docs/`; a narrative moves to a dated retrospective; a duplicate or a
  stale statement with no lesson is deleted.
- **Retrospectives go to the governance corpus's `perspectives/`**, one
  dated file per area, on a perspective branch with its own draft pull
  request there, not into this repository.
- **Plans and validation records are dated and exempt.** `docs/plans/` and
  `docs/validation/` stay as written. A finished plan retires: it leaves
  the present-tense links and is listed under a dated *History* heading in
  `docs/README.md`, and each decision of it that is still true moves into
  the present-tense documentation, a record or the code's own docstring.
  The CHANGELOG is a release log and exempt too.
- **The gate joins CI after the record is ratified.** Until then
  `check_timeless.py --all` is the sweep's measure, run from the record's
  branch; once qm#136 is ratified and the governance pin carries the tool,
  a CI step and preflight check the lines each change adds.

## The measure

`check_timeless.py --all` sees the shapes a pattern can match: shouting in
capitals and a short list of phrases that only narrate. Its report on this
branch is the starting count and each area's pull request reports it again.
Most of what the sweep is for -- history told in ordinary words, statements
the code no longer bears out, counts a command computes, the same thing
said on several pages -- only a reader finds, so each area is read in full.

## Areas

1. Top-level and reference pages: `README.md`, `QUICKSTART.md`,
   `CONTRIBUTING.md`, `AGENTS.md`, `todo.md`, `docs/*.md`, `tests/e2e/README.md`,
   the parts and crates READMEs.
2. The walkthrough: pages 00-10 written by hand, pages 11-16 written by the
   browser tests that hold them.
3. The package's docstrings, comments and `--help` texts.
4. The page's comments, the tests' docstrings, and the CI and project
   configuration's comments.
5. The plans and validation records: which retire, and where their
   still-true decisions go.

The inventory of each area -- every passage, its problem and its home --
and the order of the sweep follow below once read.
