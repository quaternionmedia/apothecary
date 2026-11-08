// Elgato Stream Deck +, as a workshop model: eight LCD keys in two rows of
// four, a touch strip under them and four knobs under that, on a body whose
// face slopes up toward the back on a stand that is part of the device. The
// controller a person at the bench jogs the machines with
// (apothecary/firmware/deck_control.py); the garage stands it at the
// workbench's front edge.
//
// Built from the maker's published figures, not from anyone's mesh. The
// origin is the front-left bottom corner of the base plate; X runs right, Y
// runs back, Z runs up -- the site's convention for a thing on the bench.
//
// Every dimension that is the maker's is named as such; the rest are assumed,
// say so, and are listed in README.md beside this file. Nothing here is a
// trademark: "Stream Deck +" names what the part models.

// Customizer parameters
face_angle = 40;   // [30:0.5:41] The face's slope from the bench (degrees): assumed; the maker gives the overall size alone, so the body's thickness follows from this
lit = true;        // Draw the keys and the strip lit, as a deck apothecary is drawing shows them

/* [Hidden] */
$fn = 32;
eps = 0.5;   // how far a part sinks into what it stands on, so the union is one closed mesh

// --- published (Elgato's technical specifications page) ---
width = 140; depth = 138; height = 110;   // overall, the stand included
key_cols = 4; key_rows = 2;               // eight LCD keys
knobs = 4;                                // four encoders with a push function
strip = [108, 14];                        // the LCD touch panel

// --- assumed: how the body is laid out ---
plate_t = 6;        // the base plate the body and its stand share
set_back = 20;      // the body's front edge behind the plate's, where the plate shows under the knobs
key = 24;           // a key's face, square
key_pitch = 28;     // centre to centre, so the four keys span the strip's width
key_r = 3;          // a key's corner radius
key_proud = 1;      // a key's face above the body's
knob_d = 16; knob_h = 14;
stand = [100, 32];  // the stand under the body's back: its width and depth
// where each row stands along the face, from the body's front edge
knob_s = 18;
strip_s = 34;
key_s = [66, 94];

// --- derived, so the envelope is the maker's whatever the angle ---
// The body is a slab `body_l` long and `body_t` thick, tilted by face_angle on
// the plate, its front edge set_back behind the plate's front. Its back-bottom
// corner reaches depth - body_t * sin(a) and its back-top corner reaches the
// maker's height: two equations, which give the slab's length and thickness.
avail = depth - set_back;
rise = height - (plate_t - eps);   // the body sinks eps into the plate, so its top still reaches the maker's height
body_l = (avail * cos(face_angle) - rise * sin(face_angle)) / cos(2 * face_angle);
body_t = (rise * cos(face_angle) - avail * sin(face_angle)) / cos(2 * face_angle);

function key_x(i) = width / 2 + (i - (key_cols - 1) / 2) * key_pitch;

module rounded_square(size, r) {
    offset(r = r) offset(delta = -r) square(size);
}

// a key's face: a rounded square standing key_proud of the body, lit or dark
module key_face(at) {
    color(lit ? "steelblue" : "#303030")
        translate([at.x - key / 2, at.y - key / 2, body_t - eps])
            linear_extrude(key_proud + eps) rounded_square([key, key], key_r);
}

module knob(at) {
    color("#202020") translate([at.x, at.y, body_t - eps]) cylinder(d = knob_d, h = knob_h + eps);
    color("#404040") translate([at.x, at.y, body_t + knob_h - eps]) cylinder(d = knob_d - 4, h = 1 + eps);
}

// the body in its own frame: x across, y along the slope from the front edge, z its thickness
module body() {
    color("#1a1a1a") cube([width, body_l, body_t]);
    for (r = [0 : key_rows - 1]) for (c = [0 : key_cols - 1])
        key_face([key_x(c), key_s[r]]);
    color(lit ? "cadetblue" : "#303030")
        translate([(width - strip[0]) / 2, strip_s, body_t - eps]) cube([strip[0], strip[1], eps + 0.5]);
    for (c = [0 : knobs - 1]) knob([key_x(c), knob_s]);
}

module stream_deck_plus() {
    color("#1a1a1a") cube([width, depth, plate_t]);
    // the body, tilted on the plate from its front edge
    translate([0, set_back, plate_t - eps]) rotate([face_angle, 0, 0]) body();
    // the stand: from the plate up to the body's underside, under its back
    back = set_back + body_l * cos(face_angle);
    color("#1a1a1a") translate([(width - stand[0]) / 2, 0, 0]) rotate([90, 0, 90])
        linear_extrude(stand[0]) polygon([
            [back - stand[1], plate_t - eps],
            [back, plate_t - eps],
            [back, plate_t + (back - set_back) * tan(face_angle)],
            [back - stand[1], plate_t + (back - stand[1] - set_back) * tan(face_angle)],
        ]);
}

stream_deck_plus();
