# Changelog

One line per change, each with a link to where it is described. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `apothecary parts import` brings an STL or OBJ in as a part. ([doc](docs/geometry-from-elsewhere.md))
- A `part.json` beside a part's SCAD stands in for a Python wrapper. ([doc](docs/geometry-from-elsewhere.md))
- The garage bench draws Ender 3s and real boards, from their makers' drawings. ([doc](docs/geometry-from-elsewhere.md))
- Personal data stays on the device: only the toolchain fetch leaves this machine. ([code](apothecary/stays_local.py))
- The ring menu seats options on nine keypad cells; the digits pressed are the address. ([code](apothecary/menu.py))
- `apothecary firmware` installs arduino-cli, and compiles and uploads sketches kept with parts. ([doc](docs/firmware.md))
- A board's identity, the sketch last flashed to it, and the sketch it announces over serial. ([doc](docs/firmware.md))
- A live serial log, on the firmware page and over the viewer. ([doc](docs/firmware.md))
- `apothecary firmware printer` identifies and polls a G-code printer. ([doc](docs/firmware.md))
- A printer pinned to its scene node sets that node's status from its polls. ([doc](docs/firmware.md))
- The viewer's Device section pins, queries, polls and watches a board. ([doc](docs/firmware.md))
- The printer monitor at `/firmware/monitor`: status, temperatures and the port's comms log. ([doc](docs/firmware.md))
- Latched printer control: refused unless armed, held to fixed caps; E-STOP always goes. ([doc](docs/firmware.md))
- Print from here: a kept G-code file, checked, then streamed one line per `ok`. ([doc](docs/firmware.md))
- Bed leveling: the stored mesh read or the bed probed, and each reading kept and drawn. ([doc](docs/firmware.md))
- The board drawn in its printer, with a nozzle marker that follows each poll. ([doc](docs/firmware.md))
- `parts/esp32_blink`: a sketch that blinks GPIO 2 and announces itself over serial. ([doc](docs/firmware.md))
- `apothecary photo` turns a picture into named, placed pieces. ([page](walkthrough/11-photographs-into-pieces.md))
- The Camera & pictures panel: capture, look, place a camera, gather. ([page](walkthrough/12-the-bench-as-it-is.md))
- Pictures added and forgotten there; pins and cameras listed and undone. ([page](walkthrough/12-the-bench-as-it-is.md))
- Badges and printer marks anchored to their machines in the 3D view. ([plan](docs/plans/one-screen-2026-09-20.md))
- Panels in front of the world, which close, collapse, float and dock. ([plan](docs/plans/one-screen-2026-09-20.md))
- The panel rail resizes, hides on `~`, and moves to the other side. ([plan](docs/plans/one-screen-2026-09-20.md))
- The machine popup: the printer monitor, tethered to its printer. ([plan](docs/plans/one-screen-2026-09-20.md))
- `/docs` and `/walkthrough` serve this repository's Markdown, rendered. ([docs](docs/README.md))
- `apothecary docs generate` writes screenshots, GIFs and recordings from the browser tests. ([docs](docs/README.md))
- `apothecary census` counts the controls a page puts on screen. ([code](apothecary/census.py))
- `problems`, `solutions`, `preflight`, `release`, `parts checklist` and `parts verify`. ([pages](docs/README.md))
- Gridfinity bins, from the vendored gridfinity-rebuilt-openscad. ([part](parts/gridfinity/README.md))
- A part can name its STL path and the OpenSCAD it needs. ([code](apothecary/projects/parts/stl_renderer.py))
- The `Assembly` model: sites, structures and parts as one recursive tree. ([code](apothecary/hierarchy.py))
- The fractal zoom viewer: any site's tree at any depth. ([page](walkthrough/04-serving-it.md))
- Real geometry in the viewer: exact primitives, and nodes as STLs. ([viewer](templates/fractal_viewer.html.j2))
- The garage: walls, utility stubs, shelving and a CNC router stub. ([code](apothecary/example_hierarchy.py))
- Nodes coloured by subsystem, a 50 mm drag snap, and a Contents tree. ([viewer](templates/fractal_viewer.html.j2))
- `apothecary parts elephant-walk` lays every part out in a row, in `.cache/`. ([code](apothecary/cli/parts.py))
- STLs built by the OpenSCAD CLI, from the CLI and the API. ([code](apothecary/projects/parts/stl_renderer.py))
- Browser tests with Playwright. ([tests](tests/e2e/README.md))
- Looks: a picture pinned at a structure or the floor, its shapes made into pieces there, over the API. ([plan](docs/plans/pictures-in-the-world-2026-09-26.md))
- A look is drawn where it is pinned: the picture as a mat on its structure's top or the floor, its shapes as outlines to click, a camera's frustum looking down onto it, a place badge over each. ([code](apothecary/static/picture_marks.js))
- A structure's ring holds Camera (pin this browser's camera, Live on the mat, Look, Keep, Unpin) and Picture (Add, Folder, Looks, Make, Size, Find, Unpin, Forget); the floor's are under the canvas ring's Pictures › Floor. ([code](apothecary/menu.py))
- A picture dropped on a structure, or pasted, is kept, pinned at its root and found; on empty canvas, at the floor. ([test](tests/e2e/test_the_loop.py))
- Make, Make all, Drop and a made piece's Word are carried out by the server through the ring's intent. ([code](apothecary/routes/menu.py))
- Why this on a piece made from a picture draws its look and a thread to its outline. ([code](apothecary/static/picture_marks.js))
- Selected sizes the drawn look: the picture's width, or a chosen shape's long side; a look's row draws it. ([viewer](templates/fractal_viewer.html.j2))

