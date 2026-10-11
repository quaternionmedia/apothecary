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
├── cameras/                a category: the library's webcam, and three mounts for it
│   ├── webcam/             webcam.scad and part.json
│   └── webcam_desk_stand/  part.json tags it a stub, as are the clamp arm and ceiling mount
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
