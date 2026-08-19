# Iterating a part

The loop for changing a part's geometry and seeing the result, without editing
the source between every attempt.

## The short version

```bash
uv run apothecary serve --port 8765          # viewer
uv run apothecary parts info datum-core      # what it is, and how big
uv run apothecary parts generate-stl datum-core -p headroom=12
uv run apothecary parts verify datum-core -p headroom=12
```

Reload the viewer and the new geometry is there.

## Overrides

Every part with a wrapper declares a `Params` model. Until recently that model
was validated and then discarded — nothing passed it to OpenSCAD. `-p` closes
that gap:

```bash
uv run apothecary parts generate-stl datum-core -p show=exploded
uv run apothecary parts generate-stl datum-core -p board_x=60 -p headroom=20
```

Repeatable, and validated against the part's own model *before* anything
renders. This matters more than it looks: OpenSCAD accepts any `-D` name
whether the file defines it or not, so a misspelling renders the defaults and
exits 0. A typo is caught in well under a second instead of looking like a
successful render of the wrong thing.

```
$ uv run apothecary parts generate-stl datum-core -p headrooom=10
Error: unknown parameter(s): headrooom. datum-core declares: board_clearance,
board_t, board_x, board_y, explode_gap, floor_t, headroom, lid_t, lip_h, show,
standoff_h, wall
```

Overrides imply `--force`: the STL on disk came from different inputs, so there
is nothing to preserve.

## What the STL on disk actually is

A rendered variant lands at the part's canonical STL path, which is what the
viewer serves. That makes an overridden render indistinguishable from a default
one, so each render drops a sidecar beside it recording the inputs:

```bash
$ uv run apothecary parts info datum-core --json-out | jq .stl_params
{
  "generated": "2026-08-19T12:47:25",
  "params": {"show": "exploded"}
}
```

`"params": {}` means the file is a plain default render.

## Checking the wrapper against the geometry

A wrapper's `get_bounds` is hand-written Python sitting beside hand-written
OpenSCAD, and nothing was keeping the two in agreement. Anything consuming the
declared envelope — catalog layout, an assembly sizing itself around the part —
is wrong by however far they have drifted.

`verify` renders to a temporary file, measures the real bounding box, and
compares:

```
$ uv run apothecary parts verify datum-core -p show=exploded
✓ datum-core
    axis      declared    measured     delta
    x            45.60       45.60      0.00
    y            45.60       45.60      0.00
    z            32.60       32.60      0.00
```

It exits non-zero on drift, so it belongs in CI. `--tolerance` defaults to
0.5 mm, which absorbs facet approximation without hiding a real mistake.

`--all` sweeps every part that declares bounds. Parts that declare none are
reported as skipped rather than passing silently — a part with no bounds is
unchecked, not correct.

## Over HTTP

The same overrides, for driving the loop from the viewer rather than a shell:

```bash
curl -X POST localhost:8765/parts/datum-core/stl/generate \
  -H 'Content-Type: application/json' \
  -d '{"params": {"show": "exploded", "headroom": 14}}'
```

```json
{
  "success": true,
  "stl_url": "/parts/datum-core/stl",
  "params": {"show": "exploded", "headroom": 14.0},
  "bounds": {"size": {"x": 45.6, "y": 45.6, "z": 38.6}, ...}
}
```

Unknown or invalid parameters are refused with `422` and the reason, on the
same rule as the CLI. The response carries the bounds the part now declares, so
a caller can lay out around the variant without a second request.

## Adding parameters to a part

Two places, kept in step:

1. The SCAD file's top-level variables. Anything assigned there can be
   overridden with `-D`, which is what `-p` produces.
2. The wrapper's `Params` model — name, type, default, and any constraint.

They are separate because the model is the thing that validates and documents;
the SCAD variable is the thing OpenSCAD reads. `verify` is what catches the two
disagreeing about size. Nothing yet catches a parameter present in one and
missing from the other.
