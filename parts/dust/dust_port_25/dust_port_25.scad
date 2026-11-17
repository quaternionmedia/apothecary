// A stand-in for a rigid dust port with a 25 mm bore, a tool's or a
// collector's, until one is measured: 25 mm of it, its mouth at the top.

include <../stub_tube.scad>

bore = 25;
outer = 31;
length = 25;
$fn = 128;

stub_tube(bore, outer, length);
