# Serving it

**Hermetic.** The API is exercised in-process; nothing binds a port.

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> client.get("/health").json()
    {'status': 'healthy', 'version': '0.1.0'}

The registered sites: `datum_core` is the sub-assembly, `garage` the bench as
it is, `parts_library` the catalog every registered part but a building appears
in, and `theatre` a theatre's shell with its lighting rig.

    >>> client.get("/sites").json()
    ['datum_core', 'garage', 'parts_library', 'theatre']

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

A part's address opens the catalog, focused on the part, its Parameters
open:

    >>> r = client.get("/viewer/parts/datum_core", follow_redirects=False)
    >>> r.status_code, r.headers["location"]
    (307, '/viewer/sites/parts_library?focus=datum_core')

## Recipes

| | |
|---|---|
| Start it | `apothecary serve` |
| Check the install | `apothecary check` |
| The assembly | `/viewer/sites/datum_core` |
| The catalog | `/viewer/sites/parts_library` |
| One part, zoomed to | `/viewer/sites/parts_library?focus=datum_core` |
| The Bench | `/firmware` |
| A board's Machine | `/firmware/monitor?port=/dev/ttyUSB0` |
