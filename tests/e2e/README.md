# Browser tests

Playwright tests of the viewer -- the Bench, a board's Machine, the camera and
the pictures -- and the walkthrough pages they write. Chromium once per machine:

```bash
uv run playwright install chromium
```

That installs the headless shell most tests run in and, beside it, full
Chromium: `test_first_camera.py` runs in that one (Playwright's `chromium`
channel), where the browser's own camera prompt stands, and skips, saying so,
when it is missing.

## Running them

```bash
uv run pytest tests/e2e --start-server          # the browser suite
uv run pytest tests/e2e/test_viewer.py --start-server -k minimap
uv run pytest tests/e2e/test_window_manager.py --start-server   # the window manager alone: no server is started
uv run apothecary test all                       # unit, walkthrough and browser tests together
uv run apothecary test all --workers 2 -k part   # the browser part on two workers, both parts narrowed to `part`
```

A browser test runs only against a server of its own (`--start-server`) or one
named on purpose (`--base-url`). With neither, `pytest` skips the browser tests,
saying which to pass: a server that happens to be listening -- a person's own
`apothecary serve`, holding their state and their pinned boards -- is never
used, and there is no port the suite falls back to. A `--base-url` that does
not answer `/health` stops the run.

| Flag | What it does |
|---|---|
| `--start-server` | Starts one server for the session, on `--server-port` if given, else on a free port. It runs the scripted `arduino-cli` from `tests/firmware_helpers.py` and the simulated printer mid-print, and none of the person's own tools: `ESPTOOL`, `CARGO`, `ESPFLASH` and `APOTHECARY_ORCASLICER` are `none` unless a module names scripted ones. Its tools dir, firmware state and render cache (`APOTHECARY_CACHE_DIR`, so a part's variants too) are temp folders of its own, and so are its pictures unless `APOTHECARY_PICTURE_ROOT` names a folder; a variant it saves goes to a bare clone of this checkout (`APOTHECARY_VARIANTS_REPO`), never the checkout's own refs. No test opens a real serial port, reads `~/.apothecary`, or sees a real board. |
| `--base-url URL` | Uses a server you started yourself for the tests instead. Tests that show the server a picture skip unless `APOTHECARY_PICTURE_ROOT` names the folder that server reads. The Bench's and the Machines' tests expect the scripted toolchain, so they fail against a real one. |
| `--slow` | Also runs tests marked `slow`: full renders and accuracy benches. |
| `--generate-docs` | Runs the tests marked `docs`, which skip without it, and turns on their `doc_recorder` screenshots (below). Pass it through `apothecary docs generate`, not by hand. |
| `--step N` | With `--base-url` naming the demo (`apothecary serve --demo`): a step-through test (`test_steps_*.py`) runs only its step N, on the demo, in the visible Chromium answering DevTools at 127.0.0.1:9222 (or the address `APOTHECARY_WALK_DEVTOOLS` names), in its tab named `apothecary-walk`, and leaves the tab there, its picture in `.cache/walk/<loop>-step-N.png`. Each step first checks that the tab is where the step before leaves it, and does nothing otherwise. Without `--step` the test runs every step on a server of its own. What they share is `stepping.py`. |
| `--headed`, `--slowmo 500`, `--tracing on` | pytest-playwright's own flags, for debugging. Open a trace with `uv run playwright show-trace test-results/<test>/trace.zip`. |

