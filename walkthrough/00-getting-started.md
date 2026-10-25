# Getting started

**Hermetic.** The checks on this page run in-process. The commands it names
are yours to run, in order, from a fresh clone.

Four steps take a fresh clone to a viewer with a bench it can drive and no
hardware plugged in: install, see what this machine has, put a fast OpenSCAD
in place, and serve the demo. Then the four loops through the page, each with
what it needs, and the installs only some of them want. Page 01 onward is the
library's tour.

## 1. Install

Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).

```bash
git clone --recurse-submodules https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync
```

A clone made without `--recurse-submodules` has no gridfinity library and an
empty `governance/qm`; `git submodule update --init --recursive` fills both.
Every command below is run through `uv run`, or with `.venv` activated
without it.

## 2. What this machine has

```bash
uv run apothecary check
```

It reports Python and the packages the server needs, the viewer's three.js
(checked in, so there is nothing to fetch), OpenSCAD and the one each part
renders with, the slicer, each firmware toolchain, and the parts. A missing
package is the only failure: it exits 1 and names `uv sync`. Everything else
is optional and says how to install it. Its last line is the next step:

```
next: apothecary openscad install, then apothecary serve --demo (walkthrough/00-getting-started.md)
```

## 3. An OpenSCAD with Manifold, before the first serve

```bash
uv run apothecary openscad install
```

Rendering a part's STL is the one thing that needs OpenSCAD, and `serve`
builds every missing STL in the background as it starts. The OpenSCAD most
package managers carry is 2021.01: it renders with CGAL, slowly, and it is
too old for the gridfinity bins, which declare the version they need and are
skipped until one is there. The install puts a development snapshot with
Manifold under the tools folder, checked against its published checksum,
and every render uses it from then on. Installing it before the first
`serve` means the first STLs are built by it.

    >>> from click.testing import CliRunner
    >>> from apothecary.cli import cli
    >>> said = CliRunner().invoke(cli, ["openscad", "install", "--help"]).output
    >>> "files.openscad.org" in said and "with Manifold" in said
    True

`apothecary openscad status` says what is installed and which one renders
use; the README's *Install* says what the install does on each
platform. STLs an older OpenSCAD already built are kept: `apothecary parts
generate-stl --all --force` builds them again.

## 4. The viewer, with a bench to drive

```bash
uv run apothecary serve --demo
```

Then open `http://127.0.0.1:8000/viewer`. `serve` keeps the terminal it was
started in until Ctrl+C; run anything else in another one.

`--demo` serves the viewer on a state folder of its own, never yours, with a
bench that needs no hardware: an idle simulated Ender pinned to printer_1's
mainboard, a simulated ESP32 devkit, and scripted firmware tools. It slices
with the real OrcaSlicer when one is installed, and says how to install it
when not; a print goes to the simulated printer. A banner on the page says it
is the demo, and no real board is touched. Its state is `.cache/demo` in the
checkout, kept between runs; deleting it starts the demo afresh. Without
`--demo`, `serve` is the same viewer on your own state and the boards plugged
into this machine.

The page opens on the garage. The world fills it, and one rail beside it
holds Site (the tree, its problems, its SCAD, its pins and jobs) and Selected,
over a strip of tabs: Pictures, the Bench, a board's Machine. The ring, `m`
or a right-click, holds every verb of what it opens on; each cell has a digit,
and the digits pressed are the address the status line shows as ⌗.
[The viewer](../docs/viewer.md) describes each of its controls.

## 5. The four loops

Each loop is a path through the page that goes round twice, and each has a
page written by the browser test that walks it, so the words there are what
the page says today.

