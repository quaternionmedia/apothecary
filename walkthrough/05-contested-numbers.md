# Contested numbers

**Hermetic.**

Some numbers are not settled. `datum-core` has three, and none is a typo to be
quietly corrected — each has a document behind it:

    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> sorted(DEFAULT.contested)
    ['board_y', 'tolerence', 'walls']

`walls` is the case that shows why prose does not resolve this. The enclosure
record's clause 3 says the house constant is 3; `parts/datum/datum.scad` uses
2.4 and cites that same record for it, which the record does not say.

    >>> [c.value for c in DEFAULT.contested["walls"]]
    [3.0, 2.4]
    >>> DEFAULT.contested["walls"][0].source
    'governance/qm/adr/DRAFT-enclosure-parts-live-in-apothecary.md, clause 3'

Every candidate carries where it came from. A value with no provenance is an
opinion, and an opinion cannot be adjudicated:

    >>> all(c.source and c.note for v in DEFAULT.contested.values() for c in v)
    True

The part ships one of the candidates rather than inventing a third — the
record's, since that is the one with authority:

    >>> DEFAULT.params_model().walls
    3.0

## The disagreement has a consequence

That is the whole reason to surface it. 0.6 mm of wall is 1.2 mm of envelope,
which is the difference between fitting an opening and not:

    >>> P = DEFAULT.params_model
    >>> round(DEFAULT.get_bounds(P(walls=3.0).model_dump()).size.x, 2)
    46.8
    >>> round(DEFAULT.get_bounds(P(walls=2.4).model_dump()).size.x, 2)
    45.6

## The dashboard

`/viewer/parts/datum-core` puts each parameter on a slider over a live render,
contested ones first, with every candidate as a button that sets it. Turn the
number, press Render, watch the envelope move.

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> client.get("/viewer/parts/datum-core").status_code
    200

The controls are built from the part's own model, so a slider cannot offer a
value the renderer would refuse:

    >>> spec = client.get("/parts/datum-core/params").json()
    >>> walls = next(f for f in spec["fields"] if f["name"] == "walls")
    >>> walls["min"] <= 2.4 <= walls["max"] and walls["min"] <= 3.0 <= walls["max"]
    True

## Recording one

Add candidates to the part's wrapper, each with its source and a note saying
what choosing it costs. Nothing else is required — the endpoint and the
dashboard read the declaration.

| | |
|---|---|
| See the disagreements | `apothecary parts info datum-core --json-out` |
| Turn them | `/viewer/parts/datum-core` |
| Render one candidate | `apothecary parts generate-stl datum-core -p walls=2.4` |
| Check the envelope it gives | `apothecary parts verify datum-core -p walls=2.4` |
