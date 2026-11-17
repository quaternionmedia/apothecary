// A tube standing on the bed with its bore through: what the dust category's
// stand-ins are drawn as, until the real hose and fittings are measured. A
// library the parts include, not a part.
module stub_tube(bore, outer, length) {
    difference() {
        cylinder(h = length, d = outer);
        translate([0, 0, -1]) cylinder(h = length + 2, d = bore);
    }
}
