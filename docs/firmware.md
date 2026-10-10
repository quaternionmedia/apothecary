# Firmware: programming boards from Apothecary

Parts are not only geometry. A footpedal has an Arduino in it; an RC snowplow
has an ESP32; the bench has a 3D printer whose mainboard already runs Marlin.
`apothecary firmware` and, in the viewer, the [Bench](#in-the-viewer-the-bench)
and each board's [Machine](#in-the-viewer-one-machine-per-board) install the
toolchain, keep sketches next to the parts they belong to, compile and upload
them, say what each connected board is running, and, for a board Apothecary
does not program, [monitor it](#printers-boards-that-already-run-a-g-code-firmware)
and let it drive its node in the viewer.

Apothecary owns only the control plane. Building, flashing and talking to
serial ports are done by external engines, run as subprocesses (pyserial is
imported behind a swappable transport slot) and never modified:

| Engine | Used for | Installed by |
|---|---|---|
| [arduino-cli](https://arduino.github.io/arduino-cli/) | boards, cores, libraries, compile, upload, serial monitor | `apothecary firmware install` (checksum-verified download into `~/.apothecary/tools/`) |
| [esptool](https://github.com/espressif/esptool) | chip identification and raw binary flashing of Espressif chips | detected: on `PATH`, bundled with the `esp32:esp32` core, or as a Python module |
| [pyserial](https://pyserial.readthedocs.io/) | the byte transport under the G-code printer seam | a declared dependency (`uv sync`); see [Serial engines](#serial-engines) |

## Setup

```bash
apothecary firmware install --avr --esp32      # arduino-cli + the AVR and ESP32 cores
apothecary firmware validate                   # exit 1 if arduino-cli is unusable
apothecary firmware cores --install rp2040:rp2040   # more cores; index URLs are added for you
apothecary firmware libraries --install FastLED --install "Control Surface@2.1.2"
```

| Variable | Meaning | Default |
|---|---|---|
| `APOTHECARY_TOOLS_DIR` | where Apothecary installs toolchains | `~/.apothecary/tools` |
| `APOTHECARY_STATE_DIR` | flash records, cached probes, bed readings, kept prints | `~/.apothecary` |
| `ARDUINO_CLI` | explicit path to an arduino-cli binary (checked first) | — |
| `APOTHECARY_SERIAL_ENGINE` | byte transport for the printer seam: `pyserial` or `simulated` | `pyserial` |

The tools dir is under `$HOME` because sandboxed editors (the VS Code snap)
point `XDG_DATA_HOME` at a tree that disappears on the next editor update.

Every arduino-cli the seam starts gets `--config-file
~/.apothecary/tools/arduino-cli.yaml`, written from
`stays_local.ARDUINO_CLI_CONFIG`: no cloud board lookup, no update check, and
named package indexes only. Its environment carries no proxy variable and no
`ARDUINO_*` override, and `~/.arduino15/arduino-cli.yaml` is not read;
`apothecary firmware validate` names the file in use. The record is *Personal
data stays on the device, by construction* (`governance/qm/adr/`).

On Linux the serial port must be writable by your user: usually
`sudo usermod -aG dialout $USER` and a new login.

## Sketches live with their parts

A sketch is a folder holding a `.ino` of the same name (arduino-cli's layout
rule) anywhere under `parts/`, including nested category folders:

```
parts/footpedal/footpedal.ino
parts/esp32_blink/esp32_blink.ino
parts/rc/snowplow/controller/controller.ino
```

An optional `firmware.json` beside the `.ino` supplies defaults:

```json
{
  "fqbn": "esp32:esp32:esp32",
  "cores": ["esp32:esp32"],
  "libraries": ["FastLED", "Control Surface@2.1.2"],
  "note": "Classic ESP32 devkits; use esp32:esp32:esp32s3 for an S3."
}
```

| Field | Purpose |
|---|---|
| `fqbn` | default board (`vendor:arch:board[:option=value,…]`); `--fqbn` or the GUI overrides it |
| `cores` | cores the sketch needs (informational; install with `firmware install --core`) |
| `libraries` | libraries to install, `Name` or `Name@Version` |
| `note` | shown under the sketch in the Bench and in a board's Flashing card |

A sketch that carries an arduino-cli *profile* (`sketch.yaml`, `sketch.json`)
is not built: a profile names where arduino-cli fetches a platform from, and
arduino-cli honours it over the command line, so it would outrank the managed
config.

Build output goes to `build/firmware/<sketch>/` (git-ignored), never into `parts/`.

## Build and upload

```bash
apothecary firmware sketches                 # what was found
apothecary firmware compile esp32_blink      # FQBN from firmware.json
apothecary firmware upload esp32_blink       # compile, then upload the fresh build
apothecary firmware upload footpedal --fqbn arduino:avr:nano:cpu=atmega328old -p /dev/ttyUSB1
apothecary firmware flash-bin /dev/ttyUSB0 0x0:build/firmware/esp32_blink/esp32_blink.ino.merged.bin --chip esp32
```

`upload` always compiles first and flashes that build, never a stale binary.
The port is auto-detected only when exactly one board is connected; with
several it refuses to guess.

### In the viewer: the Bench

The **Bench** is the same toolchain in front of the world: a tab of the
viewer's rail (the ring's Panels › Bench; `/firmware` opens the viewer with
it). It holds arduino-cli and esptool as installed,
with **Install** or **Update** (*force* downloads it again); the suggested
cores, each with **Install**; libraries typed and installed; the sketches
under `parts/`, each with the board its `firmware.json` names, **Compile**d,
or compiled and uploaded to a detected port after asking (**Compile &
upload**); **Raw flash** with esptool, one `offset path` a line, after asking;
and the task log -- the running task's output with **Cancel**, and the recent
tasks, each row showing its output again. Each is a task (`POST
/firmware/install`, `/cores/install`, `/libraries/install`,
`/sketches/{name}/compile` and `/upload`, `/esptool/flash`), and each verb is
a cell of Panels › Bench, acting on what the Bench has chosen. Its body is
filled the first time its tab is shown, so a page that never shows it asks
nothing of the toolchain. A board's own flashing is in its Machine
([below](#in-the-viewer-one-machine-per-board)); the Bench is for any sketch
and any port.

## Knowing what a board is running

`apothecary firmware devices` (and each board's Machine in the viewer) describe
each connected board from four independent sources:

| View | Source | What it tells you |
|---|---|---|
| Detected | `arduino-cli board list` | serial port, USB bridge VID:PID and serial number, any board arduino-cli matched |
| Probed | `esptool flash_id` | chip model and revision, MAC, flash size, crystal; cached per port; **resets the board** |
| Expected | Apothecary's own flash record | the sketch last uploaded to that MAC (or port), with its FQBN, time, and the SHA-256 of both the binary and the sources, plus drift flags: *source edited since*, *newer build never uploaded*, *sketch gone* |
| Observed | `arduino-cli monitor` | the sketch that announces itself over serial |

```bash
apothecary firmware probe /dev/ttyUSB0             # identify the chip
apothecary firmware listen /dev/ttyUSB0 --reset    # a few seconds of serial; names the running sketch
```

A sketch that wants to be identified prints, at boot **and every few
seconds** (the monitor takes longer to attach than a boot banner lasts):

```
apothecary <sketch-name>: hello
```

`parts/esp32_blink/esp32_blink.ino` is the reference implementation. When the
observed name matches the expected record the device is marked green; a
mismatch is red.

`GET /firmware/devices/stream?port=…&baud=…` streams a board's serial output
(server-sent events). Starting any task stops every monitor first. Bytes are
paced at the baud rate, so bytes a bridge replays after delivering them (a
CP2102 does) are dropped, and three replays in a row reopen the port.

## Printers: boards that already run a G-code firmware

A 3D-printer mainboard running Marlin is a board Apothecary *monitors*, not
one it programs. It shows up in `devices` as an unmatched serial port;
`M115` tells it apart:

```bash
apothecary firmware printer /dev/ttyUSB1        # identify (M115) and poll once
```

```
/dev/ttyUSB1   vid=0x0403 pid=0x6001  (unmatched)
    printer: Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34) · TH3D EZABL  @ 115200 baud
    state: idle
    temps: T0: 22.6/0°C  bed: 24.2/0°C
    position: X0.00 Y0.00 Z0.00 E0.00
    endstops: x_min=open  y_min=TRIGGERED  z_min=open
    filament: present
```

The identification is cached on the device, so `devices` and the viewer know
it is a printer from then on without touching the port. A poll (`M105`,
`M114`, `M27`, `M119`, and `M31` while printing) yields a `PrinterStatus`
whose `state` is one of the garage site's `PRINTER_STATUSES` (`idle`,
`printing`, `offline`), so a printer node can take it verbatim. The parsers
are written to Marlin's documented replies; RepRapFirmware, Klipper and
Prusa speak the same line protocol.

**Reset is deliberate, never incidental.** Creality boards wire DTR to reset
and the kernel asserts DTR on every open, so Apothecary opens a printer's
port once, exclusively, and holds it (`firmware.gcode.PrinterLinks`); leaves
DTR asserted on close (`gcode.keep_dtr_on_close` clears `HUPCL`), so the
next open does not reboot the board; and reboots it only when asked
(`apothecary firmware printer --reset`, or `{"reset": true}` on
`POST /firmware/devices/identify`), which is how the boot banner is captured.
The first open after a board is plugged in does reset it.

**One holder per port.** Streaming a printer through `arduino-cli monitor`,
probing it with esptool or listening for a hello banner opens the port
through another process, evicts the held link and may reset the board, so
the viewer polls a printer instead of streaming it, and a printer's Machine
offers Poll and no Listen, Probe or flashing. Identifying or polling a port
closes any monitor on it. Uploading to a port releases only that port's
link. `POST /firmware/printers/release` drops the link when another program
(a slicer's USB print, OctoPrint) needs the port.

### A pin follows the board

Every printer in the garage carries a `mainboard` node inside its base
(`printer_1.frame_system.mainboard`). Pin the real printer's port there
(`PUT /sites/{name}/nodes/{path}/device` with `{"identity": "/dev/ttyUSB1"}`,
or Pin in the viewer's Selected) and every poll writes the printer's `state`
(`offline` when a poll fails) into the `status` of **the nearest ancestor
that carries one**: the board has none, the printer above it does, so the
printer's mesh recolours with nobody editing it. A poll's `synced` list names
the node it drove and, when that differs from the pin, `via` names the board.
Nodes with no status anywhere up their path are left alone, and a hand-set
`maintenance` is never overridden by a poll. `GET /sites/{name}/devices`
returns the last poll on each binding (`printer_status`) and the ports whose
link is held (`printers`), and never opens a port itself. A pin talks to no
printer; the viewer polls a printer whose link is held once as it pins it, so
the node follows from then.

A pin stores the board's own identity (its MAC, else its USB bridge's serial
number, else the port), so it still holds when the kernel numbers the port
differently after a replug. A pin by a path that resolves to the same device
(`/dev/serial/by-id/…`, a udev name) matches too.

### In the viewer: one Machine per board

A pinned board has one surface in the viewer, its **Machine**
(`apothecary/static/widgets/machine.js`), opened from the board's badge as a
tab of the rail's strip beside Pictures and the Bench; it floats over the
world only when floated from its tab. A printer's Machine holds its
state cards, temperature chart, link verbs, the control latch and pad, the bed
reading and the print from here; a devkit's holds its port and board, the
sketch it should run against the sketch it was heard saying (its
`apothecary <name>: hello` banner), what changed since it was flashed, and
its **Flashing** card. Both carry the board's **one log**: a
printer's comms log, with the one box that asks it for a report code (poll
traffic hidden unless asked for), or a devkit's serial output. A refusal is
said in the log and in the status bar.

A devkit's port is opened only when asked. Opening its Machine shows what is
known of it and opens no port; **Listen** streams what the board says into
the log, and says that opening the port may reset the board; **Release**
closes it again. **Probe** asks esptool for the chip, its MAC and its flash
size, which resets the board. **Identify** listens a few seconds for the
hello and, pressed with none heard, asks `M115`, so a board pinned before it
was asked can turn out to be a printer; a printer's Identify asks `M115`.

The Flashing card is the Bench's form and task log for this one port: the
sketch it should run to start with (the last one flashed to it from here,
else the one its node is bound by), the board's FQBN, **Compile**, and
**Compile & upload** after asking, the task's output in the card, then
Identify's listen for the hello -- never its `M115`, which is a person's to
press for. A printer keeps its own firmware and has no Flashing card.

Selected's Device section is one line for a pinned board -- its port and what
it is doing -- with **Open** (its Machine) and **Unpin**; for a piece with
nothing pinned, the detected ports to pin, Query (`M115` without pinning) and
a box to pin by typed identity. The badge over a board in the world opens its
Machine too.

Every drawer of a board -- its badge in the world, its badge in Site's tree,
Selected's line and its Machine -- reads one model of it
(`apothecary/static/boards.js`), which polls a printer at the interval its
Machine says, and only while its Machine is open with auto-poll on: one
poller per board, whatever draws it. The model scans for boards when a site
loads, when **Rescan** asks, and by itself when a board it watches goes quiet,
so a replugged board is found without a reload; it never scans on a timer.

`/firmware/monitor?port=…` opens the viewer on the site the port is pinned
in with the Machine of the piece it is pinned to open, or, for a port
pinned nowhere, on the default site with its Machine open; either way the
Machine is a tab of the rail's strip, as every Machine is. The address
carries `?machine=` while a Machine is open, so a reload opens it again. `apothecary docs generate` writes all of it step by
step against the simulated printer into
[`generated/printer-monitor/printer-monitor.md`](generated/printer-monitor/printer-monitor.md);
[walkthrough 12](../walkthrough/12-the-bench-as-it-is.md) shows the boards
drawn where they sit.

Every device verb is also on the ring (right-click a piece, or `m`), whose
nine cells are numbered as a numeric keypad, so the digits pressed to reach
an option are its address; each device button shows its address in its
tooltip. Device holds Open (8), Poll (6), Flash (2), Query (4), Unpin (9),
Rescan (3), Link (1) and, on a printer, Control (7): Open is the board's
Machine and Flash opens it at its Flashing card -- on a printer the Flash
cell holds its place and cannot be chosen -- and a devkit's Link ends with
Listen and Probe. A board's verbs from the ring -- Poll, Query, Flash, the
link's, Control's, the bed's, the print's -- go to its Machine, opened for it
when it is not. Inside a Machine the ring is its device ring, on its port,
and the Machine's buttons wear that ring's addresses. `POST /menu/resolve`
seats the options
(`apothecary/menu.py`); `POST /menu/intent` receives the choice. A control
verb from the ring goes through the same latch, allowlist and confirms as the
button it replaces; the ring never opens a port.

### Control, behind a latch

Disarmed, the default, nothing can heat or move the machine: the API refuses
control lines with `409`. A printer's Machine's **⚙ Control** arms a per-port latch
held on the server; it lapses after five minutes without a command (each
accepted command renews it) and is dropped by a **Release** or a lost link.
**E-STOP** (`M112`) is always accepted, latch or not; the board halts until
it is reset.

What can be sent is a bounded allowlist, `firmware.gcode.CONTROL_CODES`
(heaters and fan, homing, moves, motors off, SD start, pause and abort, mesh
on and off, probing, break wait, quickstop), with heater, travel and feed
caps beside it. Out-of-bounds values are refused before they reach the port;
there is no EEPROM write and no firmware configuration. A jog is three lines
(`G91`, `G1 …`, `G90`), so the board is left in absolute mode.

```
POST /firmware/printers/control  {"port": …, "armed": true, "ttl_s": 300}
POST /firmware/printers/command  {"port": …, "command": "M140 S60"}   → 409 unless armed
GET  /firmware/printers/controls                                     → the allowlist and bounds
```

Anything else a person may send by hand is *report-only*
(`firmware.gcode.QUERY_CODES`: `M503`, `M119`, `M20`, `M420 V`, `M122` …),
through `POST /firmware/printers/query` or
`apothecary firmware printer PORT --query M119`. A code not in that list is
refused before it reaches the port.

### Bed leveling

**Read mesh** asks the board for its stored mesh (`M420 V`), the probe offset
(`M851`) and the temperatures and keeps the three as a *bed reading*; it
moves nothing and needs no latch. **Probe bed** homes and probes (`G28`,
`G29`) and then reads; it needs the latch and runs as a job that holds the
port, during which polls answer from the last poll, queries and control lines
get `409`, and E-STOP still goes through. Readings are kept under
`~/.apothecary/leveling/` and drawn as a heatmap with the range, the tilt
(a least-squares plane) and each corner against the mean, and as a relief
over the printer's bed in the world. The corner buttons move the nozzle to paper
height at each corner and are controls. `firmware.gcode.parse_meshes` reads
Marlin's printed grid and falls back to the `G29 W` points an `M503` prints.

### Printing without an SD card

**Print from here** keeps a sliced G-code file on the host
(`~/.apothecary/prints/`) and checks it before anything is sent: a file that
saves settings (`M500`), factory-resets (`M502`), updates firmware (`M997`),
kills or restarts the board, or exceeds the heater caps is refused with the
reason. **Print** needs the latch and starts a job that sends one line per
`ok`; a line unanswered for thirty seconds (heat-and-wait and home excepted),
or answered with an error or a resend, ends the print. While it prints,
heaters, fan and break-wait stay available; motion, SD, homing, the bed and
release, reconnect, reset or upload on that port are refused. **Cancel** and
a failed line send the safe-off (`M104 S0`, `M140 S0`, `M107`, `M84`); E-STOP
ends the job with nothing more sent. It is not a queue, a slicer or a
webcam; the *G-code printer seam* record's sixth decision draws that line.

### A print is a job

Every print started from the card is a *job* (`apothecary/jobs.py`): one
operation a machine performs on a part. The job records its kind (`print`),
the printer (its port, the board's own identity, the node it is pinned to),
the site, the part or piece it makes when one is chosen on the card (the
**makes** drop-down lists the parts and pieces of the site the printer is
pinned in; a piece made from a picture is chosen there by **Print** on its own
ring, and its job keeps the picture and the camera it came from, in its record
and not its row), the file it ran (name, size, SHA-256), when it started and
finished, and how it ended -- done, cancelled or failed, with the reason; the
status line says when a print starts and when it ends, or that it failed and
why. A
running job is what marks the printer's node `printing`, from the moment it
starts; a hand-set `maintenance` is left alone. Jobs are kept under
`~/.apothecary/jobs/`, this account's alone.

The card's history is the printer's jobs (`GET /jobs?machine=PORT&kind=print`),
each with its JSON (`GET /jobs/{id}`, with the tail of what the firmware
said), and the viewer's **Site** lists the jobs of the site's machines, a row
opening its machine. `GET /jobs/choices?machine=PORT` says what a job there
would record and which parts it can name. The print records kept before jobs
(`~/.apothecary/prints/records/`) are carried over as print jobs the first
time jobs are read, and left where they were.

A kind of job belongs to a kind of machine: a printer offers `print`
(`jobs.PRINT`), and a mill or a laser would register its own operation with
`jobs.register` and start its jobs from its own card in the same way.

## Serial engines

The byte transport under the G-code seam is an engine slot:

| Engine | What it is |
|---|---|
| `pyserial` | the default: any baud, every platform |
| `simulated` | an in-process pretend Marlin for demos and browser tests: any port opened through it answers with plausible, slowly moving values, and answers `G29`, `M420 V`, `M851` and `G30` with a slightly tilted bed |

`APOTHECARY_SIMULATED_PRINTER=printing` starts the simulator mid-way through
an SD print; the default is a cold, idle machine. A port must still be
*detected*; on a machine with no boards the tests' scripted `arduino-cli`
supplies two:

```bash
ARDUINO_CLI=$(uv run python -c "import sys; sys.path.insert(0, 'tests'); from pathlib import Path; from firmware_helpers import write_fake_arduino_cli; print(write_fake_arduino_cli(Path('/tmp/fake-arduino-cli')))") \
APOTHECARY_SERIAL_ENGINE=simulated APOTHECARY_SIMULATED_PRINTER=printing \
APOTHECARY_STATE_DIR=/tmp/apothecary-demo uv run apothecary serve
```

## A stable device name

Pins need none, and Linux already names every bridge with a serial under
`/dev/serial/by-id/`. For a short name, a udev rule matches that serial
(`S/N` in `apothecary firmware devices`):

```
# /etc/udev/rules.d/99-apothecary-printer.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ATTRS{serial}=="A106ZTEU", SYMLINK+="ender"
```

Then `sudo udevadm control --reload && sudo udevadm trigger`. arduino-cli
lists only kernel names, so the symlink is for the CLI and other programs.

## HTTP API

Every route is described at `/openapi.json`: the paths under `/firmware`, and
the site routes `/sites/{name}/devices` and `/sites/{name}/nodes/{path}/device`.
Long-running actions (install, compile, upload, flash) return `202` with a
task; poll `GET /firmware/tasks/{id}?since=N` for new log lines. One task
runs at a time; a second request gets `409`.

Inputs that become command-line arguments are validated by shape (FQBN,
serial port path, core id, chip name) and never pass through a shell; sketch
names resolve only to discovered sketches. These routes run binaries and open
serial ports on the host, which is why the server listens on this machine only.

## Testing

The seam's tests run against a scripted fake `arduino-cli`
(`tests/firmware_helpers.py`), so CI needs no toolchain, network or serial port:

```bash
uv run pytest tests/test_firmware_seam.py tests/test_firmware_api.py tests/test_firmware_devices.py tests/test_firmware_gcode.py
```

The G-code tests replay a transcript captured from a real Marlin board. Every
browser-test server runs the scripted `arduino-cli` and the simulated printer,
with its firmware state in a folder of its own, so no test opens a real port
or edits what is pinned in `~/.apothecary`. `tests/e2e/test_printer_ui.py`
holds the viewer and a printer's Machine to timing bounds, and the printer as
the world draws it to enclosing its board and its build volume;
`tests/e2e/test_bench.py` drives the Bench, and `tests/e2e/test_one_machine.py`
a board's Machine, its flashing and its port opened only by Listen.
[`validation/2026-09-20-ender-bench.md`](validation/2026-09-20-ender-bench.md)
is the seam against a real Ender mainboard, with a checklist for what needs
control armed.

The decision records are *Firmware toolchain seam* and *G-code printer seam*
in `governance/qm/adr/`.
