# Status and progress

**Hermetic.**

One vocabulary for how this CLI reports state, so the same outcome does not
look different depending on which command produced it.

    >>> from apothecary.cli.status import MARKS
    >>> sorted(MARKS)
    ['blocked', 'fail', 'info', 'ok', 'pass', 'skip', 'unknown']

Each state has a mark and a colour:

    >>> MARKS["pass"], MARKS["blocked"], MARKS["unknown"]
    (('OK  ', 'green'), ('STOP', 'red'), ('????', 'yellow'))

A Windows console on a legacy code page (cp1252, Windows's default) raises on
a character it does not have, so every line carrying one goes through
`_safe_echo`, and no mark carries one:

    >>> all(mark.isascii() for mark, _ in MARKS.values())
    True

The progress bar and the colours are Click's. Click is already a dependency,
and it is the CLI library the corpus's house-stack record
(`governance/qm/records/DRAFT-house-stack.md`) names; a library outside that
record's set needs an org-level record of its own.

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
| `apothecary parts generate-stl --all` | one OpenSCAD render per part |
| `apothecary parts verify --all` | a render *and* a measurement per part |
| `apothecary parts checklist --all` | an assessment per part, which renders |

The colours are the same three states the checklist uses, so `OK`, `STOP` and
`????` mean one thing across the whole CLI — and `????` is never a pass.
