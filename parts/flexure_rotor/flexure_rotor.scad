// flexure_rotor -- a rotor carried on leaves printed with its stator, in one piece.
//
// A hub with lobes stands inside a ring with posts, joined to it by thin leaves: the hub
// turns by bending them, a few degrees either way, with no bearing and nothing to
// assemble. Each lobe has a post beside it, `stop` degrees round: turning the hub that way
// closes the gap between the lobe's flank and the post's, until they touch and stop it.
// The leaves are the spring that brings it back. Drawn at `swing`, the hub is turned and
// each leaf bent as a beam built in at both ends: a cubic from the hub's root to the ring's.
// It prints flat, as drawn at swing 0, in one piece with nothing overhanging; the pockets
// in the lobes and the posts take what is bought to pull them together, which this file
// never draws. `piece` draws the ring or the hub alone, without the leaves, for a viewer
// that moves the hub and draws each leaf from the model's own curve.
//
// Units: mm and degrees. apothecary/projects/parts/flexure_rotor.py mirrors the outlines,
// measures the gaps, the stop and the leaves' bending, and holds its defaults to these
// literals; -D echo_shapes=true prints what this file computed, for checking.

/* [Rotor] */
hub = 10;             // [4:0.5:40] radius of the hub, where the leaves start [mm]
lobes = 2;            // [1:1:6] lobes on the hub, evenly spaced
lobe_r = 22;          // [6:0.5:80] radius of the lobes' tips [mm]
lobe_arc = 40;        // [5:1:120] each lobe's width [deg]
swing = 0;            // [-20:0.5:20] the hub's turn as drawn [deg]

/* [Stator] */
ring = 34;            // [8:0.5:100] inner radius of the ring, where the leaves end [mm]
wall = 5;             // [2:0.5:20] the ring's wall [mm]
post_r = 14;          // [4:0.5:80] radius of the posts' tips [mm]
post_arc = 30;        // [5:1:120] each post's width [deg]
stop = 8;             // [1:0.5:45] how far the hub turns before each lobe's flank meets its post's [deg]

/* [Leaves] */
leaves = 2;           // [1:1:4] leaves between each post and the next lobe
leaf = 0.8;           // [0.4:0.05:3] a leaf's thickness [mm]
height = 8;           // [2:0.5:30] height of the whole piece [mm]

/* [Pockets] */
pocket = 6.2;         // [0:0.1:15] diameter of a pocket in each lobe and each post, 0 for none [mm]
pocket_depth = 3;     // [0.5:0.5:20] depth of a pocket from the top [mm]

/* [Drawing] */
facets = 180;         // [36:12:720] sides of a circle
piece = "all";        // [all, ring, hub] what to draw: the piece, or one part of it alone without the leaves -- the ring and its posts, or the hub and its lobes unturned

/* [Hidden] */
leaf_steps = 24;      // straight pieces a leaf is drawn in
echo_shapes = false;  // -D echo_shapes=true prints the outlines

// ---- where things stand ----------------------------------------------------------------
function lobe_at(k) = 360 * k / lobes;                   // a lobe's middle, at swing 0
function post_from(k) = lobe_at(k) + lobe_arc / 2 + stop;  // a post's flank nearest its lobe
free = 360 / lobes - lobe_arc - stop - post_arc;         // the room for leaves after each post
function leaf_at(k, j) = post_from(k) + post_arc + free * (j + 1) / (leaves + 1);
turned = piece == "hub" ? 0 : swing;                     // the hub alone is drawn unturned

// ---- outlines ----------------------------------------------------------------------------
// An arc of radius r from a0 to a1, both ends included, a point about every 360/facets degrees.
function arc(r, a0, a1) = let (n = max(1, ceil(abs(a1 - a0) * facets / 360)))
  [for (i = [0 : n]) let (a = a0 + (a1 - a0) * i / n) [r * cos(a), r * sin(a)]];
