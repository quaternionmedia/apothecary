
x = 180;
y = 100;
z = 30;
wall = 6;
theta = -16;

module wedge() {
    difference() {
        cube([x, y, z]);
        translate([0,0,z]) rotate([theta ,0,0]) cube([x, y*2, z*2]);
    }
}

difference() {
    wedge();
    translate([wall, wall, -wall]) rotate([theta, 0, 0]) cube([x - 2*wall,y - 2*wall, z]);
}