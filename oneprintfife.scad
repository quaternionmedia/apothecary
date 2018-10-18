$fn = 128;

holes = [20,60,70,90,110,130,150,170,190];
holeRotation = [0,180,0,0,0,0,0,0,30];
holeRadius = [6,3,3,3,3,3,3,3,3];
height = 200;
bore = 20;
wall = 4;

difference() {
    union() {
        cylinder(d1=bore+wall+1, d2=bore+wall, h = height);
        translate([0,-bore/2 +3,holes[0]]) rotate([90,0,0]) {
            difference() {
                cylinder(r1=holeRadius[0]+2.5, r2 =holeRadius[0]+2, h = 6);
                translate([0,0,-1])cylinder(r1 = holeRadius[0], r2=holeRadius[0]-2, h = 7);
            }
        }
    }
    translate([0,0,2]) cylinder(d=bore, h = height);
    for ( i = [0:len(holes)-1] ){  
        translate([0,0,holes[i]]) rotate([90,0,holeRotation[i]]) cylinder(r=holeRadius[i], h=bore);
    }
}