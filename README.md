# Apothecary

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Apothecary builds 3D-printable things from Python and keeps the parts it has built.

- **Scenes to OpenSCAD.** Pydantic models (`Cube`, `Union`, `Translate`, ...) render to
  OpenSCAD or JSCAD, from Python or from a scene JSON file.
- **A parts library.** Each part is a folder under `parts/`: its SCAD, the parameters and
  bounds it declares, and the STL the `openscad` CLI builds from it.
- **A viewer.** A local FastAPI server and a three.js viewer that zooms through sites,
  assemblies and parts at any depth.
- **Boards and printers.** Sketches kept with their parts are compiled and uploaded to
  Arduinos and ESP32s; a Marlin printer is monitored, and drives its node in the viewer.
- **Photographs into pieces.** A picture becomes named, placed pieces you can build.
- **It stays on this machine.** The server answers this machine only, and the process
  connects nowhere else but to fetch the firmware toolchain (`apothecary/stays_local.py`).

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/). Rendering STLs needs OpenSCAD; nothing
else does. `uv run apothecary openscad install` downloads a development snapshot (Linux
x86_64) from files.openscad.org into `~/.apothecary/tools`, and renders use it, with
Manifold; otherwise the `openscad` CLI on `PATH` is used. `APOTHECARY_OPENSCAD` names
another.

```bash
git clone --recurse-submodules https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync
uv run apothecary check      # packages, three.js, OpenSCAD, the firmware toolchain, the parts
```

A clone made without `--recurse-submodules` has an empty `governance/qm` and no gridfinity
library: run `git submodule update --init --recursive`.

## First commands

```bash
uv run apothecary render --scene-file examples/scene.json -o scene.scad   # a scene to OpenSCAD
uv run apothecary parts list                        # the registered parts
uv run apothecary parts generate-stl datum_core     # one part's STL (needs openscad)
uv run apothecary serve                             # the viewer: http://127.0.0.1:8000/viewer
uv run apothecary problems                          # what is open here, and who can close it
uv run apothecary photo view PICTURE.jpg --width-mm 300   # a picture's pieces, in the viewer
```

In the viewer, a picture is taken from the ring. Select a structure (the bench, say) and
open its ring -- `m`, or a right-click on it -- then Camera › Pin here › Allow: the browser
asks once, and with one camera it is pinned there at once. Camera › Look then keeps a frame
and finds its shapes, and Selected says what to do next. Picture › Add on the same ring pins
a picture from disk instead; the floor's verbs are under the canvas ring's Pictures › Floor.

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

- [walkthrough/](walkthrough/01-a-part.md): the executable path through the repository,
  run by `uv run pytest walkthrough`. Start here.
- [docs/README.md](docs/README.md): the guides, plans and records.
- `uv run apothecary --help`, and `--help` on every command: the command reference.
- `/openapi.json` on a running server: the HTTP API. `/docs` serves `docs/` and
  `/walkthrough` serves `walkthrough/`, rendered.
- [CONTRIBUTING.md](CONTRIBUTING.md): the test loop, what CI gates, and how commits are
  written. [CHANGELOG.md](CHANGELOG.md): what changed.

## Troubleshooting

- `apothecary: command not found`: prefix `uv run`, or activate `.venv`
  (`source .venv/bin/activate`; on Windows `.venv\Scripts\activate`).
- An import error after a pull: `uv sync`.
- An empty viewer or a part that will not render: `uv run apothecary check` says what is
  missing.

## License

MIT; see [LICENSE](LICENSE). Each file's licence is recorded for
[REUSE](https://reuse.software/) (`REUSE.toml`, `LICENSES/`).
