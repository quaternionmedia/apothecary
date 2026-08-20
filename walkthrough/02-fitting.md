# Which numbers are whose

**Hermetic.**

`datum-core` is sized around a board this repository does not own. That makes
every dimension in it one of two kinds, and the split is the whole seam:

> The consumer owns requirements and interfaces.
> Apothecary owns realization and manufacturability.

`docs/fitting-a-part.md` is the standard. This page is how you drive it.

## Manufacturing facts carry house defaults

`walls` and `tolerence` are the constants from `parts/footpedal/button.scad`,
print-validated on QM hardware. They are the printer's facts, not the board's,
so they are parameters with house defaults rather than numbers a consumer sets.

    >>> from apothecary.projects.parts.datum_core import Params
    >>> Params().walls, Params().tolerence
    (3.0, 0.4)

Change the printer, not the part:

    >>> Params(walls=2).walls
    2.0

## Interface facts are the consumer's

The board footprint, the connector, the contact pitch. They live in the SCAD
file as defaults — a part has to render for someone who has never heard of
`datum` — but they are the numbers a fit profile will assert.

    >>> Params().board_x, Params().board_y
    (40.0, 40.0)

## Overrides reach OpenSCAD

Validated against the part's own model *before* anything renders, because
OpenSCAD accepts any `-D` name whether the file defines it or not: an unchecked
typo renders the defaults and exits 0.

    >>> from apothecary.projects.parts.stl_renderer import scad_definitions
    >>> scad_definitions({"show": "exploded", "walls": 2})
    ['-D', 'show="exploded"', '-D', 'walls=2']

A string carries its quotes, because `-D` values are parsed as source and a
bare word is an identifier:

    >>> from apothecary.projects.parts.stl_renderer import scad_literal
    >>> scad_literal("exploded"), scad_literal(True), scad_literal([1, 2])
    ('"exploded"', 'true', '[1, 2]')

## Recipes

| | |
|---|---|
| Render a variant | `apothecary parts generate-stl datum-core -p show=exploded` |
| A different printer | `apothecary parts generate-stl datum-core -p walls=2 -p tolerence=0.3` |
| Check a variant's envelope | `apothecary parts verify datum-core -p show=exploded` |
| What produced the STL on disk | `apothecary parts info datum-core --json-out` → `stl_params` |
| See the change | `apothecary serve`, then select the part — page 04 |

The whole loop, from a cold checkout:

```bash
uv run apothecary install                              # once; the viewer needs it
uv run apothecary serve --port 8765                    # look at it
# edit parts/datum-core/datum-core.scad
uv run apothecary parts generate-stl datum-core        # render
uv run apothecary parts verify datum-core              # bounds vs real geometry
```

A consuming project checks its own agreement separately — `datum` does it with
`uv run datum hil`, against the apothecary commit it pins.
