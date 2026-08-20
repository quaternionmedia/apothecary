# The parts registry

**Hermetic.**

A part is a folder, a SCAD file named after it, and a Python wrapper that says
what it is and how big.

    parts/<name>/<name>.scad          the geometry
    apothecary/projects/parts/<name>.py   the wrapper, underscored

Nothing registers a part but that naming. `scan_projects` finds the folder;
`_locate_wrapper_for_part` finds the wrapper by sanitising the name.

    >>> from apothecary.projects.registry import scan_projects, _sanitize_module_name
    >>> _sanitize_module_name("datum-core")
    'datum_core'

The wrapper is what gives a part a description, a category and — the part that
matters to anything assembling around it — an envelope.

    >>> from apothecary.projects.parts.datum_core import DEFAULT
    >>> DEFAULT.name
    'datum-core'
    >>> DEFAULT.category
    'enclosure'

## Bounds are declared, then checked

`get_bounds` is hand-written Python beside hand-written OpenSCAD, so it is
capable of lying. It reports the tray at its default parameters:

    >>> size = DEFAULT.get_bounds().size
    >>> round(size.x, 1), round(size.y, 1), round(size.z, 1)
    (46.8, 46.8, 15.6)

`apothecary parts verify <name>` renders the part and measures the real
bounding box against that claim. It exits non-zero on drift, so it belongs in
CI. On the existing library it finds four of six parts wrong — see `todo.md`.

## Recipes

| | |
|---|---|
| List what is registered | `apothecary parts list` |
| Everything about one part | `apothecary parts info datum-core --json-out` |
| Render its STL | `apothecary parts generate-stl datum-core` |
| Check the envelope is true | `apothecary parts verify datum-core` |
| Check every part's envelope | `apothecary parts verify --all` |
