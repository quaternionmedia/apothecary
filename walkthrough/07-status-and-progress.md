# Status and progress

**Hermetic.**

One vocabulary for how this CLI reports state, so the same outcome does not
look different depending on which command produced it.

    >>> from apothecary.cli.status import MARKS
    >>> sorted(MARKS)
    ['blocked', 'fail', 'info', 'ok', 'pass', 'skip', 'unknown']

Each state has a mark and a colour, and the marks are ASCII on purpose:

    >>> MARKS["pass"], MARKS["blocked"], MARKS["unknown"]
    (('OK  ', 'green'), ('STOP', 'red'), ('????', 'yellow'))

Windows still defaults to cp1252, and this CLI has already died once on a
check mark — every glyph goes through `_safe_echo`, and the fancier glyph sets
are exactly what breaks there. That is also why this is built on Click's
progress bar and styling rather than a richer library: Click is in the blessed
set and already a dependency, and an addition outside that set needs an
org-level record it would not earn here.

## Progress where a loop is slow enough to watch

`iterate` wraps a loop that keeps printing as it goes; `progress` wraps a block
that collects first. Both step aside when there is no terminal:

    >>> from apothecary.cli import status
    >>> list(status.iterate(["a", "b"], "Doing"))
    ['a', 'b']

A bar redrawing itself into a CI log is noise, and the per-item lines are the
record there — so the bar appears only for a terminal, and only when there is
more than one item to wait on.

    >>> list(status.iterate(["only-one"], "Doing"))
    ['only-one']

## Where it shows

| Command | What the bar is waiting on |
|---|---|
| `apothecary parts generate-stl --all` | one OpenSCAD render per part, tens of seconds each |
| `apothecary parts verify --all` | a render *and* a measurement per part |
| `apothecary parts checklist --all` | an assessment per part, which renders |

The colours are the same three states the checklist uses, so `OK`, `STOP` and
`????` mean one thing across the whole CLI — and `????` is never a pass.