### Changed

- A camera is pinned at a root structure with a footprint, or the floor, one per host. ([code](apothecary/routes/pictures.py))
- A camera's badge is the place badge: a click selects the structure or the floor, and shows no camera live. ([test](tests/e2e/test_camera.py))
- Forgetting a kept picture unpins its looks; pictures are served at a size and never cached. ([code](apothecary/routes/pictures.py))
- The canvas ring's Camera is Pictures, in the same seat: Add (at the floor), Floor, Purge, Gather. ([code](apothecary/menu.py))
- The camera panel is the pictures and pins panel: every camera and look pinned, every site's, each unpinned from its row. ([code](apothecary/static/widgets/camera.js))
- Kept lists every camera, look and board pinned, every site's, and every kept picture, each taken back from its row without switching the site; the camera panel keeps the gathering. ([code](apothecary/static/widgets/kept.js))

- `/sites/{name}` carries the whole `tree` beside the flat `structures` list. ([code](apothecary/api.py))
- Each part has its own folder, `parts/<name>/<name>.scad`. ([doc](docs/parts-authoring.md))
- The calibration cube is 10 mm by default, its labels cut in. ([part](apothecary/projects/parts/calibration_cube.py))
- `/` and `/viewer` open the fractal viewer on the garage site. ([page](walkthrough/04-serving-it.md))
- `apothecary serve` regenerates `docs/generated/` only when given `--refresh-docs`. ([docs](docs/README.md))
- `apothecary test` is `run [--e2e] [--slow]` and `all [--slow]`, exiting as pytest does. ([doc](CONTRIBUTING.md))
- `apothecary check` exits 1 when a required package is missing. ([readme](README.md))
- `apothecary census` is a report: it lists what it cannot classify and refuses nothing. ([code](apothecary/census.py))
- One ceiling holds the viewer's control count, in place of pinned counts per page. ([test](tests/test_census.py))
- The printer seam has one serial engine, pyserial, beside the simulator. ([doc](docs/firmware.md))
- Playwright is a dev dependency, and ruff is the one lint configuration. ([doc](CONTRIBUTING.md))
- README.md is the entry doc; QUICKSTART.md points at it; CONTRIBUTING.md names the CI gates. ([readme](README.md))
- CI lints with ruff and runs the unit and browser tests as parallel jobs on Python 3.11. ([doc](CONTRIBUTING.md))

### Removed

