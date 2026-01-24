union() {
  translate([0.0, 0.0, 22.5]) {
  rotate(a=10.0, v=[1.0, 0.0, 0.0]) {
  // Snowplow blade
cube([120.0, 3.0, 45.0], center=true);
}
}
  translate([0.0, -3.0, 6.0]) {
  difference() {
  // Chassis mount plate
cube([40.0, 4.0, 12.0], center=true);
  union() {
  translate([-12.0, 0.0, 0.0]) {
  cylinder(h=20.0, r=1, center=true);
}
  translate([12.0, 0.0, 0.0]) {
  cylinder(h=20.0, r=1, center=true);
}
}
}
}
}