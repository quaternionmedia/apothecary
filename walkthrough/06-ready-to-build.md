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
This module shipped that defect once: it read `build()` as one object when it
returns two, so it reported "no stubs remain" about an assembly it had never
looked at. It reads the assembly now:

    >>> stubs = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
    >>> stubs.state, "still guessed" in stubs.detail
    ('unknown', True)

That is `models/blackbox.py` earning its `source` field — a reader can tell a
measured envelope from a guessed one, and today the board and the mounting
surface are both guesses.

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
