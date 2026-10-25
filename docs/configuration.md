# Configuration

Apothecary takes its configuration from environment variables. None is
needed: each has a default.

## APOTHECARY_* variables

| Variable | What it names | Default | More |
|---|---|---|---|
| `APOTHECARY_TOOLS_DIR` | The folder OpenSCAD snapshots, OrcaSlicer and the firmware toolchains are installed in | `~/.apothecary/tools` | [firmware.md](firmware.md#setup), [openscad.md](openscad.md#installing-a-snapshot) |
| `APOTHECARY_STATE_DIR` | The state folder, this account's alone: pinned boards, flash records, cached probes, bed readings, kept prints and slices, jobs, cameras | `~/.apothecary` | [firmware.md](firmware.md#setup) |
| `APOTHECARY_CACHE_DIR` | The render cache -- a node's STLs, a part's variants -- and the demo's state folder | `.cache` in the checkout | [parts-authoring.md](parts-authoring.md) |
| `APOTHECARY_PICTURE_ROOT` | The one folder pictures are read from; never a home folder or anything above one, or the state folder | The folder `serve` was started in | [pictures.md](pictures.md#where-pictures-live) |
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
| `APOTHECARY_THEATRE_RIG` | The folder of a console's two exports (`patches.csv`, `fixture-parameters.csv`) the theatre site's rig is read from | `examples/theatre-rig/`, a made-up rig | [lighting.md](lighting.md#the-rig-and-another-in-its-place) |
| `APOTHECARY_CONSOLE_SACN`, `APOTHECARY_CONSOLE_OSC` | Set by `apothecary serve --console-sacn` and `--console-osc` in its server's environment: the server listens for a console's levels on the local network, UDP 5568 and 8001, receive only. Not set by hand | Unset | [lighting.md](lighting.md#getting-levels-in) |
| `APOTHECARY_DEMO` | The demo's folder, set by `apothecary serve --demo` in its server's environment; the page's banner reads it. Not set by hand | Unset | [viewer.md](viewer.md#the-header) |

## Other variables Apothecary reads

| Variable | What it names | Default |
|---|---|---|
| `ARDUINO_CLI` | The arduino-cli the Arduino module runs, checked first; `none` means none | The tools dir, then `PATH` |
| `ESPTOOL` | The esptool the Arduino module runs; `none` means none | `PATH`, the `esp32:esp32` core's, or the Python module |
| `CARGO`, `ESPFLASH` | The cargo and espflash a Rust sketch is built and flashed with; `none` means none | The tools dir, then `PATH` |
| `FAKE_DEVKIT`, `FAKE_MONITOR` | Read by the scripted arduino-cli the demo and the tests run (`apothecary/firmware/scripted.py`), never by a real one: a devkit in its board list, and a monitor that sends far more than a serial line carries | Unset |
| `OPENSCADPATH` | OpenSCAD's own library path, read for the files a SCAD includes | Unset |

[firmware.md](firmware.md#setup) says how each toolchain finds its tools. The
browser tests' servers set most of these for themselves
([tests/e2e/README.md](../tests/e2e/README.md)), and `apothecary serve --demo`
sets those its bench needs.
