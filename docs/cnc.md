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
is the router as a part: a moving-gantry machine cutting 400 x 600 x 80 mm,
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
`build_origin`. Inside it, `cnc_router.frame_system` is the control box and
`cnc_router.frame_system.controller` the board the port is pinned to: the
maker publishes no drawing of that board, so it is a box and no part draws
it. `ROUTER_STATUSES` are the words the router's node takes: `idle`,
`running`, `hold`, `alarm`, `offline` from its polls, and `maintenance` by
hand.

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
| Identified by | `M115` | `$I`; a GRBL controller answers `M115` with `error:20`, so Marlin's is tried first and GRBL's when nothing Marlin answers |
| Polled by | `M105`, `M114`, `M27`, `M119`, `M31` | the realtime `?` (a status report, no `ok`) and `$G` (the modal words) |
| Its state | `idle`, `printing`, `offline` | the controller's own word (`Idle`, `Run`, `Jog`, `Home`, `Hold:0`, `Door`, `Alarm`), folded to `idle`, `running`, `hold`, `alarm`, `offline` |
| What a poll carries | temperatures, position, endstops, filament, SD progress | machine and work position and the offset between them, the spindle's speed and whether it is on, the feed, the input pins on (limits, probe, door, hold), the alarm's number, the overrides |
| Typed while armed | heaters, fan, homing, bounded jogs, SD pause/resume/abort, the bed | homing (`$H`), unlock (`$X`), jogs (`$J=`), bounded moves, the spindle on at a speed (`M3 S`) and off, work zero here (`G10 L20 P1`), a probe down (`G38.2`), the tool to the top of Z (`G53 G0 Z0`), and the realtime `HOLD`, `RESUME`, `JOG-CANCEL` |
| The bounds | hotend 300 °C, bed 130 °C, a move 300 mm, feed 12000 | a move 600 mm, feed 4000 mm/min (the maker's figure for X and Y), the spindle 24000 rpm, a probe 80 mm deep at 500 mm/min at most |
| The stop | `M112`, always accepted | `RESET`, the soft reset (`0x18`), always accepted: everything halts, the queue empties, the spindle is off, and a reset in motion leaves the controller in alarm until unlocked or homed |
| Report-only queries | `M503`, `M119`, `M20`, `M420 V` ... | `$$` (settings), `$#` (offsets, the probe's last touch), `$G`, `$I`, `$N`, `?` |
| A streamed job | a print, from the slicer's G-code | a cut, from a CAM post's `.nc`, `.ngc`, `.gcode` or `.tap`, refused for a `$` line, a tool change (`M6`), a stop (`M0`, `M1`) or a spindle over the cap; a pause holds the controller (`!`) so it stops where it is, a cancel holds and resets; a line is answered when queued, so the host counts the planner's room from the status report (`Bf:`) and never blocks the port on a full one, and the cut is done when the controller is idle again after its last line (`finishing`) |
| Its job's word | `print`, the node `printing` | `cut`, the node `running` (`apothecary/jobs.py`) |

Machine coordinates on a Grbl machine run negative from the home corner --
the back right and the top of Z, where the switches are -- so after homing
the tool is at (0, 0, 0) there and the working area is `mpos + travel`
inside it. A poll carries both the machine position and the work position
the person's zero gives.

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
a stop goes. Its stop is then its own: `RESET` goes, and a printer's `M112`,
which a GRBL controller answers `error:20` and goes on cutting, is refused
and not sent. The same holds the other way round, for a printer on a port
the router held.

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
pad, `$J=` at the feed set, Home `$H`, Unlock `$X`, Top of Z, Go to zero,
Stop jog), Spindle (On at a speed, Off), Zero and probe (XYZ zero here, Z
zero here, Probe Z down a depth), and Cut (Resume, Hold, Abort). The Cut window,
*Cut from here*, is a printer's Print with a router's words, in the loop's
order: what it makes and its Toolpath ([docs/cam.md](cam.md)) where a printer has
Slice, the file, kept and checked, or a CAM post's, then ▶ Cut, Pause (a hold),
Resume, Cancel (a hold and a reset), the cut's progress with the operation it is
in, what the file holds, and the router's jobs. A line the controller refuses
(`error:15`) or an alarm it raises (`ALARM:3`) is said in GRBL's words beside
the line in the log, in the refusal the status line carries, in the reason a
job that stopped gives, and in the state card. A cut that would leave the travel
stops where it would, as `ALARM:2`, so the tool is zeroed with the cut's depth
under it. The ring's Control
on a router is its own (`menu.router_control_options`): Home, Unlock, Jog
(with Stop jog), Spindle, Zero (with Probe Z), Cut, Stop, Arm. The router's badge
in the world and its row on Site's tree say 🪚 and its state, its spindle while
it turns and the cut's progress, its hour in the Working space charts the spindle,
and its marks stand on the table:
the working area, the table and the tool, placed from the controller's
machine coordinates and the working area (`mpos + travel`, a Grbl machine
homed to its maximum switches). `apothecary serve --demo` pins the router's
controller to the simulated router on `/dev/ttyFAKE3`, beside the printer's
pin; `tests/e2e/test_router_ui.py` walks the Machine against it.

## Not built

- The bench: the router has not been plugged into this seam. What the
  controller really answers to `$I`, which USB bridge it has, whether its
  DTR resets it, what `$$` holds and which way it homes are confirmed at the
  bench, the first replies kept as the Ender's are
  (`docs/validation/2026-09-20-ender-bench.md`), and the checklist gains a
  section for it.
- A toolpath from geometry: the toolpath is written from the cuts a part
  declares ([docs/cam.md](cam.md)), not from a mesh; a file a CAM post wrote
  (Easel, Carbide Create, Fusion) is kept and streamed as it is.
- WiFi: the controller's own web page (ESP3D) and its SD card are not used;
  the seam is serial, and nothing leaves this machine.
