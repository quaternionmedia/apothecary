// Router coupon: a plate with a pocket and a column of holes, the first part cut
// on the garage's router. Its wrapper (apothecary/projects/parts/router_coupon.py)
// says the cuts that make it from its stock: the pocket, the holes, the outline,
// in that order; this file draws the plate those cuts leave.
//
// The plate stands at the origin, its top at z = thickness. The toolpath's zero is
// the stock's front-left top corner: the stock is the plate plus stock_margin on
// every side, so the plate's corner is at (stock_margin, stock_margin) and its top
// is the toolpath's z = 0.
//
// Parameters:
//   plate_x, plate_y  the plate, X and Y (mm)
//   thickness         the stock's, and the plate's
//   pocket_w, pocket_h, pocket_depth  the pocket, 20 mm in from the left, centred in Y
//   hole_diameter, holes              a column of holes 20 mm in from the right, evenly along Y
//   stock_margin      stock beyond the plate on each side: the toolpath's, not drawn

plate_x = 120;       // [40:5:400] the plate's width
plate_y = 80;        // [40:5:600] the plate's depth
thickness = 10;      // [3:1:40] the stock's thickness
pocket_w = 40;       // [6:1:200] the pocket's width
pocket_h = 30;       // [6:1:200] the pocket's depth, in Y
pocket_depth = 4;    // [1:0.5:20] how deep the pocket goes
hole_diameter = 3;   // [1:0.5:30] each hole's diameter
holes = 2;           // [0:1:6] holes in the column
stock_margin = 10;   // [0:1:50] stock beyond the plate on every side (the toolpath's)

/* [Hidden] */
$fn = 48;

module coupon() {
    difference() {
        cube([plate_x, plate_y, thickness]);
        // The pocket, open at the top.
        translate([20, (plate_y - pocket_h) / 2, thickness - pocket_depth])
            cube([pocket_w, pocket_h, pocket_depth + 1]);
        // The holes, through.
        for (i = [0 : holes - 1])
            translate([plate_x - 20, plate_y * (i + 1) / (holes + 1), -1])
                cylinder(d = hole_diameter, h = thickness + 2);
    }
}

coupon();
