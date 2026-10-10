# The slicer

A part, or a piece made from a picture, sliced into G-code for the pinned
printer, and kept where the Print card keeps a file, so Print follows Slice.
The owner decided how on 2026-10-10 ([the plan](plans/slicer-2026-10-10.md));
this page says what was built. The page's Slice step comes later; the server
and the command line are here now. Slicing writes files only: nothing here
opens a serial port or sends anything to a printer.

## Installing it

```bash
uv run apothecary slicer install     # the pinned OrcaSlicer, into the tools dir
uv run apothecary slicer status      # each slicer: what it slices, where it is, its version
```

`apothecary slicer install` fetches the release pinned in
`apothecary/slicer/orcaslicer_installer.py` from OrcaSlicer's GitHub releases
and nowhere else, and checks it before opening it: OrcaSlicer publishes no
checksum file, so the download is checked against the SHA-256 GitHub publishes
for the asset, which must be the one pinned beside the version.

| This machine | What an install is |
|---|---|
| Linux x86_64, arm64 | The release's AppImage, run as it is; its `resources/profiles` extracted beside it, since OrcaSlicer's own profiles are read at each slice. Where there is no FUSE the image is extracted whole and `squashfs-root/AppRun` runs. |
| macOS, Intel or Apple Silicon | `OrcaSlicer.app` copied out of the universal disk image, attached read-only and detached whatever happened |
| Windows x64, arm64 | The machine's portable zip, unpacked: `orca-slicer.exe` with its `resources` beside it |
| Anything else | Refused, saying what is published |

It goes under `~/.apothecary/tools/orcaslicer/<version>/` (or
`$APOTHECARY_TOOLS_DIR`) with `install.json` saying what it is, and `current`
names the release in use. The program a slice runs is `APOTHECARY_ORCASLICER`
when it is set (`none` means none), else that install, else `orca-slicer` on
`PATH`; a release other than the pinned one is used, and `slicer status` says
so.

**The pin moves by hand**: the version and the digests together, in a commit
that re-runs a real install and a real slice and says in its body what they
did, the hosts the install reached among it.

## The printer's profile, kept with its part

`parts/ender3/slicer.json` is printer_1's. It names the slicer a slice uses,
OrcaSlicer's own profiles it starts from (Creality's Ender-3 0.4 nozzle
machine, its 0.20 mm Standard process and Creality Generic PLA, read from the
installed release at each slice and flattened along their `inherits` chains;
none of OrcaSlicer's profile files is copied here), the values the printer
holds over them, each with its source, and what the bench measured, each with
how a slice uses it:

| Measured | Source | Used |
|---|---|---|
| Firmware: Marlin TH3D UFW 2.94a | [the bench](validation/2026-09-20-ender-bench.md), M115 | `gcode_flavor` marlin |
| Build volume 220 x 220 x 250 mm | Creality's figure (the part's `BUILD`) and the bench's pin of printer_1 | `printable_area`, `printable_height` |
| Probe offset X-44 Y-10 Z-3.15 | the bench, M851 | Not by the slicer: the firmware applies it when G28 homes Z with the probe; `z_offset` stays 0 |
| The stored mesh, leveling off | the bench, M420 V | Not by the slicer: OrcaSlicer's start G-code does not turn it on |

## Print settings from the part

A part's print settings are what its wrapper declares as `print_settings` --
the shape the *Print settings declared* readiness check reads -- and only the
fields it set; the printer's profile fills the rest. A piece made from a
picture declares none, so its slice is the printer's throughout.

| Declared | What a slice does with it |
|---|---|
| `nozzle_diameter` | Must be the printer's; a slice cannot change a nozzle, so a part asking another is refused |
| `layer_height` | The process's `layer_height`, inside the machine's range |
| `wall_thickness` | The process's `wall_loops`: as many lines as wide as the nozzle as reach it |
| `tolerance` | Reported, not passed: the part's geometry already allows for it |

Every slice's answer lists each value with its `origin` (`declared` or
`printer`) and its `source`.

## Slicing

```bash
uv run apothecary slicer slice calibration_cube            # a part, for the one printer that keeps a profile
uv run apothecary slicer slice datum_core --json-out       # the slice record, as JSON
```

A piece made from a picture lives in the running server, so it is sliced
through the route:

| Route | |
|---|---|
| `GET /slicer/status` | Each slicer module, the one a slice uses, and the printers that keep a profile |
| `POST /slicer/install` | Install the pinned release (a task) |
| `POST /slicer/slice` | `{part, port}` or `{part, site, printer}` or `{part, printer}`: slice a part or a made piece for a printer (a task). `part` is a node's path in the printer's site, as `GET /jobs/choices` lists it for the Print card, or a part's name |
| `GET /slicer/tasks/{id}?since=N` | The task's log; once it ends, `slice` is the answer: the record, or the error with the slicer's errors and warnings by line |
| `POST /slicer/tasks/{id}/cancel` | Stop a slice; nothing is kept |
| `GET /slicer/slices`, `GET /slicer/slices/{file_id}` | The slices whose files the Print card still keeps |

The G-code is kept where the Print card's file box keeps an upload (the state
folder's `prints/`), checked as one is, so it is in the Print card's list at
once. Its record -- what was sliced, for which printer, each value and its
source, OrcaSlicer's estimate of time and filament from its own G-code, its
errors and warnings, where the extruding moves reach -- is the state folder's
`slices/<file id>.json`, and is forgotten when the Print card forgets the
file. Slices run one at a time on a task runner of their own, so a slice and a
flash never wait for each other.

## Another slicer

A slicer is a module (`apothecary/slicer/modules/`): a subclass of
`SlicerModule` in a file of its own, registered in `_registry`. A printer's
profile has a section per module, in that slicer's terms. The slicer a slice
uses is the one named (`--slicer`, or the route's `slicer`), else
`APOTHECARY_SLICER`, else the `slicer` line of the printer's profile -- the
owner switches by changing that line.
