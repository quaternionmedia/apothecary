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
  program's) does not reboot the board. The kernel's default is the
  opposite -- `HUPCL`, hang up on close -- so both engines clear it on
  open (`gcode.keep_dtr_on_close`); on the bench, server → CLI → server
  reopens the port three times without a boot banner. The one open that
  does reboot the board is the first after it is plugged in, because the
  bridge comes up with DTR dropped; the banner in the log says so;
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
-- a port that is not detected right now, a udev name like `/dev/ender`, a
USB bridge's serial number, or an ESP32's MAC. **A pin follows the board,
not the socket**: pinning a detected port stores the board's own identity
(its MAC, else its bridge's serial number, `A106ZTEU` on the bench's Ender)
when it has one, so the pin still holds when the kernel numbers the port
differently after a replug -- the same printer came back as `/dev/ttyUSB0`
after a night as `/dev/ttyUSB1`. A pin by a path that resolves to the same
device (`/dev/serial/by-id/…`, a udev name) matches too. For a printer the
section shows the last poll -- state,
temperatures, position, SD progress, filament -- with **⟳ Poll now**
(one poll, no overlay) and **Watch**, which opens the ⌨ Serial log overlay
on that port. The overlay's **🖨 identify** asks `M115` (no reset); from
then on the overlay polls the port every 2 s instead of streaming it, each
poll scheduled only after the previous one returns so a slow reply never
stacks requests. Every poll updates the panel's Device section and the
tree's badge (`🖨 210°/60° 43%`) in place -- a position edit in progress
is never rebuilt under the cursor -- and a poll that moved the node's
status re-fetches the tree so the mesh recolours.

**The world wears its machines.** Every pinned, connected board stands
under a **badge in the 3D view** -- for a printer, its state, hotend and
bed, SD or host progress and a job's stage; for a devkit, what it is and
the sketch last flashed to it -- fixed to the top of the machine's envelope
and re-projected every frame, so it follows the machine as the camera
orbits, hides when the machine is out of frame or outside the level being
looked at, and dims when something stands in front of it. A click selects
the machine and, for a printer, **opens it in front of the world**: the
monitor's whole body -- cards, chart, the latch and its control pad, the
bed reading, the print from here -- in a panel tethered to the printer
(a leader line to the badge; drag it to let go), with its comms log as a
panel of its own on the left rail. It is the same module the monitor page
is made of (`apothecary/static/widgets/machine.js`), so the two hosts
have the same ids, the same chain and latch, the same confirms, and the
ring's control verbs go to whichever is open; the node ring's Device ›
Monitor opens it here rather than leaving the page. A jog from the popup
moves the nozzle marker in the world ahead of the poll that confirms it.
The badge reads the same rows the Contents badges do, so a poll from
anywhere lands in both. A printer also wears its **marks** in
the world: the nozzle marker at the position the board last reported
(tweened, as on the monitor page), the bed plane, and the newest bed
reading as a relief -- what the monitor's small board view draws, now at
the printer's node in the one scene (`apothecary/static/machine_marks.js`
is the drawing both use; `anchors.js` is the projection). This is the
first phase of the [one-screen plan](plans/one-screen-2026-09-20.md).

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
| ![The world wears its machines: a badge above the printer](generated/printer-monitor/screenshots/05-the-world-wears-its-machines-a-badge-stands-above-.png) | ![The machine open in front of the world](generated/printer-monitor/screenshots/06-click-the-badge-and-the-machine-opens-in-front-of-.png) |
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

### The ring

Everything the Device section and the monitor's buttons do is also on the
**ring**: right-click a piece (in the 3D view or its Contents row), press
`m` with a piece selected, or press the toolbar's **⌗ Ring** button. The
ring is rad's radial menu, and it addresses **nine cells numbered as a
numeric keypad** -- the same rule on every host, so a choice can be written
down and repeated:

```
7 8 9        up-left     up    up-right
4 5 6   =    left       BACK   right
1 2 3        down-left  down   down-right
```

Eight cells hold options and cell 5 never does: it backs out one level and
closes the ring at the top. Options are seated cardinals first, `8 6 2 4`
and then the corners `9 3 1 7`, so a four-option ring sits at up, right,
down and left. A digit chooses its cell from anywhere; an arrow moves the
highlight to the nearest occupied cell in that direction; `5` or Backspace
backs out; Escape closes; Enter commits. Cells with nothing in them are
drawn faint and cannot be chosen.

