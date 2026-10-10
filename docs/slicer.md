# The slicer

A part, or a piece made from a picture, sliced into G-code for the pinned
printer, and kept where the Print card keeps a file, so Print follows Slice.
The owner decided how on 2026-10-10 ([the plan](plans/slicer-2026-10-10.md));
this page says what was built: the server, the command line, and Slice as a
step of the page. Slicing writes files only: nothing here opens a serial port
or sends anything to a printer.

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

Which version a program is, is what its `--help` names first. On Windows
`orca-slicer.exe` is a GUI-subsystem program, the only launcher the release
ships, and may print nothing through a pipe; one that runs and prints nothing
is known by its version resource's `ProductVersion` or `FileVersion`. OrcaSlicer
2.4.2 leaves both empty and its fixed version numbers say 2.0.0.0, so for the
release `slicer install` put in place the version is the pinned asset's, which
its digest vouched for; `install.json` records how it was known
(`identified_by`).

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
| Probe offset X-44 Y-10 Z-3.15 | the bench, M851 | Held, nothing applied: the firmware applies it when G28 homes Z with the probe; `z_offset` stays 0 |
| The stored mesh, leveling off | the bench, M420 V | Held, nothing applied: the start is `home` alone |

## What a slice is composed from

The owner decided (2026-10-10) that the start of a print is composed from
modules as they are wanted. Each piece a slice can be composed from says what
it does (`apothecary/slicer/compose.py`; `slicer status` and `GET
/slicer/status` list them); a **stub** exists, says what it will do, and is not
chosen -- a profile naming one is refused, saying what it will do, before
anything is built. The printer's profile names its pieces under `start` and
`filament`, each with its source.

| Kind | Piece | What it does | |
|---|---|---|---|
| start | `home` | The printer's own start, as its OrcaSlicer profile has it: heat, home every axis (G28), prime the nozzle; no levelling | printer_1's |
| start | `stored-mesh` | After G28, turn on the stored bed mesh (M420 S1) | stub |
| start | `probe-each-print` | After G28, probe the bed before each print (G29) | stub |
| start | `first-layer-offset` | A first-layer Z offset measured at the bench, added to every Z | stub |
| filament | `printer` | The printer's one filament, named in its profile: Creality Generic PLA | printer_1's |
| filament | `choose` | A slice names another filament the printer has loaded | stub |
| declared | `word-print-settings` | A word declares print settings for the pieces made as it, in the shape a part declares them | stub |

## Print settings from the part

A part's print settings are what its wrapper declares as `print_settings` --
the shape the *Print settings declared* readiness check reads -- and only the
fields it set; the printer's profile fills the rest. A piece made from a
picture slices with the printer's values: a word declaring print settings
(`Word.print_settings`, a `PrintSettings`) is a stub, refused if set, and a
piece's answer says so.

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
uv run apothecary slicer slice garage/disc_1               # a made piece, through the running server
```

A piece made from a picture lives in the running server's memory, so
`apothecary slicer slice SITE/PATH` asks that server, as the page will: it
posts to the slice route and echoes the task's log as it arrives. No command
finds a running server for itself, so it asks the one at `apothecary serve`'s
own address, 127.0.0.1:8000, unless `--host` and `--port` name another, on
this machine only; with none there it says to start one. `--printer` names
the printer's node in the site, and without it the site's one printer is
used. The routes:

| Route | |
|---|---|
| `GET /slicer/status` | Each slicer module, the one a slice uses, and the printers that keep a profile |
| `POST /slicer/install` | Install the pinned release (a task) |
| `POST /slicer/slice` | `{part, port}` or `{part, site[, printer]}` or `{part, printer}`: slice a part or a made piece for a printer (a task). `part` is a node's path in the printer's site, as `GET /jobs/choices` lists it for the Print card, or a part's name; a site named without its printer slices for its one printer |
| `GET /slicer/tasks/{id}?since=N` | The task's log; once it ends, `slice` is the answer: the record, or the error with the slicer's errors and warnings by line |
| `POST /slicer/tasks/{id}/cancel` | Stop a slice; nothing is kept |
| `GET /slicer/slices`, `GET /slicer/slices/{file_id}` | The slices whose files the Print card still keeps |

**Every slice is kept**, each a file of its own in the Print card's file box
(the state folder's `prints/`) until a person forgets it there; slicing the
same part again keeps another. It is checked as an upload is, and is in the
Print card's list at once. Its record -- what was sliced, for which printer, each value and its
source, OrcaSlicer's estimate of time and filament from its own G-code, its
errors and warnings, where the extruding moves reach -- is the state folder's
`slices/<file id>.json`, and is forgotten when the Print card forgets the
file. Slices run one at a time on a task runner of their own, so a slice and a
flash never wait for each other.

## In the page

Slice is a step of the loop from a picture to a print
([walkthrough 13](../walkthrough/13-a-picture-to-a-print.md)):

- **On the ring.** A made piece's ring has **Slice** beside Print, and a part
  from the parts folder standing in the site has it after Part, when a printer
  is pinned in the site (a cell each, with several). It brings the printer's
  Machine forward with the piece chosen under **makes** and slices it there. A
  host, a camera, the printer and what is inside it have no Slice; with no
  printer pinned there is nothing to slice for, and no Slice.
- **In Print from here.** **Slice**, beside **makes**, slices what is chosen
  there for this printer -- the cell does the same. While it runs the card
  shows the slicer's log with **Cancel**; when it ends, the G-code it kept is
  chosen in the card's files, so ▶ Print follows, and the card says what the
  slice used: each value, with `declared` (the part's own, in bold) or
  `printer` beside it and its source on hover, the slicer's estimate, and its
  errors and warnings by line. A kept file a slice made says, in the card's
  files, what it was sliced from and for which printer; choosing it says that
  slice again under **makes**.
- **Installing it.** The Bench's toolchain card draws the slicer after the
  toolchain modules: what it slices, where it is, the release pinned, and its
  own **Install** (or Update), whose log is the Bench's task log. It is
  Panels › Bench › Install's last cell, **OrcaSlicer**, beside Arduino and Rust
  ESP32 -- the ring of modules for installs -- since installing a tool is the
  Bench's, and the Machine's Slice says where to install it when none is found.

## Another slicer

A slicer is a module (`apothecary/slicer/modules/`): a subclass of
`SlicerModule` in a file of its own, registered in `_registry`. A printer's
profile has a section per module, in that slicer's terms. The slicer a slice
uses is the one named (`--slicer`, or the route's `slicer`), else
`APOTHECARY_SLICER`, else the `slicer` line of the printer's profile -- the
owner switches by changing that line.
