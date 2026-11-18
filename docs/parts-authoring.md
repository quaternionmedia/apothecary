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
│   ├── my_part.rest.stl  as it rests, for a part that declares that; git-ignored
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
        tags=["example"],
        readme_path=root / "parts" / "my_part" / "README.md",
        preview_color=Color.from_hex("#3366CC"),
    )


DEFAULT = create(ROOT)
```

`tests/test_docs_site.py` runs this block, so it builds a part as written.
`DEFAULT` is what the CLI, the API and the viewer import. A part with no
parameters passes no `params_model` and states its envelope as
`default_bounds=BoundingBox3D(...)` instead of overriding `get_bounds`.
`rest` ([below](#how-it-rests)), `print_settings` and `contested` are
further `BasePart` fields; [Geometry models](models.md) describes the
types.

## A sidecar instead of a wrapper

A folder whose SCAD has a `part.json` beside it and no Python module is a
*described* part: the sidecar says what the wrapper would (description,
category, tags, colour, rest pose, bounds, provenance). See
[Described parts](geometry-from-elsewhere.md#described-parts);
`apothecary parts import` writes one for a mesh made elsewhere. A described
part has no `Params` model, so its overrides are checked against the SCAD
file's own top-level variables.

## What a part is built from

The universe lays parts out on shells by composition depth
(`apothecary/orbitals.py`). The registry holds no part-to-part relation, so it is
read from the SCAD's `include <...>` and `use <...>` of another registered part's
file and from sites that hold one part inside another (`apothecary/composition.py`).
A part that says `"parts": ["name", ...]` in its `part.json` (or `parts=[...]` in its
wrapper) is built from exactly those, an empty list meaning none; the inference is
then not consulted.

## How it rests

A part's STL is the way up it prints: its SCAD's own render, never turned.
That is what a slice and a download read. A part that stands otherwise in use
declares its rest pose, `rest`: the `-D` definitions that make its SCAD draw it
as it rests. `footpedal.scad` lays the wedge on its button face unless `print`
is false, so its wrapper says `rest={"print": False}`; `fifel.py` says the
same of the fife, which its SCAD stands on its head unless `print` is false;
and `solderfan`, a described part, says it in its `part.json` as
`"rest": {"print": false}`. Each SCAD assigns its `print` after
`/* [Hidden] */`, so neither the part's controls nor OpenSCAD's customizer
offer it, and a `-p` override or a variant's parameters that name it are
refused: set by hand, it would change which way up a slice is. A `rest` that
names a variable its SCAD does not assign would draw nothing, and is refused
when the part loads.

A wrapper or a `part.json` that says `display_rotation` is refused when the
part loads, with what to do instead: lay the part in its SCAD the way up it
prints, and declare `rest` for how it stands in use. A refused described part
is left off the library's grid; `apothecary problems` reports it broken, and
its `--detail` is those words; `apothecary check` says its part.json does not
load; `GET /parts/{name}` answers 500 with the words; `apothecary parts list`
still lists its folder.

The rest pose is the same SCAD, those definitions given beside the part's
parameters, so it follows every parameter and every edit of the SCAD: the
footpedal stands on its base, its button face tilted by `theta`, whatever
`theta` is, and the fife lies on the floor whatever its `bore`. It is rendered
only when it is asked for, into a file of its own: `<name>.rest.stl` beside
the part's STL, with its own freshness and params sidecar, and a variant's
beside the variant in the cache, under the variant's key, kept as long as the
variant is.

The page draws a part as it rests, asking for it with `?pose=rest`:
`GET /parts/{name}/stl` and `/parts/{name}/state`, a variant's
`/parts/{name}/variants/{key}` and its `/stl`, and `POST
/parts/{name}/stl/generate` and a draft's render, whose `stl_url` and
`measured` are then of the rest pose and whose `pose` says so. With no pose,
each answers the print pose. A part that declares no rest pose rests as it
prints, and is answered with its STL either way. The bounds a part declares,
`apothecary parts verify`, the readiness checklist and the slicer stay in the
print pose.

## Presets

A part whose sizes people meet as a handful of named ones keeps them as
**presets**: `presets={"port_32": Preset(params={...}, description="...")}` on
its wrapper (`apothecary.projects.parts.base.Preset`). Each is a set of the
part's parameters over its defaults, and what it stands for in words. A preset
that names a parameter the part has not got, or a value its model refuses, is
refused when the part loads, and a preset's name is letters, digits, `_` and
`-`, since `part@preset.interface` names one. `dust_port` is one part for every
round end of a dust system, a 40 mm hose's and a 32 mm port's among them, so its
sizes are its presets (`hose_40`, `port_32`, `port_25`, `outlet_35`) and not
parts of their own.

A preset is none of the variants below. A saved variant is a SCAD edited in the
page and committed to a ref of its own, outside the tree, and a part built by
Python has none; a cached variant is a render at some parameters, unnamed. A
preset ships with the part, in its description, and a person's own numbers go
over it: a caliper's reading of the real end, typed over the preset it is
nearest.

| | |
|---|---|
| `part.preset(name)` | its parameters, as the model coerces them; `KeyError` naming the presets |
| `apothecary parts info NAME` | lists them |
| `PART@PRESET` | stands a part at one, for `apothecary parts interfaces`, `fit` and `adapter` |
| `GET /parts/{name}/params` | carries them as `presets`, beside the fields |

`tests/test_parameter_coverage.py` counts a parameter of a part built by Python
as live where moving it changes the SCAD it generates or the interfaces it
declares, from its defaults or from one of its presets: a hose's give reaches
every fit and nothing drawn, and a spigot's taper is drawn only on a spigot.

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

Over HTTP, `POST /parts/{name}/stl/generate` with `{"params": {...}}`
renders into a cache of variants instead (`apothecary/projects/parts/variants.py`),
keyed by the SCAD and every file it reads, the parameters, and the OpenSCAD
and backend that render it. Each variant is served at a URL of its own,
`/parts/{name}/variants/{variant}/stl`; the part's own STL is only ever left
holding the defaults from there, and never replaces a variant the command
line put there. So two pages applying different values never share a file,
and going back to the defaults renders nothing. An unknown or invalid
parameter is a `422` with the reason; a render OpenSCAD refuses is a `422`
whose `detail.messages` are its errors and warnings by file and line. The
response carries the bounds the part declares for those parameters and
beside them the bounds of what was rendered, from OpenSCAD's summary where it
writes one, else read off the STL (`measured_from` says which), and whether
the answer is the saved part (`saved`). With `?page=<id>`, a newer request
from the same page for the same part stops the older one's render, which
answers `409`. `GET /parts/{name}/state` reads the params sidecar: what the
part's own STL was rendered with, which is where a page drawing it starts;
`GET /parts/{name}/variants/{variant}` says what made a cached variant, for a
page that has only its key.

### In the page, the text is the truth

A part whose SCAD the page edits takes its values from that text: nothing is
passed to OpenSCAD on the side. Over HTTP, values sent as `params` are
written into the part's own text (its SCAD as saved, which is its default),
and that text renders, as a draft does; a saved variant's SCAD carries its
values, so merging it applies them. The part's `Params` model still checks
each value the text gives -- a range, a type, a whole number -- and `apothecary
problems` and the part's checklist say where a model's default and the SCAD's
value disagree. A part whose SCAD is in a submodule is edited as an overlay
beside it: the include of the upstream file and the values set after it.

What counts as a value is a **top-level assignment**, read as OpenSCAD's
customizer reads one: a name, `=`, a value and `;` at the outermost level,
outside every module, function, comment and string. Before the first
`module` or `function` and outside `/* [Hidden] */` it is a parameter, which
gets a control. Its value is a literal (a number, a string, `true`, `false`,
`undef`, a vector of literals) or an expression, which is computed: the check
asks OpenSCAD for its value. A `//` comment after its `;` on its line may
carry the customizer's range (`[10:100]`, `[1:0.5:20]`), options or a unit
word; a comment line just above is its caption. A control writes only the
value's span, so the name, the spacing and the comment stay. The full
grammar, offsets and all, is the docstring of
`apothecary/projects/parts/assignments.py`, which the page follows too.

