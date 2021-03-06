$fn=128;
r = 12.5;
h = 12;
brim = 5;
walls = 3;
tolerence = .4;
bottom = 3;
// width, height of contact element (paper clip)
contactX = 10;
contactZ = 1;

// mounting posts
postR = 3;
postHole = 1;

outerR = r + brim + walls;

module contact() {
    // profile of contact device
    cube([ contactX + tolerence, r * 4, contactZ + tolerence ], center=true);
}
module button() {
    difference() {
        union() {
            cylinder(r=r, h=h);
            cylinder(r= r + brim, h=bottom);
        }
        translate([0,0,contactZ / 2]) contact();
        //hole for LED
        translate([0,0,contactZ]) cube([ 5 + tolerence, 5 + tolerence, 2 + tolerence ], center=true);
    }
}

module post() {
    difference() {
        cylinder(r=postR, h=h);
        cylinder(r=postHole, h=h);
    }
}

module housing() {
    union() {
        difference() {
            cylinder(r= r + brim+ walls, h=h);
            cylinder(r= r + brim + tolerence, h=h);
            // holes for contacts
            translate([0, .8*r, bottom + ( h - bottom ) / 4]) rotate([0,0,90]) contact();
            translate([0, -.8*r, bottom + ( h - bottom ) / 4]) rotate([0,0,90]) contact();
        }
        translate(0,0,bottom-h) cylinder(r=r + brim + walls, h=bottom);
        // add posts for mounting
        translate([outerR+postR/4,0,0]) post();
        translate([0,outerR+postR/4,0]) post();
        translate([-outerR-postR/4,0,0]) post();
        translate([0,-outerR-postR/4,0]) post();
        
    }
}


button();
//translate([0,0,-h]) housing();