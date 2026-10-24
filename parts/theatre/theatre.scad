// Theatre - a proscenium theatre's shell: the stage floor, its side and upstage walls,
// the proscenium wall with its opening, the pit below the stage, and the side walls
// running downstage into the house.
//
// Frame: millimetres; the origin is the plaster line's centre on the stage floor;
// +x is to the right as the house sees the stage, +y upstage, +z up.
//
// Every default is a measurement of one real stage house, traced from its plan
// (a few boxes, not the outline). The house beyond the side walls, the fly tower
// and the seating are not drawn.

// Customizer parameters
stage_width = 23010;       // [8000:100:40000] Stage floor, wall to wall
stage_depth = 24375;       // [6000:100:40000] Plaster line to the upstage wall
wall_height = 9000;        // [4000:100:20000] Walls, from the stage floor
house_depth = 10920;       // [0:100:40000] How far the side walls run downstage of the plaster line
proscenium_width = 15015;  // [4000:100:40000] The proscenium opening
proscenium_height = 9000;  // [3000:100:20000] The opening's height; the wall's, for no header
pit_width = 20748;         // [0:100:40000] The pit below the stage
pit_length = 14040;        // [0:100:40000] The pit, downstage to upstage
pit_depth = 1200;          // [0:50:4000] The pit, below the stage floor's underside

/* [Hidden] */
stage_floor = 200;         // the stage floor's thickness
side_wall = 1365;          // the side walls' thickness
upstage_wall = 3900;       // the upstage wall's thickness
proscenium_wall = 312;     // the proscenium wall's thickness, centred on the plaster line
pit_front = 1170;          // how far downstage of the plaster line the pit begins

half = stage_width / 2;
opening = min(proscenium_width, stage_width) / 2;
// The opening cut from the floor to its height, or past the wall's top when it has no header.
cut = proscenium_height >= wall_height ? wall_height + 2 : proscenium_height;

module stage_floor() {
    translate([-half, 0, -stage_floor]) cube([stage_width, stage_depth, stage_floor]);
}

module side_walls() {
    for (x = [-half - side_wall, half])
        translate([x, -house_depth, 0]) cube([side_wall, house_depth + stage_depth, wall_height]);
}

module upstage_wall() {
    translate([-half - side_wall, stage_depth, 0])
        cube([stage_width + 2 * side_wall, upstage_wall, wall_height]);
}

module proscenium() {
    difference() {
        translate([-half, -proscenium_wall / 2, 0]) cube([stage_width, proscenium_wall, wall_height]);
        translate([-opening, -proscenium_wall, -1]) cube([2 * opening, 2 * proscenium_wall, cut + 1]);
    }
}

module pit() {
    if (pit_width > 0 && pit_length > 0 && pit_depth > 0)
        translate([-pit_width / 2, -pit_front, -stage_floor - pit_depth])
            cube([pit_width, pit_length, pit_depth]);
}

stage_floor();
side_walls();
upstage_wall();
proscenium();
pit();
