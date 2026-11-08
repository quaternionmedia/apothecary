# Stream Deck +

An Elgato Stream Deck + as a workshop model, built in OpenSCAD from the
maker's published figures: eight LCD keys in two rows of four, a touch strip
under them and four knobs under that, on a body whose face slopes up toward
the back, standing on a base plate with its stand, which is part of the
device. The garage stands it at the workbench's right end behind the boards, the node
`stream_deck`, where a person at the machines has it to hand; `face_angle` is
a parameter, and `lit` draws the keys and the strip as a deck apothecary is
drawing shows them.

What the maker publishes, on its technical specifications page
(help.elgato.com, *Elgato Stream Deck Technical Specifications*), and the
model takes as it is:

- the overall size, `140 x 138 x 110 mm`, the stand included, which is the
  model's envelope whatever `face_angle` is set to;
- eight LCD keys, four 360° encoders with a push function, and an LCD touch
  panel of `108 x 14 mm`.

What the maker does not publish, and the model assumes, named in
`stream_deck_plus.scad` beside each number:

- a key's face is `24 mm` square at a `28 mm` pitch, so the four keys span the
  strip's width, with `3 mm` corners and standing `1 mm` proud of the face;
- a knob is `16 mm` across and `14 mm` tall;
- the base plate is `6 mm` thick and the body's front edge stands `20 mm`
  behind the plate's front; the stand under the body's back is `100 mm` wide
  and `32 mm` deep;
- where each row stands along the face, from the body's front edge: the knobs
  at `18 mm`, the strip at `34 mm`, the keys at `66` and `94 mm`;
- the face's slope, `face_angle`, `40°` by default. The body's length and
  thickness follow from the angle and the maker's envelope, so a steeper face
  is a thinner body and a shallower one thicker; past `41°` the maker's height
  is reached with no body at all, which is where the parameter's range ends.

A drawing from the maker, or a deck measured at the bench, replaces every
assumed number here; the part's name and the node stay.
`stream_deck_plus.scad` contains no one else's mesh: the model is this
repository's own, MIT. Nothing here is a trademark: "Stream Deck +" names
what the part models.
