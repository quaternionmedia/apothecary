// Creality Ender 3 (the 2018 original), as a workbench model.
//
// Built from published dimensions, not from anyone's mesh: a machine 440 x
// 440 x 465 mm overall, printing 220 x 220 x 250, on a base of 2040 and
// 2020 aluminium extrusion, with the power supply mounted on the RIGHT side
// of the base behind the right upright (which is what makes the machine 440
// wide when the frame is 400), the electronics box under the bed at the
// front left, the LCD hung off the front right corner, and the filament
// spool on a bracket on the top crossbar, its tube pointing right so the
// spool hangs over the power supply.
//
// The origin is the front-left bottom corner of the base frame; X runs right,
// Y runs back, Z runs up -- the site's printer convention. The bed's build
// surface is at bed_top_z; the printable 220 x 220 sits centred on the
// 235 x 235 plate, so the nozzle's (0, 0) is at (bed_plate_x + 7.5,
// bed_plate_y + 7.5, bed_top_z) when the bed is at its home position.
//
// Every dimension that is a published specification is named as such; the
// rest are measured off a machine of this kind or chosen to look right, and
// say so. Nothing here is a trademark: "Ender 3" names what the part models.

// Customizer parameters (where the axes are shown standing)
z_axis = 150;   // [0:1:250] Height of the X gantry above the bed (mm)
x_axis = 110;   // [0:1:220] Where the hotend stands along X, in bed coordinates (mm)
y_axis = 110;   // [0:1:220] Where the bed stands along Y, in bed coordinates (mm)
with_spool = true;   // Draw a spool on the holder
with_lcd = true;     // Draw the LCD and its bracket

/* [Hidden] */
$fn = 24;
eps = 0.5;   // how far a part sinks into what it stands on: a union of parts that
             // merely touch, with slot edges crossing, exports as a mesh OpenSCAD
             // 2021.01 will not read back into a boolean

// --- published specifications (Creality) ---
build_x = 220; build_y = 220; build_z = 250;   // printable volume
bed_plate = 235;                               // the build plate, square
overall_w = 440; overall_d = 440; overall_h = 465;

// --- the frame: 2040 and 2020 extrusion ---
frame_w = 400;      // outer width of the base frame (the PSU makes the 440)
frame_d = 410;      // outer depth of the base frame
rail = 20;          // the extrusion module: 2020 is rail x rail, 2040 is rail x 2*rail
upright_h = 420;    // the Z uprights (2040), standing on the side rails
upright_y = 150;    // where the uprights stand along Y, measured off a machine
top_bar_z = 20 + upright_h;   // the 2020 top crossbar sits on the uprights

// --- the bed ---
bed_top_z = 95;     // build surface height above the bench, measured off a machine
plate_t = 3;        // aluminium plate
carriage_t = 5;

// --- what hangs off the frame ---
psu = [50, 215, 115];         // Meanwell-style 24 V 350 W supply, published
psu_y = 195;                  // behind the right upright
box = [130, 180, 45];         // electronics box under the bed, front left (measured)
box_at = [66, 40, 21];        // clear of the Z motor's foot, just above the rails
lcd = [93, 8, 70];            // a 12864 LCD panel and its bracket
spool_d = 200; spool_w = 65;  // a 1 kg spool, common
spool_tube_d = 25; spool_tube_len = 100;

module extrusion(len, a = 20, b = 20) {
    // an aluminium extrusion with a shallow slot on each face, along X
    color("silver") difference() {
        cube([len, a, b]);
        for (face = [0, 1]) for (s = [0 : (a > 20 ? 1 : 0)]) {
            // slots on the top and bottom faces
            translate([-1, s * 20 + 6, face * (b - 2) - 1]) cube([len + 2, 8, 3]);
        }
        for (face = [0, 1]) for (s = [0 : (b > 20 ? 1 : 0)]) {
            // slots on the front and back faces
            translate([-1, face * (a - 2) - 1, s * 20 + 6]) cube([len + 2, 3, 8]);
        }
    }
}

module extrusion_y(len, a = 20, b = 20) { translate([a, 0, 0]) rotate([0, 0, 90]) extrusion(len, a, b); }

// where the nozzle stands along Y, in the frame: 30 mm in front of the X gantry
function nozzle_y() = upright_y - rail - 30;
function bed_plate_x() = frame_w / 2 - bed_plate / 2;

module ender3_base() {
    // side rails: 2040 lying flat (40 wide, 20 tall), the full depth
    for (x = [0, frame_w - 2 * rail]) translate([x, 0, 0]) extrusion_y(frame_d, 2 * rail, rail);
    // front and rear crossbars: 2020 between the rails
    for (y = [0, frame_d - rail]) translate([2 * rail, y, 0]) extrusion(frame_w - 4 * rail, rail, rail);
    // the Y rail: 2040 lying flat down the middle, on the crossbars
    translate([frame_w / 2 - rail, 0, rail]) extrusion_y(frame_d, 2 * rail, rail);
    // the Y motor at the back, against the rear crossbar (overlapping it by a
    // little: a union of parts that only touch along an edge exports as a
    // mesh that is not closed, and OpenSCAD then drops it from any boolean)
    color("dimgray") translate([frame_w / 2 - 21, frame_d - 42 - rail + 1, rail - 1]) cube([42, 42, 42]);
}

