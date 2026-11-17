// rolling_rotor -- a rotor that rolls round inside its stator instead of turning on a shaft.
//
// The rotor is a disc a little smaller than the track it stands in. Pulled to one side it
// touches the track there; pulled round, the place it touches goes round the track and the
// rotor rolls, turning back on itself by the track's radius less its own, over its own, of
// a turn for each time round -- when it rolls without slipping, which is what the drawing
// assumes. Above the track the stator's pole teeth stand back by `gap`, so the gap between
// the poles and the rotor closes to `gap` where the rotor touches and opens to `gap` plus
// twice the eccentricity opposite: a gap that travels. The stator and the rotor print side
// by side, each flat on the bed; `print = false` draws them assembled at `orbit`.
//
// Units: mm and degrees. apothecary/projects/parts/rolling_rotor.py mirrors the outlines
// and the pose, measures the gap and where it travels, and holds its defaults to these
// literals; -D echo_shapes=true prints what this file computed, for checking.

/* [Machine] */
bore = 30;            // [10:0.5:90] radius of the track the rotor rolls on [mm]
eccentricity = 1;     // [0.2:0.1:6] the track's radius less the rotor's: how far the rotor's centre stands off the axis [mm]
gap = 0.5;            // [0:0.1:5] how far the pole tips stand back from the track [mm]
stack = 12;           // [3:1:40] height of the rotor, and of the poles above the floor [mm]
orbit = 0;            // [0:1:360] where the rotor's centre stands about the axis, which is where it touches the track [deg]

/* [Stator] */
poles = 8;            // [3:1:24] pole teeth
pole_width = 8;       // [2:0.5:30] width of a tooth [mm]
pole_depth = 10;      // [3:0.5:40] a tooth's depth from its tip to the yoke [mm]
yoke = 5;             // [2:0.5:20] the ring behind the teeth [mm]
base = 2;             // [1:0.2:6] the floor the rotor stands on [mm]
track_height = 2;     // [0.6:0.2:10] height of the track above the floor [mm]

/* [Rotor] */
hole = 10;            // [0:0.5:60] diameter of the rotor's centre hole, 0 for none [mm]
outputs = 4;          // [0:1:12] holes an output's pins run in, 0 for none
output_pin = 4;       // [1:0.5:12] diameter of the output's pins [mm]
output_circle = 16;   // [3:0.5:80] radius of the circle the holes stand on [mm]

/* [Drawing] */
facets = 180;         // [36:12:720] sides of a circle

/* [Hidden] */
// true: the stator and the rotor side by side, as they print; false: assembled at orbit.
print = true;
echo_shapes = false;  // -D echo_shapes=true prints the outlines and the pose
spacing = 6;          // between the stator and the rotor as they print [mm]

// ---- derived -------------------------------------------------------------------------------
tip_r = bore + gap;                    // the pole tips stand on this circle
yoke_r = tip_r + pole_depth;           // the slots' bottoms
outer_r = yoke_r + yoke;
rotor_r = bore - eccentricity;
output_d = output_pin + 2 * eccentricity;  // a pin of output_pin orbits in it, touching its wall
// The rotor's own turn when its centre stands at `orbit`: rolling on the track without slip.
turn = -orbit * eccentricity / rotor_r;
rotor_at = print ? [outer_r + spacing + rotor_r, 0, 0]
                 : [eccentricity * cos(orbit), eccentricity * sin(orbit), base];

// ---- outlines ----------------------------------------------------------------------------
// An arc of radius r from a0 to a1, both ends included, a point about every 360/facets degrees.
function arc(r, a0, a1) = let (n = max(1, ceil(abs(a1 - a0) * facets / 360)))
  [for (i = [0 : n]) let (a = a0 + (a1 - a0) * i / n) [r * cos(a), r * sin(a)]];
// The free space the poles leave: each tooth's tip on tip_r, its straight sides, and the
// slot's bottom on yoke_r to the next tooth. The teeth are pole_width wide all the way out.
function bore_outline() = let (pitch = 360 / poles, bt = asin(pole_width / 2 / tip_r),
                               by = asin(pole_width / 2 / yoke_r))
  [for (k = [0 : poles - 1]) let (c = k * pitch)
     each concat(arc(tip_r, c - bt, c + bt), arc(yoke_r, c + by, c + pitch - by))];
// A hole is drawn round its circle, so it is never smaller than its diameter.
module round_hole(d) { circle(r = d / 2 / cos(180 / facets), $fn = facets); }

// ---- the pieces ------------------------------------------------------------------------
module stator() {
  linear_extrude(height = base) circle(r = outer_r, $fn = facets);
  linear_extrude(height = base + track_height) difference() {
    circle(r = outer_r, $fn = facets);
    round_hole(2 * bore);
  }
  linear_extrude(height = base + stack) difference() {
    circle(r = outer_r, $fn = facets);
    polygon(bore_outline());
  }
}
module rotor() {
  linear_extrude(height = stack) difference() {
    circle(r = rotor_r, $fn = facets);
    if (hole > 0) round_hole(hole);
    if (outputs > 0)
      for (k = [0 : outputs - 1]) rotate(360 * k / outputs) translate([output_circle, 0]) round_hole(output_d);
  }
}

color("#3d4958") stator();
translate(rotor_at) rotate(print ? 0 : turn) color("#d9925a") rotor();

if (echo_shapes) {
  echo(bore_outline = bore_outline(), turn = turn, rotor_at = rotor_at, outer_r = outer_r);
}
