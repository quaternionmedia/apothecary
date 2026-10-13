# OpenSCAD

Rendering a part's STL is the one thing that needs OpenSCAD: `apothecary parts
generate-stl`, `parts verify`, a site node's STL, and every check and render the
viewer's part editor and SCAD editor ask for. Everything else -- the scene
models, the API, the viewer, the firmware and the slicer -- runs without it.
OpenSCAD runs on this machine, called by the server or the command line; the
page never runs it ([parts-authoring.md](parts-authoring.md#editing-a-parts-scad-drafts-and-saves-as-variants-in-git)).

## Installing a snapshot

```bash
uv run apothecary openscad install    # the newest development snapshot, with Manifold
uv run apothecary openscad status     # each install, and which one renders use
```

`apothecary openscad install` fetches a development snapshot from
files.openscad.org (on Linux arm64, its source from GitHub) and nowhere else,
through the one tool fetch in `apothecary/stays_local.py`. A snapshot is named
by its date. What an install is depends on this machine's hardware:

| This machine | What an install is |
|---|---|
| Linux x86_64 | The night's AppImage, run as it is. Where there is no FUSE it is extracted and its `AppRun` runs; `--extract` extracts it anyway, so each run starts without mounting it |
| macOS, Intel or Apple Silicon | `OpenSCAD.app`, copied out of the night's disk image, attached read-only with `hdiutil` and detached whatever happened. The app is universal |
| Windows x64 | The night's portable zip, unpacked: no installer, no admin |
| Linux arm64 | No build is published, so it is built here from OpenSCAD's source at the night's date: cmake, headless, with Manifold, `--jobs N` compilers at once. What the build needs is checked first, and anything missing is refused with the `apt install` line that adds it; nothing here runs sudo. The build takes long on a small board |
| Windows on ARM, anything else | Refused: no snapshot is published for it. `APOTHECARY_OPENSCAD` names an OpenSCAD installed another way |

A download is checked against the size its listing gives and the SHA-256
published beside it; the detached `.asc` signature is not checked. Whatever the
platform, what is installed must run and report the date it was asked for
before it is moved into place, and a source build must also have Manifold and
render a cube with it. An install goes under the tools dir,
`~/.apothecary/tools/openscad/<date>/` (or `$APOTHECARY_TOOLS_DIR`), with
`install.json` saying how it was installed, and `current` names the date in
use.

| Flag | |
|---|---|
| `--latest` | The newest snapshot (the default) |
| `--snapshot YYYY.MM.DD` | The snapshot of that date |
| `--min VERSION` | Refuse a snapshot older than this; by default, the highest any part declares |
| `--force` | Download it again even if it is installed |
| `--extract` | Extract the AppImage (Linux x86_64), for the fast start; also for one already installed. `apothecary check` says how much faster each run would start |
| `--jobs N` | Compilers a source build runs at once |

`apothecary openscad status` says, for each install, its platform, how it was
installed, whether it runs natively here, and whether it has Manifold.
`apothecary check` names the OpenSCAD each part renders with.

STLs an older OpenSCAD built are kept: `apothecary parts generate-stl --all
--force` builds them again with the new one. A part the older one could not
build has no STL, and the next `apothecary serve` builds it.

## Which OpenSCAD a render uses

`stl_renderer.find_openscad` takes the first OpenSCAD new enough for the part,
in this order:

1. the one `APOTHECARY_OPENSCAD` names, which is then the only one tried;
2. the snapshot `apothecary openscad install` made current;
3. the `openscad` CLI on `PATH`;
4. other development snapshots: `openscad-nightly` on `PATH`, or one of the
   usual install locations.

A part declares the oldest OpenSCAD that renders it as `openscad_min_version`
([parts-authoring.md](parts-authoring.md#hooks-for-a-part-the-scad-file-does-not-fully-describe)).
With none new enough, the part is skipped by `generate-stl --all`, `verify` and
server startup, a build of it alone is refused, and the reason names the
version needed, every OpenSCAD found, and `apothecary openscad install`.
`generate-stl --openscad-path` checks the OpenSCAD it names instead.

A render uses the Manifold backend (`--backend=manifold`) wherever the
OpenSCAD has it: a snapshot from 2024.09.28 on.

## What OpenSCAD 2021.01 cannot do

2021.01 is the OpenSCAD most package managers carry, and the one CI installs.
With it:

- **Renders are slow.** It renders with CGAL, and has no Manifold.
- **The gridfinity bins do not build.** `gridfinity-rebuilt-openscad` does not
  evaluate on it; the part declares a newer `openscad_min_version`, and the
  viewer's editor says so as it opens, with Apply off from the start.
- **A part with no model has no controls.** It cannot list a SCAD's customizer
  parameters (`--export-format=param`), which a snapshot can
  ([parts-authoring.md](parts-authoring.md#a-part-without-a-model-its-scads-own-parameters)).
- **A mesh it cannot read back into a boolean is dropped from a union, and it
  exits 0.** A render is checked for that (`RenderResult.dropped`), and a site
  node's STL missing its body is refused
  ([geometry-from-elsewhere.md](geometry-from-elsewhere.md#put-it-in-a-site)).

## How many run at once

OpenSCAD runs are queued: `APOTHECARY_OPENSCAD_RUNS` at once, by default two,
or one on a machine with a single core. A render or a check waiting its turn
says it is queued, and how far back; a newer request from the same page for
the same part cancels the older one's run.
