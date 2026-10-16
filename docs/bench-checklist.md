# The bench checklist: the Ender 3 and the ESP32, for real

The suites hold every path below against the simulated printer and the
scripted devkit; this is how the same paths are confirmed on the real Ender 3
and a real ESP32 devkit. A person runs it, at the bench. No test flashes a
board or moves a printer.

Tick each box as it passes. When one fails, note the time and the port, and
download the board's log (the Machine's `⤓`): it holds every line sent and
what the board answered.

**Safety.** Stay at the printer while anything heats or moves. Keep a hand
near its own power switch: it is faster than the page's ⏹ E-STOP, which is
always there and never asks. Heat and motion only with the bed clear and
nothing printing from its own SD card.

## Setting up

- [ ] `uv sync`, then `uv run apothecary check`: OpenSCAD, the slicer and the
      firmware toolchains each say what is installed.
- [ ] What is missing, once, with the network up:
      `uv run apothecary openscad install --latest`,
      `uv run apothecary slicer install`,
      `uv run apothecary firmware install --esp32` (arduino-cli and the ESP32
      core, for the Arduino blink),
      `uv run apothecary firmware install --rust-esp32` (Rust for the ESP32).
- [ ] `uv run apothecary firmware devices`: the printer's board (an FTDI
      bridge) and the ESP32's (a CP2102 bridge), each on its own port. Note
      which is which; the port numbers can swap between plug-ins, the pins
      follow the boards.
- [ ] `uv run apothecary serve` -- your own server and state, not `--demo` --
      and open `http://127.0.0.1:8000/viewer`.
- [ ] **Pin the printer.** Select `printer_1` in Site. Its Device section lists
      the free ports: choose the printer's, **Pin**. The pin goes to the
      printer's mainboard, and when nothing is printing the page asks the
      board once what it is (M115): the status line says *asked it once what
      it is: Marlin …*, and `printer_1` wears its ⚡ badge.
- [ ] **Pin the ESP32.** Select `esp32_blink`, choose the ESP32's port,
      **Query**, **Pin**: `esp32_blink` wears its ⚡ badge.

The ring opens with **Ctrl + right-click** (or `m` on the selection). The
addresses below are cells pressed in order on a numeric keypad. Inside a
Machine, Ctrl + right-click opens the board's own ring (the device ring); from
`printer_1`'s ring the same cells sit under Device, cell 7 (`⌗7…`).

## A. The link, nothing armed

- [ ] Open the printer's Machine: click its ⚡ badge, or `printer_1`'s ring ›
      Device › Open (⌗78). It docks in the rail: state `idle`, temperatures
      near the room's, the chart filling after a few polls.
- [ ] Pull the filament out of the runout sensor: within one poll the endstop
      chip reads `filament OUT`; push it back → `present`.
- [ ] **⏻ Reboot**, pressed twice (the button says *again to reboot* after the first press), or the
      ring's Link › Reboot (⌗16): the boot banner lands in the log, the link
      is kept, the next poll answers.

## B. Armed: heat

- [ ] **⚙ Control**: the overlay opens and counts down from 5:00; the ring's
      Control › (⌗77) reads *Disarm*.
- [ ] Bed **45** → Set: `M140 S45` in the log, the bed card's target `/45°` on
      the next poll, the bar filling. **Off** → target 0.
- [ ] Hotend **150** → Set; watch it climb; **Off**. (Below printing
      temperature on purpose: nothing extrudes.)
- [ ] Fan to about 128 → Set: the part fan spins; **Off**.
- [ ] **900** in the hotend box → Set: refused before the port (`above 300` in
      the log, no `M104 S900` line).
- [ ] Five minutes with no command: the latch lapses, the overlay closes.

## C. Armed: motion

- [ ] **Home XY**, then **Home Z**: X and Y home, the probe touches at the
      bed's centre, the position card reads X0 Y0 and a Z.
- [ ] Step **10**, **Y+**: the bed moves 10 mm; the nozzle marker over the
      printer in the world moves when the button is pressed, and the position
      card confirms within one poll. The ring's Control › Jog › Y+ (⌗728) does
      the same. **Y−** twice, then Motors › Off (⌗738).
- [ ] The bed level card's corners, **FL**, **FR**, **BL**, **BR**: the nozzle
      parks at each corner at paper height; slide a sheet of paper under it.
      The stored mesh predicts the right side high and the left low; adjust
      the screws to what you find. **Home Z** afterwards.

## D. Armed: levelling

- [ ] **▤ Probe bed**, or Control › Level › Probe (⌗748) → the dialog → the
      state card reads `leveling: homing`, then `probing`; the temperatures
      keep updating; a jog pressed meanwhile is refused (*a bed reading holds
      the port*). When it reads `saved`, the heatmap redraws and the history
      has a *probe* row: compare its range with the last one.
