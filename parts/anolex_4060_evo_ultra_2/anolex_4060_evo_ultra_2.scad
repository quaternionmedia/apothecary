// AnoleX 4060-Evo Ultra 2, a desktop CNC router, as a workshop model.
//
// Built from published dimensions, not from anyone's mesh: a moving-gantry
// router cutting 400 x 600 x 80 mm, on a base of two aluminium side beams
// carrying the Y rails, a fixed T-slot table between them, a gantry of two
// plates and a cross beam riding the Y rails, the X carriage on the beam's
// front face, the Z plate on the carriage, and an 800 W trim router in a
// 65 mm clamp on the Z plate. The control box sits at the back of the base,
// between the beams, its sockets facing the rear.
//
// The origin is the front-left bottom corner of the base frame; X runs right,
// Y runs back, Z runs up -- the site's machine convention. The table top is at
// table_top_z; the 400 x 600 working area sits centred on the table, so the
// tool's (0, 0) is at the working area's front-left corner when the gantry is
// at its front stop.
//
// Every dimension that is a published specification is named as such; the
// rest are taken from the maker's listed footprint or chosen to look right,
// and say so. Nothing here is a trademark: "4060-Evo Ultra 2" names what the
// part models.

// Customizer parameters (where the axes are shown standing)
x_axis = 200;   // [0:1:400] Where the tool stands along X, in work coordinates (mm)
y_axis = 300;   // [0:1:600] Where the gantry stands along Y, in work coordinates (mm)
z_axis = 40;    // [0:1:80] Tool tip height above the table (mm)
with_router = true;   // Draw the trim router in its clamp

/* [Hidden] */
$fn = 24;
eps = 0.5;   // how far a part sinks into what it stands on: a union of parts that
             // merely touch exports as a mesh OpenSCAD 2021.01 will not read back

// --- published specifications (AnoleX) ---
work_x = 400; work_y = 600; work_z = 80;   // the working area; Z is the 4030-Evo Ultra 2's, the same gantry
rail_w = 15; rail_h = 15;                  // HGH15 linear rail, two per axis
block = [34, 61, 28];                      // an HGH15 carriage block: width, length, height over the rail's base
screw_d = 12;                              // 1204 ball screw: 12 mm, 4 mm lead
nema = 56.4; motor_len = 80;               // NEMA 23 closed-loop steppers (the length is a usual one)
router_d = 65; router_len = 150;           // the 800 W trim router: a 65 mm body in a 65 mm clamp

// --- the base: sized from the maker's listed 4030 footprint (24.8 in wide and
// 20.47 in high) plus the 300 mm the 4060 base adds along Y; the maker lists no
// overall size for the 4060 itself ---
frame_w = 630;      // outer width of the base
frame_d = 930;      // outer depth of the base
beam = [40, 80];    // the side beams: aluminium profile, 40 wide and 80 tall
cross_t = 20;       // the front and rear cross plates
table = [460, 680, 20];        // the T-slot table, a little larger than the work area
table_top_z = beam[1] + 20;    // the table stands on supports above the beams' top

// --- the gantry: chosen to clear 80 mm of Z travel over the table ---
leg = [20, 140, 230];          // each gantry leg: a plate standing on its Y block
beam_x = [40, 120];            // the cross beam: 40 deep, 120 tall
carriage = [150, 20, 200];     // the X carriage plate on the beam's front face
z_plate = [120, 16, 180];      // the Z plate riding the carriage's Z rails
clamp = [100, 60, 40];         // the router clamp on the Z plate's front
control_box = [200, 100, 90];  // the controller's enclosure at the back, between the beams

