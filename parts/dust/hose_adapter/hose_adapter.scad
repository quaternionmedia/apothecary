difference() {
  union() {
  // a
cylinder(h=40.0, r1=19.5, r2=20.5, center=false, $fn=128);
  translate([0.0, 0.0, 40.0]) {
  // flare
cylinder(h=2.5, r1=20.5, r2=23.0, center=false, $fn=128);
}
  translate([0.0, 0.0, 42.5]) {
  // collar
cylinder(h=2.5, r=23.0, center=false, $fn=128);
}
  translate([0.0, 0.0, 45.0]) {
  // transition
cylinder(h=8.0, r1=23.0, r2=16.3, center=false, $fn=128);
}
  translate([0.0, 0.0, 53.0]) {
  // step
cylinder(h=25.0, r1=16.3, r2=15.7, center=false, $fn=128);
}
  translate([0.0, 0.0, 78.0]) {
  // shoulder
cylinder(h=3.5, r1=15.7, r2=12.8, center=false, $fn=128);
}
  translate([0.0, 0.0, 81.5]) {
  // b
cylinder(h=20.0, r1=12.8, r2=12.2, center=false, $fn=128);
}
}
  union() {
  translate([0.0, 0.0, -1.0]) {
  // a bore
cylinder(h=41.01, r=17.5, center=false, $fn=128);
}
  translate([0.0, 0.0, 39.99]) {
  // flare bore
cylinder(h=2.52, r=17.5, center=false, $fn=128);
}
  translate([0.0, 0.0, 42.49]) {
  // collar bore
cylinder(h=2.52, r=17.5, center=false, $fn=128);
}
  translate([0.0, 0.0, 44.99]) {
  // transition bore
cylinder(h=8.02, r1=17.50475, r2=13.69525, center=false, $fn=128);
}
  translate([0.0, 0.0, 52.99]) {
  // step bore
cylinder(h=25.02, r=13.7, center=false, $fn=128);
}
  translate([0.0, 0.0, 77.99]) {
  // shoulder bore
cylinder(h=3.52, r1=13.71, r2=10.19, center=false, $fn=128);
}
  translate([0.0, 0.0, 81.49]) {
  // b bore
cylinder(h=21.01, r=10.2, center=false, $fn=128);
}
}
}
