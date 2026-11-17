# parts/

The printable sources. Each part is a folder holding a SCAD file of the same
name; a folder whose subfolders are parts is a category.

```
parts/
├── couch_block/
│   ├── couch_block.scad    the source
│   └── couch_block.stl     built by apothecary parts generate-stl, git-ignored
├── boards/                 a category
│   └── arduino_uno/        arduino_uno.scad and part.json: a part with no Python
├── cameras/                a category: the library's webcam, and mounts for it
│   ├── webcam/             webcam.scad and part.json
│   └── webcam_desk_stand/  part.json tags it a stub, as it does the clamp arm and the ceiling mount
├── dust/                   a category: a hose adapter, and stand-ins for the hose and ports it fits
│   ├── hose_adapter/       hose_adapter.scad, written from its Python, which declares its interfaces
│   └── dust_hose_40/       dust_hose_40.scad and part.json, its interface a stub's
├── stream_deck_plus/
│   └── stream_deck_plus.scad   the Stream Deck + at the bench, from the maker's published size
├── anolex_4060_evo_ultra_2/
│   └── anolex_4060_evo_ultra_2.scad   the router, drawn as it is
├── router_coupon/
│   └── router_coupon.scad   a plate with a pocket and holes, cut on the router (its cuts in the wrapper)
├── router_emoji/
│   └── router_emoji.scad    a 😮 cut on the router, measured to calibrate it (its cuts in the wrapper)
├── ender3/
│   ├── ender3.scad         the printer, drawn as it is
│   └── slicer.json         printer_1's slicer profile, kept with its part
└── esp32_blink/
    ├── esp32_blink.ino     an Arduino sketch kept beside the parts
    └── rust/               the Rust esp32_blink: a Cargo project, its firmware.json naming its toolchain
```

Names use underscores. `apothecary parts list` shows every part and the
module that describes it, and marks the stubs.

Adding a part: [docs/parts-authoring.md](../docs/parts-authoring.md).
Sketches: [docs/firmware.md](../docs/firmware.md#sketches-live-with-their-parts).
A printer's slicer profile: [docs/slicer.md](../docs/slicer.md).
