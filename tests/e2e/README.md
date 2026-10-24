# Browser tests

Playwright tests of the viewer, the firmware and printer pages, the camera
panel, and the two walkthrough pages. Chromium once per machine:

```bash
uv run playwright install chromium
```

## Running them

```bash
uv run pytest tests/e2e --start-server          # the browser suite
uv run pytest tests/e2e/test_viewer.py --start-server -k minimap
uv run apothecary test run --e2e                 # unit, walkthrough and browser tests together
```

Without a server, `pytest` skips the browser tests with a note saying so.

| Flag | What it does |
|---|---|
| `--start-server` | Starts one server for the session, on `--server-port` if given, else on a free port. It runs the scripted `arduino-cli` from `tests/firmware_helpers.py` and the simulated printer, and keeps its firmware state in a temp folder, and its pictures too unless `APOTHECARY_PICTURE_ROOT` names a folder. No test opens a real serial port, reads `~/.apothecary`, or sees a real board. |
| `--base-url URL` | Uses a server you started yourself instead. Tests that show the server a picture skip unless `APOTHECARY_PICTURE_ROOT` names the folder that server reads. The firmware-page tests expect the scripted toolchain, so they fail against a real one. |
| `--slow` | Also runs tests marked `slow`: full renders and accuracy benches. |
| `--generate-docs` | Runs the tests marked `docs`, which skip without it, and turns on their `doc_recorder` screenshots (below). Pass it through `apothecary docs generate`, not by hand. |
| `--headed`, `--slowmo 500`, `--tracing on` | pytest-playwright's own flags, for debugging. Open a trace with `uv run playwright show-trace test-results/<test>/trace.zip`. |

Every server comes from one factory, the `start_server` fixture in
`conftest.py`, on a free port with state of its own. `test_printer_ui.py` and
`test_ring.py` ask it for servers of their own, so what they pin, arm and print
stays off the session's server. Every other module uses that one, which lives
for the whole run: take back what a test pins, places or adds, or the tests
after it see it.

## The two recorders

Both are fixtures in `conftest.py`; the recorders themselves are in `doc_capture.py`.

- `walkthrough` writes `walkthrough/11-*.md` and `walkthrough/12-*.md` and
  their screenshots on every run that includes `test_docs_photo_walkthrough.py`
  or `test_docs_bench_walkthrough.py`. Each sentence is emitted after the
  assertion behind it. A screenshot is rewritten only when its pixels change;
  commit the page and pictures when they do.
- `doc_recorder` takes screenshots for `docs/generated/`. The tests that use it
  are marked `docs` and skip unless `--generate-docs` is given;
  `apothecary docs generate` runs them that way, on a scripted server of its own.

Before a screenshot of the viewer, `viewer_ready.settled(page)` waits until the
level's geometry has loaded and the canvas has drawn it. Install
`viewer_ready.WAVE_DONE` with `page.add_init_script` before the page loads.
