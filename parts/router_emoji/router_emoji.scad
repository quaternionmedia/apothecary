// Router emoji: the router's calibration piece, a 😮 -- a round face, two eyes and
// an open mouth, each a circle a person measures across with calipers. Its wrapper
// (apothecary/projects/parts/router_emoji.py) says the cuts that make it from its
// stock: the eyes and the mouth bored through, then the face cut around, in that
// order; this file draws the face those cuts leave.
//
// The face stands at the origin, its centre at (face_diameter / 2, face_diameter / 2)
// and its top at z = thickness. The toolpath's zero is the stock's front-left top
// corner: the stock is the face's square plus stock_margin on every side, so the
// face's centre is stock_margin further in, and its top is the toolpath's z = 0.
//
// Parameters:
//   face_diameter    the face, across: an outside size (mm)
//   eye_diameter     each eye, across: an inside size, wider than the 6 mm tool
//   mouth_diameter   the mouth, across: an inside size
//   thickness        the stock's, and the face's
//   stock_margin     stock beyond the face on each side: the toolpath's, not drawn

face_diameter = 60;    // [40:5:200] the face, across
eye_diameter = 10;     // [8:0.5:40] each eye, across
mouth_diameter = 20;   // [8:0.5:80] the mouth, across
thickness = 6;         // [3:1:40] the stock's thickness
stock_margin = 10;     // [0:1:50] stock beyond the face on every side (the toolpath's)

/* [Hidden] */
$fn = 96;

module face() {
    r = face_diameter / 2;
    translate([r, r, 0])
        difference() {
            cylinder(d = face_diameter, h = thickness);
            // The eyes, out and up from the centre, through.
            for (side = [-1, 1])
                translate([side * 0.35 * r, 0.3 * r, -1])
                    cylinder(d = eye_diameter, h = thickness + 2);
            // The mouth, down from the centre, through.
            translate([0, -0.35 * r, -1])
                cylinder(d = mouth_diameter, h = thickness + 2);
        }
}

face();
