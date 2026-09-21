# Geometry made elsewhere

A mesh you exported from CAD, downloaded, or scanned, in a site and drawn in
the world -- and the machines and boards on the garage bench drawn as the
things they are.

## Bring a file in

```bash
apothecary parts import ~/Downloads/bracket.stl --name bracket \
    --title "Spool bracket" --author "A. Person" --license CC-BY-4.0 \
    --url https://example.org/bracket --units mm --up z
```

`parts import` reads an STL (binary or ASCII) or an OBJ, turns it into
millimetres and Z-up (`--units in`, `--up y` for a file from an inch-based
tool or a Y-up game engine -- a quarter turn, not a mirror), and writes a
part folder:

```
parts/bracket/
  bracket.mesh.stl          the mesh as brought, converted, in mm, Z-up
  bracket.stl               the part's render (a copy: the viewer needs no OpenSCAD for it)
  bracket.scad              one line: import("bracket.mesh.stl")
  bracket.mesh.stl.license  SPDX lines for REUSE, from --author and --license
  part.json                 what the part is, and where it came from
```

The part then lists (`apothecary parts list`), answers `apothecary parts
info bracket` with its measured bounds, and is served by the API and drawn
by the viewer like any part with a Python wrapper. There is no wrapper to
write: `part.json` is the wrapper (see *Described parts*).

Nothing is fetched. The file is one you already have; `--url` records where
it came from so the next person knows, and that is all it does -- the
program cannot reach past this machine (`apothecary/stays_local.py`).

What is not read: 3MF, STEP, glTF, PLY. `parts import` names the tool that
would read each (OpenSCAD imports 3MF directly; STEP is not a mesh, export
an STL from the CAD tool) rather than guessing.

## Put it in a site

A node whose `part_ref` names the part *is* the part; children live inside it:

```python
Assembly(
    name="bracket",
    part_ref="bracket",
    position=Vector3D(x=1500, y=200, z=BENCH_TOP_Z),
    footprint=BoundingBox3D(min_point=Vector3D(), max_point=Vector3D(x=80, y=40, z=25)),
)
```

`parts import` prints the `footprint=` line with the measured bounds. The
footprint is what places it: the viewer centres the mesh in the footprint
box, the layout check uses it for overlaps, and the site's own OpenSCAD
render imports the STL at the node's position.

Two things worth knowing about OpenSCAD 2021.01, the version on most
machines: it drops a mesh it cannot read back into a boolean ("The given
mesh is not closed", a CGAL assertion) from a union **and exits 0** -- so a
render that unions an imported mesh with anything else is checked for
that, and a node's STL is refused rather than served without its body
(`RenderResult.dropped`). Its own exports are the usual culprit: parts that
merely touch along an edge, pins drawn as hexagonal prisms, a cylinder
cutting a box's face. The models here overlap their neighbours by half a
millimetre for that reason, and every one of them survives a union. A mesh
from elsewhere that does not is still drawn by the viewer (it draws a part
by its own STL) and still renders alone; it is the union with other
geometry that OpenSCAD refuses. And the viewer, focused *inside* a node,
draws the node's children, not the node -- zoomed into a printer you see
its board and its posts, not its body, which is the picture at the level
above.

A mesh that is not in the scene's frame can be moved in the model rather
than in the file: `Import(file=..., scale=25.4, rotate=Vector3D(x=90),
translate=Vector3D(z=10))` renders as `translate(){rotate(){scale(){import()}}}`
and `.bounds()` reads the file to say where the transformed mesh ends up.

## Described parts

A folder under `parts/` with a `<name>.scad` and a `part.json` is a part
with no Python module -- the sidecar says what the wrapper would have said:

```json
{
  "description": "Arduino Uno R3, from the published board drawing",
  "category": "electrical",
  "tags": ["board", "arduino"],
  "preview_color": [0.0, 0.5, 0.5],
  "bounds": {"min": [-6.5, 0, 0], "max": [68.6, 53.3, 13]},
  "source": {"title": "...", "author": "...", "url": "...", "license": "MIT", "units": "mm", "up": "z"}
}
```

The registry names such a part's wrapper
`apothecary.projects.parts.described.<name>`, and importing that name builds
the part from the sidecar (`apothecary/projects/parts/described.py`). A
folder whose subfolders are parts is a category (`parts/boards/`); a SCAD
file of its own there is a library its parts include, not a part.

## The bench, drawn as it is

The garage's printers are Ender 3s (`parts/ender3`): a 2018 original with the
power supply on the right side of the frame behind the upright, the
electronics box under the bed at the front left, the LCD off the front
right corner and the spool on a bracket over the top bar -- built in
OpenSCAD from Creality's published dimensions (440 x 440 x 465 overall,
220 x 220 x 250 printable; the SCAD says which numbers are specifications
and which are measured). The axes are parameters (`z_axis`, `x_axis`,
`y_axis`), so the model can stand where the last poll said.

The boards are the boards (`parts/boards/`): an Arduino Uno R3, a Raspberry
Pi 4 B, a Teensy 4.0, an ESP32-DevKitC V4 and a Creality V4.2.2 mainboard,
each from its maker's published drawing (outline, holes, headers, jacks),
each described by a sidecar. The printer's `mainboard` node is the Creality
board in the electronics box; `esp32_blink` is the DevKitC standing on its
pins; an Uno, a Pi and a Teensy lie at the right end of the bench.

A machine drawn as it is needs one more thing than a block: where its build
volume starts. `build_origin` on a node with a `build_volume` says where
that volume's (0, 0, 0) is in the node's frame -- the nozzle at home, on the
bed -- and `GET /firmware/printers/where` carries it to the world's marks
and the board view, so the bed plane, the nozzle marker and a bed reading's
relief sit on the Ender 3's bed at 95 mm, not on the floor of its footprint.
Without it, a viewer centres the volume on the footprint and puts it on the
floor, which is right for a block.

No mesh of anyone else's went into any of these; they are our own OpenSCAD
from public dimensions, MIT like the rest of the repository.

## Licences and what gets committed

STL files are build artifacts and `.gitignore` ignores them, imported ones
included. To share an imported mesh in the repository:

1. Its licence must be one the open-license record accepts (OSI- or
   FSF-approved, or a CC licence without NC/ND); `--license` records the
   SPDX id and writes the `.license` file REUSE reads for a binary.
2. Un-ignore the file (`!parts/<name>/<name>.mesh.stl` in `.gitignore`) and
   add its licence text under `LICENSES/` if it is not MIT.
3. Give it an `[[annotations]]` block of its own in `REUSE.toml` with
   `precedence = "override"`, naming the maker and the licence, the way the
   three.js block does: the repository's `**` block is *aggregate*, so a
   `.license` file beside a mesh is otherwise added to the MIT claim, not
   substituted for it.
4. A copyleft mesh bundled into this MIT repository needs the combined-work
   note the record asks for, and the adoption record's component audit
   gains a row (it is extended when a component is added).

An imported mesh you do not share stays what it was: a file on your
machine, in a folder the program reads and never sends anywhere.