// where the working area starts, in the frame: centred on the table
function work_x0() = (frame_w - work_x) / 2;
function table_y0() = (frame_d - table[1]) / 2;
function work_y0() = table_y0() + (table[1] - work_y) / 2;
// where the tool stands in the frame, for the axes as set
function tool_x() = work_x0() + x_axis;
function tool_y() = work_y0() + y_axis;
function tool_z() = table_top_z + z_axis;
// the gantry's legs and beam stand behind the tool: the Z plate and the X
// carriage are in front of the beam
function beam_y() = tool_y() + clamp[1] / 2 + z_plate[1] + carriage[1];

module hgh15_rail(len, along_y = true) {
    // a rail with its row of bolt holes left out: at bench scale a bar
    color("gainsboro") if (along_y) cube([rail_w, len, rail_h]); else cube([len, rail_w, rail_h]);
}

module hgh15_block(along_y = true) {
    // a carriage block over its rail, sunk a little into it
    color("darkslategray") translate([0, 0, rail_h - eps])
        if (along_y) translate([-(block[0] - rail_w) / 2, 0, 0]) cube([block[0], block[1], block[2] - rail_h + eps]);
        else translate([0, -(block[0] - rail_w) / 2, 0]) cube([block[1], block[0], block[2] - rail_h + eps]);
}

module nema23(len = motor_len) {
    // a NEMA 23 motor along +Z from its flange, with the encoder cap of a closed-loop one
    color("dimgray") cube([nema, nema, len]);
    color("black") translate([nema / 2, nema / 2, len - eps]) cylinder(d = 38, h = 12 + eps);
}

module anolex_base() {
    // the two side beams, the full depth, carrying the Y rails
    for (x = [0, frame_w - beam[0]]) translate([x, 0, 0]) {
        color("silver") cube([beam[0], frame_d, beam[1]]);
        translate([(beam[0] - rail_w) / 2, 30, beam[1] - eps]) hgh15_rail(frame_d - 60);
    }
    // the front and rear cross plates between the beams, sunk into them
    for (y = [0, frame_d - cross_t]) translate([beam[0] - eps, y, 0])
        color("silver") cube([frame_w - 2 * beam[0] + 2 * eps, cross_t, beam[1] - 20]);
    // the table on four supports, standing on the cross plates' level
    translate([(frame_w - table[0]) / 2, table_y0(), 0]) {
        color("darkgray") translate([0, 0, table_top_z - table[2]]) cube([table[0], table[1], table[2]]);
        color("silver") for (x = [20, table[0] - 60]) for (y = [20, table[1] - 60])
            translate([x, y, beam[1] - 20 - eps]) cube([40, 40, table_top_z - table[2] - (beam[1] - 20) + 2 * eps]);
        // the T-slots, as grooves along Y
        color("dimgray") for (i = [1 : 5]) translate([i * table[0] / 6 - 4, -1, table_top_z - 3]) cube([8, table[1] + 2, 3 + eps]);
    }
    // the Y ball screw under the table's centre line, and its motor behind the rear plate
    color("gainsboro") translate([frame_w / 2, cross_t - eps, beam[1] - 30]) rotate([-90, 0, 0]) cylinder(d = screw_d, h = frame_d - 2 * cross_t + 2 * eps);
    translate([frame_w / 2 - nema / 2, frame_d - eps, beam[1] - 30 + nema / 2]) rotate([-90, 0, 0]) nema23();
    // the emergency stop on the front-left beam, a red mushroom
    color("red") translate([beam[0] / 2, 20, beam[1] - eps]) cylinder(d = 30, h = 18 + eps);
    color("yellow") translate([beam[0] / 2, 20, beam[1] - eps]) cylinder(d = 40, h = 4 + eps);
}

module anolex_control_box() {
    // at the back, between the beams, standing on the floor; its USB and power
    // sockets face the rear, so the lead to the computer leaves behind the machine
    translate([(frame_w - control_box[0]) / 2, frame_d - cross_t - control_box[1] + eps, 0]) {
        color("black") cube(control_box);
        color("dimgray") translate([20, control_box[1] - 1, 30]) cube([12, 2, 8]);     // USB
        color("dimgray") translate([control_box[0] - 50, control_box[1] - 1, 20]) cube([30, 2, 25]);  // mains
    }
}