### Adding a parameter

Two places, kept in step: a top-level variable in the SCAD file (what `-p`
reaches as `-D`) and a field on the wrapper's `Params` (what validates and
documents it). `tests/test_parameter_coverage.py` fails on a field with no
SCAD variable behind it; `apothecary parts verify` fails when the two
disagree about size. A field's unit is declared on it,
`json_schema_extra={"unit": "mm"}`, as a customizer parameter's is by its
comment's unit word; the viewer shows a unit only where one is declared.

### A part without a model: its SCAD's own parameters

A part with no `Params` model still has controls in the viewer where the
OpenSCAD it renders with can list its SCAD's parameters: a development
snapshot can (`--export-format=param`), 2021.01 cannot. `GET
/parts/{name}/params` then answers what OpenSCAD's customizer lists
(`apothecary/projects/parts/customizer.py`, `source: "customizer"`): its
parameters as [above](#in-the-page-the-text-is-the-truth), each typed by its
value and its comment -- `width = 34; // [10:100]` a number with its range,
`hollow = true;` a tick, `label = "hi";` a string, `shape = "round"; //
[round, square]` a choice, `size = [10, 20];` a vector -- and grouped by a
`/* [Size] */` above them. Where there is nothing to list, the
`404`'s `detail` says why, `lists: false` when the OpenSCAD in use cannot
list at all. `POST /parts/{name}/validate` and `.../stl/generate` check a
staged set against the same list: a number as a number, a choice one of its
options, a range or length the SCAD states kept to; a value the SCAD itself
assigns is no override.

### Editing a part's SCAD: drafts, and saves as variants in git

A draft is a part's SCAD as edited in the page. `POST
/parts/{name}/draft/check` with `{scad, params}` writes it to a hidden file
of its own beside the part (`.<stem>.<random>.draft.scad`, ignored by git,
never a part), so its includes resolve, has OpenSCAD evaluate it without
rendering, and removes it: the answer is what OpenSCAD said, by line of the
draft and naming the part's SCAD, the fields to build controls from (the
model's, or the draft's own as OpenSCAD lists them), and the staged
parameters checked against them. `POST /parts/{name}/draft/render` renders it
into the cache of variants, answered as generate answers, `draft` the
sha256 of its text; the cache keeps the text, at
`/parts/{name}/variants/{variant}/scad`. The part's own SCAD and STL are
never written.

Saving is a variant in git: `POST /parts/{name}/saved` with `{name, scad,
params}` commits the SCAD, `params` written into it as its assignments, to
`refs/apothecary/variants/<part>/<name>` in the repository that tracks the
part, with git's plumbing alone
(`apothecary/projects/parts/saved.py`), so the working tree, the index and
the checked-out branch are never touched. The commit's author is the git
identity of the checkout, and its parent is the variant's last save or
`HEAD`. `GET /parts/{name}/saved` lists a part's variants from those refs
(`?diff=true`: with what each changes against the part's SCAD), and `GET
/parts/{name}/saved/{variant}` reads one with its SCAD. Making one the
part's source is a merge you do: `git merge
refs/apothecary/variants/<part>/<name>`. Keeping a variant's values in the
part's own description instead (`params_in: "part-description"`) is a stub: a
save that asks for it is refused, saying what it would do.
`APOTHECARY_VARIANTS_REPO` names another repository to save into, a
clone of the checkout; the browser suite's servers save into one of their own.

In the viewer, the part's SCAD window holds its SCAD
([viewer.md](viewer.md#the-scad-editor) says how it checks, renders and saves,
and its keys); walkthrough 06 goes round it.

A part built by Python geometry (the snowplow) has no SCAD of its own to
edit: `GET /parts/{name}/scad` answers the SCAD its geometry generates
(`X-Part-Scad: generated`), and a draft or a save of it is a `403`.

Every check and render is OpenSCAD run by the server on this machine; the
page never runs it. OpenSCAD built to WebAssembly would duplicate the server,
carry GPLv3 object code into the page, and need `wasm-unsafe-eval`, which the
page's Content-Security-Policy (`apothecary/stays_local.py`) does not allow.

## Hooks for a part the SCAD file does not fully describe

Most parts need none of these. Each is a `BasePart` field or method a
wrapper sets or overrides, and every build path (`generate-stl`, `verify`,
the viewer's `POST /parts/{name}/stl/generate`, server startup) goes
through them.

`openscad_min_version` is the oldest OpenSCAD that renders the part, as
`openscad --version` numbers it (`"2021.08.24"`). The first OpenSCAD new
enough is used, in the order [openscad.md](openscad.md#which-openscad-a-render-uses)
gives (`stl_renderer.find_openscad`). With none, `can_generate_stl()` names
the version needed, every OpenSCAD it found, and `apothecary openscad
install`.
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
`snowplow_assembly(...)`, `apothecary parts render snowplow -o
parts/rc/snowplow/snowplow.scad` rewrites the file, and
`tests/test_snowplow_part.py` fails when the two differ. A parameter of
such a part lives in `Params` and in the code;
`tests/test_parameter_coverage.py` fails on one that leaves the generated
SCAD unchanged.

`interfaces(params)` is where another part meets this one: a list of
`apothecary.models.interfaces` objects (a spigot, a socket, a bolt hole, a
slot), each named and given in the part's own frame by a position and a normal
pointing out of the part. A part nothing meets returns none, the default. A part
built from a `fittings.Profile` returns the profile's, so they come from the same
numbers as its solid; `hose_adapter` and `dust_port` are two. A described part lists them under
`interfaces` in its `part.json`. `apothecary parts verify` reads each round one
on the render and fails on drift, `apothecary parts interfaces NAME` lists them,
and [connections.md](connections.md) says how two fit and how parts are placed by
them.

## A piece made from a picture is a part

A shape a finder saw in a picture and a person made into a piece
(`Picture › Make` on the ring; `apothecary/vision/views.py`) has no file
and no wrapper, and is a part all the same: `MadePart`
(`apothecary/vision/piece.py`) wraps its record as a `BasePart`, and the
viewer edits it in the one editor it edits any part in, on either: its
Parameters, which `Part › Edit` opens, and its SCAD window, which
`Part › View › SCAD` opens.

What makes that possible is one parameter contract, in core
(`apothecary/projects/parts/params.py`): `params_spec(part)` reads a
`ParamsSpec` -- each field's type, default, range, pattern and the
candidates its sources disagree about -- off `params_model`, `contested`
and `get_bounds`, and `validate_staged(part, params)` answers a
`Validation`. `GET /parts/{name}/params` and `POST /parts/{name}/validate`
return them for a part from this folder; `GET /sites/{s}/made/{piece}/params`
and `POST /sites/{s}/made/{piece}/validate` return the same shapes for a
made piece, and `PUT /sites/{s}/made/{piece}` with `{params}` is its Apply.

The hooks a made piece implements are the ones above. Its `params_model` is
a `PieceParams` built for the record: the word it is made as, drawn from
the vocabulary, and its three sides in millimetres, each defaulting to what
the piece is now. Its `contested` is its provenance: the thickness always
carries the guess (a picture from above cannot see it), and the sides the
finder measured are offered whenever the piece no longer has them, so after
a person states a size, or after the view is re-scaled, the found number is
one click away, and taking it reads the piece as found again. Its
`geometry` is what `piece_from_shape` builds for the parameters, rendered
through the same seam as the snowplow's; its `get_bounds` is the box it
occupies as built, turned as its shape was seen. `validate_overrides` is
`BasePart`'s. Re-sizing a view (`PUT /sites/{s}/views/{id}/scale`) rebuilds
every piece made from it whose sides no person stated, and lays it on its
shape again only if it still stands where it was made.

## Checking a part

```bash
uv run apothecary parts list                 # found, by which module, and whether it loads
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
