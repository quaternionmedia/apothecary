// cycloidal_disc -- a lobed disc that rolls round inside a ring of pins, the ratio set by its teeth.
//
// Pins stand in a ring in the stator's floor; the disc inside them has one lobe fewer. A
// crank carries the disc's centre round a small circle, and the lobes, running on the
// pins, turn the disc back one pin's pitch of a lobe each turn of the crank: the rolling
// rotor's roll, with the slip taken away by teeth. The disc's flank is the curve each
// pin's centre runs on, seen from the turning disc, moved in by the pin's radius and the
// clearance, so every pin stands `clearance` from it at every turn of the crank.
//
// The stator and the disc print side by side, each flat on the bed with nothing
// overhanging; `print = false` (hidden) draws them assembled at `crank`. The pins, the
// crank's bearing, the output's pins and anything in the pockets are bought, and this
// file never draws them -- unless `printed_pins` stands the pins up out of the floor.
//
// Units: mm and degrees. apothecary/projects/parts/cycloidal_disc.py mirrors the outlines
// and the pose, measures each pin's gap and the disc's free turn, and holds its defaults to
// these literals; -D echo_shapes=true prints what this file computed, for checking.

/* [Machine] */
pins = 11;            // [4:1:41] pins round the ring; the disc has one lobe fewer
pin_circle = 30;      // [10:0.5:120] radius of the circle the pins' centres stand on [mm]
pin = 5;              // [1:0.1:20] diameter of a pin [mm]
eccentricity = 1;     // [0.2:0.1:6] how far the crank carries the disc's centre off the axis [mm]
clearance = 0.1;      // [0:0.01:1] how far the disc's flank stands back from each pin, as drawn [mm]
thickness = 7;        // [2:0.5:40] the disc's thickness [mm]
crank = 0;            // [0:1:360] where the crank carries the disc's centre about the axis [deg]
printed_pins = false; // the pins printed with the floor instead of bought and pressed in

/* [Stator] */
base = 3;             // [1.5:0.5:10] the floor the pins stand in [mm]
wall = 6;             // [2:0.5:30] the housing's wall outside the pins [mm]
shaft = 8;            // [0:0.5:40] diameter of the hole in the floor the crank's shaft runs through, 0 for none [mm]

/* [Disc] */
bearing = 22;         // [0:0.5:80] diameter of the disc's centre hole, for the bearing on the crank, 0 for none [mm]
outputs = 6;          // [0:1:12] holes an output's pins run in, 0 for none
output_pin = 4;       // [1:0.5:12] diameter of the output's pins [mm]
output_circle = 18;   // [3:0.5:100] radius of the circle the output holes stand on [mm]

/* [Inserts] */
lobe_insert = 0;      // [0:0.1:20] diameter of a pocket from the top of each lobe for a bought insert, 0 for none [mm]
pole_insert = 0;      // [0:0.1:20] diameter of a pocket from the top of the wall between each two pins for a bought insert, 0 for none [mm]
insert_depth = 4;     // [1:0.5:40] depth of each insert's pocket from the top [mm]

/* [Drawing] */
profile = 720;        // [120:12:2880] points on the disc's profile
facets = 180;         // [36:12:720] sides of a circle
piece = "all";        // [all, stator, disc] what to draw: both, or one alone -- the disc in its own frame, its centre on the axis and unturned, where assembled

/* [Hidden] */
// true: the stator and the disc side by side, as they print; false: assembled at crank.
print = true;
echo_shapes = false;  // -D echo_shapes=true prints the outlines and the pose
spacing = 6;          // between the stator and the disc as they print [mm]
room = 1;             // between the pins' outsides and the housing's wall [mm]
insert_wall = 2;      // the least wall round an insert's pocket [mm]

