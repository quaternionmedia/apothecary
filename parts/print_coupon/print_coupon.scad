// Print coupon: the printer's piece made to be measured. A plate with two square
// blocks standing on it, a square pocket in each, a square window through the plate
// and a single-wall fin, every size a person reads with calipers, each labelled.
// Its wrapper (apothecary/projects/parts/print_coupon.py) names each feature, the
// jaws that read it and where they close; apothecary/print_tuning.py says what the
// readings imply for the printer (docs/print-tuning.md).
//
// The plate's front-left bottom corner is the origin, its long side along X. Block A
// stands at the front left, block B to its right, the fin past B; the window is
// behind B. Everything stands on the plate, so nothing needs a support. Labels are
// cut into the plate's top, clear of every face a jaw meets.
//
//   outside sizes  the plate, X and Y (the jaws take in the first layer); A and B,
//                  X and Y (above it)
//   inside sizes   A's and B's pockets, X and Y (above the first layers); the
//                  window, X and Y (through them)
//   heights        the plate's top, B's and A's, from the bed face
//   a single wall  the fin, across

/* [Plate] */
plate_x = 54;       // [40:1:120] the plate along X, its long side
plate_y = 36;       // [30:1:100] the plate along Y
plate_t = 2;        // [1:0.2:6] the plate's thickness: the first top measured

/* [Blocks] */
a_size = 20;        // [10:1:40] block A, square
a_height = 10;      // [2:0.2:30] block A above the plate
a_pocket = 12;      // [4:1:30] block A's pocket, square, down to the plate
b_size = 12;        // [8:1:30] block B, square
b_height = 6;       // [2:0.2:30] block B above the plate
b_pocket = 6;       // [3:1:20] block B's pocket, square, down to the plate

/* [Window and fin] */
window = 8;         // [4:1:20] a square window through the plate, behind B
fin_t = 0.45;       // [0.2:0.01:1.2] the fin's thickness: one line of the slicer's
fin_length = 15;    // [5:1:30] the fin along Y
fin_height = 6;     // [2:0.2:20] the fin above the plate

/* [Room] */
margin = 4;         // [3:0.5:10] from the plate's edge to what stands on it
gap = 6;            // [4:0.5:12] between two features, room for a jaw
label_depth = 0.6;  // [0.2:0.2:1] how deep a label is cut into the plate's top

/* [Hidden] */
eps = 0.01;  // what stands on the plate starts this far into it, so the two are one
label_size = 4;

a_x0 = margin;
a_y0 = margin;
b_x0 = margin + a_size + gap;
b_y0 = margin;
fin_x0 = b_x0 + b_size + gap;
fin_y0 = margin;
w_x0 = b_x0 + (b_size - window) / 2;
w_y0 = margin + b_size + gap;

module block(x0, y0, size, height, pocket) {
    difference() {
        translate([x0, y0, plate_t - eps]) cube([size, size, height + eps]);
        translate([x0 + (size - pocket) / 2, y0 + (size - pocket) / 2, plate_t])
            cube([pocket, pocket, height + 1]);
    }
}

module label(t, x, y) {
    translate([x, y, plate_t - label_depth])
        linear_extrude(label_depth + 1)
            text(t, size = label_size, halign = "center", valign = "center",
                 font = "Liberation Sans:style=Bold");
}

module coupon() {
    difference() {
        union() {
            cube([plate_x, plate_y, plate_t]);
            block(a_x0, a_y0, a_size, a_height, a_pocket);
            block(b_x0, b_y0, b_size, b_height, b_pocket);
            translate([fin_x0, fin_y0, plate_t - eps])
                cube([fin_t, fin_length, fin_height + eps]);
        }
        translate([w_x0, w_y0, -1]) cube([window, window, plate_t + 2]);
        label("A", a_x0 + a_size / 2, (a_y0 + a_size + plate_y) / 2);
        label("B", b_x0 + b_size / 2, margin + b_size + gap / 2);
        label("W", w_x0 + window / 2, (w_y0 + window + plate_y) / 2);
        label("F", fin_x0 + fin_t / 2, fin_y0 + fin_length + gap / 2 + 1);
        label("X", plate_x - margin, plate_y - margin);
    }
}

coupon();
