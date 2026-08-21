# Ready to build

**Hermetic.**

Before a spool is spent, one question: is this part ready to print and then
check against the real one? Answered from what the repository already knows,
not from a document somebody keeps by hand.

    >>> from apothecary.projects.parts.readiness import assess
    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> report = assess(DEFAULT, build_volume=(220.0, 220.0, 250.0))
    >>> [c.name for c in report.checks]
    ['Source geometry exists', 'Geometry renders', 'Declared bounds match geometry', 'Print settings declared', 'No disputed dimensions', 'Fits the printer', 'Fitted to measured artifacts']

## An unanswered question is not a pass

Three states, and the middle one is the whole point. `unknown` means the check
could not run — no OpenSCAD, no build volume, no measured envelope — and it
never counts as ready:

    >>> from apothecary.projects.parts.readiness import Check, Readiness, PASS, UNKNOWN
    >>> Readiness("x", [Check("asked", PASS), Check("could not ask", UNKNOWN)]).ready
    False

A checklist that ticks a box it could not check is worse than no checklist.
This module shipped that defect twice. First it read `build()` as one object
when it returns two, so it reported "no stubs remain" about an assembly it had
never looked at. Then, once it read the assembly properly, it reported *that*
assembly's stubs for every part in the library — `calibration_cube` was told it
was fitted to a board it has never heard of.

It is part-specific now, and the answer differs between the two enclosure
parts for a reason worth knowing:

    >>> from apothecary.projects.parts.datum import DEFAULT as datum_part
    >>> fitted = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
    >>> fitted.state
    'pass'
    >>> theirs = assess(datum_part)
    >>> stubs = next(c for c in theirs.checks if c.name == "Fitted to measured artifacts")
    >>> stubs.state, "still guessed" in stubs.detail
    ('unknown', True)

`parts/datum` is the part `projects/assemblies/datum_bench.py` drives through
the black-box seam, so it inherits the board and mounting-surface stubs.
`datum-core` is not wired to that seam at all — which is not a clean bill of
health so much as a gap, and `docs/boundaries.md` names it as one. That is
`models/blackbox.py` earning its `source` field: a reader can tell a measured
envelope from a guessed one, and from a part that is not fitted to either.

## What blocks datum-core today

    >>> disputed = next(c for c in report.checks if c.name == "No disputed dimensions")
    >>> disputed.state
    'blocked'

Its own sources disagree about three of its dimensions. A part cannot be called
ready to build while nobody has decided how big it is — page 05 is where those
are turned, and each candidate carries where it came from.

Every check that is not a pass says what to do about it:

    >>> all(c.fix or c.detail for c in report.checks if c.state != "pass")
    True

## Recipes

| | |
|---|---|
| One part | `apothecary parts checklist datum-core` |
| Against a printer | `apothecary parts checklist datum-core --build-volume 220,220,250` |
| Every part | `apothecary parts checklist --all` |
| In the viewer | select a part — **Build readiness** sits above its parameters |
| Over HTTP | `/parts/datum-core/checklist?build_volume=220,220,250` |

It exits non-zero when something is blocking, so it can gate a build.
