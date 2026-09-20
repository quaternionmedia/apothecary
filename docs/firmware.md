# Firmware: programming boards from Apothecary

Parts are not only geometry. A footpedal has an Arduino in it; an RC snowplow
has an ESP32; the bench has a 3D printer whose mainboard already runs Marlin.
`apothecary firmware` and the `/firmware` page let you install the toolchain,
keep sketches next to the parts they belong to, compile and upload them, see
what each connected board is running -- and, for a board Apothecary does not
program, [monitor it](#printers-boards-that-already-run-a-g-code-firmware)
and let it drive its node in the viewer.

Apothecary owns only the control plane. Building, flashing and talking to
serial ports are done by external engines, invoked as subprocesses (or, for
pyserial, imported behind a swappable transport slot) and never modified:

| Engine | Used for | Installed by |
|---|---|---|
| [arduino-cli](https://arduino.github.io/arduino-cli/) | boards, cores, libraries, compile, upload, serial monitor | `apothecary firmware install` (checksum-verified download into `~/.apothecary/tools/`) |
| [esptool](https://github.com/espressif/esptool) | chip identification and raw binary flashing of Espressif chips | detected: on `PATH`, bundled with the `esp32:esp32` core, or as a Python module |
| [pyserial](https://pyserial.readthedocs.io/) | the byte transport under the G-code printer seam (any baud, every platform); the stdlib's `termios` stands in when it is absent | a declared dependency (`uv sync`) -- see [Serial engine](#serial-engine) |

Two pages and one overlay make up the GUI: the **`/firmware`** page
(toolchain, sketches, tasks, device cards), the viewer's **⌨ Serial log**
overlay and **Device** panel section, and the **`/firmware/monitor`** page
for one printer at a time. Each links to the others.

## Setup

```bash
apothecary firmware install --avr --esp32      # arduino-cli + the AVR and ESP32 cores
apothecary firmware validate                   # exit 1 if arduino-cli is unusable
apothecary firmware cores --install rp2040:rp2040   # more cores; index URLs are added for you
apothecary firmware libraries --install FastLED --install "Control Surface@2.1.2"
```

Environment:

| Variable | Meaning | Default |
|---|---|---|
| `APOTHECARY_TOOLS_DIR` | where Apothecary installs toolchains | `~/.apothecary/tools` |
| `APOTHECARY_STATE_DIR` | where flash records and cached probes live | `~/.apothecary` |
| `ARDUINO_CLI` | explicit path to an arduino-cli binary (checked first) | — |
| `APOTHECARY_SERIAL_ENGINE` | byte transport for the G-code printer seam: `pyserial` or `termios` | pyserial if installed |

The tools dir is under `$HOME` on purpose rather than an XDG data dir: sandboxed
editors (the VS Code snap, for one) point `XDG_DATA_HOME` at a per-revision tree
that disappears on the next editor update.

On Linux the serial port must be writable by your user — usually
`sudo usermod -aG dialout $USER` and a new login.

## Sketches live with their parts

A sketch is a folder holding a `.ino` of the same name — arduino-cli's own
layout rule — anywhere under `parts/`, including nested category folders:

```
parts/footpedal/footpedal.ino
parts/esp32_blink/esp32_blink.ino
parts/rc/snowplow/controller/controller.ino
```

An optional `firmware.json` beside the `.ino` supplies defaults so nobody
retypes them per build:

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
| `note` | shown in the GUI's build panel |

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

## Knowing what a board is running

`apothecary firmware devices` (and the Devices panel on `/firmware`) describe
each connected board from four independent sources:

| View | Source | What it tells you |
|---|---|---|
| Detected | `arduino-cli board list` | serial port, USB bridge VID:PID, any board arduino-cli matched |
| Probed | `esptool flash_id` | chip model and revision, MAC, flash size, crystal — cached per port; **resets the board** |
| Expected | Apothecary's own flash record | the sketch last uploaded to that MAC (or port), with its FQBN, time, and the SHA-256 of both the binary and the sources — plus drift flags: *source edited since*, *newer build never uploaded*, *sketch gone* |
| Observed | `arduino-cli monitor` | the sketch that announces itself over serial |

```bash
apothecary firmware probe /dev/ttyUSB0             # identify the chip
apothecary firmware listen /dev/ttyUSB0 --reset    # a few seconds of serial; names the running sketch
```

### The announce protocol

A sketch that wants to be identified prints, at boot **and every few seconds**:

```
apothecary <sketch-name>: hello
```

Periodically, not just at boot: the monitor takes longer to attach than a boot
banner lasts. `parts/esp32_blink/esp32_blink.ino` is the reference
implementation (it also prints a `chip: …` line the GUI shows next to the
probe result). When the observed name matches the expected record the GUI
marks the device green; a mismatch is red.

### Live serial

`GET /firmware/devices/stream?port=/dev/ttyUSB0&baud=115200` is a server-sent
events stream of the board's serial output. It backs the **Live** button on
each device card and the **⌨ Serial log** toggle in the fractal viewer, which
floats a terminal over the 3D view and remembers its state across reloads.

Starting any task (compile, upload, install, flash) stops every monitor first
— the port is needed — and the page reconnects when the task ends.

Some USB-UART bridges occasionally replay bytes they already delivered (seen
on a CP2102). Serial bytes are paced through a token bucket refilled at the
baud rate: a burst the wire could not have carried, or a verbatim repeat
arriving faster than the wire could resend it, is dropped; three in a row
reopen the port and print `[apothecary: serial replay detected -- reopening
port]` in the log. Genuine output is never throttled.

## Printers: boards that already run a G-code firmware

A 3D-printer mainboard (a Creality Ender board running Marlin, say) is not a
board Apothecary programs; it is one Apothecary *monitors*. It shows up in
`devices` as an unmatched serial port like any other; `M115` tells them apart:

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

The identification is cached on the device (like an esptool probe), so
`devices` and the viewer know it is a printer from then on without touching
the port. A poll (`M105`, `M114`, `M27`, `M119`, and `M31` while printing)
yields a `PrinterStatus` whose `state` is one of the garage site's
`PRINTER_STATUSES` (`idle`, `printing`, `offline`) so a printer node can take
it verbatim.

**Reset is deliberate, never incidental.** Every Creality board wires DTR to
reset, exactly like an Arduino. The kernel asserts DTR whenever a port is
opened, so whether an open reboots the firmware depends on whether the
*previous* program dropped DTR when it closed -- most do, and a running
print then dies by accident. Apothecary therefore:

- opens a printer's port once and *holds* it (`firmware.gcode.PrinterLinks`);
  every later poll reuses that link at ~0.1 s;
- leaves DTR asserted on close, so the next open (its own or another
  program's) does not reboot the board;
- reboots the board only when asked -- `apothecary firmware printer --reset`,
  or `{"reset": true}` on the identify route -- which is how the boot banner
  in `boot_lines` is captured. `M115` needs no banner, so identification
  without `--reset` is the default.

One holder per port: streaming a printer through `arduino-cli monitor`
releases the held link (and may reset the board); identifying or polling a
port closes any monitor on it. The viewer's ⌨ Serial log overlay polls a
printer every 2 s instead of streaming it for this reason. Uploading to a
port releases only that port's link, not every printer's.
`POST /firmware/printers/release` drops the link when another program (a
slicer's USB print, OctoPrint) needs the port.

### A printer drives its scene node

Every printer in the garage carries a **`mainboard`** node inside its base
enclosure (`printer_1.frame_system.mainboard`, a Creality-4.2-sized PCB,
category `electrical`). That is where a real printer's port belongs: pin it
there (`PUT /sites/{site}/nodes/printer_1.frame_system.mainboard/device`
with `{"identity": "/dev/ttyUSB1"}`, or the viewer's Device panel) and every
poll writes the printer's `state` -- `idle`, `printing`, or `offline` when a
poll fails -- into the **printer Structure's** `status`, so the mesh
recolours in the viewer without anyone editing it. The rule is "the nearest
ancestor that carries a status": the board has none of its own, the
printer above it does. Pinning the printer Structure directly still works
(same rule, zero hops); the board is simply the honest place, and the one
the walkthrough uses. In the viewer the printer's Contents row shows the
board's badge (dimmed, "via frame_system.mainboard") and its Device section
names the board that speaks for it, with a link to jump there.

Two deliberate limits: nodes with no status anywhere up their path are left
alone (a footpedal has none), and a hand-set `maintenance` is never
overridden by a poll, because the printer may be idle *because* someone is
working on it. `GET /sites/{site}/devices` refreshes every printer whose
link is already held and returns the last poll on each binding row
(`printer_status`); it never opens a port itself. A poll's `synced` list
names the node whose status it drove and, when that differs from the pin,
`via` names the board.

### In the viewer

Select any node and the **Device** section of the Selected panel shows what
is pinned to it (port, firmware or chip, how it was bound) or offers a
**Pin** picker of detected devices not already bound elsewhere, a **Query**
button (asks the picked port `M115` without pinning it -- is this a
printer, and which firmware?), and a text box to **pin by typed identity**
-- a port that is not detected right now, a udev name like `/dev/ender`, or
an ESP32's MAC. For a printer the section shows the last poll -- state,
temperatures, position, SD progress, filament -- with **⟳ Poll now**
(one poll, no overlay) and **Watch**, which opens the ⌨ Serial log overlay
on that port. The overlay's **🖨 identify** asks `M115` (no reset); from
then on the overlay polls the port every 2 s instead of streaming it, each
poll scheduled only after the previous one returns so a slow reply never
stacks requests. Every poll updates the panel's Device section and the
tree's badge (`🖨 210°/60° 43%`) in place -- a position edit in progress
is never rebuilt under the cursor -- and a poll that moved the node's
status re-fetches the tree so the mesh recolours.

**Repolling.** The toolbar's **↻ Devices** toggle (on by default, 5/10/30 s)
rescans the ports and re-polls every printer whose link is held, on a
schedule that is paused while the tab is hidden and never overlaps itself
-- so a board that was replugged, or came back as `/dev/ttyUSB2` after a
USB hiccup, shows up (or shows as `⌁ off` with a **⟳ Rescan** button) without
a reload. Its state is remembered per browser.

The whole flow, step by step with screenshots, is generated from a
Playwright walkthrough: run `apothecary docs generate` and open
[`docs/generated/printer-monitor/printer-monitor.md`](generated/printer-monitor/printer-monitor.md)
(the generated tree is a build artifact, gitignored like STLs). A taste:

| | |
|---|---|
| ![Pin it: the section shows the last poll](generated/printer-monitor/screenshots/03-pin-it-the-section-shows-the-last-poll-state-tempe.png) | ![The printer followed its board](generated/printer-monitor/screenshots/04-the-printer-followed-its-board-printer-1-s-status-.png) |
| *Pin a detected port to the mainboard; its Device section shows the last poll* | *The printer above it follows: status, badge, and "via" the board* |

The walkthrough runs against the simulated printer mid-print, so it looks
the same on every machine; `tests/e2e/test_docs_printer_monitor.py` is the
source, and editing it is how you edit those docs.

The port scan behind all of this (`arduino-cli board list`, ~2 s) is cached
for two seconds server-side so the panel, the overlay and the firmware page
share one scan; the ⟳ buttons force a fresh one (`GET
/firmware/devices?fresh=1`).

`tests/e2e/test_printer_ui.py` holds this to timing bounds against its own
server with the simulated printer: panel up within 1 s of a click, polls at
the stated cadence and never stacked, an edit surviving two polls, a poll
reaching the firmware page within 5 s.

The seam itself is the G-code line protocol every host speaks (OctoPrint,
Pronterface, Cura), with Marlin, RepRapFirmware, Klipper and Prusa on the
other end; the parsers are written to Marlin's documented replies.

### The focused monitor

`/firmware/monitor?port=/dev/ttyUSB2` is one printer, full width: status
cards (state, hotend and bed with target bars, position, SD progress and
elapsed time, endstops and filament, the board and its link), a temperature
history chart over the last polls (hotend and bed on one °C axis, targets
dashed, crosshair tooltip), and the port's **comms log** -- every command
and reply, boot banner and link event, kept on the server per port so it
survives a page reload, shows polls made by other clients, and is not lost
when the link is reopened. *Poll traffic* is hidden by default so the log
reads as a story (open, `M115`, your queries, resets); tick it to see every
`M105`. The log downloads as a text file.

The header's controls act on the board's comms directly:

| Control | Does |
|---|---|
| **auto-poll** 1/2/5/10 s | polls on a schedule, each poll after the previous returns; paused while the tab is hidden |
| **⟳ Poll** | one poll now |
| **⇄ Reconnect** | release and reopen the link (no reset) -- the remedy for a wedged port or a replugged board |
| **M115** | re-identify (no reset) |
| **⏻ Reset board** | reboot with a DTR pulse, after a confirmation -- never mid-print; the boot banner lands in the log |
| **Release** | drop the held link so another program can open the port; auto-poll stops, the control latch disarms |
| **⚙ Control**, **E-STOP** | see [Control, behind a latch](#control-behind-a-latch) |

It is linked from the Device section (**⤢ Monitor**), the serial overlay
(**⤢ monitor**, once the port is identified), the firmware page's device
cards, and the **🖨 Monitor** link in both toolbars (which opens it with a
port picker). On the firmware page a printer card has only **Poll** and **⤢ Monitor**:
Probe (esptool), Identify (the hello-banner listener) and Live all open the
port through another process, which would evict the held link and may
reset the board, so the monitor is the live view for a printer.

![The focused monitor](generated/printer-monitor/screenshots/08-monitor-opens-the-focused-view-status-cards-temper.png)

### Control, behind a latch

The monitor's **⚙ Control** toggle arms a per-port latch and opens a control
overlay: hotend and bed targets, fan, home (all/XY/Z), a jog pad with a
step size and feedrate, motors off, quickstop, SD start/resume, pause and
abort, mesh on/off. Disarmed -- the default, and what a **Release** or a
dropped link returns to -- nothing on the page can heat or move the
machine, and the API refuses control lines with `409`. The latch lapses
after five minutes without a command (every accepted command renews it;
the header counts down) and survives a page reload, since it lives on the
server. **E-STOP** (`M112`) is always available, latch or not; the board
halts until it is reset.

What can be sent is a bounded allowlist (`firmware.gcode.CONTROL_CODES`):
`M104`/`M140` with temperature caps (300 / 130 °C), `M106`/`M107`, `G28`,
`G90`/`G91`, `G0`/`G1` with axis moves capped at 300 mm and feed at
12000, `M84`, `M23 <file>`/`M24`/`M25`/`M524`, `M420 S0|1`, `M108`,
`M410`. A jog from the pad is three lines (`G91`, `G1 …`, `G90`) so the
board is always left in absolute mode. Out-of-bounds values are refused
before they reach the port; there is no job streaming, no EEPROM write, no
firmware configuration -- those are a print host's business. Control
traffic is amber in the comms log, tagged `control`.

```
POST /firmware/printers/control  {"port": …, "armed": true, "ttl_s": 300}
POST /firmware/printers/command  {"port": …, "command": "M140 S60"}   → 409 unless armed
GET  /firmware/printers/controls                                     → the allowlist and bounds
```

### Manual queries

Beyond the fixed poll, a printer answers any *report-only* G-code by hand --
`M503` (all settings), `M119` (endstops), `M20` (SD files), `M420 V` (bed
mesh), `M122` (TMC drivers) and so on. The allowlist is
`firmware.gcode.QUERY_CODES`; anything not in it (`M104`, `G28`, `M500`...)
is refused before it reaches the port, so the seam keeps its "query codes
only" promise however the box is used.

```bash
apothecary firmware printer /dev/ttyUSB2 --query M119 --query "M420 V"
```

`GET /firmware/printers/queries` lists the codes; `POST
/firmware/printers/query` (`{"port": …, "command": "M503"}`) runs one over
the held link. In the viewer the ⌨ Serial log overlay grows a query box
(with those codes as suggestions) whenever it is on a printer.

### Serial engine

The byte transport under the G-code seam is an engine slot: **pyserial**
(BSD; any baud, every platform) when installed -- it is a declared
dependency, so normally -- else the stdlib's `termios` (POSIX, standard baud
table, enough for a 115200 board with nothing installed). Everything above
the slot is engine-agnostic. `APOTHECARY_SERIAL_ENGINE=pyserial|termios`
pins one.

A third engine, `simulated`, is an in-process pretend Marlin for demos and
browser tests with no hardware: any port "opened" through it answers the
query codes with plausible, slowly moving values.
`APOTHECARY_SIMULATED_PRINTER=printing` starts it mid-way through an SD
print that advances about 1 %/s; the default is a cold, idle machine. It
still needs a port to be *detected* -- on a machine with no boards, the
scripted fake `arduino-cli` from the tests supplies two:

```bash
ARDUINO_CLI=$(uv run python -c "import sys; sys.path.insert(0, 'tests'); from pathlib import Path; from firmware_helpers import write_fake_arduino_cli; print(write_fake_arduino_cli(Path('/tmp/fake-arduino-cli')))") \
APOTHECARY_SERIAL_ENGINE=simulated APOTHECARY_SIMULATED_PRINTER=printing \
APOTHECARY_STATE_DIR=/tmp/apothecary-demo uv run apothecary serve
```

### Optional: a stable device name

`/dev/ttyUSB0` and `/dev/ttyUSB1` can swap between boots when two bridges
are plugged in. A udev rule names the printer by its bridge's USB serial
number (`apothecary firmware devices` shows it as `S/N` on the firmware page;
`udevadm info -q property /dev/ttyUSB1 | grep ID_SERIAL_SHORT` on Linux):

```
# /etc/udev/rules.d/99-apothecary-printer.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ATTRS{serial}=="A106ZTEU", SYMLINK+="ender"
```

Then `sudo udevadm control --reload && sudo udevadm trigger`, and pin
`/dev/ender` instead of `/dev/ttyUSB1`. Note arduino-cli lists only the
kernel names, so the device panel still shows `/dev/ttyUSBn`; the symlink
is for pins and for `apothecary firmware printer /dev/ender`. Not required
-- pins to `/dev/ttyUSBn` work as long as the board keeps that name.

## HTTP API

All routes are under `/firmware`. Long-running actions return `202` with a
task; poll `GET /firmware/tasks/{id}?since=N` for new log lines. One task runs
at a time — a second request gets `409`.

| Route | Purpose |
|---|---|
| `GET /status` | toolchain state, cores, suggested cores, active task |
| `GET /sketches`, `/boards`, `/boards/all`, `/cores` | catalogue |
| `POST /install`, `/cores/install`, `/libraries/install` | toolchain tasks |
| `POST /sketches/{name}/compile`, `/upload` | build tasks (`{"fqbn": …, "port": …}`) |
| `POST /esptool/flash` | raw flash task; image paths must be inside the repository |
| `GET /devices` | detected + probed + expected, per port |
| `POST /devices/probe`, `/devices/listen` | identify the chip; capture serial (`reset: true` probes first) |
| `GET /devices/stream` | server-sent events of serial output |
| `POST /devices/identify` | `M115`: is this a G-code printer, and which firmware (`{"port": …, "baud": …, "reset": false}`) |
| `GET /printers/status?port=…` | one poll over the held link: temperatures, position, endstops, SD progress, and the scene nodes it updated (`synced`) |
| `GET /printers/queries`, `POST /printers/query` | the report-only codes a user may send by hand, and sending one (`{"port": …, "command": "M503"}`) |
| `GET/POST /printers/control`, `GET /printers/controls`, `POST /printers/command` | the control latch (arm/disarm, state), the bounded control allowlist, and sending one control line while armed (`M112` always) |
| `GET /sites/{name}/devices?fresh=1` | (site API) the bindings view; `fresh` forces a port rescan -- what the viewer's ↻ Devices and Rescan use |
| `POST /printers/release` | drop the held link so another program can open the port |
| `GET /printers/info?port=…` | device, held link (baud, engine, opened at), last poll, active task -- what the monitor page needs at once |
| `GET /printers/log?port=…&since=N` | the port's comms log from index `N` (`tx`/`rx`/`boot`/`sys` entries, each tagged with its origin: `poll`, `query`, `identify`) |
| `POST /printers/reconnect` | release + reopen (no reset), then poll |
| `POST /printers/reset` | reboot the board (DTR pulse); returns the boot banner |
| `GET /monitor?port=…` | the focused monitor page |
| `GET /tasks`, `/tasks/{id}`, `POST /tasks/{id}/cancel` | task log and control |

Inputs that become command-line arguments are validated by shape (FQBN,
serial port path, core id, chip name) and never pass through a shell; sketch
names resolve only to discovered sketches. The server binds to localhost by
default and these routes run binaries and open serial ports on the host, so
keep it that way.

## Testing

The seam's tests run against a scripted fake `arduino-cli`
(`tests/conftest.py`), so CI needs no toolchain, network, or serial port:

```bash
uv run pytest tests/test_firmware_seam.py tests/test_firmware_api.py tests/test_firmware_devices.py tests/test_firmware_gcode.py
```

The G-code tests replay a transcript captured from a real Marlin board
(`tests/test_firmware_gcode.py`), so the parsers are held to actual output.
The browser tests (`tests/e2e/test_printer_ui.py`, run with
`pytest tests/e2e --start-server`) drive the Device panel, the overlay and
the focused monitor against the simulated printer under timing bounds, and
`tests/e2e/test_docs_printer_monitor.py` is the walkthrough that
`apothecary docs generate` turns into screenshots.

The decision record for all of this is *Firmware toolchain seam* in
`governance/qm/adr/`.
