module test_rotator(w) {
    difference() {
        cylinder(10.5, d=32, $fn=32);
        translate([0, 0, -1])
        difference() {
            cylinder(21, d=w, $fn=20);
            translate([-w/2, -w/2, 0])
            translate([0, 0, -1])
            cube([w, 1, 25]);
        }
    }
}

module rotator_incline(w, dia1 = 32, dia2 = 32) {
    difference() {
        cylinder(10.5, d1=dia1, d2=dia2, $fn=32);
        translate([0, 0, -1])
        difference() {
            cylinder(21, d=w, $fn=20);
            translate([-w/2, -w/2, 0])
            translate([0, 0, -1])
            cube([w, 1, 25]);
        }
    }
}

//test_rotator(6.25);

module spool_male() {
    difference() {
    union() {
        difference () {
            difference() {
                // the center whole
                difference() {
                    // the spool
                    difference() {
                        // the edges
                        union() {
                            cylinder(1, d=48, $fn=32);
                            cylinder(20, d=39, $fn=32);
                            translate([0, 0, 20])
                            cylinder(1, d=48, $fn=32);
                        }
                        translate([0, 0, -1])
                        cylinder(19, d=35, $fn=32);
                    }
                }
                union() {
                    translate([-20, 0, 5])
                    cube([10,11,10]);
                    translate([-20, 0, 2])
                    cube([10, 1, 16]);
                }
            }
            translate([0, 0, -1])
            cylinder(11, d=48.5, $fn=31);
        }
        difference() {
            difference() {
                translate([0, 0, 2])
                cylinder(17, d=35, $fn=32);
                translate([0, 0, -1])
                cylinder(19, d=34, $fn=32);
            }
            // hack
            union() {
                translate([-20, 0, 1])
                //cube([10, 10, 14]);
                cube([10,11,14]);
                translate([-20, 0, 2])
                cube([10, 1, 16]);
            }
        }
    }
    translate([0, 0, -5])
    cylinder(40, d=9, $fn=32);
    }

}

module spool_female() {
    difference () {
        difference() {
            // the center whole
            difference() {
                // the spool
                difference() {
                    // the edges
                    union() {
                        cylinder(1, d=48, $fn=32);
                        cylinder(20, d=39, $fn=32);
                        translate([0, 0, 20])
                        cylinder(1, d=48, $fn=32);
                    }
                    translate([0, 0, -1])
                    cylinder(19, d=35, $fn=32);
                }
                //translate([0, 0, -5])
                cylinder(40, d=9, $fn=32);
            }
            union() {
                // Mirror!
                translate([-20, -10, 5])
                cube(10);
                translate([-20, 0, 2])
                cube([10, 1, 16]);
            }
        }
        translate([0, 0, -1])
        cylinder(11, d=48.5, $fn=31);
    }


    //difference() {
    //difference() {
    //    translate([0, 0, 2])
    //    cylinder(17, d=31, $fn=32);
    //    translate([0, 0, -1])
    //    cylinder(19, d=30, $fn=32);
    //}
    //// hack
    //union() {
    //    translate([-20, 0, 1])
    //    cube([10, 10, 14]);
    //    translate([-20, 0, 2])
    //    cube([10, 1, 16]);
    //}
    //}
}

module shaft() {
    difference() {
        union() {
        cube([40, 40, 2]);
        translate([20, 20, -40])
        cylinder(40, d=5, $fn=32);
        }
        translate([19.75, 15, -41])
        cube([0.5, 10, 10]);
    }
}

module spool_female_2()
{
spool_female();
translate([0,0,21])
//rotator_incline(6.25, 48);
rotator_incline(4.6, 48);
}
color([1,0,0]) spool_male();
color([0,1,0]) spool_female_2();
color([0,0,1]) test_rotator(4.5);