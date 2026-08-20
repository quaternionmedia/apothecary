// datum-cap -- the cover for a datum-core tray.
//
// Four contact openings on a 2 x 2 grid and one indicator light pipe, over a
// lip that drops into the core's cavity. Split from datum-core because the
// enclosure record asks for one core body and separate pieces around it, and
// because a `show` parameter selecting between two objects is two parts
// wearing one name -- its bounds depended on which mode you asked for.
//
// It renders from its own defaults and knows nothing about any particular PCB.

$fn = 64;

/* [Board] */
board_x = 40;
board_y = 40;
board_clearance = 0.4;

/* [Print settings] */
// House constants, print-validated on QM hardware -- parts/footpedal/button.scad.
walls = 3;
tolerence = .4;

/* [Plate] */
lid_t = 2.0;
corner_r = 3.0;
lip_h = 3.0;

/* [Indicator] */
indicator_d = 4.0;
indicator_x = 0;
indicator_y = 14;

/* [Contacts] */
contact_d = 12.0;
contact_pitch_x = 18.0;
contact_pitch_y = 18.0;

// ---------------------------------------------------------------- derived --

wall = walls;
lip_clearance = tolerence / 2;

cavity_x = board_x + 2 * board_clearance;
cavity_y = board_y + 2 * board_clearance;
outer_x = cavity_x + 2 * wall;
outer_y = cavity_y + 2 * wall;
lid_h = lid_t + lip_h;

_CORNERS = [[-1, -1], [-1, 1], [1, -1], [1, 1]];

// ----------------------------------------------------------------- shapes --

module rrect(x, y, h, r) {
    hull()
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (x / 2 - r), sy * (y / 2 - r), 0])
                cylinder(r = r, h = h);
}

module contact_positions() {
    for (sx = [-1, 1], sy = [-1, 1])
        translate([sx * contact_pitch_x / 2, sy * contact_pitch_y / 2, 0])
            children();
}

// ------------------------------------------------------------------ render --

// Modelled plate-down, which is how it prints.
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
            cylinder(d = contact_d, h = lid_h + 0.2);

    translate([indicator_x, indicator_y, -0.1])
        cylinder(d = indicator_d, h = lid_h + 0.2);
}