module ender3_uprights() {
    for (x = [0, frame_w - rail]) translate([x, upright_y, rail - eps]) {
        // 2040 standing: 20 in X, 40 in Y, sunk a little into the rail
        color("silver") difference() {
            cube([rail, 2 * rail, upright_h + eps]);
            for (s = [0, 1]) translate([-1, s * 20 + 6, eps + 1]) cube([rail + 2, 8, upright_h]);
        }
    }
    // the 2020 top crossbar, sunk a little into the uprights
    translate([0, upright_y + rail / 2, top_bar_z - eps]) extrusion(frame_w, rail, rail);
    // the Z motor on the left upright's foot, and its leadscrew
    color("dimgray") translate([rail - eps, upright_y - 42 + eps, rail - eps]) cube([42, 42, 40]);
    // the leadscrew, in front of the X gantry's plate rather than through it: a
    // cylinder cutting a box's face is what the exporter tessellates worst
    color("gainsboro") translate([rail + 10, upright_y - 30, rail + 40 - eps]) cylinder(d = 8, h = upright_h - 60);
}

module ender3_gantry(z) {
    // the X gantry: a 2040 standing on edge (20 deep, 40 tall), in front of the uprights,
    // carried up the uprights on two wheel plates; the nozzle tip is z above the bed
    tip = bed_top_z + z;
    translate([0, upright_y - rail, tip + 50]) extrusion(frame_w, rail, 2 * rail);
    color("dimgray") for (x = [-2, frame_w - 40]) translate([x, upright_y - rail - 2, tip + 40]) cube([42, 44, 60]);
    // the X motor on the left end
    color("dimgray") translate([0, upright_y - rail - 42 + eps, tip + 49]) cube([42, 42, 42]);
    // the hotend carriage, its fan shroud, and the nozzle
    hx = bed_plate_x() + 7.5 + x_axis;
    color("dimgray") translate([hx - 22, upright_y - rail - 45, tip + 10]) cube([44, 45 + eps, 62]);
    color("black") translate([hx - 18, upright_y - rail - 60, tip + 6]) cube([36, 16 + eps, 40]);
    color("gainsboro") translate([hx, nozzle_y(), tip]) cylinder(d1 = 2, d2 = 8, h = 14 + eps);
}

module ender3_bed(y) {
    // the carriage rides the Y rail; the plate sits on springs above it. The bed
    // moves, not the nozzle: at y = 0 the printable area's front edge is under
    // the nozzle, at y = 220 the bed hangs out the front of the frame.
    by = nozzle_y() - 7.5 - y;
    translate([bed_plate_x(), by, 0]) {
        color("dimgray") translate([0, 0, 2 * rail - eps]) cube([bed_plate, bed_plate, carriage_t + eps]);
        color("gold") for (x = [15, bed_plate - 15]) for (yy = [15, bed_plate - 15])
            translate([x, yy, 2 * rail + carriage_t - eps]) cylinder(d = 8, h = bed_top_z - plate_t - 2 * rail - carriage_t + 2 * eps);
        color("darkslategray") translate([0, 0, bed_top_z - plate_t]) cube([bed_plate, bed_plate, plate_t]);
        // the printable area, marked
        color("black") translate([7.5, 7.5, bed_top_z - eps]) difference() {
            cube([build_x, build_y, 0.3 + eps]);
            translate([1, 1, -1]) cube([build_x - 2, build_y - 2, 3]);
        }
    }
}

module ender3_psu() {
    // on the right side, standing on the right rail behind the upright: the offset supply
    color("gray") translate([frame_w - eps, psu_y, rail - eps]) cube([psu.x + eps, psu.y, psu.z + eps]);
    color("black") translate([frame_w + psu.x - 1, psu_y + 20, rail + 20]) cube([2, 70, 70]);   // the fan grille
    color("black") translate([frame_w + 10, psu_y + psu.y - 1, rail + 30]) cube([30, 4, 20]);  // the switch
}

module ender3_electronics_box() {
    // under the bed, front left, hung from the bed's frame just above the
    // rails (so no face of it lies in the plane of the motor's foot), with
    // its fan on the left face
    translate([box_at.x, box_at.y, box_at.z]) {
        color("black") cube(box);
        color("dimgray") translate([-1, 60, 5]) cube([2, 45, 35]);
    }
}

module ender3_lcd() {
    // hung off the front-right corner on a bracket, tilted back
    translate([frame_w - 110, -6, rail + 40]) rotate([20, 0, 0]) {
        color("black") cube(lcd);
        color("darkslateblue") translate([6, -1, 12]) cube([lcd.x - 12, 1.2, 40]);
        color("dimgray") translate([lcd.x / 2 - 8, -8, lcd.z - 22]) cylinder(d = 16, h = 10);  // the knob
    }
    color("silver") translate([frame_w - 20, 0, rail - eps]) cube([20, 30, 60 + eps]);   // the bracket
}

module ender3_spool_holder() {
    // a bracket on the top bar, near the right upright; the tube points right
    ty = upright_y + rail;
    tz = top_bar_z + rail + 10;
    color("black") translate([frame_w - 70, ty - 10, top_bar_z + rail - eps]) cube([50, 40, 10 + eps]);
    color("black") translate([frame_w - 30, ty + 10, tz]) rotate([0, 90, 0]) cylinder(d = spool_tube_d, h = spool_tube_len);
    if (with_spool)
        color("cornflowerblue") translate([frame_w - 30 + 18, ty + 10, tz]) rotate([0, 90, 0]) difference() {
            cylinder(d = spool_d, h = spool_w);
            translate([0, 0, -1]) cylinder(d = 52, h = spool_w + 2);
        }
}

module ender3() {
    ender3_base();
    ender3_uprights();
    ender3_bed(y_axis);
    ender3_gantry(z_axis);
    ender3_psu();
    ender3_electronics_box();
    if (with_lcd) ender3_lcd();
    ender3_spool_holder();
}

ender3();