The node ring, on a piece with a board pinned to it, gains a **Device**
option in cell 2 (after Zoom in and Move), which opens the device ring; on
the monitor page the device ring is the top ring, titled by the port:

```
   Device ring                     Control ring (printers only)
 7:Control    8:Watch    9:Pin|Unpin    7:Arm|Disarm  8:Heat  9:Print
 4:Query      5:back     6:Poll         4:Level       5:back  6:Home
 1:Link       2:Monitor  3:Rescan       1:Stop        2:Jog   3:Motors
```

Link opens `8:Reconnect  6:Reset  2:Release` (the same cell 1 on a devkit,
which has no Control); Heat opens `8:Hotend on  6:Hotend off  2:Bed on
4:Bed off  9:Fan on  3:Fan off`; Home opens `8:All  6:XY  2:Z`; Print opens
`8:Resume  6:Pause  2:Abort  4:Send file` (the three verbs go to whichever
print is running, the card's or the one streamed from the host); Motors
opens `8:Off  6:Quickstop  2:Break wait`; and Jog is seated so **the keypad
is the jog pad**, as Level is
seated so **the keypad is the bed** (the corners are the bed's corners, seen
from the front; Probe and Read are the cardinals, Mesh on and off the other
two):

```
      Jog                        Level
 7:        8:Y+   9:Z+      7:Back left  8:Probe    9:Back right
 4:X-      5:back 6:X+      4:Mesh off   5:back     6:Read
 1:        2:Y-   3:Z-      1:Front left 2:Mesh on  3:Front right
```

Stop is E-STOP and is drawn as destructive. Pin or Unpin is one cell, and
Arm or Disarm is one cell, since a board is either pinned or not and the
latch is either armed or not. (The cells above are what
`apothecary.menu.resolve` seats today; the placement rule, not this table,
is the contract.)

The digits pressed to reach an option are its **address**: from a printer's
node, `2` (Device) `7` (Control) `2` (Jog) `8` (Y+) is `⌗2728`, and E-STOP is
`⌗271`; given the same piece and the same board the same digits reach the
same thing. Every
intent the ring sends carries its address, and **every device button on the
page shows its ⌗ address** in its tooltip (`data-address` on the element),
so the button you already know teaches you the digits that replace it.
Control verbs chosen from the ring go through the monitor's own control
chain -- the latch, the allowlist, the confirm on Abort and E-STOP -- exactly
as the buttons do; the ring never opens a port by itself.

The canvas ring (right-click empty canvas, or `m` with nothing selected)
also carries **Panels**: one cell per panel the page has -- Contents,
Selected, Jobs, Validation, OpenSCAD -- each toggled by its address
(`⌗98` is Contents at the root), and **Rail**, which hides and shows the
rail as the **tilde key** does. The panels are the side column, now a
rail of windows standing in front of the world: each closes to a tab,
collapses, floats free and drags (a free panel resizes from its corner),
docks back, and has a body height you drag; the rail itself has a width
you drag from its inner edge (never more than half the page, so the
world is never pushed off the screen), hides on `~` and comes back on
`~` or its tab, and moves to the other side of the page by its grip or
its ⇄ button, every panel going with it. All of it is remembered per
browser (`apothecary/static/panels.js`).
This is the second phase of the [one-screen plan](plans/one-screen-2026-09-20.md);
the machine's own windows follow.

The options come from the server: `POST /menu/resolve` is told what the ring
was opened on and what the page knows about the board under it (`{port,
printer, armed, bound}`) and hands back the ring with every option's cell;
`POST /menu/intent` is told the choice, with its address. `apothecary
census` counts the page's own controls and says how many of them are also
on the ring; that number is the migration's meter, and it falls as
ring-backed buttons are deleted.

### The focused monitor

`/firmware/monitor?port=/dev/ttyUSB2` is one printer, full width -- the
machine module (`apothecary/static/widgets/machine.js`) mounted as a page,
the same one the world opens as a popup over the printer: status
cards (state, hotend and bed with target bars, position, SD progress and
elapsed time, endstops and filament, the board and its link), a temperature
history chart over the last polls (hotend and bed on one °C axis, targets
dashed, crosshair tooltip), and the port's **comms log** -- every command
and reply, boot banner and link event, kept on the server per port so it
survives a page reload, shows polls made by other clients, and is not lost
when the link is reopened. *Poll traffic* is hidden by default so the log
reads as a story (open, `M115`, your queries, resets); tick it to see every
`M105`. The log downloads as a text file.

**The board in its printer.** When the port is pinned to a node, a card
draws that board where it sits: the printer's own OpenSCAD geometry as a
translucent outline, the board solid, the build volume as a wire box on the
printer's base, and a nozzle marker at the position the last poll reported.
The marker *moves* rather than jumps -- each poll tweens it, and a jog from
the control overlay or the ring moves it the moment the jog is sent, ahead
of the poll that confirms it -- so the control page shows the motion it
commands. A bed reading, when the page has one, is laid over the bed as a
relief (see [Bed leveling](#bed-leveling)). The firmware page's device cards draw the same view, small, for
any port pinned somewhere (a devkit on the bench as much as a mainboard in
a printer). `GET /firmware/printers/where?port=…` is what both ask: the
site, the board's node and the printer above it, with world positions,
footprint, build volume and base height. Without OpenSCAD on the server the
shapes are unavailable and the card says so, keeping the volume and the
marker.

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

![The focused monitor](generated/printer-monitor/screenshots/10-monitor-opens-the-focused-view-status-cards-temper.png)

### Control, behind a latch

The monitor's **⚙ Control** toggle arms a per-port latch and opens a control
overlay: hotend and bed targets, fan, home (all/XY/Z), a jog pad with a
step size and feedrate, motors off, quickstop, SD start/resume, pause and
abort, mesh on/off, break wait, and the Bed level card's probe and corner
moves. Disarmed -- the default, and what a **Release** or a
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
`M410`, `G29` (the plain probe) and `G30 X.. Y..` (one point, on the
bed). A jog from the pad is three lines (`G91`, `G1 …`, `G90`) so the
board is always left in absolute mode. Out-of-bounds values are refused
before they reach the port; there is no job streaming, no EEPROM write, no
firmware configuration. Control traffic is amber in the comms log, tagged
`control`; a file streamed from the host goes past this list as a whole,
checked once before the first line (see [Printing without an SD
card](#printing-without-an-sd-card)).

```
POST /firmware/printers/control  {"port": …, "armed": true, "ttl_s": 300}
POST /firmware/printers/command  {"port": …, "command": "M140 S60"}   → 409 unless armed
GET  /firmware/printers/controls                                     → the allowlist and bounds
```

### Bed leveling

The monitor's **Bed level** card reads the bed the way a person trams it:
as a mesh, a tilt, and four corners. **Read mesh** asks the board for the
mesh it has stored (`M420 V`), the probe offset (`M851`) and the current
temperatures, and saves the three together as a *bed reading*; it moves
nothing and needs no latch. **Probe bed** homes (`G28`), probes (`G29`) and
then reads the same way -- it travels the whole bed, so it needs control
armed and asks once before it starts. A probe takes minutes on a real bed,
so it runs as a **job** that holds the port: while it runs the state card
says `leveling: probing`, polls answer from the last poll without queueing
behind the probe, queries and control lines are refused with `409`, and the
emergency stop still goes through. When the job is done the card shows the
reading and a poll follows.

A reading is drawn as a **heatmap** the way the bed lies (the back row on
top, blue below the mean and amber above, the same two hues as the
temperature chart), with the range, the tilt across X and Y as a
least-squares plane through the points, and each **corner against the
mean** -- which is what a turn of a bed screw changes. Every reading is
kept, with every line the firmware said, under `~/.apothecary/leveling/`
(`APOTHECARY_STATE_DIR` moves it), and the card's history lists the port's
readings newest first; pick one to see it, or download it as JSON. Comparing
the range before and after a turn of the screws is the whole method.

The reading is also drawn **in the world**: the *Board in its printer*
card (and the firmware page's card) lays the mesh over the bed as a relief
-- a surface through the probed points, its lowest point resting on the
bed and the rest lifted by their height above it, stretched ×10–×50 so a
couple of millimetres can be seen at all (the note says by how much), in
the heatmap's own two hues, with a post at each corner down to the bed.
Marlin prints the grid without its positions, so where it lies is an
estimate: the bed less what the probe's offset puts out of reach, inset by
Marlin's default 10 mm. It follows whichever reading the card shows.

![Bed level: a probed mesh as a heatmap, with its range, tilt and corners](generated/printer-monitor/screenshots/12-bed-level-probe-bed-homes-and-probes-armed-and-ask.png)

![The reading laid over the bed in the board view](generated/printer-monitor/screenshots/13-the-reading-is-drawn-in-the-world-too-the-board-vi.png)

The four **corner buttons** move the nozzle to that corner of the bed at
paper height (`Z0.2`, 30 mm in from the edges of the build volume, lifted
to `Z5` on the way) for a tramming check with a sheet of paper; they are
controls, so they need the latch, and they go out through the same chain
as a jog. On the ring the Level cell is seated so the keypad is the bed:
from the monitor `7` (Control) `4` (Level) `1` is the front-left corner and
`⌗748` is Probe.

```
POST /firmware/printers/level     {"port": …, "probe": true, "note": "…"}   → 202, the job
GET  /firmware/printers/level?port=…                                       → the job's stage
GET  /firmware/printers/leveling?port=…                                    → readings, newest first
GET  /firmware/printers/leveling/{id}                                      → one reading, with the mesh and every line
```

The mesh parser (`firmware.gcode.parse_meshes`) reads Marlin's printed grid
-- the bilinear grid and, when the firmware prints it, the subdivided one
-- and falls back to the `G29 W I.. J.. Z..` points an `M503` prints, so a
board that stores its mesh in EEPROM reads too. The simulated printer
answers `G29`, `M420 V`, `M851` and `G30` with a bed that is slightly
tilted and a little bowed, so the card can be tried without a machine.

### Printing without an SD card

The monitor's **Print from here** card streams a sliced G-code file to the
printer over the held link, so a machine with no card reader, or a card
nobody wants to walk across the room, still prints. Pick a file and it is
**kept** on the host (`~/.apothecary/prints/`) and **checked** before
anything is sent: a file that saves settings (`M500`), factory-resets
(`M502`), updates firmware (`M997`), kills or restarts the board, or asks a
heater for more than the seam's caps (300 °C hotend, 130 °C bed) is listed
with the reason and refused; the rest are listed with their line count.
**Print** needs control armed, asks once, and starts a **job** that feeds
the file one line at a time, each after the firmware's `ok` -- the same
flow control every host uses, so the planner stays fed and the host never
runs ahead of the machine. A heat-and-wait or a home is given the minutes it
needs; any other line that goes unanswered for thirty seconds, or that the
board answers with an error or a resend, ends the print.

While it prints, the state card reads *printing* with the progress, the
card shows the line count, the elapsed time and the line in flight, and
polls keep coming between lines -- a poll that would have to queue behind a
slow line answers from the last one instead. Heaters, fan and break-wait are
still yours from the overlay (a hotend a few degrees off is fixed
mid-print); motion, SD, homing and the bed are the job's, and a release,
reconnect, reset or firmware upload on that port is refused until the print
ends. **Pause** stops the feed (the printer finishes what it has queued),
**Resume** needs the latch, **Cancel** stops the feed and sends the
safe-off -- `M104 S0`, `M140 S0`, `M107`, `M84`: heaters and fan off,
motors free, no blind park. A failed line does the same. **E-STOP** halts
the board and the job ends with nothing more sent.

The stream stays out of the comms log (a print is thousands of lines and
the log is for reading); the log says when a print starts, every 500 lines,
what the board objected to, and how it ended. Every print is a **record**
(`~/.apothecary/prints/records/`) with its outcome -- done, cancelled or
failed -- the lines sent, and the tail of what the firmware said; the
card's history lists the port's prints newest first. On the ring, the
Control ring's **Print** cell (`9`) carries Resume, Pause and Abort to
whichever print is running -- the card's or the one from here -- and
**Send file** (`⌗794`) starts the chosen file.

![Print from here: a kept file streaming, with its progress](generated/printer-monitor/screenshots/14-print-from-here-a-sliced-g-code-file-is-kept-on-th.png)

```
GET/POST /firmware/printers/prints?name=…    the kept files; keep one (the body is the file)
DELETE   /firmware/printers/prints/{id}
POST     /firmware/printers/print            {"port": …, "file_id": …}  → 202, the job (latch required)
GET      /firmware/printers/print?port=…     the job's stage and progress
POST     /firmware/printers/print/pause|resume|cancel   {"port": …}
GET      /firmware/printers/print/records?port=…        prints from here, newest first; /{id} in full
```

What this is not: a queue, a slicer, a webcam or a timelapse. One print at
a time, from a file already sliced, watched from this page; see the
*G-code printer seam* record's sixth decision for where the line is drawn.

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
are plugged in, and a port comes back with whatever number is free after a
replug. Pins do not mind: they are kept as the bridge's USB serial number
(above), and `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A106ZTEU-if00-port0`
is a name Linux gives every bridge with a serial, usable for a pin and for
`apothecary firmware printer` with no setup. For a short name a udev rule
names the printer by that serial number (`apothecary firmware devices` and
the firmware page show it as `S/N`; `udevadm info -q property /dev/ttyUSB1
| grep ID_SERIAL_SHORT` on Linux):

```
# /etc/udev/rules.d/99-apothecary-printer.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ATTRS{serial}=="A106ZTEU", SYMLINK+="ender"
```

Then `sudo udevadm control --reload && sudo udevadm trigger`, and
`/dev/ender` names the board. Note arduino-cli lists only the kernel
names, so the device panel and the monitor's port picker still show
`/dev/ttyUSBn`; the symlink is for the CLI and for other programs. Not
required.

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
| `POST /printers/level`, `GET /printers/level?port=…` | start a bed reading as a job (`{"port": …, "probe": true}`; a probe needs the latch and answers `409` without it, or while a job holds the port) and ask its stage |
| `GET /printers/leveling?port=…`, `GET /printers/leveling/{id}` | saved bed readings (mesh, stats, probe offset, temperatures), newest first, and one in full with every line the firmware said |
| `GET/POST /printers/prints`, `DELETE /printers/prints/{id}` | the G-code files kept on the host (`POST ?name=…` with the file as the body; checked, listed with problems), and forgetting one |
| `POST /printers/print`, `GET /printers/print?port=…`, `POST /printers/print/pause|resume|cancel` | stream a kept file to the printer (`{"port": …, "file_id": …}`; latch required, `409` while a job holds the port), the job's progress, and the three verbs (pause and cancel need no latch) |
| `GET /printers/print/records?port=…`, `GET /printers/print/records/{id}` | prints streamed from here, newest first, and one in full |
| `GET /sites/{name}/devices?fresh=1` | (site API) the bindings view; `fresh` forces a port rescan -- what the viewer's ↻ Devices and Rescan use |
| `POST /printers/release` | drop the held link so another program can open the port |
| `GET /printers/info?port=…` | device, held link (baud, engine, opened at), last poll, active task -- what the monitor page needs at once |
| `GET /printers/log?port=…&since=N` | the port's comms log from index `N` (`tx`/`rx`/`boot`/`sys` entries, each tagged with its origin: `poll`, `query`, `identify`) |
| `POST /printers/reconnect` | release + reopen (no reset), then poll |
| `POST /printers/reset` | reboot the board (DTR pulse); returns the boot banner |
| `GET /monitor?port=…` | the focused monitor page |
| `GET /printers/where?port=…` | (site API) where a port is pinned, with the geometry the board view draws |
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
`apothecary docs generate` turns into screenshots. The shared e2e server
sees the machine's real ports but keeps its firmware state in a folder of
its own, so a test run never edits what is pinned in `~/.apothecary`.

What the simulator cannot say, the bench does:
[`validation/2026-09-20-ender-bench.md`](validation/2026-09-20-ender-bench.md)
is the seam against a real Ender mainboard -- what was verified without
arming control, the three defects it found, and a checklist for the rest
(heaters, motion, a probe, a print from the host, the stop).

The decision record for all of this is *Firmware toolchain seam* in
`governance/qm/adr/`.
