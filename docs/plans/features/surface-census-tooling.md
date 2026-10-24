# Counting the controls, repeatably

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | built — `apothecary census`, `apothecary/census.py`, 23 tests |
| **Depends on** | rad is a unification engine — the foundational principle |
| **Graduates to** | possibly a rad-side script, once a second host wants one |
| **Verified** | Run it. It reads `templates/fractal_viewer.html.j2` and reports twenty controls of its own, four things done to the scene, six places in the lists, three ways of taking hold, no ring. It refuses rather than guessing when it meets anything unclassified, and it refuses rather than answering nothing when it finds nothing at all. Both refusals have tests. |

## What
Clause §4 of the unification record asks a host to record its count before and
after. This takes the count.

    apothecary census

Two scans, deliberately not added together:

- **The page's own markup**, giving every button, drop-down, tick-box, typing
  box, form and link, one at a time. This is the meter. It has to reach nothing.
- **Every place the page listens**, each identified by what it listens on, what
  it listens for, *and the first thing it then does*.

Everything either scan finds is looked up in a table written by hand. Anything
not in the table stops the count and is named with its line number.

Each entry answers two questions kept firmly apart: what kind of surface it is
(a control of its own, something done to the scene, a place in the lists, the
drag handle, the ring) and what it changes (the arrangement itself, or only which
part you are looking at). Keeping them apart is the whole repair — see below.

## Why now
Because the number was wrong, and nobody could have known.

The stub this replaces said a hand count was defensible and that tooling should
wait for a second host. That was wrong in a way worth recording. The hand count
said twelve. A counter was then written, and it agreed — but only because it had
been built until it agreed. An independent reviewer, asked to break it, showed:

- **It counted names, not controls.** Two buttons on a job, fetched the same way,
  counted once. Three boxes for typing a position counted once. A drop-down that
  nothing listens to was invisible.
- **Its own rule did not produce its own number.** Stepping out of a piece by
  button was called a control; stepping out by clicking the trail was called
  moving your attention. Identical code. Applied evenly the rule gives nine or
  sixteen — never twelve.
- **A new control could hide inside an old one.** A delete button added to a row
  of a list attached exactly as the existing buttons did and produced no
  complaint at all.
- **Failing to read the page and finding nothing gave the same answer: zero.**
  Reformatting the page with a tidying tool would have reported a perfect score.

So the lesson is the opposite of what the stub assumed. A hand count is not
defensible; it is unfalsifiable, and a machine count built to match it is worse,
because it looks like evidence. The counter is worth having *before* a second
host, not after — it is what made the original figure's wrongness visible.

## Seam
`apothecary/census.py` and `apothecary/cli/census.py`. No new dependency; it
reads a file. rad's `scripts/` holds offline checkers of the same shape
(`check-palette.mjs`, `check-gate.mjs`), which is where a shared version would
live if a second host ever wants one.

## What it deliberately cannot do
Written into the module itself, so it travels with the number:

- It reads the page as text, so a listener inside a comment would be counted.
- The drawing library brings listeners of its own — turning and sliding the view
  by dragging are real, are not counted, and cannot be.
- It is one page. The command line and anything talking straight to the machine
  are not in the number.

## Open questions
- A count is still not the kind of check that can be replayed the way the shared
  contract's own checks are. The record says so; this page exists so the weakness
  stays visible rather than being quietly upgraded.
- Whether the second question — what a thing changes — should have its own meter.
  Of the twenty controls, fourteen change the arrangement, five only change what
  you are looking at, and one does nothing but hand you a file. A reader could
  argue the real number is fourteen. Both are in the output and neither is
  hidden; deciding which is *the* figure is a decision for a person.
