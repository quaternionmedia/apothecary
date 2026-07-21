# Changelog

All notable changes to Apothecary will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Fractal `Assembly` model** (prototype, unratified) – Site/Structure/Substructure/Feature collapsed into one generic recursive class (`apothecary/hierarchy.py`); depth is unbounded rather than four fixed levels
- **Revision/diff building blocks** (prototype) – `apothecary/revisions.py`: `Revision`, `RevisionGraph` (branching history), `diff_assemblies` (path-addressed structural diff) — first slice toward planning/comparing design iterations, no compositing/merge yet
- **Fractal zoom viewer** (prototype, unratified) – `/viewer/sites/{name}` navigates any registered site's Assembly tree at any depth with standardized controls (click to select, double-click or scroll-past-resistance to zoom in, one zoom-out control) and an abstract depth-ladder minimap
- **Parts library as a fractal tree** – the registered `parts/` library is migrated in as leaf `Assembly` nodes (`apothecary/example_parts_library.py`, new `part_ref` field), reachable by zooming into the `parts_library` site instead of a separate parts browser
- **Real geometry in the fractal viewer** – placeholder boxes upgrade in the background to real geometry: a leaf's own Cube/Cylinder/Sphere renders as an exact Three.js primitive (`_primitive_descriptor` in `api.py`), and a `part_ref` leaf loads its real OpenSCAD-rendered STL, generating it on demand if missing. Composite nodes (more than one combined child) keep the bounding box — real CSG rendering of those stays future work.
- **"Show all levels" toggle** – renders every leaf beneath the current focus at once, at its true global position, instead of just this level's direct children — at the cost of render time, per its own label
- **Elephant walk** – `apothecary parts elephant-walk` generates a preview file with all parts arranged in a line, using bounding boxes to prevent overlap
- **Dev command** – `apothecary dev` for quick development workflow (generate STLs + start server)
- **STL rendering** – OpenSCAD CLI integration for SCAD→STL conversion
- **STL API endpoints** – `GET /parts/{name}/stl`, `POST /parts/{name}/stl/generate`
- **OpenSCAD status endpoint** – `GET /openscad/status` to check availability
- **PartFiles data model** – Links SCAD/JSCAD/STL files with status tracking
- **`apothecary test all`** – Combined test runner with aggregate summary
- Three.js-based 3D viewer with real STL geometry loading
- Viewer download/open dropdowns for SCAD and JSCAD files
- Loading overlay with blur effect during STL generation
- `QUICKSTART.md` for rapid onboarding
- `CONTRIBUTING.md` with development guidelines
- Documentation index at `docs/README.md`
- Comprehensive E2E tests using Playwright

### Changed
- **`/sites/{name}` payload** – gains an additive recursive `tree` key (the whole Assembly tree, including additions/subtractions) alongside the existing flattened `structures` list
- **Calibration cube** – Default size reduced to 10mm, labels as relief (not extruded), axes preview-only
- **Parts reorganized** – Each part now has its own folder (`parts/<name>/<name>.scad`)
- **Viewer renders actual STL** – No more placeholder geometry; auto-generates if missing
- **Root redirects to viewer** – `/` now redirects to `/viewer` with elephant_walk as default
- Refactored viewer into Jinja2 template + dedicated module
- Registry scanner updated for new folder structure
- Reduced `api.py` from 827 to ~450 lines

### Removed
- **Standalone parts browser and Site/Structure hierarchy viewer** – `templates/viewer.html.j2` and `templates/site_viewer.html.j2`, along with `/viewer/random` and `/viewer/parts/{name}`, absorbed into the fractal zoom viewer (`/viewer` now redirects to it)
- `render_context.py` (orphaned, unused)
- `openscad_framework.py` (deprecated compatibility shim)
- `star_cookeicutter.py` (legacy misspelling)
- Legacy JSCAD viewer endpoints (`/viewer/ui/*`, `/css/*`)
- `_require_viewer_root()` helper (no longer needed)
- `E2E_SETUP.md` (consolidated into CONTRIBUTING.md)

### Fixed
- **Fractal viewer: world position was only ever one level deep** – `Assembly.world_bounds()`/`api.py`'s tree serialization only offset a node by its own `position`, not its accumulated ancestor chain, so anything nested more than one level below a site's direct children rendered as if its parent were sitting at the origin. Fixed by threading cumulative world position through `_assembly_tree`'s recursion — the root cause of camera framing looking "too zoomed in and not centered" once you zoomed past the first level.
- **Fractal viewer: camera framing and grid size** – framing now considers all three axes (not just the horizontal footprint) and targets the true 3D center instead of an arbitrary height guess; the grid/axes helpers resize to match whatever's actually in view instead of a fixed 2000mm grid, often far too small a few levels deep
- Viewer loads without console errors
- Parts dropdown properly populates on page load
- `.gitignore` no longer lists tracked `parts/` folder

## [0.1.0] - 2026-01-02

### Added
- Initial release
- Core primitives: `Cube`, `Sphere`, `Cylinder`
- Boolean operations: `Union`, `Difference`, `Intersection`
- Transform operations: `Translate`, `Rotate`, `Scale`
- `Scene` model with `render()` and `render_jscad()` methods
- FastAPI server with REST API
- CLI with commands: `render`, `templategenerate`, `parts`, `serve`, `inventory`
- Parts registry with wrapper system
- Jinja2 template support
- Example parts: parametric star, V-slot, dryer knob, solder fan mount

---

## Release Notes Format

### Added
New features and capabilities.

### Changed
Changes in existing functionality.

### Deprecated
Features that will be removed in upcoming releases.

### Removed
Features removed in this release.

### Fixed
Bug fixes.

### Security
Security-related changes.
