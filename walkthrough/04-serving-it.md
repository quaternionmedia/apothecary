# Serving it

**Hermetic.** The API is exercised in-process; nothing binds a port.

    >>> from fastapi.testclient import TestClient
    >>> from apothecary.api import app
    >>> client = TestClient(app)
    >>> client.get("/health").json()
    {'status': 'healthy', 'version': '0.1.0'}

Three sites are registered. `datum_core` is the sub-assembly; `parts_library`
is the catalog every registered part appears in.

    >>> client.get("/sites").json()
    ['datum_core', 'garage', 'parts_library']

Every site read carries its generated OpenSCAD, so the viewer's code panel
fills on load rather than waiting for someone to drag something:

    >>> body = client.get("/sites/datum_core").json()
    >>> body["is_valid"], "hull()" in body["scad"]
    (True, True)

## The viewer serves its own 3D library

Loading three.js from a CDN meant the page worked only for a browser that could
reach that CDN. When it could not, the module never executed and the canvas,
the contents list and the code panel came up empty together — while the static
markup still read "Layout valid".

    >>> page = client.get("/viewer/sites/datum_core").text
    >>> "jsdelivr" in page
    False
    >>> '"three": "/vendor/three/build/three.module.js"' in page
    True

## Recipes

| | |
|---|---|
| Install what it needs | `apothecary install` — once, or the page renders nothing |
| Start it | `apothecary serve --port 8765` |
| Check the install | `apothecary check` |
| The assembly | `/viewer/sites/datum_core` |
| The catalog | `/viewer/sites/parts_library` |
| One part, zoomed to | `/viewer/sites/parts_library?focus=datum_core` |
