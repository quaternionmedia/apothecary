// A stand-in for a rigid dust port with a 32 mm bore, a tool's or a
// collector's, until one is measured: 30 mm of it, its mouth at the top.

include <../stub_tube.scad>

bore = 32;
outer = 38;
length = 30;
$fn = 128;

stub_tube(bore, outer, length);
