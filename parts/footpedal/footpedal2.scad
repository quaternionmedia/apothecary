$fn=128;

// housing dimensions
x = 180;
y = 180;
z = 2.5;
rise = 5;
wall = 2.5;
arduino = [20, 50, 10];

// button dimensions
r = 17;
gap = 1.5;

module button() {
    union() {
        difference() {
            cylinder(r = r, h = z);
            cylinder(r = r-gap, h = z);
            translate([-r/2, 0, 0]) cube([r, r, z]);
        }
        translate([r/2, .75*r, 0]) cube([gap, r, z]);
        translate([-r/2, .75*r, 0]) cube([gap, r, z]);
    }
}

module plate() {
    difference() {
        cube([x, y, z]);
       for ( dx = [0:3] ) {
           for (dy = [0:2]) {
            translate([dx*x/4+x/8, dy*y/3+y/8, 0]) button();
            }
           } 
        
    }
}

module housing() {
    difference() {
        cube([x, y, z + rise]);
        translate([wall, wall, z]) cube([x-2*wall, y-2*wall, rise]);
        translate([20, 0, z]) cube(arduino);
    }
}

module singleButtonPlate() {
    difference() {
        cube([2.8*r, 3.7*r, z]);
        translate([1.4*r, 1.4*r, 0]) button();        
    }
}

//button();
//plate();
housing();
