# Apothecary Library Expansion Guide

Welcome to the Library Expansion documentation for the Apothecary project. This guide provides a foundation for modular, dockable part design, interface schemas, assembly graphs, and UI planning. It is intended for contributors, maintainers, and users who wish to extend the parts library or integrate new features.

## Overview

- **Modular, Dockable Part Model**: Parts are designed as composable modules with well-defined interfaces, enabling flexible assembly and reuse.
- **Interface Schema**: A formal specification for how parts connect, including coordinate frames, constraints, and compatibility.
- **Assembly Graph**: Describes how parts are connected in a scene, supporting hierarchical and parametric assemblies.
- **UI Planning**: Recommendations for UI components to support part browsing, parameter editing, docking, and assembly visualization.

## Documentation Structure

- [modular-interfaces.md](modular-interfaces.md): Formal interface & docking specification
- [interface-schema.md](interface-schema.md): JSON/YAML schema for interfaces (optional, next)
- [ui-architecture.md](ui-architecture.md): UI component inventory and design (optional, next)
- [snowplow-part.md](snowplow-part.md): Example technical part specification (optional, next)

## Getting Started

1. Review the [modular-interfaces.md](modular-interfaces.md) for interface and docking standards.
2. Use the interface schema to define new parts and their connections.
3. Reference the UI architecture for integration with the web viewer or editor.
4. See the snowplow part example for a complete, documented part definition.

## Contributing

- Follow the modular design and documentation standards outlined here.
- Link new documentation and parts to this guide for discoverability.
- Use the release checklist in each spec to ensure quality and consistency.

---

For questions or to propose changes, open an issue or pull request in the repository.
