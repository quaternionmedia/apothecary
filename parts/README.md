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
├── dust/                   a category: a round end of a dust system, and the adapter between two
│   ├── dust_port/          dust_port.scad, written from its Python: one part, its sizes its presets
│   └── hose_adapter/       hose_adapter.scad, written from its Python, its parameters its two ends
├── stream_deck_plus/
│   └── stream_deck_plus.scad   the Stream Deck + at the bench, from the maker's published size
├── anolex_4060_evo_ultra_2/
│   └── anolex_4060_evo_ultra_2.scad   the router, drawn as it is
├── router_coupon/
│   └── router_coupon.scad   a plate with a pocket and holes, cut on the router (its cuts in the wrapper)
├── router_emoji/
│   └── router_emoji.scad    a 😮 cut on the router, measured to calibrate it (its cuts in the wrapper)
├── print_coupon/
│   └── print_coupon.scad   a plate, blocks, pockets, a window and a fin, measured to tune a printer (its plan in the wrapper)
├── bed_shims/
│   └── bed_shims.scad      a shim for each low corner of a bed on solid mounts, lifting it to the highest
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
