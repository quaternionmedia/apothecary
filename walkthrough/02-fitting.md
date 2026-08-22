# Which numbers are whose

**Hermetic.**

`datum_core` is sized around a board this repository does not own. That makes
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

## Every number in the file is a control

A dimension that lives only in the SCAD file cannot be staged, validated or
iterated — it can only be edited, which is the loop this tooling replaces. So
every top-level number in a part's SCAD has a parameter, and a test holds the
two together in both directions:

    >>> import re
    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> text = DEFAULT.source_file.read_text(encoding="utf-8")
    >>> numbers = {m.group(1) for m in re.finditer(r"^(\w+)\s*=\s*-?[\d.]+\s*;", text, re.M)}
    >>> numbers == set(DEFAULT.params_model.model_fields)
    True

Both directions matter. A number with no parameter is untunable; a parameter
with no number renders nothing when moved — `datum_core` carried six of those
after the cover moved to `datum_cap`.

## Staging, then iterating

A render is thirty seconds of OpenSCAD; validation is a Pydantic call. Moving a
slider stages a value and validates the whole staged set, which costs nothing:

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> staged = client.post(
    ...     "/parts/datum_core/validate", json={"params": {"walls": 2.4}}
    ... ).json()
    >>> staged["valid"], round(staged["bounds"]["size"]["x"], 1)
    (True, 45.6)

The envelope comes back before anything is rendered, so the consequence of a
change is visible before it is paid for. A set that could never render is
refused here:

    >>> client.post(
    ...     "/parts/datum_core/validate", json={"params": {"walls": -1}}
    ... ).json()["valid"]
    False

In the viewer the staged changes are marked, counted and shown against their
previous values, and **Apply** is the only thing that renders.

## Overrides reach OpenSCAD

Validated against the part's own model *before* anything renders, because
OpenSCAD accepts any `-D` name whether the file defines it or not: an unchecked
typo renders the defaults and exits 0.

    >>> from apothecary.projects.parts.stl_renderer import scad_definitions
    >>> scad_definitions({"tag": "draft", "walls": 2})
    ['-D', 'tag="draft"', '-D', 'walls=2']

A string carries its quotes, because `-D` values are parsed as source and a
bare word is an identifier:

    >>> from apothecary.projects.parts.stl_renderer import scad_literal
    >>> scad_literal("exploded"), scad_literal(True), scad_literal([1, 2])
    ('"exploded"', 'true', '[1, 2]')

## Recipes

| | |
|---|---|
| Render a variant | `apothecary parts generate-stl datum_core -p headroom=12` |
| A different printer | `apothecary parts generate-stl datum_core -p walls=2 -p tolerence=0.3` |
| Check a variant's envelope | `apothecary parts verify datum_core -p headroom=12` |
| What produced the STL on disk | `apothecary parts info datum_core --json-out` → `stl_params` |
| See the change | `apothecary serve`, then select the part — page 04 |

The whole loop, from a cold checkout:

```bash
uv run apothecary install                              # once; the viewer needs it
uv run apothecary serve --port 8765                    # look at it
# edit parts/datum_core/datum_core.scad
uv run apothecary parts generate-stl datum_core        # render
uv run apothecary parts verify datum_core              # bounds vs real geometry
```

A consuming project checks its own agreement separately — `datum` does it with
`uv run datum hil`, against the apothecary commit it pins.
