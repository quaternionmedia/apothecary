include<V-Slot.scad>
$fn = 32;

h = 20;
w = 10;
d = 10.2;

L = 2*25.4;

// rotate([0,90,0]) t_nut();
module rail() {
     intersection() {
         difference() {
             translate([-w/2,0,0]) cube([w, d, h]);
             intersection() {
                rotate([0,0,45]) cube(h);
                extrusion(0, tolerance);
             }
         }
         rotate([0,0,45]) cube(20);
         translate([-5,4,0]) cube([10,10,20]);
//         translate([-5,-8,0]) rotate([0,0,10]) cube(20);
     }
 }

 module bracket() {
     difference() {
         cube([20,20,L]);
         translate([-4,1,0]) rotate([0,0,20]) cube([30,30,2*25.4]);
         translate([0,3,L/4]) cube([15,5,L/2]);
         translate([0,5,L/2]) rotate([0,90,0]) cylinder(r=1.5, h=20);
         
     }
     
 }
 
 module bevel() {
     difference() {
        cube([20,L,2]);
        rotate([0,-45,0]) cube([2*sqrt(2),L,2*sqrt(2)]); 
     }
 }
 
 module assembly() {
     linear_extrude(height=2*25.4) {
         projection() rail();
     }
    translate([-10,10.2,0]) bracket();
 }
 
 difference() {
     assembly();
     translate([10,10.2,L]) rotate([90,180,-90]) bevel();
 }