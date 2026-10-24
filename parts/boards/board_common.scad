// What every board model here is made of: a PCB with holes, pin headers,
// chips and jacks, drawn from published dimensions. Nothing here is anyone's
// mesh; a board's outline, hole positions and connector placements are
// specifications the makers publish so that cases and shields can be made.
//
// Every board's origin is its PCB's front-left bottom corner (x right, y back,
// z up), with the PCB lying flat on z = 0 -- so a board placed at a node in
// a site sits on that node's floor, which is where a board sits on a bench.

pcb_t = 1.6;
pitch = 2.54;

module pcb(size, holes = [], hole_d = 3.2, col = "darkgreen") {
    color(col) difference() {
        cube([size.x, size.y, pcb_t]);
        for (h = holes) translate([h.x, h.y, -1]) cylinder(d = hole_d, h = pcb_t + 2, $fn = 16);
    }
}

// Pins are square posts that overlap what they stand in. OpenSCAD 2021.01
// exports a union with hexagonal pins, or with parts that only touch along
// an edge, as a mesh that is not closed -- and then drops it from any later
// union, silently. Every part here overlaps its neighbour by a little.
pin = 0.64;

// a row of `n` pins at the given start, along +x (or +y when `along_y`), with plastic bodies
module header(n, at, along_y = false, rows = 1, h = 8.5) {
    translate([at.x, at.y, pcb_t - 0.1]) rotate([0, 0, along_y ? 90 : 0]) translate([0, along_y ? -rows * pitch : 0, 0]) {
        color("black") cube([n * pitch, rows * pitch, h]);
        color("gold") for (i = [0 : n - 1]) for (r = [0 : rows - 1])
            translate([i * pitch + pitch / 2 - pin / 2, r * pitch + pitch / 2 - pin / 2, -3]) cube([pin, pin, h + 6]);
    }
}

// a row of `n` bare pins pointing down (a devkit standing on a breadboard).
// The pins are one gold strip, not n posts: n posts through a plastic bar
// under a PCB is a face with n holes, which OpenSCAD 2021.01 exports as a
// mesh CGAL will not read back. At bench scale a strip is a row of pins.
module pins_down(n, at, along_y = false, len = 11) {
    // one translate per solid, from the board's own frame: a chain of
    // translates with negative offsets rounds differently and the exporter
    // then writes a mesh CGAL will not read back (seen; not understood)
    rotate([0, 0, along_y ? 90 : 0]) {
        color("black") translate([at.x, at.y - pitch / 2, pcb_t - pitch]) cube([n * pitch, pitch, pitch + 0.1]);
        color("gold") translate([at.x + pitch / 2 - pin / 2, at.y - pin / 2, -len]) cube([(n - 1) * pitch + pin, pin, len + pcb_t - pitch + 0.2]);
    }
}

module chip(size, at, col = "black") { color(col) translate([at.x, at.y, pcb_t - 0.1]) cube([size.x, size.y, size.z + 0.1]); }

module usb_b(at) {           // a full-size USB-B jack, its face at the -x side
    color("silver") translate([at.x, at.y, pcb_t]) cube([16, 12, 11]);
}
module barrel_jack(at) {     // a 2.1 mm DC jack, its face at the -x side
    color("black") translate([at.x, at.y, pcb_t]) cube([14, 9, 11]);
}
module micro_usb(at, along_y = false) {
    color("silver") translate([at.x, at.y, pcb_t]) cube(along_y ? [8, 6, 3] : [6, 8, 3]);
}
module usb_c(at) { color("silver") translate([at.x, at.y, pcb_t]) cube([9, 7.5, 3.2]); }
module usb_a_stack(at) {     // two USB-A ports one above the other, the face at +x
    color("silver") translate([at.x, at.y, pcb_t]) cube([17.5, 13.2, 16]);
}
module rj45(at) { color("silver") translate([at.x, at.y, pcb_t]) cube([21.5, 16, 13.5]); }
module button(at) { color("silver") translate([at.x, at.y, pcb_t - 0.1]) cube([6, 6, 3.6]); color("black") translate([at.x + 1.5, at.y + 1.5, pcb_t + 3.4]) cube([3, 3, 1.1]); }
module crystal(at) { color("silver") translate([at.x, at.y, pcb_t]) cube([11, 4.5, 3.5]); }
module heatsink(at, size = [9, 9, 8]) { color("black") translate([at.x, at.y, pcb_t - 0.1]) cube([size.x, size.y, size.z + 4.1]); }
module screw_terminal(n, at, along_y = false) {
    translate([at.x, at.y, pcb_t]) rotate([0, 0, along_y ? 90 : 0]) color("mediumblue") cube([n * 5.08, 8, 10]);
}
module jst(n, at, along_y = false) {   // a JST-XH style header
    translate([at.x, at.y, pcb_t]) rotate([0, 0, along_y ? 90 : 0]) color("ivory") cube([n * 2.5 + 2.4, 5.8, 7]);
}
module sd_slot(at) { color("silver") translate([at.x, at.y, pcb_t]) cube([26, 28, 3]); }
