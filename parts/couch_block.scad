// foot for new pink couch! ~H 2018-02-19
// h=4
// 1/2b = 3
// 1/2w = 2


$fn=64;
x = 25.4;

difference() {

linear_extrude(height=2*x) {  
minkowski() {
    polygon([
        [-1.5*x, 3.5*x],
        [1.5*x, 3.5*x],
        [2.5*x, .5*x],
        [-2.5*x, .5*x]
        ]);
    
    
    circle(r=.5*x);
};
};
 pilot_hole();
translate([1.5*x, 0,0])
pilot_hole();
translate([-1.5*x, 0,0])
pilot_hole();
};

module pilot_hole() {
    
translate([0,0,x])
rotate([-90,0,0])
cylinder(r=.4*x, h=x*3.7);

translate([0,0,x])
rotate([-90,0,0])
cylinder(r=.05*x, h=4*x);
}