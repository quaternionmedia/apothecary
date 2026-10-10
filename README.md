# Apothecary

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Apothecary builds 3D-printable things from Python and keeps the parts it has built.

- **Scenes to OpenSCAD.** Pydantic models (`Cube`, `Union`, `Translate`, ...) render to
  OpenSCAD or JSCAD, from Python or from a scene JSON file.
- **A parts library.** Each part is a folder under `parts/`: its SCAD, the parameters and
  bounds it declares, and the STL the `openscad` CLI builds from it.
- **A viewer.** A local FastAPI server and one page: a three.js world that zooms through
  sites, assemblies and parts at any depth, with one rail beside it -- **Site** (the
  tree, its problems, its SCAD, every pin and the site's jobs) and **Selected** stacked
  over a strip of tabs, **Pictures**, the **Bench** and a docked **Machine**. The ring
  (`m`, or a right-click) reaches every one of them by address.
- **Boards and printers.** Sketches kept with their parts are compiled and uploaded to
  Arduinos and ESP32s, from the command line or the viewer's Bench; a Marlin printer is
  monitored, and drives its node in the viewer. Each board pinned in the viewer has one
  Machine -- its state, its one log, its controls, a devkit's flashing -- opened from its
  badge, polled once whatever shows it. A print is a job, kept with the part it makes
  and listed in the printer's site.
- **Photographs into pieces.** A picture becomes named, placed pieces you can build.
- **It stays on this machine.** The server answers this machine only, and the process
  connects nowhere else but to fetch its tools, the firmware toolchain and OpenSCAD
  (`apothecary/stays_local.py`).

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/). Rendering STLs needs OpenSCAD; nothing
else does. `uv run apothecary openscad install` puts a development snapshot into
`~/.apothecary/tools`, and renders use it, with Manifold; otherwise the `openscad` CLI on
`PATH` is used. `APOTHECARY_OPENSCAD` names another. What it installs is native to the
machine:

- **Linux x86_64**: the night's AppImage from files.openscad.org; where there is no FUSE,
  the AppImage is extracted and its `AppRun` used.
- **macOS**, Intel and Apple Silicon: `OpenSCAD.app`, copied out of the night's disk image
  (attached read-only with `hdiutil`, then detached). The app is universal.
- **Windows x64**: the night's portable zip, unpacked; no installer, no admin.
- **Linux arm64**: no current build is published, so it is built here from OpenSCAD's
  source at the night's date (cmake, headless, with Manifold; `--jobs N`). What the build
  needs is checked first, and anything missing is refused with the `sudo apt install` line
  that adds it; it never runs sudo itself. The build takes long on a small board.
- **Windows on ARM** is not supported yet; it is a planned item.

`uv run apothecary openscad status` says, for each install, its platform, how it was
installed, whether it runs natively here, and whether it has Manifold.

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

In the viewer, a picture is taken by a camera, a part of the site. Select a structure (the
bench, say) and open its ring -- `m`, or a right-click on it -- then Camera › Add here: a
camera stands above the bench, looking straight down, selected. On the camera's own ring,
Device › Allow asks the browser once, and with one camera it is the camera's device at once.
Take picture -- on its ring, in Selected, or `P` -- keeps a frame that lies on the bench
where the camera looks, as a view, and the bench's Picture › Find shapes finds its shapes;
each step's message names the next. Picture › Make stands a shape up as a piece; its Part ›
Edit adjusts it, and a printer's Machine prints it: Print from here keeps a sliced file and
lists the site's pieces under *makes*, and the print is a job that names the piece
([walkthrough 13](walkthrough/13-a-picture-to-a-print.md) goes round twice). The camera's
turn ring and tilt arc aim it, and Part › Edit sets its numbers. Picture › Add on the
bench's ring pins a picture from disk instead, and Picture › Folder one already in the
picture folder: the seven newest by name, and any other once it is chosen in Pictures, a
tab of the rail beside the world. The floor's verbs are under the canvas ring's Pictures ›
Floor.

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
