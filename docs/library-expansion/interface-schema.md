# Interface Schema Specification

This document provides a formal JSON/YAML schema for defining part interfaces in the Apothecary library. Use this schema to ensure consistency, compatibility, and validation across all modular, dockable components.

## 1. Schema Overview

Each part interface is described as an object with required and optional fields. The schema supports multiple interface types and extensible metadata.

## 2. JSON Schema (Draft)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Apothecary Part Interface",
  "type": "object",
  "properties": {
    "name": { "type": "string", "description": "Unique interface name" },
    "type": { "type": "string", "enum": ["bolt_hole", "slot", "tab", "hinge", "surface", "custom"], "description": "Interface type" },
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+$", "default": "1.0", "description": "Interface version" },
    "position": {
      "type": "object",
      "properties": {
        "x": { "type": "number" },
        "y": { "type": "number" },
        "z": { "type": "number" }
      },
      "required": ["x", "y", "z"],
      "description": "Origin in local coordinates"
    },
    "normal": {
      "type": "object",
      "properties": {
        "x": { "type": "number" },
        "y": { "type": "number" },
        "z": { "type": "number" }
      },
      "required": ["x", "y", "z"],
      "description": "Normal vector for docking orientation"
    },
    "diameter": { "type": "number", "description": "Diameter (for bolt_hole)" },
    "width": { "type": "number", "description": "Width (for slot/tab)" },
    "length": { "type": "number", "description": "Length (for slot/tab)" },
    "metadata": { "type": "object", "description": "Additional user-defined fields" }
  },
  "required": ["name", "type", "position", "normal"],
  "additionalProperties": false
}
```

## 3. YAML Example

```yaml
interfaces:
  - name: mount_left
    type: bolt_hole
    version: "1.0"
    diameter: 3.0
    position: { x: -12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
  - name: edge_slot
    type: slot
    width: 2.0
    length: 100.0
    position: { x: 0, y: 0, z: -22 }
    normal: { x: 0, y: 0, z: -1 }
```

## 4. Validation

- Use this schema to validate part interface files with standard JSON Schema tools.
- Extend the `metadata` field for custom requirements.

## 5. Versioning

- Increment the `version` field for breaking changes.
- Maintain backward compatibility where possible.

## 6. References

- See [modular-interfaces.md](modular-interfaces.md) for interface usage and best practices.

---

For questions or proposals, see the [README](README.md) or open an issue in the repository.