// The hub and its lobes, turned by swing: each lobe's tip, its flanks straight down to the
// hub, the hub's rim to the next lobe.
function hub_outline() = [for (k = [0 : lobes - 1]) let (c = lobe_at(k) + turned, h = lobe_arc / 2)
  each concat(arc(lobe_r, c - h, c + h), arc(hub, c + h, c - h + 360 / lobes))];
// The free space inside the ring and its posts: each post's tip, its flanks straight out
// to the ring, the ring to the next post.
function cavity_outline() = [for (k = [0 : lobes - 1]) let (a = post_from(k), b = a + post_arc)
  each concat(arc(post_r, a, b), arc(ring, b, a + 360 / lobes))];
// A leaf at angle a: its middle a cubic from the hub's rim, turned by swing, to the ring,
// leaving each square to it (Hermite, the shape of a beam built in at both ends when the
// turn is small); `ext` carries it on straight into the hub and the ring.
function hermite(p0, t0, p1, t1, u) =
  (2 * u * u * u - 3 * u * u + 1) * p0 + (u * u * u - 2 * u * u + u) * t0
  + (-2 * u * u * u + 3 * u * u) * p1 + (u * u * u - u * u) * t1;
function hermite_d(p0, t0, p1, t1, u) =
  (6 * u * u - 6 * u) * p0 + (3 * u * u - 4 * u + 1) * t0
  + (-6 * u * u + 6 * u) * p1 + (3 * u * u - 2 * u) * t1;
function leaf_outline(a, ext) = let (
    span = ring - hub, u0 = [cos(a + swing), sin(a + swing)], u1 = [cos(a), sin(a)],
    p0 = hub * u0, t0 = span * u0, p1 = ring * u1, t1 = span * u1,
    mid = [for (i = [0 : leaf_steps]) hermite(p0, t0, p1, t1, i / leaf_steps)],
    side = [for (i = [0 : leaf_steps]) let (d = hermite_d(p0, t0, p1, t1, i / leaf_steps)) [-d[1], d[0]] / norm(d)],
    n0 = [-u0[1], u0[0]], n1 = [-u1[1], u1[0]], h = leaf / 2)
  concat(ext > 0 ? [p0 - ext * u0 + h * n0] : [],
         [for (i = [0 : leaf_steps]) mid[i] + h * side[i]],
         ext > 0 ? [p1 + ext * u1 + h * n1, p1 + ext * u1 - h * n1] : [],
         [for (i = [leaf_steps : -1 : 0]) mid[i] - h * side[i]],
         ext > 0 ? [p0 - ext * u0 - h * n0] : []);
function leaf_angles() = [for (k = [0 : lobes - 1]) for (j = [0 : leaves - 1]) leaf_at(k, j)];

// ---- the piece -------------------------------------------------------------------------
module pocket_at(r, a) {
  translate([r * cos(a), r * sin(a), height - pocket_depth])
    linear_extrude(height = pocket_depth + 1) circle(r = pocket / 2 / cos(180 / facets), $fn = facets);
}
module flexure_rotor() {
  difference() {
    linear_extrude(height = height) union() {
      if (piece != "hub") difference() {
        circle(r = ring + wall, $fn = facets);
        polygon(cavity_outline());
      }
      if (piece != "ring") polygon(hub_outline());
      if (piece == "all") for (a = leaf_angles()) polygon(leaf_outline(a, leaf));
    }
    if (pocket > 0) for (k = [0 : lobes - 1]) {
      if (piece != "ring") pocket_at((hub + lobe_r) / 2, lobe_at(k) + turned);
      if (piece != "hub") pocket_at((post_r + ring) / 2, post_from(k) + post_arc / 2);
    }
  }
}

color("#d9925a") flexure_rotor();

if (echo_shapes) {
  echo(hub_outline = hub_outline(), cavity_outline = cavity_outline(),
       leaves = [for (a = leaf_angles()) leaf_outline(a, leaf)]);
}