module anolex_gantry() {
    by = beam_y();
    // each leg stands on its Y block, straddling the rail on the beam
    for (x = [0, frame_w - beam[0]]) translate([x + (beam[0] - rail_w) / 2, by - leg[1] / 2, beam[1] - eps]) {
        hgh15_block();
        translate([-(block[0] - rail_w) / 2 + (block[0] - leg[0]) / 2, 0, block[2] - eps]) color("silver") cube(leg);
    }
    // the cross beam between the legs' tops, sunk a little into them
    translate([0, by - beam_x[0] / 2, beam[1] + block[2] + leg[2] - beam_x[1] - eps])
        color("silver") cube([frame_w, beam_x[0], beam_x[1] + eps]);
    // the two X rails on the beam's front face, the X carriage on their blocks
    bz = beam[1] + block[2] + leg[2] - beam_x[1];
    for (z = [bz + 20, bz + beam_x[1] - 20 - rail_h]) translate([beam[0], by - beam_x[0] / 2 - rail_h + eps, z]) rotate([90, 0, 0]) mirror([0, 0, 1]) hgh15_rail(frame_w - 2 * beam[0], along_y = false);
    cx = tool_x() - carriage[0] / 2;
    cy = by - beam_x[0] / 2 - block[2];
    color("silver") translate([cx, cy - carriage[1] + eps, bz - 20]) cube([carriage[0], carriage[1], carriage[2]]);
    // the X motor on the right end of the beam, its screw along the beam's front
    translate([frame_w - eps, by - beam_x[0] / 2 + (beam_x[0] - nema) / 2, bz + (beam_x[1] - nema) / 2]) rotate([0, 90, 0]) nema23(60);
    color("gainsboro") translate([beam[0] - eps, by - beam_x[0] / 2 - 10, bz + beam_x[1] / 2]) rotate([0, 90, 0]) cylinder(d = screw_d, h = frame_w - 2 * beam[0] + 2 * eps);
}

module anolex_z_axis() {
    by = beam_y();
    cy = by - beam_x[0] / 2 - block[2] - carriage[1];
    bz = beam[1] + block[2] + leg[2] - beam_x[1];
    // the Z plate rides two short rails on the carriage's front face; it is
    // z_axis up its travel, so the tool tip stands at tool_z()
    zy = cy - z_plate[1] + eps;
    zz = tool_z() + clamp[2] + 10;   // the plate's bottom: above the clamp's top
    color("silver") translate([tool_x() - z_plate[0] / 2, zy, zz]) cube(z_plate);
    // the Z motor on top of the carriage, its screw down behind the plate
    translate([tool_x() - nema / 2, cy - nema + 4, bz - 20 + carriage[2] - eps]) nema23(60);
    // the clamp on the plate's front, holding the router
    color("dimgray") translate([tool_x() - clamp[0] / 2, zy - clamp[1] + eps, tool_z()]) difference() {
        cube(clamp);
        translate([clamp[0] / 2, clamp[1] / 2 - 8, -1]) cylinder(d = router_d + 1, h = clamp[2] + 2);
    }
    if (with_router) translate([tool_x(), zy - clamp[1] / 2 - 8 + eps, tool_z() - 8]) {
        color("darkslateblue") translate([0, 0, 8 + eps]) cylinder(d = router_d, h = router_len);
        color("silver") translate([0, 0, 2]) cylinder(d = 18, h = 6 + 2 * eps);   // the collet nut
        color("gainsboro") cylinder(d = 3.175, h = 8 + eps);                    // a 1/8 in tool, its tip at the table + z_axis
    }
}

module anolex_4060_evo_ultra_2() {
    anolex_base();
    anolex_control_box();
    anolex_gantry();
    anolex_z_axis();
}

anolex_4060_evo_ultra_2();
