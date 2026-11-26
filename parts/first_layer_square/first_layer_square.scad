// A one-layer square: what a printer's first layer is read from. Printed with the bed
// probed first, it says whether the nozzle stands where it should over the bed: lines
// pressed flat into one sheet are right; lines round and standing apart, or not
// holding, say the nozzle is high; lines thin, see-through or scraped say it is low.
// What is read goes into the printer's first-layer offset, kept in its Print window
// (apothecary/slicer/first_layer_offset.py), and the next square says whether it was
// right.
//
// The square's front-left corner, on the bed, is the origin.

/* [Square] */
size = 50;          // [20:1:150] the square's side, mm

/* [Hidden] */
height = 0.2;       // one first layer: the printer profile's first layer

cube([size, size, height]);
