# Configuration

Apothecary takes its configuration from environment variables. None is
needed: each has a default.

## APOTHECARY_* variables

| Variable | What it names | Default | More |
|---|---|---|---|
| `APOTHECARY_PORT` | The port `serve` and `photo view` listen on, and the one `slicer slice` and `lighting simulate` find a running server on; `--port` names another for one command | `6283` | [dev-loop.md](dev-loop.md#two-loops-at-once) |
| `APOTHECARY_TOOLS_DIR` | The folder OpenSCAD snapshots, OrcaSlicer and the firmware toolchains are installed in | `~/.apothecary/tools` | [firmware.md](firmware.md#setup), [openscad.md](openscad.md#installing-a-snapshot) |
| `APOTHECARY_STATE_DIR` | The state folder, this account's alone: pinned boards, flash records, cached probes, bed readings, kept prints and slices, jobs, cameras, the family's table and a site's procedures ([family.md](family.md)) | `~/.apothecary` | [firmware.md](firmware.md#setup) |
| `APOTHECARY_CACHE_DIR` | The render cache -- a node's STLs, a part's variants -- and the demo's state folder | `.cache` in the checkout | [parts-authoring.md](parts-authoring.md) |
| `APOTHECARY_PICTURE_ROOT` | The one folder pictures are read from; never a home folder or anything above one, or the state folder | The folder `serve` was started in | [pictures.md](pictures.md#where-pictures-live) |
| `APOTHECARY_MARKS_TABLE` | A fitted table of the thresholds that sort a whiteboard's marks, as `apothecary photo fit --out` writes one | The packaged thresholds | [pictures.md](pictures.md#a-whiteboards-marks) |
| `APOTHECARY_LOOKSATWORDS` | Where `apothecary photo notes --send` sends a whiteboard's words; refused unless it is on this machine | looksatwords' own port on this machine | [pictures.md](pictures.md#a-whiteboards-notes) |
| `APOTHECARY_OPENSCAD` | The OpenSCAD every render uses, and the only one tried | The search order | [openscad.md](openscad.md#which-openscad-a-render-uses) |
| `APOTHECARY_OPENSCAD_RUNS` | How many OpenSCAD runs go at once | Two, or one on a single core | [openscad.md](openscad.md#how-many-run-at-once) |
| `APOTHECARY_SKIP_STL_GENERATION` | `1`, `true` or `yes`: `serve` builds no missing STL as it starts | Unset: it builds them in the background | [README](../README.md) |
| `APOTHECARY_VARIANTS_REPO` | Another repository a saved variant is committed to, a clone of the checkout | The repository that tracks the part | [parts-authoring.md](parts-authoring.md#editing-a-parts-scad-drafts-and-saves-as-variants-in-git) |
| `APOTHECARY_ORCASLICER` | The OrcaSlicer a slice runs; `none` means none | The installed release, else `orca-slicer` on `PATH` | [slicer.md](slicer.md#installing-it) |
| `APOTHECARY_SLICER` | The slicer module a slice uses, when the command or route names none | The printer profile's `slicer` line | [slicer.md](slicer.md#another-slicer) |
| `APOTHECARY_SERIAL_ENGINE` | The byte transport under the printer seam and the Rust module's ports: `pyserial` or `simulated` | `pyserial` | [firmware.md](firmware.md#serial-engines) |
| `APOTHECARY_SIMULATED_PRINTER` | With the simulated engine, `printing` starts the simulated printer part way through a print | Idle | [firmware.md](firmware.md) |
| `APOTHECARY_SIMULATED_PROGRESS` | With the simulated engine, holds a print at this fraction, 0 to 1, so pictures of it are the same on every run | The print goes round | `tests/e2e/README.md` |
| `APOTHECARY_SIMULATED_SPEED` | Multiplies the simulated printer's every dwell (`G4`): 1 is real time, 0 skips them | 1 | |
| `APOTHECARY_SIMULATED_DEVKIT` | With the simulated engine, the ports the Rust module finds, each a pretend devkit (comma-separated) | None | [firmware.md](firmware.md#setup) |
| `APOTHECARY_SIMULATED_DECK` | With the simulated engine, the Stream Deck + decks found, each a pretend deck that keeps the images it is sent and hears the events it is given (comma-separated) | None | [stream-deck.md](stream-deck.md#simulated) |
| `APOTHECARY_DECK_CONTROL` | `1`, `true`, `yes` or `on`: the server starts the Stream Deck + layout (its knobs jog the machines) on every deck found at start; a real deck is opened by it, which takes it from any other program. Unset, a layout is started by `POST /firmware/decks/{id}/control` alone. The demo sets it | Unset | [stream-deck.md](stream-deck.md#the-controller) |
| `APOTHECARY_SIMULATED_ROUTER` | With the simulated engine, the ports that answer as the simulated GRBL router rather than the simulated printer (comma-separated) | None | [cnc.md](cnc.md#simulated) |
| `APOTHECARY_SIMULATED_ROUTER_STATE` | `alarm` starts the simulated router as a real one powers up with homing enabled, in alarm until homed | Idle, the tool over the middle of the table | [cnc.md](cnc.md#simulated) |
| `APOTHECARY_THEATRE_RIG` | The folder of a console's two exports (`patches.csv`, `fixture-parameters.csv`) the theatre site's rig is read from | `examples/theatre-rig/`, a made-up rig | [lighting.md](lighting.md#the-rig-and-another-in-its-place) |
| `APOTHECARY_CONSOLE_SACN`, `APOTHECARY_CONSOLE_OSC` | Set by `apothecary serve --console-sacn` and `--console-osc` in its server's environment: the server listens for a console's levels on the local network, UDP 5568 and 8001, receive only. Not set by hand | Unset | [lighting.md](lighting.md#getting-levels-in) |
| `APOTHECARY_CARLOS` | Carlos's address on this machine. `apothecary serve --carlos URL` sets it in its server's environment, and the server sends a site's wiring there to be held and drawn; `apothecary rig` asks it for a rig, and holds a concert's frames there, when no `--carlos` is given | Unset: nothing is sent | [the bench plan](plans/qm-family-carlos-2026-10-29.md#the-demo), [the concert plan](plans/carlos-concert-rig-2026-10-29.md#the-demo) |
| `APOTHECARY_CARLOS_SITE` | The site whose wiring `serve --carlos` sends | `garage` | [the plan](plans/qm-family-carlos-2026-10-29.md#the-demo) |
| `APOTHECARY_QMCP` | qmcp, through which image models are asked about the shape chosen on a mat, only when a person asks (Models, and `apothecary vision`): an address on this machine, reached over MCP, or `simulated`, a qmcp in process (`simulated:slow`, `:empty`, `:broken`, `:down` for each way it can fail); `off` is the same as unset. `apothecary serve --demo` sets `simulated` unless another is named | Unset: nothing is asked, and the plain reader still reads a colour | [the plan](plans/image-models-through-qmcp-2026-10-30.md), [the checklist](models-checklist.md) |
| `APOTHECARY_DEMO` | The demo's folder, set by `apothecary serve --demo` in its server's environment; the page's banner reads it. Not set by hand | Unset | [viewer.md](viewer.md#the-header) |

## Other variables Apothecary reads

| Variable | What it names | Default |
|---|---|---|
| `ARDUINO_CLI` | The arduino-cli the Arduino module runs, checked first; `none` means none | The tools dir, then `PATH` |
| `ESPTOOL` | The esptool the Arduino module runs; `none` means none | `PATH`, the `esp32:esp32` core's, or the Python module |
| `CARGO`, `ESPFLASH` | The cargo and espflash a Rust sketch is built and flashed with; `none` means none | The tools dir, then `PATH` |
| `FAKE_DEVKIT`, `FAKE_ROUTER`, `FAKE_MONITOR` | Read by the scripted arduino-cli the demo and the tests run (`apothecary/firmware/scripted.py`), never by a real one: a devkit in its board list, the router's controller in it, and a monitor that sends far more than a serial line carries | Unset |
| `OPENSCADPATH` | OpenSCAD's own library path, read for the files a SCAD includes | Unset |

[firmware.md](firmware.md#setup) says how each toolchain finds its tools. The
browser tests' servers set most of these for themselves
([tests/e2e/README.md](../tests/e2e/README.md)), and `apothecary serve --demo`
sets those its bench needs.