- [ ] **Mesh on**, then **Read mesh** (⌗746): the record says *leveling on*.
      Apothecary never writes the printer's EEPROM; to keep a mesh across a
      power cycle, store it from the printer's own screen.

## E. Print from here

- [ ] *Print from here* → **Choose File** → `docs/validation/dry-run-square.gcode`
      (nothing in it heats or extrudes): it lists as `dry-run-square.gcode ·
      23 lines`.
- [ ] A file that must be refused -- any `.gcode` with an `M500` line -- lists
      as *refused: line N: M500 saves settings to EEPROM*, and **▶ Print**
      stays refused for it.
- [ ] **▶ Print**, or Print › Send file (⌗794) → the dialog → the head homes
      and traces a 60 mm square 10 mm above the bed; the card shows the line
      in flight; the status line says the print started.
- [ ] **⏸ Pause** mid-square (⌗796): the head finishes what was queued and
      stops; **Resume** (⌗798).
- [ ] **■ Cancel**, pressed twice: `M104 S0`, `M140 S0`, `M107`, `M84` in the
      log; the history and Site's Jobs read *cancelled*; the status line says
      the print ended.
- [ ] Print it again to the end: *done · 23/23*, `dry run done` on the
      printer's screen, the state back to `idle`.

## F. Slice, then print a real piece

- [ ] Choose a part under *makes* in *Print from here* (or a made piece's
      ring › Slice) → **Slice**: OrcaSlicer's log in the card, then the kept
      G-code chosen, each setting with where it came from, and the slicer's
      estimate of time and filament.
- [ ] Before printing it, read the G-code's start in the card's file list
      (or the kept file): `G28` before the first extrusion, nothing added to Z.
- [ ] With filament loaded: **▶ Print** it, and watch the first layer. Note
      any stutter on long straight moves.
- [ ] Optional, with a camera over the bench: the loop of walkthrough page 03
      on the real hardware -- Camera › Add here, Device, Take picture, Find
      shapes, Make, Part › Edit, Slice, Print.

## G. Stop, and let go

- [ ] With the printer idle, **⏹ E-STOP** (⌗71): it never asks; `Error:Printer
      halted. kill() called!` in the log, the next poll `offline`. **⏻ Reboot**
      brings it back.
- [ ] **Release**: the link drops, the latch with it; `uv run apothecary
      firmware printer <the printer's port>` from a terminal answers without a
      boot banner; **⇄ Reconnect** in the Machine holds it again, also
      without one.

## H. The ESP32: the Rust blink, and the Arduino one beside it

- [ ] The **Bench** tab (or Panels › Bench › Bench, ⌗438): its toolchain card
      shows *Rust for the ESP32*, installed, with cargo's and espflash's
      versions; its install cell is Panels › Bench › Install › Rust ESP32
      (⌗4366). Choose sketch **esp32_blink@rust-esp32 · esp32** and the
      ESP32's port -- check it is not the printer's.
- [ ] **Compile** (⌗432): the log shows `cargo build --release --offline`
      and, last, *no build path in the image*. With the network unplugged,
      Compile again: it still builds.
- [ ] **Compile & upload** (Bench › Upload, ⌗434) → the dialog → espflash ends
      *Flashing has completed!*; the LED on GPIO 2 blinks once a second.
- [ ] `esp32_blink`'s ring › Device › Open (⌗18): the Sketch card reads
      *should run esp32_blink@rust-esp32 · esp32*. Device › Query (⌗14): the
      log says *heard esp32_blink say hello*, and the card *✓ matches*.
- [ ] **Listen** (⌗114): `apothecary esp32_blink: hello`, the chip line, then
      `blink 1`, `blink 2`, … once a second, the hello and chip line again
      every ten blinks. Note the chip line exactly.
- [ ] Flash **esp32_blink@arduino · esp32:esp32:esp32** the same way and
      compare: every line should read the same as the Rust build's. A
      difference is a defect of the Rust one.
- [ ] **Release**, then Device › Flash (⌗12): the Flashing card starts from
      the sketch the board should run.
- [ ] With arduino-cli out of the way (`ARDUINO_CLI=none uv run apothecary
      serve`): the ESP32 is still found -- its Machine says *found by
      rust-esp32* -- and **Listen** still hears the hello. Note whether opening
      the port reset the board; it should not. **Probe** asks espflash for
      the chip and its MAC (this one resets it).

## Results

| Section | Date | Passed | Notes |
|---|---|---|---|
| Setting up | | | |
| A. The link | | | |
| B. Heat | | | |
| C. Motion | | | |
| D. Levelling | | | |
| E. Print from here | | | |
| F. Slice and print | | | |
| G. Stop and let go | | | |
| H. The ESP32 | | | |
