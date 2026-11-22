// Bed shims: one for each levelling screw whose corner stands low, as thick as lifts
// that corner to the highest. apothecary/bed_shims.py computes the thicknesses from
// bed readings, and `apothecary bed shims` says them with the command that slices this
// part at them (docs/bed-shims.md).
//
// A shim is a ring that stacks on its corner's solid mount, around the screw, with an
// open slot so it slides onto the screw once the knob is loosened, not taken off. A tab
// trails opposite the slot. It is thicker than the shim, flush with the shim's face on
// the bed, and starts clear of the ring, so once fitted it hangs into the gap beside the
// mount and never bears. It is what a hand holds, and it carries the corner's label, cut
// into its top.
//
// The shims lie in a column along Y, in the order of `labels`, each ring's slot toward
// +X and its tab toward -X. The front-left of the column's box, on the bed, is the
// origin.

/* [Shims] */
thicknesses = [0.5, 0.5, 0.5];      // each shim's thickness, mm, in the order of labels
labels = ["FL", "BR", "BL"];        // each shim's label, cut into its tab
outer_d = 12;       // [6:0.5:40] the ring across: at least the mount's face it bears on
hole_d = 4.6;       // [2:0.1:10] the hole the screw passes
slot = true;        // an open slot from the hole to the rim
gap = 4;            // [2:0.5:20] between two shims on the bed

/* [Tab] */
tab_length = 14;    // [8:1:40] how far the tab reaches past the ring
tab_width = 9;      // [5:0.5:30] the tab across
tab_t = 1.2;        // [0.6:0.1:4] the tab's thickness, more than the shim's where it is thin
tab_clear = 1;      // [0:0.5:5] between the ring's rim and where the tab thickens
label_size = 5;     // [2:0.5:8] the letters' height
label_depth = 0.6;  // [0.2:0.1:2] how deep a label is cut into the tab

/* [Hidden] */
$fn = 72;
eps = 0.01;
r = outer_d / 2;

assert(len(thicknesses) == len(labels), "a thickness for each label, and a label for each thickness");

module shim(t, label) {
    thick = max(t, tab_t);
    difference() {
        union() {
            // the ring, and the tab at the ring's thickness reaching into it
            cylinder(r = r, h = t);
            translate([-r - tab_length, -tab_width / 2, 0]) cube([tab_length + r, tab_width, t]);
            // the tab's thick part, clear of the ring and the mount under it
            translate([-r - tab_length, -tab_width / 2, 0])
                cube([tab_length - tab_clear, tab_width, thick]);
        }
        translate([0, 0, -eps]) cylinder(d = hole_d, h = thick + 2 * eps);
        if (slot)
            translate([0, -hole_d / 2, -eps]) cube([r + eps, hole_d, thick + 2 * eps]);
        translate([-r - (tab_length + tab_clear) / 2, 0, thick - label_depth])
            linear_extrude(height = label_depth + eps)
                text(label, size = label_size, halign = "center", valign = "center",
                     font = "Liberation Sans:style=Bold");
    }
}

for (i = [0 : len(thicknesses) - 1])
    translate([tab_length + r, r + i * (outer_d + gap), 0])
        shim(thicknesses[i], labels[i]);
