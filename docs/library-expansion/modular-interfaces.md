# Modular Interfaces Specification

This document defines the modular interface and docking system for the Apothecary parts library. It establishes standards for how parts expose connection points, how assemblies are described, and how compatibility and transforms are managed.

## 1. Interface Definition

An **interface** is a named, typed connection point on a part. Interfaces allow parts to be docked, assembled, or constrained together in a parametric, reusable way.

### Interface Types
- **bolt_hole**: Circular hole for fastener
- **slot**: Rectangular or custom slot
- **tab**: Protruding feature for insertion
- **hinge**: Rotational joint
- **surface**: Planar mating face
- **custom**: User-defined

### Interface Example (YAML)
```yaml
interfaces:
  - name: mount_left
    type: bolt_hole
    diameter: 3.0
    position: { x: -12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
  - name: mount_right
    type: bolt_hole
    diameter: 3.0
    position: { x: 12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
```

## 2. Coordinate Frames

- All interfaces are defined in the local coordinate frame of the part.
- The assembly system resolves transforms to connect interfaces in a global scene.
- **normal** vectors define the intended direction for docking.

## 3. Versioning & Compatibility

- Each interface has a `version` field (default: 1.0).
- Compatibility is determined by type, size, and optionally metadata (e.g., fastener size).
- Use semantic versioning for interface changes.

## 4. Transform Resolution

- When docking, the system computes the transform that aligns the child interface’s origin and normal to the parent’s.
- Example: To bolt a snowplow blade to a mount, align `mount_left` on the blade to `mount_left` on the mount plate.

## 5. Reference: Snowplow Interfaces

```yaml
interfaces:
  - name: blade_mount_left
    type: bolt_hole
    diameter: 3.0
    position: { x: -12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
  - name: blade_mount_right
    type: bolt_hole
    diameter: 3.0
    position: { x: 12, y: 0, z: 0 }
    normal: { x: 0, y: 1, z: 0 }
  - name: edge_slot
    type: slot
    width: 2.0
    length: 100.0
    position: { x: 0, y: 0, z: -22 }
    normal: { x: 0, y: 0, z: -1 }
```

## 6. File Organization

- Place interface definitions in each part’s YAML or JSON metadata file.
- Use `interfaces:` as the top-level key.
- Reference interfaces in assembly/scene files for docking.

## 7. UI Integration

- UI should visualize interfaces as selectable features.
- Docking assistant should allow users to align compatible interfaces.
- Parameter editor should expose interface parameters for editing.

## 8. Validation API Contract

- Provide an API endpoint or CLI tool to validate interface definitions for completeness and compatibility.
- Example: `apothecary validate-interface parts/rc/snowplow/blade.yaml`

## 9. Release Checklist

- [ ] Interface types and parameters documented
- [ ] Coordinate frames and normals specified
- [ ] Version and compatibility fields present
- [ ] Example(s) included
- [ ] File organization matches standard
- [ ] UI/validation requirements addressed

---

For questions or proposals, see the [README](README.md) or open an issue in the repository.
