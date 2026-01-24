# UI Architecture for Modular Parts

This document outlines the recommended UI architecture for integrating modular, dockable parts in the Apothecary library. It covers component inventory, wireframe-level design, API/metadata extensions, and user experience flow.

## 1. Component Inventory

- **Part Library Panel**: Browse/search available parts and assemblies.
- **Interface Inspector**: Visualize and select part interfaces for docking.
- **Docking Assistant**: Guide users through aligning and connecting compatible interfaces.
- **Assembly Tree**: Hierarchical view of current assembly and subcomponents.
- **Parameter Editor**: Edit part and interface parameters live.
- **Constraint Debugger**: Visualize and resolve assembly constraints.
- **Metadata Viewer**: Display part metadata, documentation, and previews.

## 2. Wireframe-Level Design

- **Main Workspace**: 3D viewer for assembly and manipulation.
- **Sidebar**: Switchable tabs for Library, Inspector, Parameters, and Metadata.
- **Bottom Panel**: Assembly tree and constraint debugger.
- **Context Menus**: Right-click on parts/interfaces for quick actions (dock, edit, info).

## 3. API & Metadata Extensions

- Extend part metadata to include:
  - `interfaces` (see schema)
  - `ui_hints` (e.g., default color, icon, preview orientation)
  - `assembly_constraints`
- Expose API endpoints for:
  - Listing parts/interfaces
  - Validating docking compatibility
  - Saving/loading assemblies
  - Editing parameters

## 4. UX Flow Example (Snowplow)

1. User opens the Part Library and drags the snowplow blade into the workspace.
2. Interface Inspector highlights available docking points.
3. User selects the mount plate and chooses a compatible interface.
4. Docking Assistant aligns and connects the parts, resolving transforms.
5. Parameter Editor allows live adjustment of blade width, angle, etc.
6. Assembly Tree updates to reflect the new hierarchy.
7. Metadata Viewer shows documentation and preview for the snowplow.

## 5. Upgrade Roadmap

- **Phase 1**: Static part library, manual docking, basic parameter editing.
- **Phase 2**: Interactive interface selection, constraint debugging, live validation.
- **Phase 3**: Advanced assembly graph editing, undo/redo, collaborative editing.
- **Phase 4**: Custom UI themes, plugin support, export/import workflows.

## 6. References

- [modular-interfaces.md](modular-interfaces.md)
- [interface-schema.md](interface-schema.md)

---

For questions or proposals, see the [README](README.md) or open an issue in the repository.
