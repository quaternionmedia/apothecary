# 58 — A ring searched by typing

**Hermetic.** Nothing here opens a port or a browser. This page is run by `uv run
pytest` (the quick loop) and by `apothecary test run`, as a doctest: every value shown is
the value the run computed, and a run that computes another fails here.

Every option of the ring has an address, the digits pressed to reach it, so a person who
knows the address reaches the option in a few presses. A person who does not knows its
word. Typed while the ring is open, the word finds the option and shows the keys that
reach it, so the next time is pressed rather than typed ([docs/viewer.md, the
ring](../docs/viewer.md#the-ring)). The rule is rad's *typing in an open ring finds an
item*, and rad's own conformance vectors hold this page's functions and the page's ring
alike ([tests/conformance/rad/](../tests/conformance/rad/source.json)).

## The canvas ring, searched

The garage's canvas ring, as `m` opens it with nothing selected. `step` finds every
option whose path has a word beginning `step`: Step out first, its own label holding the
word and one key away, then the ones further in. Each shows its keys from a closed ring:
`m`, then its address.

    >>> from apothecary.example_hierarchy import create_example_site
    >>> from apothecary.menu import Context, Pointing, resolve, search_keys
    >>> ring = resolve(Context(pointing=Pointing.CANVAS, targets=[]), create_example_site())
    >>> for found in search_keys(ring, "step", opener="m")[:3]:
    ...     print(found.path, "|", found.keys)
    Step out | m 1
    Panels › Tools › Deck › Step | m 4 3 2 4
    Panels › Machine › Loops › Experiment › Step | m 4 4 2 1 8

Each word typed is the start of a word somewhere on the path, so two words find an option
under a ring by the ring's name and its own: `pan w` is Panels, then a W.

    >>> for found in search_keys(ring, "pan w", opener="m")[:3]:
    ...     print(found.path, "|", found.keys)
    Panels › Windows | m 4 9
    Panels › Site › Workspace | m 4 8 3
    Panels › Windows › World alone | m 4 9 8

## Typing, Tab and Enter

The ring reads each key as the query does first. A letter begins the query; Tab completes
it to the first result, and again to the next; Enter presses the one Tab is on.

    >>> from apothecary.menu import Query, type_query
    >>> query = Query()
    >>> for key in ["l", "a", "y", "Tab", "Tab"]:
    ...     read = type_query(ring, query, key)
    ...     query = read.query
    ...     print(repr(key), "->", read.text)
    'l' -> l
    'a' -> la
    'y' -> lay
    'Tab' -> View › Layers
    'Tab' -> Panels › Site › Layers
    >>> chosen = type_query(ring, query, "Enter").chosen
    >>> (chosen.path, chosen.address)
    ('Panels › Site › Layers', '487')

A digit is never the query's: it is a cell, pressed at once, and the query goes. So the
digits a result shows can be pressed while it is shown.

    >>> read = type_query(ring, type_query(ring, Query(), "s").query, "1")
    >>> (read.passed, read.text)
    (True, '')

## Over the route, with the page's own keys

`POST /menu/search` takes what `/menu/resolve` takes, the query, the key that opens the
ring and the page's own keys, and answers resolve's ring searched, the page's keys after
the ring's options. The page runs the same search in `static/ring.js` as each key is
typed; the route is the same rule for anything that is not the page.

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> answer = client.post("/menu/search", json={
    ...     "context": {"pointing": "canvas", "targets": []}, "site": "garage",
    ...     "query": "fit", "opener": "m",
    ...     "shortcuts": [{"key": "Shift+f", "does": "Fit the level", "label": "Shift+F"}],
    ... })
    >>> for found in answer.json():
    ...     print(found["path"], "|", found["keys"])
    View › Fit | m 2 8
    Pictures › Floor › Fit | m 9 6 8
    Fit the level | Shift+F

## Where the rule comes from

The vectors are rad's, copied from the commit that carries them and never edited here; the
coordinate they are is the one rad's record pins.

    >>> import json, pathlib
    >>> source = json.loads(pathlib.Path("tests/conformance/rad/source.json").read_text())
    >>> (source["repository"], source["coordinate"], source["replayed"])
    ('quaternionmedia/rad', '0.0.2', ['search'])
