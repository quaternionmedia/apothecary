# The router: an AnoleX 4060-Evo Ultra 2 beside the Ender

The garage has two machines that make things: printer_1, a Creality Ender 3,
and cnc_router, an AnoleX 4060-Evo Ultra 2, a desktop CNC router. Each is
drawn as the machine is, from published dimensions; each has a board inside
it that a serial port is pinned to; each is polled over a held link, driven
while a control latch is armed, and runs a streamed job. The printer's half is
[firmware.md](firmware.md#printers-boards-that-already-run-a-g-code-firmware);
this page is the router's, and says where the two differ.
[Walkthrough page 19](../walkthrough/19-the-router.md) runs what this page
describes.

## The machine

[`parts/anolex_4060_evo_ultra_2`](../parts/anolex_4060_evo_ultra_2/README.md)
is the router as a part: a moving-table machine cutting 400 x 600 x 80 mm,
HGH15 linear rails and 1204 ball screws on each axis, NEMA 23 closed-loop
steppers, an 800 W trim router (8,000 to 24,000 rpm, set by a dial on the
router, started and stopped by the controller) in a 65 mm clamp on the Z
plate, and the control box at the back of the base. Its SCAD says which
numbers are the maker's specifications and which are taken from its listed
footprint or chosen; the axes are parameters, so the garage draws the tool
where a poll says it is.

In the garage (`apothecary/example_hierarchy.py`) the router stands on a
steel stand of its own, `cnc_stand`, beside storage, as printer_1 stands on
the workbench. Its working area is its `build_volume` and the tool's
(0, 0, 0) on the table, at the working area's front-left corner, its
`build_origin`. Inside, it is built as printer_1 is: `cnc_router.frame_system`
is the control box and `cnc_router.frame_system.controller` the board the
port is pinned to, drawn as the board it is assumed to be
([`parts/boards/anolex_grbl_esp32`](../parts/boards/anolex_grbl_esp32/README.md):
the maker publishes no drawing of it, and the board's README says what is
assumed); `cnc_router.gantry_system` is the gantry on the Y rails, its legs
and cross beam, with `z_carriage_system` inside it, the X carriage plate, the
Z plate, the clamp and the spindle in it, each placed from the part's own
constants where the part draws them at its default axes. Stepped into, the
router is its part, whole, with the control box and the gantry drawn inside
it, each a double-click further in ([viewer.md](viewer.md#the-world)). `ROUTER_STATUSES` are
the words the router's node takes: `idle`, `running`, `hold`, `alarm`,
`offline` from its polls, and `maintenance` by hand.

## The controller and its dialect

The 4060-Evo Ultra 2's controller is an ESP32 running Grbl_ESP32, which
reports as `Grbl 1.3a`, reached over USB (and, by its own web page, over
WiFi, which Apothecary does not use: nothing leaves this machine). It speaks
GRBL's dialect of G-code, the one grbl 1.1 on an Arduino, FluidNC and grblHAL
speak too, and every sender (UGS, Candle, bCNC, LightBurn) understands: a
line out, `ok` or `error:N` back, and a few single characters the controller
acts on at once, outside the line queue. `apothecary/firmware/grbl.py` is
that dialect; `gcode.py`'s held link, comms log, control latch and registry
of links are shared with the printer's, so a router's port is opened, kept
and released exactly as a printer's is.

| | A printer (Marlin, `gcode.py`) | The router (GRBL, `grbl.py`) |
|---|---|---|
| Identified by | `M115` | `$I`; a GRBL controller answers `M115` with `error:20`, so Marlin's is tried first and GRBL's when nothing Marlin answers; a board answering neither is refused with both objections |
| Polled by | `M105`, `M114`, `M27`, `M119`, `M31` | the realtime `?` (a status report, no `ok`) and `$G` (the modal words) |
| Its state | `idle`, `printing`, `offline` | the controller's own word (`Idle`, `Run`, `Jog`, `Home`, `Hold:0`, `Door`, `Alarm`), folded to `idle`, `running`, `hold`, `alarm`, `offline` |
| What a poll carries | temperatures, position, endstops, filament, SD progress | machine and work position and the offset between them, the spindle's speed and whether it is on, the feed, the input pins on (limits, probe, door, hold), the alarm's number, the overrides |
| Typed while armed | heaters, fan, homing, bounded jogs, SD pause/resume/abort, the bed | homing (`$H`), unlock (`$X`), jogs (`$J=`), bounded moves, the spindle on at a speed (`M3 S`) and off, work zero here (`G10 L20 P1`), a probe down (`G38.2`), a move in machine coordinates (`G53 G0`: the tool to the top of Z, a table map's points), and the realtime `HOLD`, `RESUME`, `JOG-CANCEL` |
| The bounds | hotend 300 °C, bed 130 °C, a move 300 mm, feed 12000 | a move 600 mm, feed 4000 mm/min (the maker's figure for X and Y), the spindle 24000 rpm, a probe 80 mm deep at 500 mm/min at most |
| The stop | `M112`, always accepted | `RESET`, the soft reset (`0x18`), always accepted: everything halts, the queue empties, the spindle is off, and a reset in motion leaves the controller in alarm until unlocked or homed |
| Report-only queries | `M503`, `M119`, `M20`, `M420 V` ... | `$$` (settings), `$#` (offsets, the probe's last touch), `$G`, `$I`, `$N`, `?` |
| A bed reading | Read mesh, Probe bed; the mesh as a heatmap, and as a relief over the bed in the world | a table map: Probe table turns the spindle off, homes, and at each point of a grid inside the working area goes there in machine coordinates at the top of Z (`G53 G0`), probes down to the touch plate (`G38.2`) and lifts; the touches, in machine coordinates, kept, listed and drawn as a printer's reading is, the relief where the points were probed; a stored mesh (Read mesh) is Marlin's, refused for a GRBL board before the port, and never a printer's reading kept under a port name the router took ([firmware.md](firmware.md#bed-leveling)) |
| A streamed job | a print, from the slicer's G-code | a cut, from a CAM post's `.nc`, `.ngc`, `.gcode` or `.tap`, refused for a `$` line, a tool change (`M6`), a stop (`M0`, `M1`), a spindle over the cap, a code GRBL does not take (a printer's `M117`, `G29`), or a dwell over a minute (`G4 P` is seconds to GRBL, milliseconds to Marlin); kept for a router, and sent to nothing else; a pause holds the controller (`!`) so it stops where it is, a cancel holds and resets; a line is answered when queued, so the host counts the planner's room from the status report (`Bf:`) and never blocks the port on a full one, and the cut is done when the controller is idle again after its last line (`finishing`) |
| Its job's word | `print`, the node `printing` | `cut`, the node `running` (`apothecary/jobs.py`) |

Machine coordinates on a Grbl machine count from the switches it homes to, axis by
axis: an axis that homes toward its maximum counts down from that switch, and is at
`mpos + travel` in the working volume; one that homes toward its minimum (its bit of
`$23` set) counts up from that switch, and is where it says it is. The AnoleX's X is
of the second kind -- homed, it reads X 0.9 -- and its Y and Z of the first. A poll
carries the machine position, the work position the person's zero gives, and
`tool_position`, the tool in the working volume each axis counted up from its low end,
worked out from the controller's own `$23` and `$130` to `$132` (`grbl.in_volume`);
`work_origin` is the work zero in the same volume, and `travel` the volume. The world
and the Machine place the tool, and a file's zero, by those. The AnoleX's table carries
Y (the part's `bed_moves_y`, as the Ender's bed does): the tool's mark stands still
along Y and the working volume, the table map and a file's path ride under it. The world
draws the router -- and the printer -- as its pieces, as the part's `kinematics` says:
what stands still, and each of what moves (the AnoleX's table, X carriage and Z slide;
the Ender's bed, X gantry and hotend carriage), each rendered once at the part's own
axes (`POST /parts/{ref}/stl/generate` with its `piece`). As the tool's mark tweens
toward each poll, each piece is moved with it by how far its axes stand from the
part's, within the part's range, so the machine moves as the real one does, a poll
behind it. The world polls the router it draws while no Machine is open on it and the
server holds its link, and its Machine's polls while one is; until a poll carries
`tool_position` no tool is drawn, and the working volume is the controller's `travel`
once it has said it ([viewer.md](viewer.md#a-machines-frame)). The polls mean the table
only once the machine has been homed: before that the controller counts from wherever
it stood at power on.

The same routes serve both: `POST /firmware/devices/identify`,
`GET /firmware/printers/status`, `/printers/control`, `/printers/command`,
`/printers/query` and `/printers/queries?port=` (the dialect's list),
`/printers/prints` and `/printers/print`; the `printers` in their paths is
the G-code machine seam's, which a router is in. A poll is kept in the
evidence log as a printer's is (`apothecary/evidence/printers.py`), the
router's state, the controller's word, both positions, the spindle and the
pins as observations of `garage:cnc_router` and its `#spindle:main`, by
`router poll: ?, $G`. `apothecary firmware printer PORT` identifies a router
and polls it once, saying the controller's word, the spindle and the work
position; `--query '$G'` and the other GRBL queries work there.

Which dialect a port is driven in is what the board on it answered as, and a
port's name moves between boards: the router can come up on the port the
printer held yesterday. The printer's record does not count for it
([docs/firmware.md](firmware.md#a-record-is-one-boards-not-its-ports)), so the
router is a board nothing has identified -- a line either dialect has is taken,
`--query '$I'` reaches it, and it is asked what it is before a control line or
a stop goes. Its stop is then its own: a stop asked in either word goes as
`RESET`, so a printer's `M112`, which a GRBL controller answers `error:20` and
goes on cutting, is never what reaches it. The same holds the other way round:
a printer on a port the router held is sent `M112` for a `RESET`.

### A home is proved first

A home drives an axis at the seek rate (`$25`) until its limit switch closes, for up to
one and a half times its travel, and nothing else stops it: it goes toward the table if
the axis is wired the other way round, and into its end stop if the switch says nothing.
So `$H`, `$HX`, `$HY` and `$HZ` are sent only for axes the open port has shown two things
of (`grbl.check_home`), whoever asks -- the pad, the ring, the deck, Probe table's own
home:

- **its switch**, reported on and then off again in the status report's pins: press it by
  hand for two seconds while the Machine polls, and let go. With hard limits on (`$21=1`)
  that puts the controller in alarm (`ALARM:1`), which Unlock or the home clears;
- **which way it goes**: the axis jogged a millimetre the way the controller says it homes
  (`$23`), with a person watching the tool. For Z that is the way it must rise.

A home that is not proved is refused before the port, in words: which way the axis will
seek, how fast and how far at most, from the controller's own settings, and which of the
two is missing. What a port showed is kept while it is open and gone when it is opened
again, a replug or the controller's power included. The simulated router has no switch
for a hand to press, and its homes are held to none of this.

### A cut needs the tool placed

After its power is cycled a controller reports its machine position as zero wherever
the tool stands, and the work zero it kept is an offset from that: a cut's coordinates
are only as true as the last home, or the last work zero set here. So a cut is refused
(`grbl.not_placed`) until each axis has, on the open port, been homed (`$H`, or its
own `$HX`, `$HY`, `$HZ`) or given a work zero (`G10 L20 P1`, or the touch plate's Z).
What a port showed is gone when it is opened again, and taken away by a banner nothing
here asked for (the controller's power cycled, its button pressed) and by a reset in
motion (`ALARM:3`, the controller's own word that its position may be lost). A reset
this server sent to a controller standing still keeps it. While an axis is not placed
the poll's `todo` says which and since when, and the Machine's Needs you card shows
it. The simulated router is held to none of this.

### What a cut leaves

A cut is done when its controller is idle again after its last line. One whose
controller ends in alarm, or is still running when a move's time has run out, failed,
and is held and reset as a cancelled one is. A cut that is done sends `M5`: a file
that never says it does not leave the spindle turning. A pause that lands while a
line waits for room in the planner keeps that line: resumed, the cut sends it and
then the rest; room that never comes within a move's time fails the cut, and no line
is left out. A hold or a resume typed at a cut is the cut's own pause and resume.
A controller that restarts under a cut is known by its banner, and the cut fails
there. A table map can be stopped: the stop, or the server stopping, holds and
resets the router under it, and no further point is probed.

### What the state asks of a person

What stops a person is in the machine's state, for the page, the deck and a program alike,
and not only in a line of the log. A poll (`GET /firmware/printers/status`) carries
`refused`, the last control line the port refused or its board objected to, with why and
when, until a line goes; `todo`, what must be done before the machine moves again -- a
controller in alarm takes no jog until Unlock (`$X`) or a home; and `homing`, for each
axis which way a home will seek, how fast and how far, and whether its switch has been
seen and the axis jogged that way. The Machine shows the first two in a **Needs you**
card, there only while there is something, and the third beside the Home buttons, each
axis with what to do first; a Home not yet proved is greyed, with the controller's own
figures for it in its tip (`can`, docs/firmware.md), and so is a jog while it is in alarm. `refused` is a printer's
too.

### The plate's thickness

The touch plate is a puck the bit comes down on, and the touch is called the plate's
thickness, so that Z 0 is the stock's top under it. The thickness is a person's to
measure: the maker's nominal figure is 19 mm and its manual's own example measures 19.08
([manual.json](../parts/anolex_4060_evo_ultra_2/manual.json), the Z probe). It is kept
for the machine's board (`GET` and `PUT /firmware/printers/plate`), the nominal until one
is kept, and the pad's **plate** field holds it.

**Probe Z to plate** is one control line, `PROBE-PLATE Z<thickness> D<depth> F<feed>`,
bounded as a probe is and by a plate of 50 mm at most: the bit comes down the depth at
most until it touches, the touch is written to the work zero as the plate's thickness
(`G10 L20 P1 Z<thickness>`), and the bit lifts 5 mm. The manual's sender sets the touch
with `G92`, which a soft reset forgets; a stop here is a soft reset, so the zero is
written where **Z zero here** writes it and a stop does not take it. A probe that touches
nothing sets nothing and says so, with the controller in alarm as after any probe that
finds nothing. The pad's *How to zero Z with the touch plate* is the manual's procedure
with one step added: the clip touched to the plate by hand first, to see **Pins on** show
the probe before the bit is trusted to stop on it.

## Simulated

`APOTHECARY_SERIAL_ENGINE=simulated` answers every port as the simulated
Ender; the ports `APOTHECARY_SIMULATED_ROUTER` names (comma-separated) answer
as the simulated router instead, a pretend Grbl_ESP32 (`grbl.SimulatedRouter`):
it homes, unlocks, jogs and moves, its moves and dwells queued fifteen deep as
Grbl's planner holds them -- a line is answered `ok` once queued, the queue
runs in its own time, each move the time its distance and feed say
(`APOTHECARY_SIMULATED_SPEED` scales it, `0` skips it), and a line that finds
the queue full waits for room -- holds and resumes, runs its spindle, takes a
work zero, probes a plate 20 mm under the tool, answers `$I`, `$$`, `$#`,
`$G` and `?`, and goes into alarm on a reset in motion or a move past its
travel. It starts idle with the tool over the
middle of the table, as the part draws it; `APOTHECARY_SIMULATED_ROUTER_STATE=alarm`
starts it as a real one powers up with homing enabled, in alarm until homed.
`tests/test_firmware_grbl.py` holds the dialect against it, and says that its
replies follow grbl 1.1's interface and Grbl_ESP32's report code rather than a
recording of the garage's router.

## In the page

A board identified as a router has a router's Machine: the same window and
head as a printer's -- auto-poll, Poll (`?` and `$G`), Reconnect, `$I`,
Reboot, Release, ⚙ Control and ⏹ E-STOP, which is the soft reset -- and its
own cards in Status: the state and the controller's word, the tool in the
work zero and in machine coordinates, the spindle, the feed and the
overrides, the input pins on. Armed, its control pad holds Motion (the jog
pad, `$J=` at the feed set, Home `$H` and Home X, Y and Z (`$HX`, `$HY`, `$HZ`), Unlock `$X`, Top of Z, Go to zero,
Stop jog), Spindle (On at a speed, Off), Zero and probe (XYZ zero here, Z
zero here, Probe Z down a depth), and Cut (Resume, Hold, Abort). Its Table
map window, where a printer's is Bed level, takes the map (Probe table, armed,
the probe's lead clipped to the table; the card says how many points are
done) and shows the one kept: the touches as a heatmap, the range, the tilt
and the corners against the mean, where the grid lies, and each map in its
history; the world lays the one shown over the table
([firmware.md](firmware.md#bed-leveling)). The Cut window,
*Cut from here*, is a printer's Print with a router's words, in the loop's
order: what it makes and its Toolpath ([docs/cam.md](cam.md)) where a printer has
Slice, the file, kept and checked, or a CAM post's, then ▶ Cut, Pause (a hold),
Resume, Cancel (a hold and a reset), the cut's progress with the operation it is
in, what the file holds, and the router's jobs, each control there once what it
needs holds (Toolpath once a part is chosen, ▶ Cut once a file is, Hold and
Abort while a cut runs, Resume while it is held;
[walkthrough page 24](../walkthrough/24-a-cut-from-the-card.md) pictures each). Under a
toolpath that names what to measure -- the 😮 of `parts/router_emoji`, cut to calibrate
the router -- **measured** takes what the piece measures and Keep keeps the tool's
allowance it makes for the router's next toolpaths
([docs/cam.md](cam.md#measured-by-hand-fed-back)). A line the controller refuses
(`error:15`) or an alarm it raises (`ALARM:3`) is said in GRBL's words beside
the line in the log, in the refusal the status line carries, in the reason a
job that stopped gives, and in the state card. A cut that would leave the travel
stops where it would, as `ALARM:2`, so the tool is zeroed with the cut's depth
under it. The ring's Control
on a router is its own (`menu.router_control_options`): Home (All, X, Y, Z), Unlock, Jog
(with Stop jog), Spindle, Zero (with Probe Z), Cut (with Measure), Stop, Arm. The router's badge
in the world and its row on Site's tree say 🪚 and its state, its spindle while
it turns and the cut's progress, its hour in the Workspace charts the spindle,
and its marks stand on the table:
the working area, the table and the tool, placed from the controller's
machine coordinates and the working area (`mpos + travel`, a Grbl machine
homed to its maximum switches). `apothecary serve --simulated` pins the router's
controller to the simulated router on `/dev/ttyFAKE3`, beside the printer's
pin; `tests/e2e/test_router_ui.py` walks the Machine against it.

## Not built

- The bench, past the first answer: the real controller identifies itself as
  `Grbl 1.3a · Grbl_ESP32` at 115200 baud, `Idle`, behind a CH340 bridge
  (`0x1A86:0x7523`) with no USB serial number, so its pin is kept under the
  bridge's make, `usb:1a86:7523`, and follows it from port to port.
  What `$I` and `$$` hold, whether opening the port resets it and which way it
  homes are confirmed in section I of [the bench checklist](bench-checklist.md#i-the-router-the-anolex-4060-evo-ultra-2),
  the first replies kept as the Ender's are
  (`docs/validation/2026-09-20-ender-bench.md`).
- Single-axis homing on the real controller: `$HX`, `$HY` and `$HZ` are Grbl 1.1's
  and the allowlist takes them, the pad sends them and the simulated router homes only
  the axis named; whether this Grbl_ESP32 build takes them is confirmed in section I
  of [the bench checklist](bench-checklist.md#i-the-router-the-anolex-4060-evo-ultra-2).
- A toolpath from geometry: the toolpath is written from the cuts a part
  declares ([docs/cam.md](cam.md)), not from a mesh; a file a CAM post wrote
  (Easel, Carbide Create, Fusion) is kept and streamed as it is.
- WiFi: the controller's own web page (ESP3D) and its SD card are not used;
  the seam is serial, and nothing leaves this machine.
