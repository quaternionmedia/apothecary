# Contested numbers

**Hermetic.**

Some numbers are not settled, and none is a typo to be quietly corrected —
each has a document behind it:

    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> sorted(DEFAULT.contested)
    ['board_y']

`board_y` is the case that shows why prose does not resolve this. The datum
packet specifies the board outline as at most 40 mm, so an enclosure must
accept that. The black-box stub the seam serves today describes a specific
30 mm board. Both are live, and no schematic exists to settle them.

    >>> [c.value for c in DEFAULT.contested["board_y"]]
    [40.0, 30.0]
    >>> DEFAULT.contested["board_y"][0].source
    'datum HANDOFF.md, WP-4'

Every candidate carries where it came from. A value with no provenance is an
opinion, and an opinion cannot be adjudicated:

    >>> all(c.source and c.note for v in DEFAULT.contested.values() for c in v)
    True

## A disagreement can be settled by retiring one of its sides

This page listed three until recently. `walls` and `tolerence` were disputed
only by `parts/datum`, a single-piece tray that carried 2.4 and 0.2 while
citing the enclosure record for values that record does not contain. When the
compound — `datum_core` plus `datum_cap` — replaced it, the dissenting source
stopped existing and the house constants were left unopposed:

    >>> DEFAULT.params_model().walls, DEFAULT.params_model().tolerence
    (3.0, 0.4)

That is a real resolution, not a silencing, because what went away was an
artifact making a claim it could not support. The distinction matters: a
citation is provenance only while a reader can go and look, so a candidate
pointing at a deleted file is worse than no candidate at all. `board_y` stayed
precisely because both of its sources are still there to be read.

## The disagreement has a consequence

That is the whole reason to surface it. The wall thickness is settled now, but
it shows the shape of the consequence: 0.6 mm of wall is 1.2 mm of envelope,
which is the difference between fitting an opening and not:

    >>> P = DEFAULT.params_model
    >>> round(DEFAULT.get_bounds(P(walls=3.0).model_dump()).size.x, 2)
    46.8
    >>> round(DEFAULT.get_bounds(P(walls=2.4).model_dump()).size.x, 2)
    45.6

## Where you turn them

In the viewer. Select a part and its panel carries every parameter as a
control, contested ones first, each candidate a button that sets it. Turn the
number, press Regenerate, watch the envelope move.

There is one viewer and no second page onto the same object, so a link to a
part lands there:

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> r = client.get("/viewer/parts/datum_core", follow_redirects=False)
    >>> r.status_code, r.headers["location"]
    (307, '/viewer/sites/parts_library?focus=datum_core')

The controls are built from the part's own model, so a slider cannot offer a
value the renderer would refuse. That is not free: `gt=0` reaches the schema as
an *exclusive* minimum, and a slider stopping exactly on it hands back a value
the model rejects.

    >>> from apothecary.projects.parts.datum_core import Params
    >>> spec = client.get("/parts/datum_core/params").json()
    >>> walls = next(f for f in spec["fields"] if f["name"] == "walls")
    >>> walls["min"] <= 2.4 <= walls["max"] and walls["min"] <= 3.0 <= walls["max"]
    True
    >>> Params(walls=walls["min"]) and Params(walls=walls["max"]) and "accepted"
    'accepted'

## Recording one

Add candidates to the part's wrapper, each with its source and a note saying
what choosing it costs. Nothing else is required — the endpoint and the
dashboard read the declaration.

| | |
|---|---|
| See the disagreements | `apothecary parts info datum_core --json-out` |
| Turn them | the viewer, with the part selected |
| Render one candidate | `apothecary parts generate-stl datum_core -p walls=2.4` |
| Check the envelope it gives | `apothecary parts verify datum_core -p walls=2.4` |
