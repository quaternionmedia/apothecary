difference() {
  // end
cylinder(h=30.0, r=19.0, center=false, $fn=128);
  translate([0.0, 0.0, -1.0]) {
  // end bore
cylinder(h=32.0, r=16.0, center=false, $fn=128);
}
}
