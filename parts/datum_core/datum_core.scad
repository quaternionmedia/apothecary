// datum_core -- the tray of an enclosure for a 40 x 40 mm control-surface board.
//
// One edge connector cutout, an antenna relief, and four board standoffs. The
// cover is a separate part, datum_cap: the enclosure record asks for one core
// body with separate pieces around it. Every dimension below is a parameter; the defaults
// describe a generic 40 mm board and render on their own, with no knowledge of
// any particular PCB.
//
// The board dimensions are assumptions until a schematic exists. Tune them
// here rather than in a consumer.

$fn = 64;

/* [Board] */
board_x = 40;
board_y = 40;
board_t = 1.6;
board_clearance = 0.4;

/* [Print settings] */
// House constants, print-validated on QM hardware -- parts/footpedal/button.scad.
// They are manufacturing facts, not this board's: a consumer overrides them for
// its own printer, it does not own them. (The spelling matches the original.)
walls = 3;
tolerence = .4;

/* [Shell] */
floor_t = 2.0;
corner_r = 3.0;
// board underside to floor
standoff_h = 4.0;
// board top to lid underside
headroom = 8.0;

/* [Mounting] */
// hole centres, inset from the board edge
mount_inset = 3.5;
boss_d = 5.0;
screw_d = 2.2;

/* [Edge connector] */
connector_w = 9.4;
connector_h = 3.6;
connector_margin = 0.6;

/* [Antenna] */
// A radio module wants no material in front of its antenna. The wall is
// thinned rather than removed, so the enclosure stays closed: ported from
// the single-piece tray this part replaced, which had it and this did not.
antenna_band = 8.0;
antenna_wall = 0.8;

// ---------------------------------------------------------------- derived --

// The side wall comes from the print settings above.
wall = walls;

cavity_x = board_x + 2 * board_clearance;
cavity_y = board_y + 2 * board_clearance;
outer_x = cavity_x + 2 * wall;
outer_y = cavity_y + 2 * wall;

board_z = floor_t + standoff_h;
tray_h = board_z + board_t + headroom;
connector_z = board_z + board_t + connector_h / 2;

// ----------------------------------------------------------------- shapes --

module rrect(x, y, h, r) {
    hull()
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (x / 2 - r), sy * (y / 2 - r), 0])
                cylinder(r = r, h = h);
}

module mount_positions() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * (board_x / 2 - mount_inset), sy * (board_y / 2 - mount_inset), 0])
            children();
}

// A slot with semicircular ends, lying along +Y. Long enough to clear any wall.
module connector_cut(len) {
    hull()
        for (sx = [-1, 1])
            translate([sx * (connector_w / 2 - connector_h / 2), 0, 0])
                rotate([-90, 0, 0])
                    cylinder(d = connector_h + 2 * connector_margin, h = len);
}

module standoff() {
    difference() {
        cylinder(d = boss_d, h = standoff_h);
        translate([0, 0, -0.1])
            cylinder(d = screw_d, h = standoff_h + 0.2);
    }
}

// ------------------------------------------------------------------ pieces --

module tray() {
    difference() {
        rrect(outer_x, outer_y, tray_h, corner_r);

        translate([0, 0, floor_t])
            rrect(cavity_x, cavity_y, tray_h, max(0.1, corner_r - wall));

        // Through the +Y wall, sitting on the board the way a connector does.
        translate([0, cavity_y / 2 - 0.5, connector_z])
            connector_cut(wall + 1.5);

        // Antenna relief on the -Y wall, opposite the connector: the wall is
        // thinned to antenna_wall over a band, not cut through.
        translate([-cavity_x / 2, -outer_y / 2 - 0.01, board_z])
            cube([cavity_x, wall - antenna_wall + 0.01, antenna_band]);
    }

    translate([0, 0, floor_t])
        mount_positions()
            standoff();
}

// ------------------------------------------------------------------ render --

tray();
