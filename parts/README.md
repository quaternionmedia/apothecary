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
└── esp32_blink/            esp32_blink.ino: a sketch kept beside the parts
```

Names use underscores. `apothecary parts list` shows every part and the
module that describes it.

Adding a part: [docs/parts-authoring.md](../docs/parts-authoring.md).
Sketches: [docs/firmware.md](../docs/firmware.md#sketches-live-with-their-parts).
