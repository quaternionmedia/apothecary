"""The stated picture the views tests pin, and the steps they take with it.

A stated description of a picture 1000 by 500 pixels (so not square), named
``bench_top`` in the unit tests' picture root (the ``world`` fixture in
tests/conftest.py) and ``world_bench`` in the browser tests' (tests/e2e/garage.py).
Pinned at node ``workbench`` in site ``garage``, it is laid in the bench's clear
stretch between ``printer_1`` and the footpedal; tests/test_views_api.py says where
each of its three shapes lands in the world.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

WIDE, HIGH = 1000, 500
TALLNESS = HIGH / WIDE
BENCH_TOP = (900.0, 300.0, 780.0)  # the bench's top-centre
LAID = (1094.0, 300.0, 780.0)  # a pinned picture's middle: clear of what rests on the top
SHAPES = [
    {
        "kind": "rect",
        "min": [0.135, 0.41],
        "max": [0.235, 0.51],
        "label": "block",
        "points": [[0.135, 0.41], [0.235, 0.41], [0.235, 0.51], [0.135, 0.51]],
    },
    {
        "kind": "disc",
        "min": [0.585, 0.7478],
        "max": [0.615, 0.8078],
        "label": "coin",
        "confidence": 0.9,
    },
    {
        "kind": "rect",
        "min": [0.3178, 0.1578],
        "max": [0.3378, 0.1978],
        "label": "bar",
        "confidence": 0.8,
    },
]


def png(size=(WIDE, HIGH), shapes="rt") -> bytes:
    """A light ground with the shapes named drawn dark: ``r`` a rectangle, ``e`` a
    disc, ``t`` a triangle."""
    img = Image.new("L", size, 245)
    pen = ImageDraw.Draw(img)
    if "r" in shapes:
        pen.rectangle((40, 40, 260, 160), fill=30)
    if "e" in shapes:
        pen.ellipse((360, 60, 520, 220), fill=20)
    if "t" in shapes:
        pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def forget_cameras():
    """Every camera a test added taken away, and every site built fresh: a Reset alone
    stands a site's cameras back in it, and the next test's state folder has none."""
    from apothecary.api import _site_store
    from apothecary.vision import cameras

    for camera in cameras.records():
        cameras.remove(camera.site, None, camera.name)
    for name in _site_store.loaded():
        _site_store.reset(name)


def pin(c, *, site="garage", host="workbench", picture="bench_top.png", finder="stated", **more):
    """Pin a picture as a view and Find shapes in it: the two steps a person takes,
    as most tests want them taken, through a test client."""
    r = c.post(f"/sites/{site}/views", json={"host": host, "picture": picture, **more})
    assert r.status_code == 201, r.text
    r = c.post(f"/sites/{site}/views/{r.json()['id']}/find", json={"finder": finder})
    assert r.status_code == 200, r.text
    return r.json()


def roots(c, site="garage"):
    """A site's structures by name, as the test client reads them."""
    return {s["name"]: s for s in c.get(f"/sites/{site}").json()["structures"]}
