r = 12.5;
h = 15;
brim = 5;
walls = 4;

module button() {
    difference() {
        union() {
            cylinder(r=r, h=h);
            cylinder(r=r+brim, h=2);
        }
        cube([10,r*3,1], center=true);
    }
}

button();

