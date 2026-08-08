// datum — a modular control-surface enclosure.
//
// A tray that carries one board, opens on one edge for USB-C, and thins over
// the antenna. Every dimension that depends on the board is a parameter, so
// the same file serves a different board by being called with different
// numbers rather than by being edited.
//
// House constants follow parts/footpedal/button.scad, per the datum project's
// record on enclosure parts: wall 2.4, tolerance 0.2, cap radius 2.
//
// SIGNAL ONLY. Nothing here is rated to sit between a person and a conductor.
// Where a module goes in a wall box, this part is cosmetic and mechanical and
// the listed box is the barrier. See the datum project's signal-only record.

// ---- board envelope (from the black box; defaults are the T1-Core stub) ----
board_w = 40.0;   // X
board_d = 30.0;   // Y
board_h = 1.6;    // Z, bare board
mount_inset = 3.5;
mount_hole = 2.2;

// ---- house constants -------------------------------------------------------
wall = 2.4;
tol = 0.2;
r_cap = 2.0;

// ---- fit --------------------------------------------------------------------
standoff = 3.0;   // board underside to floor: clearance for through-hole tails
headroom = 8.0;   // above the board: modules, connectors, a finger
usb_w = 10.0;     // USB-C opening width
usb_h = 4.0;      // USB-C opening height
antenna_band = 8.0;  // depth of the thinned strip at the antenna edge
antenna_wall = 0.8;  // thinned to stay out of the radio's way

inner_w = board_w + 2 * tol;
inner_d = board_d + 2 * tol;
inner_h = standoff + board_h + headroom;
outer_w = inner_w + 2 * wall;
outer_d = inner_d + 2 * wall;
outer_h = inner_h + wall;

$fn = 48;

module rounded_box(w, d, h, r) {
    hull() for (x = [r, w - r], y = [r, d - r])
        translate([x, y, 0]) cylinder(r = r, h = h);
}

module shell() {
    difference() {
        rounded_box(outer_w, outer_d, outer_h, r_cap);
        // cavity
        translate([wall, wall, wall])
            rounded_box(inner_w, inner_d, inner_h + 1, max(r_cap - wall / 2, 0.1));
        // USB-C opening, centred on the front edge (y = 0)
        translate([outer_w / 2 - usb_w / 2, -1, wall + standoff + board_h / 2 - usb_h / 2])
            cube([usb_w, wall + 2, usb_h]);
        // antenna relief: thin the back wall rather than removing it
        translate([wall, outer_d - wall - 0.01, wall + standoff])
            cube([inner_w, wall - antenna_wall + 0.01, antenna_band]);
    }
}

module standoffs() {
    for (p = [[mount_inset, mount_inset],
              [board_w - mount_inset, mount_inset],
              [mount_inset, board_d - mount_inset],
              [board_w - mount_inset, board_d - mount_inset]])
        translate([wall + tol + p[0], wall + tol + p[1], wall])
            difference() {
                cylinder(d = mount_hole + 2.6, h = standoff);
                // pilot for a self-tapping M2: undersized on purpose
                translate([0, 0, -0.5]) cylinder(d = mount_hole - 0.4, h = standoff + 1);
            }
}

module datum() {
    shell();
    standoffs();
}

datum();
