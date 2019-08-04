$fn=128;

filterW=130;
filterH=10;
fanW=120;
wall=2;
holeOff=7.5;
holeDiam=4.5;

module plateHole() {
    cylinder(r=holeDiam/2, h=wall);    
}

difference() {
    //base
    cube([filterW+2*wall, filterW+2*wall, filterH+wall]);
    //filter cutout
    translate([wall, wall, wall]) 
        cube([filterW, filterW, filterH]);
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
    
}
