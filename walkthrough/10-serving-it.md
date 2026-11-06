# Serving it

**Hermetic.** The API is exercised in-process; nothing binds a port.

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> client.get("/health").json()
    {'status': 'healthy', 'version': '0.1.0'}

The registered sites: `apothecary` is the universe, `datum_core` the
sub-assembly, `garage` the bench as it is, and `theatre` a theatre's shell
with its lighting rig.

    >>> client.get("/sites").json()
    ['apothecary', 'datum_core', 'garage', 'theatre']

The universe holds every registered part as a leaf, and every other site as
one piece, drawn in miniature from boxes its tree carries. A building is the
site's that holds it, and no leaf:

    >>> tree = client.get("/sites/apothecary").json()["tree"]
    >>> sorted(piece["site_ref"] for piece in tree["children"] if piece["site_ref"])
    ['datum_core', 'garage', 'theatre']
    >>> parts = {leaf["part_ref"] for leaf in tree["children"] if leaf["part_ref"]}
    >>> "datum_core" in parts, "theatre" in parts
    (True, False)

Every site read carries its generated OpenSCAD, so the SCAD section of the
viewer's Site panel fills on load:

    >>> body = client.get("/sites/datum_core").json()
    >>> body["is_valid"], "hull()" in body["scad"]
    (True, True)

## The viewer serves its own 3D library

The page loads three.js from this server, not from a CDN, so it draws with no
network:

    >>> page = client.get("/viewer/sites/datum_core").text
    >>> "jsdelivr" in page
    False
    >>> '"three": "/static/vendor/three/three.module.js"' in page
    True

The library is checked in under `apothecary/static/vendor/three/`, so a fresh
clone serves it with no install step; the README beside it says how to update it.

## One page

The viewer is the only page. `/firmware` opens it with the Bench in front of
the world, and `/firmware/monitor?port=…` with that board's Machine and the
sections a link asks for -- a printer's Status and Log, a devkit's Sketch and
Log:

    >>> r = client.get("/firmware", follow_redirects=False)
    >>> r.status_code, r.headers["location"]
    (307, '/viewer/sites/garage?panel=bench')

A part's address opens the universe, focused on the part, its Parameters
open:

    >>> r = client.get("/viewer/parts/datum_core", follow_redirects=False)
    >>> r.status_code, r.headers["location"]
    (307, '/viewer/sites/apothecary?focus=datum_core')

The universe was the site `parts_library`, and that address goes to it still,
its query kept:

    >>> r = client.get("/viewer/sites/parts_library?focus=datum_core", follow_redirects=False)
    >>> r.status_code, r.headers["location"]
    (307, '/viewer/sites/apothecary?focus=datum_core')

## Recipes

| | |
|---|---|
| Start it | `apothecary serve` |
| Check the install | `apothecary check` |
| The assembly | `/viewer/sites/datum_core` |
| The universe: every part, and every other site | `/viewer/sites/apothecary` |
| One part, zoomed to | `/viewer/sites/apothecary?focus=datum_core` |
| The Bench | `/firmware` |
| A board's Machine | `/firmware/monitor?port=/dev/ttyUSB0` |
