$fn = 128;

peg = [6.8, 4.2, 10];

difference() {
    cylinder(d=25, h = 20);
    translate([0,0,-1]) cylinder(d=7, h=10);
    translate([-10,0,20]) cube([10,23,11],center=true);
    translate([10,0,20]) cube([10,23,11],center=true);
}