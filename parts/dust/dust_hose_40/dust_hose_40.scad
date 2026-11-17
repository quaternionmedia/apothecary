// A stand-in for a smooth 40 mm bore dust hose, until it is measured: 100 mm of
// it, its end at the top. part.json declares that end as a socket that opens
// 5% when pushed, a guess for rubber or PVC.

include <../stub_tube.scad>

bore = 40;
outer = 48;
length = 100;
$fn = 128;

stub_tube(bore, outer, length);