- `system`, `install`, `submodules`, `testrun`, `dev`, `inventory`: stubs naming what to use. ([code](apothecary/cli/retired.py))
- `test setup-e2e`, `validate-e2e` and `run-e2e`, also stubs. ([code](apothecary/cli/testing.py))
- The JSCAD viewer's install step and `package.json`; no route served it. ([code](apothecary/cli/server.py))
- `/parts/random`, `/parts/{name}/jscad`, `/parts/{name}/files`, `/openscad/status`. ([code](apothecary/api.py))
- `/problems`, `/solutions`, `/spaces` and `/firmware/printers/controls`. ([code](apothecary/spaces.py))
- `census --typed-only` and the hand-kept workflows table it printed. ([code](apothecary/census.py))
- The ring's Get shape and Word wedges, and its selection and edge contexts. ([code](apothecary/menu.py))
- `elephant_walk` as a registered part; the preview is written to `.cache/`. ([code](apothecary/cli/parts.py))
- `PartFiles`, the revision-graph prototype, and the uncalled parts of `apothecary.models`. ([doc](docs/models.md))
- The stdlib termios serial engine. ([doc](docs/firmware.md))
- The tutorial, the library-expansion spec and the finished plans; git keeps them. ([docs](docs/README.md))
- The standalone parts browser and Site/Structure viewer. ([viewer](templates/fractal_viewer.html.j2))
- Legacy JSCAD viewer endpoints and three orphaned modules. ([code](apothecary/api.py))
- `E2E_SETUP.md`; the browser tests are described beside them. ([tests](tests/e2e/README.md))
- The camera panel's camera, capture, Look, placement and Open as one; no verb opens another site. ([code](apothecary/static/widgets/camera.js))

### Fixed

- Camera › Pin here › Allow pins the one camera the browser names at once and names Look; with several it reopens the ring at Pin here; a refusal says what to do. ([test](tests/e2e/test_first_camera.py))
- A camera allowed for the site in the address bar is named under Pin here without a reload. ([code](apothecary/static/pictures.js))
- Selected names the ring path that takes or adds a picture at a host or the floor, and what Look, Live and Keep do once a camera is pinned. ([viewer](templates/fractal_viewer.html.j2))
- A piece moved with the gizmo keeps its new place when let go. ([code](templates/fractal_viewer.html.j2))
- A placed camera's mark is hidden while its piece is out of view. ([page](walkthrough/12-the-bench-as-it-is.md))
- A piece from a picture shows its provenance in Selected, and an unsized one no printer status. ([page](walkthrough/11-photographs-into-pieces.md))
- The camera panel's messages are said once, in the status bar, refusals as errors. ([code](apothecary/static/widgets/camera.js))
- A camera's badge selects its piece, and a first click shows this browser's camera. ([test](tests/e2e/test_camera.py))
- Closing a printer's port keeps DTR up, so the next open does not reboot the board. ([doc](docs/firmware.md))
- A pin follows its board when the kernel renumbers the port. ([doc](docs/firmware.md))
- The board view places its printer once, not offset twice. ([code](apothecary/static/board_view.js))
- A node's world position accumulates down the whole tree, not one level. ([code](apothecary/hierarchy.py))
- Framing uses all three axes, and the grid sizes to what is in view. ([viewer](templates/fractal_viewer.html.j2))
- A loaded STL is no longer drawn turned 90 degrees. ([viewer](templates/fractal_viewer.html.j2))
- Moving a node no longer rescales every real-geometry mesh on screen. ([viewer](templates/fractal_viewer.html.j2))
- The viewer loads without console errors. ([tests](tests/e2e/README.md))
- `.gitignore` no longer lists the tracked `parts/` folder. ([file](.gitignore))

## [0.1.0] - 2026-01-02

### Added

- Primitives, booleans and transforms as Pydantic models, rendered by a `Scene`. ([doc](docs/scene-json.md))
- A FastAPI server, Jinja2 templates, and `render`, `templategenerate`, `parts`, `serve`. ([doc](templates/README.md))
- The parts registry, with wrappers. ([doc](docs/parts-authoring.md))
- Example parts: parametric star, V-slot, dryer knob, solder fan mount. ([parts](parts/README.md))
