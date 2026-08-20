# Navigating a sub-assembly

**Hermetic.**

A printable part is one solid. That is the right shape for a printer and the
wrong shape for a reader: "how tall is the standoff" has no answer in a mesh.

`datum-core` is therefore also an `Assembly` tree — the same enclosure, with
every feature addressable.

    >>> from apothecary.datum_core_site import create_datum_core_site
    >>> site = create_datum_core_site()
    >>> [s.name for s in site.children]
    ['tray', 'lid']

Cuts are nodes, not anonymous geometry. `_assembly_tree` folds `children`,
`additions` and `subtractions` into one navigable list, so a subtraction is
reachable in the viewer exactly like a child.

    >>> tray = site.children[0]
    >>> shell = tray.children[0]
    >>> shell.name, [s.name for s in shell.subtractions]
    ('shell', ['cavity', 'connector-opening'])

Four levels deep, and every node compiles on its own:

    >>> def walk(node, path=""):
    ...     here = f"{path}.{node.name}" if path else node.name
    ...     yield here
    ...     for child in [*node.children, *node.additions, *node.subtractions]:
    ...         yield from walk(child, here)
    >>> paths = list(walk(site))
    >>> len(paths), max(p.count(".") for p in paths)
    (22, 4)
    >>> "datum-core.tray.mounting.boss-front-left.pilot-hole" in paths
    True

## It is a model, so it is gated

Built from primitives rather than importing the STL, because an imported mesh
has no interior to navigate. That makes it a second description of one object,
and `tests/test_datum_core_site.py` reads the SCAD file's own defaults and
holds all shared dimensions to them.

    >>> from apothecary import datum_core_site as dc
    >>> dc.WALLS, dc.TOLERENCE
    (3.0, 0.4)
    >>> round(dc.OUTER_X, 1), round(dc.TRAY_H, 1)
    (46.8, 15.6)

The lid sits above the tray by the documented gap, and a validator says so
rather than leaving it to the eye:

    >>> from apothecary.datum_core_site import validate_datum_core
    >>> validate_datum_core(site).is_valid
    True
    >>> site.children[1].position.z = 5.0        # lid sunk into the tray
    >>> report = validate_datum_core(site)
    >>> report.is_valid
    False
    >>> "inside the tray" in report.violations[0].message
    True

## Recipes

| | |
|---|---|
| Every registered site | `curl localhost:8765/sites` |
| One node's geometry | `curl localhost:8765/sites/datum-core/nodes/tray.shell/stl` |
| The generated OpenSCAD | `curl localhost:8765/sites/datum-core` → `scad` |
