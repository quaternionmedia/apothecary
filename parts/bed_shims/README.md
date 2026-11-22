# Bed shims

A shim for each levelling screw whose corner stands low, as thick as lifts that corner
to the highest. Each stacks on its corner's solid mount, around the screw, and raises
that corner by its thickness. The shims lie flat in a column. Each is a ring with the
hole its screw passes and an open slot to the rim, so it slides onto its mount once
the knob is loosened, with nothing taken off. A tab trails opposite the slot and carries
the corner's label (**FL**, **FR**, **BR**, **BL** on printer_1), cut into its top. The
tab is thicker than a thin shim and starts clear of the ring, so once fitted it hangs
beside the mount and never bears. It is what a hand holds, and the label reads
whatever the shim's thickness.

The thicknesses come from bed readings, never from this part: `apothecary bed shims`
fits a plane to the printer's newest heated pair of probes and takes it at each screw
the printer's profile holds. It then says the command that slices this part at the
shims it found ([docs/bed-shims.md](../../docs/bed-shims.md)). The part draws as many
shims as it is given thicknesses, one label each, and a corner that gets none is left
out.

Its wrapper, `apothecary/projects/parts/bed_shims.py`, declares a layer height of
0.1 mm. Each thickness the computation gives is a whole number of those layers over a
first layer of 0.2 mm, so each shim's top lands on a layer. Print them in a filament
that holds its shape at the bed's temperature: a shim sits under the heated plate.

The ring's size and the screw's hole are parameters (`outer_d`, `hole_d`), and the
part's presets are the bed screws, `m3` and `m4`, each setting the hole. Their defaults,
a hole for an M4 and a 12 mm ring, are defaults awaiting a caliper reading: they are not
printer_1's measured screw and mount. What a machine's mounts are found to be is kept
for that machine (`apothecary bed mount`), and its shims are sliced at it.

```bash
uv run apothecary bed shims --site garage --printer printer_1   # the shims, and the slice command
uv run apothecary parts verify bed_shims -p thicknesses=0.7,0.8 -p "labels=FL BL"
```