// ---- derived -------------------------------------------------------------------------------
lobes = pins - 1;
offset = pin / 2 + clearance;                       // the flank stands this far in from the pins' centres' curve
tip_r = pin_circle + eccentricity - offset;         // the lobes' tips, from the disc's centre
inner_r = pin_circle + pin / 2 + room;              // the housing's wall's inside
outer_r = inner_r + wall;
height = base + thickness;
output_d = output_pin + 2 * eccentricity;           // a pin of output_pin orbits in it, touching its wall
// The disc's own turn when the crank stands at `crank`: one pin's pitch back each turn.
turn = -crank / lobes;
disc_at = print ? [outer_r + spacing + tip_r, 0, 0]
        : piece == "disc" ? [0, 0, base]
        : [eccentricity * cos(crank), eccentricity * sin(crank), base];
pole_insert_r = inner_r + wall / 2;
lobe_insert_r = pin_circle - eccentricity - offset - insert_wall - lobe_insert / 2;  // under each lobe's tip, a wall in from the roots

// ---- outlines ----------------------------------------------------------------------------
// The disc's flank at s: the curve every pin's centre runs on in the disc's frame,
// [R cos s - E cos N s, R sin s - E sin N s], moved in along its outward normal by offset.
function flank(s) = let (
    cx = pin_circle * cos(s) - eccentricity * cos(pins * s),
    cy = pin_circle * sin(s) - eccentricity * sin(pins * s),
    nx = pin_circle * cos(s) - eccentricity * pins * cos(pins * s),
    ny = pin_circle * sin(s) - eccentricity * pins * sin(pins * s),
    l = sqrt(nx * nx + ny * ny))
  [cx - offset * nx / l, cy - offset * ny / l];
function profile_outline() = [for (i = [0 : profile - 1]) flank(360 * i / profile)];
// A hole is drawn round its circle, so it is never smaller than its diameter.
module round_hole(d) { circle(r = d / 2 / cos(180 / facets), $fn = facets); }
// A pocket from the top, `top` high, `insert_depth` deep, at [x, y].
module pocket(d, x, y, top) {
  translate([x, y, top - insert_depth]) linear_extrude(height = insert_depth + 1) round_hole(d);
}

// ---- the pieces ------------------------------------------------------------------------
module stator() {
  difference() {
    union() {
      linear_extrude(height = base) difference() {
        circle(r = outer_r, $fn = facets);
        if (!printed_pins) for (k = [0 : pins - 1]) rotate(360 * k / pins) translate([pin_circle, 0]) round_hole(pin);
        if (shaft > 0) round_hole(shaft);
      }
      linear_extrude(height = height) difference() {
        circle(r = outer_r, $fn = facets);
        circle(r = inner_r, $fn = facets);
      }
      if (printed_pins)
        for (k = [0 : pins - 1]) rotate(360 * k / pins) translate([pin_circle, 0, 0])
          cylinder(h = height, r = pin / 2, $fn = facets);
    }
    if (pole_insert > 0)
      for (k = [0 : pins - 1]) let (a = 180 * (2 * k + 1) / pins)
        pocket(pole_insert, pole_insert_r * cos(a), pole_insert_r * sin(a), height);
  }
}
module disc() {
  difference() {
    linear_extrude(height = thickness) difference() {
      polygon(profile_outline());
      if (bearing > 0) round_hole(bearing);
      if (outputs > 0)
        for (k = [0 : outputs - 1]) rotate(360 * k / outputs) translate([output_circle, 0]) round_hole(output_d);
    }
    if (lobe_insert > 0)
      for (k = [0 : lobes - 1]) let (a = 180 * (2 * k + 1) / lobes)
        pocket(lobe_insert, lobe_insert_r * cos(a), lobe_insert_r * sin(a), thickness);
  }
}

if (piece != "disc") color("#3d4958") stator();
if (piece != "stator") translate(disc_at) rotate(print || piece == "disc" ? 0 : turn) color("#d9925a") disc();

if (echo_shapes) {
  echo(profile_outline = profile_outline(), turn = turn, disc_at = disc_at, outer_r = outer_r);
}
