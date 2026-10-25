# Apothecary

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Apothecary builds 3D-printable things from Python and keeps the parts it has built.

- **Scenes to OpenSCAD.** Pydantic models (`Cube`, `Union`, `Translate`, ...) render to
  OpenSCAD or JSCAD, from Python or from a scene JSON file
  ([docs/scene-json.md](docs/scene-json.md)).
- **A parts library.** Each part is a folder under `parts/`: its SCAD, the parameters and
  bounds it declares, and the STL the `openscad` CLI builds from it.
- **A viewer.** A local FastAPI server and one page: a three.js world that zooms through
  sites, assemblies and parts at any depth, a rail of panels beside it, and a ring that
  reaches every verb by address. A part's parameters and its SCAD are edited there, applied
  as a variant drawn in its own tab, and saved as a variant kept in git
  ([docs/viewer.md](docs/viewer.md)).
- **Boards and printers.** Sketches kept with their parts, Arduino and Rust, are compiled and
  uploaded to Arduinos and ESP32s, from the command line or the viewer; a Marlin printer is
  monitored, and drives its node in the viewer ([docs/firmware.md](docs/firmware.md)). A part
  or a made piece is sliced for the pinned printer with OrcaSlicer, and a print is a job,
  kept with the part it makes ([docs/slicer.md](docs/slicer.md)).
- **Photographs into pieces.** A picture becomes named, placed pieces you can build.
- **It stays on this machine.** The server answers this machine only, and the process
  connects nowhere else but to fetch its tools: OpenSCAD, the slicer, the firmware
  toolchain, and the crates a Rust sketch builds from (`apothecary/stays_local.py`).

## Start here

[Walkthrough page 00, *Getting started*](walkthrough/00-getting-started.md): install, then

```bash
uv run apothecary check              # what is installed here, and what is missing
uv run apothecary openscad install   # an OpenSCAD with Manifold, before the first serve
uv run apothecary serve --demo       # the viewer, with a simulated printer and board
```

and the four loops through the page -- designing a part, editing its SCAD, a picture to a
print, firmware -- with what each needs. `uv run apothecary --help` ends with the same three
steps.

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/); page 00's first step is the clone and
`uv sync`. A clone made without `--recurse-submodules` has an empty `governance/qm` and no
gridfinity library: run `git submodule update --init --recursive`.

Rendering STLs needs OpenSCAD; nothing else does. Run `uv run apothecary openscad install`
before the first `serve`: it puts a development snapshot with Manifold into the tools
folder, and renders use it. [docs/openscad.md](docs/openscad.md) says what it installs on
each platform, which OpenSCAD a render uses, and what 2021.01, the version most package
managers carry, cannot do.

The rest is optional, each into the same tools folder: the slicer, each firmware
toolchain and the browser the tests drive. Page 00's
[last install section](walkthrough/00-getting-started.md#6-the-installs-only-some-loops-want)
names each.

## First commands

```bash
uv run apothecary serve                             # the viewer: http://127.0.0.1:8000/viewer
```

`serve` keeps its terminal until Ctrl+C; run the rest in another one.

```bash
uv run apothecary render --scene-file examples/scene.json -o scene.scad   # a scene to OpenSCAD
uv run apothecary parts list                        # the registered parts
uv run apothecary parts generate-stl datum_core     # one part's STL (needs openscad)
uv run apothecary problems                          # what is open here, and who can close it
uv run apothecary photo view examples/shapes.png --width-mm 300 --port 8001   # a picture's pieces, in a viewer of its own
```

In the viewer, a camera is a part of the site: Camera › Add here stands one above a
structure, Take picture (`P`) pins its frame where it looks, Picture › Find shapes finds the
shapes in it, and Picture › Make stands one up as a piece to slice and print
([docs/pictures.md](docs/pictures.md); [walkthrough 13](walkthrough/13-a-picture-to-a-print.md)
goes round twice).

From Python:

```python
from apothecary import Cube, Scene, Sphere, Translate, Union, Vector3D

base = Cube(size=Vector3D(x=20, y=20, z=5))
dome = Translate(v=Vector3D(x=10, y=10, z=5), children=[Sphere(r=8)])
print(Scene(name="demo", objects=[Union(children=[base, dome])]).render())
```

STLs are build products and are not committed. `apothecary serve` builds the missing ones
in the background when OpenSCAD is present (`APOTHECARY_SKIP_STL_GENERATION=1` skips that);
`apothecary parts generate-stl --all` builds them all.

## Where next

- [walkthrough/](walkthrough/00-getting-started.md): the executable path through the
  repository, run by `uv run pytest walkthrough`. Start at page 00.
- [docs/README.md](docs/README.md): the guides, plans and records.
- `uv run apothecary --help`, and `--help` on every command: the command reference.
- `/openapi.json` on a running server: the HTTP API. `/docs` serves `docs/` and
  `/walkthrough` serves `walkthrough/`, rendered.
- [CONTRIBUTING.md](CONTRIBUTING.md): the test loop -- `uv run apothecary test run` is the
  ordinary test command -- what CI gates, and how commits are written.
  [CHANGELOG.md](CHANGELOG.md): what changed.

## Troubleshooting

- `apothecary: command not found`: prefix `uv run`, or activate `.venv`
  (`source .venv/bin/activate`; on Windows `.venv\Scripts\activate`).
- An import error after a pull: `uv sync`.
- An empty viewer or a part that will not render: `uv run apothecary check` says what is
  missing.
- A part drawn as a placeholder box: it has no STL yet. `serve` builds the missing ones as it
  starts; an OpenSCAD too old for the part (`check` names it) never will, and
  `apothecary openscad install` puts in one that can.

## License

MIT; see [LICENSE](LICENSE). Each file's licence is recorded for
[REUSE](https://reuse.software/) (`REUSE.toml`, `LICENSES/`).
