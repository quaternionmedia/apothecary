# Fitting a part to something it does not own

The seam between a project that owns facts about a physical thing and this
repository, which owns geometry: what is built of it, and how it is checked.
`datum` is its consumer; [walkthrough 08](../walkthrough/08-fitting.md) drives it,
[14](../walkthrough/14-problems-and-solutions.md) checks who owns each open
problem, and [16](../walkthrough/16-being-depended-on.md) is the release side.

## Three objects, at every level of complexity

| | Owner | What it is |
|---|---|---|
| **Black box** | consumer | What a part is fitted around: envelope, mounts, keepouts |
| **`Params` model** | part | What the part accepts, with house defaults for everything manufacturing |
| **Validator** | apothecary | Whether the realized geometry is coherent (`LayoutReport`, `parts verify`) |

Nothing new appears as an assembly grows; only the tree gets deeper.

| Rung | Example | Black boxes | Notes |
|---|---|---|---|
| 1. Unfitted part | `calibration_cube` | none | `PrintSettings` alone |
| 2. Fitted part | `datum_core` | one | The box becomes parameter overrides |
| 3. Sub-assembly | `datum_core` + `datum_cap` | one | Interfaces *between* the pieces, the lip clearance, stay apothecary's |
| 4. Site | `garage` | one per structure | Plus layout constraints; the validator is still apothecary's |
| 5. Third-party interfaces | a DIN rail, a VESA pattern | named external interfaces | The standard is a third owner, cited not copied |

## The seam as built

`apothecary/models/blackbox.py`: a `BlackBox` describes an artifact apothecary
places but does not author, and `BlackBoxProvider` is a Protocol, so where the
description comes from is a separate, replaceable question. `StubProvider`
returns hand-entered datasheet numbers; `KiCadProvider`
(`apothecary/shims/kicad.py`) reads a real board outline through the same
interface, and swapping one for the other changes no geometry code. `source`
on each box tells a measured envelope from a guessed one.

`datum_core.params_for(board)` is the whole adapter from a box to tray
parameters. `apothecary/projects/assemblies/datum_bench.py` places the tray
and reports which envelopes are still guesses, so a review starts from what
nobody has measured.

## A gate per pair of descriptions

Two descriptions of one object drift the moment nothing compares them, so
each pair has a gate:

| Pair | Gate |
|---|---|
| SCAD defaults ↔ assembly model | `tests/test_datum_core_site.py` |
| SCAD variables ↔ `Params` | `tests/test_parameter_coverage.py` |
| Declared bounds ↔ rendered geometry | `apothecary parts verify` |
| Black box ↔ part params | `datum_core.params_for`, driven by `datum_bench.py` |
| Black box ↔ the schematic | `KiCadProvider`; built, unfed until a schematic exists |

## A pin, not a path

`datum.apothecary` names what `datum` depends on here, and `datum`'s CI checks
that reference and renders every part through this repository's CLI.
Geometry changes land here and arrive there by a reviewed bump.

Clause 5 of `datum`'s enclosure record asks for a *released* apothecary
version, consumed through the CLI or API rather than by path. No release is
tagged, so a consumer pins a commit until the first one is, and the gap is
owned here. Both sides check it: `datum apothecary --check` reports the
deviation while nothing is published and fails once something is, and
`apothecary release` says what stands between this commit and something a
consumer may pin.

## Where a problem is owned

`apothecary/spaces.py` gives every open problem an owner, derived from its
kind rather than typed:

| Owner | Means | Example |
|---|---|---|
| `apothecary` | a commit here closes it | a wrapper whose declared bounds its geometry does not have |
| `datum` | only the consumer can close it | a board envelope that is still a stub |
| `human` | a decision between defensible alternatives | a dimension its sources disagree about |
| `measurement` | waits on a physical artifact | a mounting surface nobody has measured |

    apothecary problems --owner datum
    apothecary solutions

Every kind of problem `spaces.py` knows has one of these owners.

## Where the seam is blurred

- `apothecary/datum_core_site.py` lives here and models `datum`'s enclosure.
  It is geometry, but it exists for one consumer; if a second never appears,
  it is a candidate for moving.
- `PrintSettings` defaults to `wall_thickness=1.2, tolerance=0.2`;
  `parts/footpedal/button.scad` declares `walls = 3, tolerence = .4`, called
  print-validated, and `datum_core` carries those as its `Params` defaults.
  Two house constants disagree, and no part reads `PrintSettings` for its
  wall. That belongs with whoever owns the print profile.
