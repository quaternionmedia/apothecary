include<V-Slot.scad>
$fn = 32;

h = 20;
w = 10;
d = 10.2;

L = 10;
extension = .2;

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
         translate([-4,5,0]) rotate([0,0,20]) cube([30,30,L]);
         translate([3,2,L/4]) cube([9,10,L]);
         translate([0,7,L/4]) rotate([34,0,0]) cube([3,15,15]);
         translate([0,7,L*.6]) rotate([0,90,0]) cylinder(r=1.75, h=20);
         
     }
     
 }
 
 module bevel() {
     difference() {
        cube([20,L,5]);
        rotate([0,-45,0]) cube([5*sqrt(2),L,5*sqrt(2)]); 
     }
 }
 
 module assembly() {
     linear_extrude(height=L) {
         projection() rail();
     }
    translate([-4.8,10.2,0]) cube([9.3,extension,L]);
    translate([-10,10 + extension,0]) bracket();
 }
 
 module mount() {
     difference() {
         assembly();
         translate([11,8,L]) rotate([90,180,-90]) bevel();
         translate([-5,0,0]) cube([10,10+extension,4]);
     }
 }
 // left
 // mount();
 
 // right
 mirror([1,0,0]) mount();