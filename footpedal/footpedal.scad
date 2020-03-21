$fn=128;
x = 180;
y = 100;
z = 30;
wall = 4;
theta = -16;

module wedge() {
    
minkowski() {
    
      cylinder(r=wall,h=1);

    difference() {
        cube([x, y, z]);
        translate([0,0,z]) rotate([theta ,0,0]) cube([x, y*2, z*2]);
    }
}
}

module button(d=12.5) {
    cylinder(r=d, h=z);
}

module pedalboard() {
    difference() {
        wedge();
        // subtract bulk of underside, leaving wall in middle
        translate([wall, wall, -wall]) rotate([theta, 0, 0]) cube([(x - 2*wall)/2,y - 2*wall, z]);
        translate([x/2+wall, wall, -wall]) rotate([theta, 0, 0]) cube([x/2 - 2*wall,y - 2*wall, z]);
        // make holes for buttons
        for (row = [1 , 3]) {
            for (column = [1 : 4]) {
                translate([column*x/4 - x/8, row*y/4, 0]) rotate([theta, 0, 0]) button();
            }
        }
        // make hole for arduino nano
        translate([x*.18, -wall, z/5]) cube([20, wall*4, 10]);  
        
    }
}


rotate([180-theta, 0, 0]) 
pedalboard();