| Loop | Page | Needs | Under `serve --demo` |
|---|---|---|---|
| Designing a part: a size moved, checked, applied and drawn | [14](14-designing-a-part.md) | nothing but OpenSCAD | the same |
| Editing a part's SCAD, kept as a variant in git | [16](16-editing-a-parts-scad.md) | nothing but OpenSCAD | the same |
| A picture to a print: a camera's picture, a piece made from it, sliced and printed | [13](13-a-picture-to-a-print.md) | a printer pinned to printer_1's mainboard, OrcaSlicer, and a camera or a picture | the simulated Ender, OrcaSlicer if installed |
| Firmware: a sketch built, flashed and heard saying hello | [15](15-firmware.md) | an ESP32 devkit and a toolchain | the simulated devkit and the scripted tools |

    >>> from apothecary.projects.parts.skeleton import ROOT
    >>> loops = sorted((ROOT / "walkthrough").glob("1[3-6]-*.md"))
    >>> [page.name for page in loops]
    ['13-a-picture-to-a-print.md', '14-designing-a-part.md', '15-firmware.md', '16-editing-a-parts-scad.md']
    >>> all("rewritten by every run of the browser suite" in page.read_text(encoding="utf-8")
    ...     for page in loops)
    True

Where each starts:

- **Designing a part** and **editing its SCAD** start in the catalog,
  `/viewer/sites/parts_library`: a part's ring, Part › Edit. Its parameters
  open in Selected, with its SCAD in an editor below them.
- **A picture to a print** starts at the bench in the garage: its ring,
  Camera › Add here, then the camera's Device. With no camera, the bench's
  Picture › Add pins a picture from disk instead;
  `examples/shapes.png` is three shapes the finder
  reads. Each step's message names the next one.
- **Firmware** starts at the Bench, a tab of the rail, or the canvas ring's
  Panels › Bench › Bench: the sketches under `parts/`, each named with its
  toolchain.

## 6. The installs only some loops want

```bash
uv run apothecary slicer install                  # OrcaSlicer, the pinned release: Slice and Print
uv run apothecary firmware install --esp32        # arduino-cli and the ESP32 core: parts/esp32_blink
uv run apothecary firmware install --avr          # the core for an Arduino Uno, Nano or Mega
uv run apothecary firmware install --rust-esp32   # Rust for the ESP32: rustup, Xtensa Rust, espflash
uv run playwright install chromium                # the browser the tests drive
```

Each tool goes under the tools folder, `~/.apothecary/tools` unless
`APOTHECARY_TOOLS_DIR` names another, fetched from its publisher and checked
against what the publisher says it is; `apothecary check` reports it after.
Those fetches are the only connections the process makes
(`apothecary/stays_local.py`).

    >>> for argv in (["slicer", "install"], ["firmware", "install"]):
    ...     assert CliRunner().invoke(cli, [*argv, "--help"]).exit_code == 0, argv
    >>> flags = CliRunner().invoke(cli, ["firmware", "install", "--help"]).output
    >>> all(flag in flags for flag in ("--esp32", "--avr", "--rust-esp32"))
    True

The tests: `uv run apothecary test run` is the ordinary command, the unit
tests and this walkthrough, whose demonstration drives Chromium.
`CONTRIBUTING.md` has the rest of the loop.

## 7. Where next

[Page 01](01-a-part.md) onward is the library's tour: what a part is and how
its envelope is checked, which numbers are whose, an assembly as a tree, the
API, the numbers its sources disagree about, whether a part is ready to
build, and what is open and who can close it. Then
[`docs/`](../docs/README.md): the guides, the plans and the records.
`apothecary --help` is the command reference, and it ends with the steps
above:

    >>> shown = CliRunner().invoke(cli, ["--help"]).output
    >>> print(shown[shown.index("Start here:"):].strip())  # doctest: +NORMALIZE_WHITESPACE
    Start here:
      1. apothecary check              what is installed here, and what is missing
      2. apothecary openscad install   an OpenSCAD with Manifold: fast renders, and the
                                       parts OpenSCAD 2021.01 is too old to build
      3. apothecary serve --demo       the viewer, with a simulated printer and board
    walkthrough/00-getting-started.md says each step, then the four loops through the page.

## Recipes

| | |
|---|---|
| What is installed | `apothecary check` |
| The OpenSCAD renders use | `apothecary openscad status` |
| The viewer, no hardware | `apothecary serve --demo` |
| The viewer, this machine's boards | `apothecary serve` |
| The ordinary tests | `apothecary test run` |
| Every command | `apothecary --help` |
