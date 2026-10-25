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
uv run apothecary test all                       # unit, walkthrough and browser tests together
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
simulated devkit. Every other module uses the session's server, which lives
for the whole run: take back what a test pins, places or adds, or the tests
after it see it.

## Running in parallel

A file's tests run in order and on one server: the walkthroughs and the ring build
on the steps before them. So parallel runs keep files whole. `-n auto --dist
loadfile` gives each worker its own server on a free port (`--server-port` is
refused with `-n`). `--shard K/N` runs the K-th of N shards, files placed
heaviest first onto the lightest shard by `durations.json`; CI runs three. A
file missing from `durations.json` counts as the average test for each of its
tests; refresh the file from a serial run's `--durations=0` when the shards
drift apart.

## The two recorders

Both are fixtures in `conftest.py`; the recorders themselves are in `doc_capture.py`.

- `walkthrough` writes `walkthrough/11-*.md` and `walkthrough/12-*.md` and
  their screenshots on every run that includes `test_docs_photo_walkthrough.py`
  or `test_docs_bench_walkthrough.py`. Each sentence is emitted after the
  assertion behind it. A screenshot is rewritten only when its pixels change;
  commit the page and pictures when they do. What changes on every run whatever
  the page does -- a time, a picture's name made of one -- is blanked (`shows`'s
  `blank`), so a picture changes only when the page does. A loop's page --
  `walkthrough/13-a-picture-to-a-print.md` from `test_picture_to_print.py`,
  `walkthrough/14-designing-a-part.md` from `test_part_loop.py`,
  `walkthrough/15-firmware.md` from `test_the_firmware_loop.py`,
  `walkthrough/16-editing-a-parts-scad.md` from `test_scad_loop.py` -- is written
  the same way by a test marked `e2e` and not `walkthrough`, which passes
  `browser_suite_only=True` to the fixture: the browser suite writes it,
  `apothecary test run` stays quick, and the page's header and footer say so.
  The fixture fails a run whose marker and flag disagree.
- `doc_recorder` takes screenshots for `docs/generated/`. The tests that use it
  are marked `docs` and skip unless `--generate-docs` is given;
  `apothecary docs generate` runs them that way, on a scripted server of its own.

Before a screenshot of the viewer, `viewer_ready.settled(page)` waits until the
level's geometry has loaded (`window.fractalViewer.waveDone`), the camera is at
rest, the badges' occlusion is tested where it came to rest, nothing is part
way through an animation, and the canvas has drawn it.
