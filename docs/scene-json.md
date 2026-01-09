# Scene JSON format

This document describes the JSON shape accepted by Apothecary for scenes, both on the CLI (`render`, `templategenerate`, `validate`) and via the FastAPI `/render` endpoint.

## Top-level `Scene`

A scene corresponds to the `apothecary.scene.Scene` model:

- `name` (string, optional) – human-friendly name for the scene. Defaults to `"untitled"`.
- `version` (string, optional) – version tag; if omitted, defaults to the library version.
- `objects` (array, required) – list of OpenSCAD objects, encoded as JSON objects.

Example:

```json
{
  "name": "demo",
  "objects": [
    {
      "type": "cube",
      "size": {"x": 10, "y": 10, "z": 5},
      "center": false,
      "comment": "House base"
    }
  ]
}
```

## Primitive objects

Objects are encoded with a loose `type` discriminator plus fields appropriate to that type. The FastAPI API and CLI both accept either explicit `type` or inferred shapes (for compatibility).

### Cube

```json
{
  "type": "cube",
  "size": {"x": 10, "y": 10, "z": 5},
  "center": false,
  "comment": "optional comment"
}
```

- `size` – either a `{x, y, z}` vector or a scalar.
- `center` – boolean (default `false`).

### Sphere

```json
{
  "type": "sphere",
  "r": 5,
  "fn": 32,
  "comment": "optional comment"
}
```

### Cylinder

```json
{
  "type": "cylinder",
  "h": 10,
  "r": 5,
  "center": false,
  "fn": 32,
  "comment": "optional comment"
}
```

You may also supply `r1`/`r2` instead of `r` for tapered cylinders.

## Boolean operations

Boolean nodes wrap other objects via a `children` array:

### Union

```json
{
  "type": "union",
  "children": [ /* child objects */ ],
  "comment": "optional comment"
}
```

### Difference

```json
{
  "type": "difference",
  "children": [ /* first child is base, rest are subtractors */ ],
  "comment": "optional comment"
}
```

### Intersection

```json
{
  "type": "intersection",
  "children": [ /* child objects */ ],
  "comment": "optional comment"
}
```

## Transform nodes

Transforms also use a `children` array.

### Translate

```json
{
  "type": "translate",
  "v": {"x": 1, "y": 2, "z": 3},
  "children": [ /* child objects */ ],
  "comment": "optional comment"
}
```

### Rotate

```json
{
  "type": "rotate",
  "a": {"x": 0, "y": 0, "z": 45},
  "children": [ /* child objects */ ],
  "comment": "optional comment"
}
```

`a` may also be a scalar; `v` is optional and may be a vector if provided.

### Scale

```json
{
  "type": "scale",
  "v": {"x": 1, "y": 1, "z": 1},
  "children": [ /* child objects */ ],
  "comment": "optional comment"
}
```

## Error handling

On the CLI (`render`, `templategenerate`, `validate`):

- Invalid JSON results in a non-zero exit code and a message starting with `"Failed to parse scene JSON"`.
- Schema/validation errors surface as `"Scene validation failed: ..."`.
- `validate` requires explicit input (`--scene-file` or `--scene-json`) and will error with `"No scene input provided."` if neither is supplied.

On the API (`POST /render`):

- Invalid payloads are rejected by FastAPI/Pydantic with a 422 status and a validation error body.
- If rendering fails due to ambiguous object types, the service attempts a best-effort rehydration of objects based on their shape.
