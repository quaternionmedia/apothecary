# Parts authoring

A part is a folder under `parts/` holding a SCAD file of the same name, plus
either a Python wrapper under `apothecary/projects/parts/` or a `part.json`
sidecar beside the SCAD. The registry finds both; `apothecary parts list`
shows each part with the module that describes it.

## Layout

```
parts/
├── my_part/
│   ├── my_part.scad      the source
│   ├── README.md         optional; the wrapper's readme_path
│   ├── my_part.stl       built by generate-stl, git-ignored
│   └── my_part.params.json   the overrides it was built with, git-ignored
└── boards/               a category: its subfolders are parts
    ├── board_common.scad a library its parts include, not a part
    └── arduino_uno/
        ├── arduino_uno.scad
        └── part.json     a described part: no Python
```

Names use underscores throughout: the folder, the SCAD file, the wrapper
module and the part's `name` are all `my_part`. A wrapper for a part in a
category folder may be a package mirroring the folder
(`parts/rc/snowplow/` is served by `apothecary/projects/parts/rc/snowplow/`).

## A wrapper

`apothecary/projects/parts/my_part.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from apothecary.models import BoundingBox3D, Color

from .base import BasePart
from .skeleton import ROOT


class Params(BaseModel):
    """The SCAD file's top-level variables a caller may set, with its defaults."""

    size: float = Field(20.0, gt=0, description="Edge length in mm")
    wall: float = Field(2.0, gt=0, description="Wall thickness in mm")


class MyPart(BasePart):
    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = Params(**(params or {}))
        return BoundingBox3D.for_cube(p.size, center=False)


def create(root: Path) -> MyPart:
    return MyPart(
        name="my_part",
        source_file=root / "parts" / "my_part" / "my_part.scad",
        description="A hollow cube",
        params_model=Params,
        category="misc",
        tags=["demo"],
        readme_path=root / "parts" / "my_part" / "README.md",
        preview_color=Color.from_hex("#3366CC"),
    )


DEFAULT = create(ROOT)
```

`tests/test_docs_site.py` runs this block, so it builds a part as written.
`DEFAULT` is what the CLI, the API and the viewer import. A part with no
parameters passes no `params_model` and states its envelope as
`default_bounds=BoundingBox3D(...)` instead of overriding `get_bounds`.
`display_rotation`, `print_settings` and `contested` are further `BasePart`
fields; [Geometry models](models.md) describes the types.

## A sidecar instead of a wrapper

A folder whose SCAD has a `part.json` beside it and no Python module is a
*described* part: the sidecar says what the wrapper would (description,
category, tags, colour, rotation, bounds, provenance). See
[Described parts](geometry-from-elsewhere.md#described-parts);
`apothecary parts import` writes one for a mesh made elsewhere. A described
part has no `Params` model, so its overrides are checked against the SCAD
file's own top-level variables.

## Overrides

```bash
uv run apothecary parts generate-stl datum_core -p headroom=12
uv run apothecary parts generate-stl datum_core -p board_x=60 -p headroom=20
```

`-p` is repeatable and is checked against the part's `Params` model before
anything renders. OpenSCAD accepts any `-D` name whether the file defines it
or not, so a misspelling would otherwise render the defaults and exit 0:

```
$ uv run apothecary parts generate-stl datum_core -p headrooom=10
Error: unknown parameter(s): headrooom. datum_core declares: ...
```

Overrides imply `--force`. The STL lands at the part's own path, which is
what the viewer serves, so a build with overrides records them in
`<name>.params.json` beside it, and a default build removes that file:
`apothecary parts info NAME --json-out` shows the record as `stl_params`,
and `null` means a default render.

Over HTTP, `POST /parts/{name}/stl/generate` with `{"params": {...}}` does
the same build; an unknown or invalid parameter is a `422` with the reason,
and the response carries the bounds the part declares for those parameters.

### Adding a parameter

Two places, kept in step: a top-level variable in the SCAD file (what `-p`
reaches as `-D`) and a field on the wrapper's `Params` (what validates and
documents it). `tests/test_parameter_coverage.py` fails on a field with no
SCAD variable behind it; `apothecary parts verify` fails when the two
disagree about size.

## Hooks for a part the SCAD file does not fully describe

Most parts need none of these. Each is a `BasePart` field or method a
wrapper sets or overrides, and every build path (`generate-stl`, `verify`,
the viewer's `POST /parts/{name}/stl/generate`, server startup) goes
through them.

`openscad_min_version` is the oldest OpenSCAD that renders the part, as
`openscad --version` numbers it (`"2021.08.24"`). The default install is
used when it is new enough, else a development snapshot: `openscad-nightly`
on `PATH` or one of the usual install locations. With neither,
`can_generate_stl()` names the version needed and where snapshots are.
`generate-stl --all`, `verify` and server startup skip the part with that
reason, `checklist` gives it, and a build of that part alone is refused
with it: `generate-stl NAME` fails, and `POST /parts/{name}/stl/generate`
answers `503`. `generate-stl --openscad-path` checks the OpenSCAD it names
instead. Gridfinity sets it: `gridfinity-rebuilt-openscad` does not
evaluate on OpenSCAD 2021.01.

`scad_overrides(params)` is what `-D` receives for validated parameters,
for a part whose model does not name things as its SCAD does. Gridfinity's
`hole_options` is one nested model in Python and six booleans in
`gridfinity-rebuilt-bins.scad`, so it translates, and only the overrides
given: a default build passes no `-D`, which is why its model's defaults
are the file's own. The params sidecar records the parameters, not the
translation. `tests/test_parameter_coverage.py` fails, for every part, when
a name it emits is not a top-level variable of the file or a default is not
the file's own.

`geometry(params)` is the part built in Python, for a part whose source is
code. When it returns an object, every build renders that object's SCAD
from a scratch file, with no `-D`; `apothecary parts render NAME -o FILE`
writes that SCAD; and the STL goes stale when the part's code changes. The
SCAD file stays as the geometry at the default parameters, for a reader and
the registry. The snowplow is one: `SnowplowPart.geometry` returns
`snowplow_assembly(...)`, `apothecary parts render rc.snowplow -o
parts/rc/snowplow/snowplow.scad` rewrites the file, and
`tests/test_snowplow_part.py` fails when the two differ. A parameter of
such a part lives in `Params` and in the code;
`tests/test_parameter_coverage.py` fails on one that leaves the generated
SCAD unchanged.

## Checking a part

```bash
uv run apothecary parts list                 # found, and by which module
uv run apothecary parts info my_part         # metadata, bounds, readme, stl_params
uv run apothecary parts generate-stl my_part # build the STL the viewer serves
uv run apothecary parts verify my_part       # declared bounds against the rendered geometry
uv run apothecary parts checklist my_part    # ready to print and check against a real one?
uv run apothecary parts render my_part -o include.scad   # an include stub to use it from SCAD
```

`verify` renders to a temporary file, measures the real bounding box and
compares it per axis with what `get_bounds` declares; it exits non-zero on
drift beyond `--tolerance`. `--all` sweeps every part that declares bounds
and reports the ones that declare none as skipped, not passed. `checklist`
adds the print settings, contested dimensions and black boxes, and exits
non-zero when anything blocks a print.

`tests/test_parts_wrappers.py` fails when a part under `parts/` has neither a
wrapper nor a sidecar.
