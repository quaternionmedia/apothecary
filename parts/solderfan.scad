$fn=128;

filterW=130;
filterH=10;
fanW=120;
wall=2;
holeOff=7.5;
holeDiam=4.5;
overhang=15;
overhangSide=pow(2, .5)*overhang/2;

module plateHole() {
    cylinder(r=holeDiam/2, h=wall);    
}

module lipCut() {
    rotate([0,0,45]) cube(overhang);
}
union() {
    difference() {
        //base
        cube([filterW+2*wall, filterW+2*wall, filterH+wall]);
        //filter cutout
        translate([wall, wall, wall]) 
            cube([filterW, filterW, filterH-wall]);
        //overhang cutouts
        translate([wall+overhangSide,wall,filterH])
            lipCut();
        translate([wall+filterW-overhangSide,wall,filterH]) 
            lipCut();
        translate([wall,wall+filterW-overhangSide,filterH]) 
            rotate([0,0,-90])
            lipCut();
        translate([wall+filterW-overhangSide,wall+filterW,filterH])
            rotate([0,0,180])
            lipCut();
        //front cutout
        translate([wall, wall+overhangSide, filterH])
            cube([filterW, filterW-2*overhangSide, wall]);
        translate([wall+overhangSide,wall, filterH])
            cube([filterW-2*overhangSide, filterW, wall]);
        //fan cutout
        translate([wall+filterW/2, wall+filterW/2, 0])
            cylinder(r=(fanW-2*wall)/2, h=wall);
        //screw cutouts
        x=wall+(filterW-fanW)/2 + holeOff;
        y=wall+(filterW-fanW)/2 + fanW - holeOff;
        translate([x, x, 0]) plateHole();
        translate([y, y, 0]) plateHole();
        translate([x, y, 0]) plateHole();
        translate([y, x, 0]) plateHole();
    
    };
    //polyhedron()
}