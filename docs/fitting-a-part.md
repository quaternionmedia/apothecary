# Fitting a part to something it does not own

A standard for the seam between a project that owns facts about a physical
thing and this repository, which owns geometry. Written against `datum-core`,
but the shape is meant to hold from a single unfitted part up to a multi-
structure build.

Status: proposed. A record candidate for `governance/qm`, not yet drafted there.

## The line

One sentence decides every argument about where a number lives:

> **The consumer owns requirements and interfaces. Apothecary owns realization
> and manufacturability.**

| Fact | Owner | Example |
|---|---|---|
| What must fit, and where | consumer | board 40 × 40 mm; connector 3.6 mm above the board; contacts on an 18 mm pitch |
| How geometry realizes that | apothecary | corner radius, floor thickness, lip height, facet count |
| How it prints | apothecary | `PrintSettings` — nozzle, layer height, wall, tolerance |
| Whether the result is valid | apothecary | `LayoutReport` — overlaps, build volume |

`datum` does not get an opinion on wall thickness, and apothecary does not get
an opinion on where the connector is. Each of those was previously held by the
wrong repository: every dimension of `datum-core` lived in apothecary's SCAD,
including the ones the PCB determines.

The test for which side a number belongs to: **would it change if you printed
the same object on a different machine?** If yes it is manufacturing and it is
apothecary's. Would it change if the board changed? Then it is interface and it
is the consumer's.

## The three objects, at every level of complexity

Nothing new appears as an assembly grows. The same three objects recur; only
the tree gets deeper.

| | Owner | What it is |
|---|---|---|
| **Fit profile** | consumer | A versioned, machine-readable statement of the interfaces the consumer owns |
| **`Params` model** | part | What the part accepts, with house defaults for everything manufacturing |
| **Validator** | apothecary | Whether the realized geometry is coherent (`LayoutReport`) |

### The complexity ladder

| Rung | Example | Fit profile | Notes |
|---|---|---|---|
| 1. Unfitted part | `calibration_cube` | none | Nothing external to fit. `PrintSettings` alone |
| 2. Fitted part | `datum-core` tray | one | The profile drives parameter overrides |
| 3. Sub-assembly | tray + lid | one | Several nodes consume different subsets. Interfaces *between* the pieces — the lip clearance — stay apothecary's |
| 4. Site | `garage` | one per structure | Plus layout constraints; the validator is still apothecary's |
| 5. Third-party interfaces | a DIN rail, a VESA pattern | profile references named external interfaces | The external standard is a third owner, cited not copied |

The thing that scales is that rung 5 needs no new concept. A VESA pattern is
just an interface block whose owner happens to be a standards body rather than
a sibling repository.

## Rules

These are the envelope discipline `datum` already applies to its event schema,
pointed at geometry instead. They are what stop the profile becoming a second
copy of the SCAD file.

1. **A profile is versioned and additive.** Fields are added, never removed and
   never repurposed.
2. **A part ignores profile fields it does not recognise.** An older part keeps
   working against a richer profile. This is the whole reason for a profile
   rather than a shared constants file.
3. **A part must render coherently from its own defaults, with no profile at
   all.** Already a `datum` non-negotiable; it is what keeps the part useful to
   apothecary's other users.
4. **A profile names interfaces, never geometry.**
   `connector_height_above_board`, not `cutout_z`. The moment a profile names a
   cutout, the consumer has started designing the part.
5. **Manufacturing facts never appear in a profile.** They are parameters with
   house defaults, overridable by a consumer with a different printer, owned by
   neither.
6. **One gate per pair of descriptions.** Two descriptions of one object drift
   the moment nothing compares them:

   | Pair | Gate | State |
   |---|---|---|
   | SCAD defaults ↔ assembly model | `tests/test_datum_core_site.py` | wired |
   | Declared bounds ↔ rendered geometry | `apothecary parts verify` | wired |
   | Fit profile ↔ part params | — | **not built** |
   | Fit profile ↔ the schematic | — | needs WP-4 |

## What datum's profile would look like

Illustrative. Not implemented — the gate in row three of that table is the
missing piece, and building it is the next step after this standard is agreed.

```json
{
  "profile_version": "1.0.0",
  "src": "datum/t1-core",
  "board": {"x": 40.0, "y": 40.0, "thickness": 1.6},
  "mount_pattern": {"holes": 4, "inset": 3.5, "screw": "M2"},
  "connector": {"width": 9.4, "height": 3.6, "above_board": 0.0, "edge": "+y"},
  "indicator": {"diameter": 4.0, "at": [0.0, 14.0]},
  "contacts": {"count": 4, "pitch": [18.0, 18.0], "opening": 12.0},
  "tallest_component": 8.0
}
```

Every one of those is a fact the PCB determines and `datum` is entitled to
assert. None of them is a wall thickness, a corner radius or a facet count.

## What this changes about datum-core today

`walls` and `tolerence` are now parameters carrying the house constants from
`parts/footpedal/button.scad`, print-validated on QM hardware, rather than the
`2.4` and `0.25` invented for this part. The tray envelope is 46.8 mm square as
a result, not 45.6.

The board dimensions still live in the SCAD file as its defaults, which rule 3
requires — they are what makes the part render for someone who has never heard
of `datum`. What changes when the profile exists is that `datum` will assert its
own numbers rather than inheriting whatever the part happens to default to.

## Known inconsistency

`PrintSettings` defaults to `wall_thickness=1.2, tolerance=0.2`; `button.scad`
declares `walls = 3, tolerence = .4` and the packet calls those print-validated.
Two house constants disagree, and no part reads `PrintSettings` for its wall.
Reconciling them is out of scope here and belongs with whoever owns the print
profile.
