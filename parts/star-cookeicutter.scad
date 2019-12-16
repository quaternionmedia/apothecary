//-- 5-pointed star
//-- (c)  2010 Juan Gonzalez-Gomez (Obijuan) juan@iearobotics.com
//-- GPL license
use <parametric_star.scad>
$fn=64;

module star(r=15, wall=.1, h=10) {
        minkowski() {
            parametric_star(ri=r/2.718-wall, re=r-wall, h=h);
            cylinder(r=2);
        }
}

difference() {
    star(r=30, wall=0);
    star(r=28);
}
