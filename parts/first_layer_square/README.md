# First layer square

A square one first layer thick, 50 mm across by default (`size`). It is what a
printer's first layer is read from: printed with the bed probed first, it says
whether the nozzle stands where it should over the bed.

| The square shows | The nozzle is | The first-layer offset |
|---|---|---|
| Lines pressed flat into one smooth sheet | where it should be | kept as it is |
| Lines round, standing apart, or not holding to the bed | high | lower |
| Lines thin or see-through, ridged, scraped, or no plastic | low | higher |

The offset is kept for the printer in its Print window's *first layer* row, a
step of 0.05 mm at a time, and every slice made for the printer after is made
with it: OrcaSlicer's `z_offset`, on top of the probe's own offset, which the
board keeps and applies itself ([docs/slicer.md](../../docs/slicer.md#a-printers-first-layer-offset)).
Slice the square again after each change: the next square says whether the step
was right.

Its wrapper, `apothecary/projects/parts/first_layer_square.py`, declares the
first layer as `bed_shims` prints it: a probe first, no brim and no skirt, so
what the square shows is the layer a shim's is.
