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
  sites, assemblies and parts at any depth, its panels as windows beside it, and a ring that
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

## What it does, and how to see it

Each row is one thing the code does, where to see it under `uv run apothecary serve --demo`
(the page at `http://127.0.0.1:8000/viewer`, unless the row gives a command), the tests that
hold it (paths under `tests/`), and the walkthrough page its run writes or its doctests
check. A review walks these rows on the running demo, on the whole codebase at once:
`uv run apothecary test all` runs every test named here, and
`tests/test_readme_map.py` fails when a row names a test or a page that is not there, when a
browser test is in no row, or when a page a run writes is in no row that names the run.

| What it does | See it | Held by | Page |
|---|---|---|---|
| A part designed in the page: a size moved, checked, applied and drawn as a variant | `/viewer/sites/parts_library`, a part's ring, Part › Edit; move a size, Apply | `e2e/test_part_loop.py`, `e2e/test_part_iteration.py`, `e2e/test_part_iteration_answers.py`, `e2e/test_text_tied.py`, `e2e/test_assignments_in_the_page.py`, `e2e/test_nothing_covers_a_control.py`, `test_part_variants.py` | [04](walkthrough/04-designing-a-part.md) |
| A part's SCAD edited in the page, checked as typing stops, saved as a variant in git | Part › Edit, then Part › View › SCAD (or Panels › Windows › Part view); type in its SCAD editor; Part › Save | `e2e/test_scad_loop.py`, `test_saved_variants.py` | [06](walkthrough/06-editing-a-parts-scad.md) |
| A picture to a print: a camera's picture, a piece made from it, sliced for printer_1 and printed | In the garage, the bench's ring: Camera › Add here (or Picture › Add, `examples/pictures/shapes.png`); Picture › Find shapes, Picture › Make; the piece's Slice, then its print | `e2e/test_picture_to_print.py`, `e2e/test_steps_a_picture_to_a_print.py`, `e2e/test_the_loop.py`, `e2e/test_edit_a_made_piece.py`, `e2e/test_picture_in_the_world.py`, `e2e/test_pictures_panel.py`, `test_slicer.py`, `test_made_part.py` | [03](walkthrough/03-a-picture-to-a-print.md) |
| A part that computes itself: the airgap's rotor, stator and windings from its SCAD's assignments, analysed as a field, torque and dynamics model | `/viewer/parts/airgap`, the part's ring, Part › Edit; Panels › Airgap › Airgap beside it, following the text; Panels › Windows › Airgap view, each of its sections a window | `e2e/test_airgap.py`, `test_airgap_part.py`, `test_airgap_metrics.py` | [17](walkthrough/17-a-part-that-computes-itself.md) |
| Firmware: a sketch built, flashed and heard saying hello, in Arduino and in Rust | The Bench, a tab beside Pictures: `esp32_blink`, built and flashed to the devkit; its hello in the devkit's Machine | `e2e/test_the_firmware_loop.py`, `e2e/test_steps_firmware.py`, `e2e/test_bench.py`, `test_firmware_seam.py` | [05](walkthrough/05-firmware.md) |
| A photograph made into named pieces, opened as an arrangement | `uv run apothecary photo view examples/pictures/shapes.png --width-mm 300 --port 8001` | `e2e/test_docs_photo_walkthrough.py`, `e2e/test_gathering_map_in_a_browser.py`, `test_gathering.py`, `test_photo_shapes.py` | [01](walkthrough/01-photographs-into-pieces.md) |
| The bench drawn as it is: Ender 3s, the boards, a camera placed above a piece | The garage's bench; double-click printer_1 for its mainboard; a camera added above the bench | `e2e/test_docs_bench_walkthrough.py`, `e2e/test_camera.py`, `e2e/test_first_camera.py`, `test_geometry_from_elsewhere.py` | [02](walkthrough/02-the-bench-as-it-is.md) |
| One Machine per board: a printer watched, controlled and printed to; a devkit listened to | printer_1's ring, Device › Open: its Machine beside Pictures, then Control and its pad's window; the devkit's Machine, Listen | `e2e/test_one_machine.py`, `e2e/test_steps_one_machine.py`, `e2e/test_printer_ui.py`, `e2e/test_less_on_screen.py`, `e2e/test_docs_printer_monitor.py`, `test_firmware_gcode.py`, `test_jobs.py` | |
| The ring: every verb of what it opens on, at an address; the pointer and the keys | `m` or Ctrl + right-click on a piece; a digit reaches a cell; Settings | `e2e/test_ring.py`, `e2e/test_the_pointer_and_the_keys.py`, `test_menu.py` | |
| The world: site, assembly and part at any depth, drawn as OpenSCAD draws them on a floor grid under the level, the panels as windows of one layout, any window opened from a stack's + or the header's ⊞ Windows, views that lay windows out together, the site's problems and pins | Double-click a piece to step in, Page Up to step out; drag a window's tab or a splitter; a stack's +; ⊞ Windows › Part, Machine or Airgap; the Site panel | `e2e/test_viewer.py`, `e2e/test_viewer_regressions.py`, `e2e/test_world_resize.py`, `e2e/test_render_on_demand.py`, `e2e/test_site_panel.py`, `e2e/test_docs_fractal_viewer.py`, `e2e/test_window_manager.py`, `e2e/test_focused_systems.py`, `test_systems.py` | |
| The demo, and the paths a newcomer takes | The demo's banner; the bare `/viewer` address; the header's Docs | `e2e/test_the_demo.py`, `e2e/test_onboarding.py`, `e2e/test_paths_people_take.py`, `test_demo.py` | [00](walkthrough/00-getting-started.md) |
| The HTTP API, and the docs it serves | `/openapi.json`, `/docs`, `/walkthrough` | `test_api.py`, `test_docs_site.py` | [10](walkthrough/10-serving-it.md) |
| Scenes to OpenSCAD, and the parts library | `uv run apothecary render --scene-file examples/scenes/cube.json -o scene.scad`; `uv run apothecary parts list` | `test_models.py`, `test_scene_render.py`, `test_registry.py` | [07](walkthrough/07-a-part.md), [09](walkthrough/09-an-assembly.md) |
| Whose numbers are whose, which disagree, what is ready to build, and what is open | `uv run apothecary problems` | `test_parameter_coverage.py`, `test_contested_values.py`, `test_readiness.py` | [08](walkthrough/08-fitting.md), [11](walkthrough/11-contested-numbers.md), [12](walkthrough/12-ready-to-build.md), [13](walkthrough/13-status-and-progress.md), [14](walkthrough/14-problems-and-solutions.md) |
| A theatre's shell sized by sliders, its lighting rig drawn in it, its fixtures lit by a console's levels, received and never answered | `/viewer/sites/theatre`; the shell's ring, Part › Edit, its sliders; then `uv run apothecary lighting simulate` ([docs/lighting.md](docs/lighting.md)) | `e2e/test_lighting_overlay.py`, `test_theatre_site.py`, `test_lighting.py`, `test_lighting_routes.py`, `test_console_feedback.py` | |
| It stays on this machine: the server answers this machine only, and the process connects nowhere else | `curl -H 'Host: evil.example' http://127.0.0.1:8000/sites/garage/attached` answers 403; without the header, the garage's cameras and views | `test_stays_local.py` | [02](walkthrough/02-the-bench-as-it-is.md) |
| The checks before a push, and what a project pinning this one may rely on | `uv run --group preflight apothecary preflight` | `test_cli_testing.py`, `test_e2e_shards.py`, `test_browser_suite_is_not_gated.py` | [15](walkthrough/15-preflight.md), [16](walkthrough/16-being-depended-on.md) |

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
uv run apothecary render --scene-file examples/scenes/cube.json -o scene.scad   # a scene to OpenSCAD
uv run apothecary parts list                        # the registered parts
uv run apothecary parts generate-stl datum_core     # one part's STL (needs openscad)
uv run apothecary problems                          # what is open here, and who can close it
uv run apothecary photo view examples/pictures/shapes.png --width-mm 300 --port 8001   # a picture's pieces, in a viewer of its own
```

In the viewer, a camera is a part of the site: Camera › Add here stands one above a
structure, Take picture (`P`) pins its frame where it looks, Picture › Find shapes finds the
shapes in it, and Picture › Make stands one up as a piece to slice and print
([docs/pictures.md](docs/pictures.md); [walkthrough 03](walkthrough/03-a-picture-to-a-print.md)
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
- [examples/README.md](examples/README.md): small things to run, by kind -- scenes, scripts,
  pictures -- and *LLM's own*, the lane for language-model agents' contributions.
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