Every server comes from one factory, the `start_server` fixture in
`conftest.py`, on a free port with state of its own. A module whose tests change
what a server holds -- a pin, an armed latch, a flash, a print, a saved
variant -- or need a bench of their own asks it for servers of its own, so what
they do stays off the session's server (`grep -l start_server
tests/e2e/test_*.py` lists them); `test_docs_bench_walkthrough.py` asks for one
whose picture folder holds only what its page puts there; and each loop's
module for the bench its loop needs:
`test_picture_to_print.py` the simulated printer idle and pinned to printer_1's
mainboard with a scripted OrcaSlicer, `test_part_loop.py` an OpenSCAD that
refuses one size, `test_scad_loop.py` this machine's OpenSCAD, and
`test_the_firmware_loop.py` scripted arduino-cli, cargo and espflash around one
simulated devkit; `test_the_demo.py` runs `serve --demo` itself, with a guard that
logs any serial port it touches to the file `APOTHECARY_TEST_SERIAL_GUARD` names, and
fails on any. Every other module uses the session's server, which lives
for the whole run: take back what a test pins, places or adds, or the tests
after it see it.

## Running in parallel

A file's tests run in order and on one server: the walkthroughs and the ring build
on the steps before them. So parallel runs keep files whole. `-n auto --dist
loadfile` gives each worker its own server on a free port (`--server-port` is
refused with `-n`). `--shard K/N` runs the K-th of N shards, files placed
heaviest first onto the lightest shard by `durations.json`; CI runs three, at a version tag. A
file missing from `durations.json` counts as the average test for each of its
tests. `--record-durations` writes a run's times into it -- each file run replaces
its entries, the rest are kept -- so when the shards drift apart, `uv run
apothecary test all --record-durations` (on as many workers as you like) brings it
up to date.

## What each layer holds

The suite is layered so that a change is held once, by the layer it belongs to,
and a feature's test does not break when the layout around it changes:

| Layer | What it holds | Runs in |
|---|---|---|
| Unit tests (`tests/`) | The registry of focused systems (`test_systems.py`), the ring, the census, the docs | `uv run pytest` |
| The window manager (`test_window_manager.py`, marked `windows`) | `panels.js` and `systems.js` on a page of their own, served from the checkout by the browser's routing, with windows made up for each case: where a window opens, views, what a browser remembers, a window's life, systems from a registry, a stack's +. No server, no world | `apothecary test run`, and every browser run |
| Focused systems (`test_focused_systems.py`) | Every system the registry names, in the viewer, parameterized over the registry: it opens its main window alone, each section shows its part, a ring verb opens the section it acts on, its view lays everything out, a reload keeps or forgets it | the browser suite |
| Features and loops (the rest) | What a person does with a part, a board, a picture, end to end, and the walkthrough pages and pictures the loops write | the browser suite |

Four rules keep it so:

- **A feature's test asserts what the feature does, not where a window stands.**
  It opens what it needs through the shared helpers -- `windows.py` (a window, a
  view, ⊞ Windows, a board's Machine laid out once its kind is known),
  `rings.py` (a ring's cells, from a row or the world), `part_editing.py`
  (Part › Edit in the Part view, a parameter, the code), `garage.py` (the viewer
  on garage, a row selected, the status line, a picture pinned, the fake camera's
  drawing, Find shapes and Make), `boards.py` (the simulated boards' ports, the
  sketches, a task's end), and `../views_helpers.py` (the stated picture, shared
  with the unit tests) -- and leaves where a window opens to the window manager's
  tests. A walk, whose pictures show what a person pressed, lays a view out from
  the ring (`by_hand=True`).
- **A test module shares nothing by being imported.** A helper or a fixture two
  files use lives in one of those modules or in a conftest, and
  `tests/test_e2e_helpers.py` refuses a test file that keeps its own copy of one,
  or imports another test file.
- **A focused system is held by the registry's test.** One added to
  `apothecary/systems.py` needs a line in each of `test_focused_systems.py`'s
  tables (how it is opened, what each section shows, a verb that opens one), and
  `test_every_system_and_section_has_a_line_here` fails until it has them.
- **A case is a parameter, not a copy.** Where a behaviour has variants -- a
  window's home, a verb and the section it opens, which window a remembered stack
  had in front -- they are one parameterized test, each case named.

## The two recorders

Both are fixtures in `conftest.py`; the recorders themselves are in `doc_capture.py`.

- `walkthrough` writes `walkthrough/01-*.md` and `walkthrough/02-*.md` and
  their screenshots on every run that includes `test_docs_photo_walkthrough.py`
  or `test_docs_bench_walkthrough.py`. Each numbered step is written as the run
  reaches it, after the assertions before it. The page's opening, its notes and
  its list of what it does not show are the test's fixed words: nothing checks
  them against the run, so they are kept true by whoever edits the test. CI, at
  a version tag, fails when a page a run rewrote differs from the committed one
  (`git diff --exit-code -- 'walkthrough/*.md'` in `pytest.yml`), so a page's words carry
  nothing that changes from run to run -- a temporary folder, a time, a count
  that varies -- and a step that would show one names it instead. A screenshot
  is rewritten only when its pixels change; commit the page and pictures when
  they do. What changes on every run whatever the page does -- a time, a
  picture's name made of one -- is blanked (`shows`'s `blank`), and the picture
  is taken once the page has drawn under its blanks, at the size they leave it
  (`doc_capture.picture`), so a picture changes only when the page does. A
  loop's page --
  `walkthrough/03-a-picture-to-a-print.md` from `test_picture_to_print.py`,
  `walkthrough/04-designing-a-part.md` from `test_part_loop.py`,
  `walkthrough/05-firmware.md` from `test_the_firmware_loop.py`,
  `walkthrough/06-editing-a-parts-scad.md` from `test_scad_loop.py` -- is written
  the same way by a test marked `e2e` and not `walkthrough`, which passes
  `browser_suite_only=True` to the fixture: the browser suite writes it,
  `apothecary test run` stays quick, and the page's header and footer say so.
  The fixture fails a run whose marker and flag disagree. A loop's test goes
  round its loop at least twice, through the page's own controls and ring
  cells, asserting what a person sees; a loop that needs hardware runs against
  the scripted tools and the simulated printer, and its real run is a step of
  [the bench checklist](../../docs/bench-checklist.md).
- `doc_recorder` takes screenshots for `docs/generated/`. The tests that use it
  are marked `docs` and skip unless `--generate-docs` is given;
  `apothecary docs generate` runs them that way, on a scripted server of its own.

After the browser tests, CI runs `tests/e2e/picture_drift.py`: a walkthrough
picture the run rewrote that differs from the committed one in more than its
`TOLERANCE` of the pixels is named in a warning, and it never fails the run,
since a person judges a picture against its caption.

Before a screenshot of the viewer, `viewer_ready.settled(page)` waits until the
level's geometry has loaded (`window.fractalViewer.waveDone`), the camera is at
rest, the badges' occlusion is tested where it came to rest, nothing is part
way through an animation, and the canvas has drawn it.
