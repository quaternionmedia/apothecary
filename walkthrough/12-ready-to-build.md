# Ready to build

**Hermetic.**

Before a spool is spent, one question: is this part ready to print and then
check against the real one? Answered from what the repository already knows,
not from a document somebody keeps by hand.

    >>> from apothecary.projects.parts.readiness import assess
    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> report = assess(DEFAULT, build_volume=(220.0, 220.0, 250.0))
    >>> [c.name for c in report.checks]
    ['Source geometry exists', 'Geometry renders', 'Declared bounds match geometry', 'Print settings declared', 'Model defaults match the SCAD', 'No disputed dimensions', 'Fits the printer', 'Fitted to measured artifacts']

A part's default is its SCAD as saved, so where its Python model says
another default, that is asked too; `datum_core`'s agree:

    >>> next(c for c in report.checks if c.name == "Model defaults match the SCAD").state
    'pass'

## An unanswered question is not a pass

Each check is `pass`, `blocked` or `unknown`. `unknown` means the check could
not run — no OpenSCAD, no build volume, no measured envelope — and it never
counts as ready:

    >>> from apothecary.projects.parts.readiness import Check, Readiness, PASS, UNKNOWN
    >>> Readiness("x", [Check("asked", PASS), Check("could not ask", UNKNOWN)]).ready
    False

The check for stubs is per part, and its answer differs between parts:

    >>> from apothecary.projects.parts.calibration_cube import DEFAULT as cube
    >>> stubs = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
    >>> stubs.state, "still guessed" in stubs.detail
    ('unknown', True)
    >>> theirs = assess(cube)
    >>> fitted = next(c for c in theirs.checks if c.name == "Fitted to measured artifacts")
    >>> fitted.state
    'pass'

`datum_core` is the part `projects/assemblies/datum_bench.py` drives through
the black-box seam, so it inherits the board and mounting-surface stubs.

`calibration_cube` is fitted to nothing, and says so. The `source` field of
`models/blackbox.py` lets a reader tell a measured envelope from a guessed one,
and both from a part fitted to neither. So the `pass` belongs to the part with
no claims on it, and the `unknown` to the one with real, unmeasured
dependencies.

## What blocks datum_core

    >>> disputed = next(c for c in report.checks if c.name == "No disputed dimensions")
    >>> disputed.state
    'blocked'

Its own sources disagree about how deep the board is (`board_y`). A part is
not ready to build while its size is undecided; [page 11](11-contested-numbers.md)
is where that is turned, and each candidate carries where it came from.

Every check that is not a pass says what to do about it:

    >>> all(c.fix or c.detail for c in report.checks if c.state != "pass")
    True

## Recipes

| | |
|---|---|
| One part | `apothecary parts checklist datum_core` |
| Against a printer | `apothecary parts checklist datum_core --build-volume 220,220,250` |
| Every part | `apothecary parts checklist --all` |
| In the viewer | select a part — **Build readiness** sits above its parameters |
| Over HTTP | `/parts/datum_core/checklist?build_volume=220,220,250` |

It exits non-zero when something is blocking, so it can gate a build.
