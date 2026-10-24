# Giving photo-derived geometry a scale

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | the refusing-to-guess half is built; real references are still one line each |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | photo-derived geometry carries no scale (qm `project/apothecary`) |
| **Verified** | `apothecary/hierarchy.py::Assembly.validate()` and `check_no_overlaps` read: overlap checking uses `footprint`, so a node without one is not checked at all. |

## What
A photo yields pixels; apothecary is metric throughout — `Vector3D`,
`BoundingBox3D`, `HardwareSizes`, `PrintSettings.clearance_hole`. Three
candidate scale references: a registered part visible in frame, a dimension the
user enters, or a declared millimetres-per-pixel. No default, nothing inferred.

## Why now
**Two of the three are built:** a width for the whole picture, and naming a shape
whose real width is known. The part-in-frame variant is not, because it needs the
parts registry as a ruler and nobody has pointed a camera at a real part yet.

Immediately, because "placement" cannot be decided without it and the current
plan decides it by declining: without a scale reference a node is placed with
`footprint=None` and `status="unscaled"`, so sibling-overlap validation is
**inert** rather than confidently wrong. That is the right first answer and it is
not a permanent one.

## Seam
`ScaleReference` in `vision/models.py`, consumed by `compose.picture_to_site`.
Ask for `require_scale=True` to refuse rather than place unsized pieces.
The part-in-frame variant is the interesting one because it reuses the parts
registry as a ruler — a real part with known `default_bounds` appearing in the
photograph.

## Open questions
- Camera intrinsics, perspective and foreshortening are explicitly **not** being
  solved. A single scalar assumes a plane parallel to the sensor. Say so.
- Whether an unscaled site should be renderable at all, or refused at the STL
  boundary.
