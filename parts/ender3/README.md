# Ender 3

A Creality Ender 3 (the 2018 original) as a workbench model, built in
OpenSCAD from published dimensions -- a machine 440 x 440 x 465 mm overall
printing 220 x 220 x 250 -- with the power supply on the right side of the
frame behind the upright, the electronics box under the bed at the front
left, the LCD off the front-right corner and the spool on a bracket over the
top crossbar. The axes (`z_axis`, `x_axis`, `y_axis`) are parameters, so the
garage draws its one printer, printer_1, with its nozzle where the last poll
said.

`ender3.scad` says which numbers are Creality's specifications and which are
measured off a machine of this kind or chosen to look right. It contains no
one else's mesh: the model is this repository's own, MIT.

`slicer.json` beside it is printer_1's slicer profile: OrcaSlicer's own
Creality Ender-3 profiles, read from the installed release at each slice, and
what the bench measured, each value with where it came from. A part or a
made piece sliced for printer_1 is sliced with it;
[docs/slicer.md](../../docs/slicer.md) says how.
