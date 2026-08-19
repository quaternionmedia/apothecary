// datum-core -- a two-piece enclosure for a 40 x 40 mm control-surface board.
//
// Four contact openings, one indicator light pipe, one edge connector cutout,
// and four board standoffs. Every dimension below is a parameter; the defaults
// describe a generic 40 mm board and render on their own, with no knowledge of
// any particular PCB.
//
// The board dimensions are assumptions until a schematic exists. Tune them
// here rather than in a consumer.

$fn = 64;

/* [What to render] */
// tray = the printable base, lid = the printable cover, exploded = both
show = "tray"; // [tray, lid, exploded]

/* [Board] */
board_x = 40;
board_y = 40;
board_t = 1.6;
board_clearance = 0.4;

/* [Shell] */
wall = 2.4;
floor_t = 2.0;
lid_t = 2.0;
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

/* [Indicator] */
indicator_d = 4.0;
indicator_x = 0;
indicator_y = 14;

/* [Contacts] */
contact_d = 12.0;
contact_pitch_x = 18.0;
contact_pitch_y = 18.0;

/* [Lid fit] */
lip_h = 3.0;
lip_clearance = 0.25;

/* [Assembly preview] */
explode_gap = 12.0;

// ---------------------------------------------------------------- derived --

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

module contact_positions() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * contact_pitch_x / 2, sy * contact_pitch_y / 2, 0])
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
    }

    translate([0, 0, floor_t])
        mount_positions()
            standoff();
}

// Modelled plate-down, which is how it prints.
module lid() {
    difference() {
        union() {
            rrect(outer_x, outer_y, lid_t, corner_r);
            translate([0, 0, lid_t])
                rrect(cavity_x - 2 * lip_clearance,
                      cavity_y - 2 * lip_clearance,
                      lip_h,
                      max(0.1, corner_r - wall));
        }

        translate([0, 0, -0.1])
            contact_positions()
                cylinder(d = contact_d, h = lid_t + lip_h + 0.2);

        translate([indicator_x, indicator_y, -0.1])
            cylinder(d = indicator_d, h = lid_t + lip_h + 0.2);
    }
}

// ------------------------------------------------------------------ render --

if (show == "tray") {
    tray();
} else if (show == "lid") {
    lid();
} else {
    tray();
    translate([0, 0, tray_h + explode_gap + lid_t])
        rotate([180, 0, 0])
            lid();
}
