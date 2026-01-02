# Changelog

All notable changes to Apothecary will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- **Calibration cube** – Default size reduced to 10mm, labels as relief (not extruded), axes preview-only
- **Parts reorganized** – Each part now has its own folder (`parts/<name>/<name>.scad`)
- **Viewer renders actual STL** – No more placeholder geometry; auto-generates if missing
- **Root redirects to viewer** – `/` now redirects to `/viewer` with elephant_walk as default
- Refactored viewer into Jinja2 template + dedicated module
- Registry scanner updated for new folder structure
- Reduced `api.py` from 827 to ~450 lines

### Removed
- `render_context.py` (orphaned, unused)
- `openscad_framework.py` (deprecated compatibility shim)
- `star_cookeicutter.py` (legacy misspelling)
- Legacy JSCAD viewer endpoints (`/viewer/ui/*`, `/css/*`)
- `_require_viewer_root()` helper (no longer needed)
- `E2E_SETUP.md` (consolidated into CONTRIBUTING.md)

### Fixed
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
