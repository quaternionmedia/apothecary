# Contested numbers

**Hermetic.**

Some numbers are not settled, and none is a typo to be quietly corrected —
each has a document behind it:

    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> sorted(DEFAULT.contested)
    ['board_y']

`board_y` is the case that shows why prose does not resolve this. The datum
packet specifies the board outline as at most 40 mm, so an enclosure must
accept that. The black-box stub the seam serves describes a specific 30 mm
board. Both are live, and no schematic exists to settle them.

    >>> [c.value for c in DEFAULT.contested["board_y"]]
    [40.0, 30.0]
    >>> DEFAULT.contested["board_y"][0].source
    'datum HANDOFF.md, WP-4'

Every candidate carries where it came from. A value with no provenance is an
opinion, and an opinion cannot be adjudicated:

    >>> all(c.source and c.note for v in DEFAULT.contested.values() for c in v)
    True

## A candidate's source must be readable

A citation is provenance only while a reader can go and look, so a candidate
is kept only while its source can be read, and one citing a file that is
deleted goes with it. A disagreement whose only dissenting source is gone is
settled, and the number stops being contested. `board_y` stays contested
because both of its sources are there to be read.

## The disagreement has a consequence

The board's depth is the enclosure's depth: the two candidates are 10 mm
apart, and so are the envelopes they give, which is the difference between
fitting a board and not:

    >>> P = DEFAULT.params_model
    >>> round(DEFAULT.get_bounds(P(board_y=40.0).model_dump()).size.y, 2)
    46.8
    >>> round(DEFAULT.get_bounds(P(board_y=30.0).model_dump()).size.y, 2)
    36.8

## Where you turn them

In the viewer: a part's ring, Part › Edit, opens its parameters in Parameters, a
contested one first, each candidate a button that sets it ([the part
editor](../docs/viewer.md#the-part-editor)). Turn the number and the declared
envelope follows; Apply renders the part with it.

The controls are built from the part's own model, so a slider cannot offer a
value the renderer would refuse. That is not free: `gt=0` reaches the schema as
an *exclusive* minimum, and a slider stopping exactly on it would hand back a
value the model rejects. The endpoint gives a range whose ends the model
accepts, and each candidate is inside it:

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> from apothecary.projects.parts.datum_core import Params
    >>> client = TestClient(app)
    >>> spec = client.get("/parts/datum_core/params").json()
    >>> board_y = next(f for f in spec["fields"] if f["name"] == "board_y")
    >>> [c["value"] for c in board_y["contested"]]
    [40.0, 30.0]
    >>> all(board_y["min"] <= c["value"] <= board_y["max"] for c in board_y["contested"])
    True
    >>> Params(board_y=board_y["min"]) and Params(board_y=board_y["max"]) and "accepted"
    'accepted'

## Recording one

Add candidates to the part's wrapper, each with its source and a note saying
what choosing it costs. Nothing else is required — the endpoint and the
viewer read the declaration.

| | |
|---|---|
| See the disagreements | `apothecary parts info datum_core --json-out` |
| Turn them | the viewer: the part's ring, Part › Edit |
| Render one candidate | `apothecary parts generate-stl datum_core -p board_y=30` |
| Check the envelope it gives | `apothecary parts verify datum_core -p board_y=30` |
