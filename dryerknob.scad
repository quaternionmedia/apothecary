$fn = 100;

peg = [6.8, 4.2, 10];

difference() {
    cylinder(d=33, h = 20);
    difference() {
       translate([0,0,-1]) cylinder(d=8, h=10);
        translate([4.5,0,-1]) cube([7,8,7],center = true);
    }
    //translate([-18,0,20]) rotate([90,0,0]) cylinder(r=15,center=true, h = 40);
    translate([-18,0,20]) rotate([90,0,0]) cube([30,30,30], center=true);
    //translate([18,0,20]) rotate([90,0,0]) cylinder(r=15,center=true, h = 40);
}