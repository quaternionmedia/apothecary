# AnoleX Grbl_ESP32 controller

The controller board in an AnoleX 4060-Evo Ultra 2's control box, as a
workshop model: the node the garage pins the router's serial port to,
`cnc_router.frame_system.controller`, inside the control box the machine's
part draws at the back of its base
([parts/anolex_4060_evo_ultra_2](../../anolex_4060_evo_ultra_2/README.md)).

The maker publishes no drawing of this board, so this model is not built from
one. What is established is what the bench saw of it over USB
([docs/cnc.md](../../../docs/cnc.md#the-controller-and-its-dialect)): it
identifies as `Grbl 1.3a` running Grbl_ESP32, so its processor is an ESP32,
and it is reached through a CH340 USB bridge (`0x1A86:0x7523`) with no USB
serial number; Grbl_ESP32 carries ESP3D, which serves a web page and reads an
SD card, neither of which Apothecary uses. The rest is assumed and drawn to
stand for it:

- The PCB is 100 x 80 mm with four 3.2 mm mounting holes, a size a board of
  this kind has and one that stands in the 200 x 100 mm control box the
  machine's part draws.
- The ESP32 is a WROOM-32 module with its antenna at the left edge.
- The USB socket is a USB-B jack at the back edge, facing the rear as the
  control box's socket does, with the CH340 beside it.
- The 24 V input and the spindle's output are screw terminals along the same
  edge, with a relay for the spindle: the 800 W trim router is started and
  stopped by the controller and its speed set by a dial on the router.
- The three axes' drivers are not on the board: closed-loop NEMA 23 steppers
  have drivers of their own, so the board carries a four-pin step and
  direction header for each, along the front edge.
- The limit switches have a three-pin header each and the probe a two-pin one,
  beside the drivers'; the SD slot is at the right edge, with a reset button.

A drawing from the maker, or a photograph of the board out of its box,
replaces every assumed number here; the pin path and the part's name stay.
`anolex_grbl_esp32.scad` contains no one else's mesh: the model is this
repository's own, MIT.
