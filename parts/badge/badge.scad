// Badge: a face or a word engraved in a plate. A face is drawn after its emoji from
// circles and strokes; its wrapper (apothecary/projects/parts/badge.py) places every
// eye, open mouth and stroke as this file does, as shares of the face's radius, and
// says the cuts that make a face on the router. A word is drawn in a font's outlines,
// and printed.
//
// The plate stands at the origin, its top at z = thickness: a face's centre at
// (diameter / 2, diameter / 2), a word's plate from (0, 0) to (width, height).
//
// Parameters:
//   kind          face or word
//   face          open, smile, neutral, wink, frown or grin: 😮 🙂 😐 😉 🙁 😀
//   text, font    the word, and the font it is drawn in (OpenSCAD's Liberation family)
//   diameter      a face, across (mm)
//   width, height a word's plate (mm)
//   text_size     the word's letters, high (mm)
//   thickness     the plate's (mm)
//   depth         how deep the face or the word is engraved (mm)
//   stroke        a face's strokes, wide: the router cuts them its tool's width (mm)
//   stock_margin  stock beyond a face on each side: the toolpath's, not drawn

kind = "face";
face = "smile";
text = "HELLO";
font = "Liberation Sans:style=Bold";
diameter = 80;         // [50:5:200]
width = 120;           // [30:5:220]
height = 40;           // [15:5:120]
text_size = 16;        // [4:1:80]
thickness = 6;         // [2:1:40]
depth = 2;             // [0.5:0.5:20]
stroke = 6;            // [1:0.5:12]
stock_margin = 10;     // [0:1:50]

/* [Hidden] */
$fn = 96;
// Shares of the face's radius, as the wrapper has them: each eye out and up and its
// diameter; an open mouth down and its diameter; the smile's arc about the centre and the
// frown's below it, each in ARC_SEGMENTS chords; a line's half length and its drop.
EYE_OUT = 0.35; EYE_UP = 0.3; EYE = 0.3;
MOUTH_DOWN = 0.4; MOUTH = 0.5;
ARC = 0.55; ARC_SEGMENTS = 12; FROWN_DOWN = 0.95;
LINE_HALF = 0.3; LINE_DOWN = 0.4;
// What a word keeps clear of its plate's edge.
WORD_MARGIN = 3;

function arc(cy, r, a0, a1) =
    [for (k = [0:ARC_SEGMENTS]) let (a = a0 + (a1 - a0) * k / ARC_SEGMENTS) [r * cos(a), cy + r * sin(a)]];

// A stroke the width of `stroke` along a line's points: what a tool that wide leaves
// when its centre runs along them.
module stroke_along(points) {
    for (i = [0:len(points) - 2])
        hull() {
            translate(points[i]) circle(d = stroke);
            translate(points[i + 1]) circle(d = stroke);
        }
}

module face_marks(r) {
    // The eyes: both, or the left alone where the right winks.
    for (side = face == "wink" ? [-1] : [-1, 1])
        translate([side * EYE_OUT * r, EYE_UP * r]) circle(d = EYE * r);
    if (face == "open") translate([0, -MOUTH_DOWN * r]) circle(d = MOUTH * r);
    if (face == "smile" || face == "wink") stroke_along(arc(0, ARC * r, 215, 325));
    if (face == "grin") let (a = arc(0, ARC * r, 200, 340)) stroke_along(concat(a, [a[0]]));
    if (face == "frown") stroke_along(arc(-FROWN_DOWN * r, ARC * r, 55, 125));
    if (face == "neutral") stroke_along([[-LINE_HALF * r, -LINE_DOWN * r], [LINE_HALF * r, -LINE_DOWN * r]]);
    if (face == "wink") stroke_along([[(EYE_OUT - EYE / 2) * r, EYE_UP * r], [(EYE_OUT + EYE / 2) * r, EYE_UP * r]]);
}

module face_badge() {
    r = diameter / 2;
    translate([r, r, 0])
        difference() {
            cylinder(r = r, h = thickness);
            translate([0, 0, thickness - depth]) linear_extrude(depth + 1) face_marks(r);
        }
}

module plate() {
    c = min(height / 4, 6);
    translate([c, c]) offset(r = c) square([width - 2 * c, height - 2 * c]);
}

module word_badge() {
    difference() {
        linear_extrude(thickness) plate();
        translate([0, 0, thickness - depth])
            linear_extrude(depth + 1)
                intersection() {
                    offset(delta = -WORD_MARGIN) plate();
                    translate([width / 2, height / 2])
                        text(text, size = text_size, font = font, halign = "center", valign = "center");
                }
    }
}

if (kind == "word") word_badge(); else face_badge();
