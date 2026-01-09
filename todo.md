# TODO

## Completed (v0.2.0)
- [x] Reorganized parts into per-part folders (`parts/<name>/<name>.scad`)
- [x] Added `PartFiles` data model linking SCAD/JSCAD/STL files
- [x] Created STL renderer service using OpenSCAD CLI
- [x] Added API endpoints: `/parts/{name}/stl`, `/stl/generate`, `/files`
- [x] Updated viewer to load actual STL geometry via Three.js STLLoader
- [x] Added `apothecary test all` for combined test suite with aggregate output
- [x] Removed orphaned code: `render_context.py`, `openscad_framework.py`, legacy JSCAD viewer endpoints

## Known Issues
1. **JSCAD imports** – Generated modules emit `import ... from '@jscad/modeling/src/primitives'` which may not work in all environments (see `apothecary/jscad.py` lines 8-10, 117-119).

2. **Packaging** – The wheel only ships the Python package; `parts/` and `templates/` aren't included, so PyPI installs can't render parts. Needs `include_package_data=True` or MANIFEST.in.

3. **Path leakage** – `/parts` endpoints expose absolute filesystem paths in include stubs. Should use relative/virtual URLs.

## Next Steps
- [ ] Fix JSCAD import syntax and add regression test (e.g., `node --check`)
- [ ] Update packaging to include `parts/` and `templates/` in wheel
- [ ] Sanitize `/parts` payload to emit relative paths only
- [ ] Add OpenSCAD availability check to `apothecary check` command
- [ ] Consider WASM OpenSCAD for browser-side STL generation
