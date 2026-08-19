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

4. **Declared bounds disagree with geometry** – `apothecary parts verify --all`
   finds four wrappers whose `get_bounds` does not match what OpenSCAD emits.
   Only `calibration_cube` and `datum-core` agree.

   | Part | Declared | Measured |
   |---|---|---|
   | V-Slot | 20 x 20 x 100 | 20 x 20 x 20 |
   | couch_block | 40 x 40 x 20 | 152.4 x 101.6 x 50.8 |
   | dryerknob | 30 x 30 x 15 | 33 x 33 x 20 |
   | parametric_star | 40 x 40 x 2 | 27.14 x 28.53 x 3 |

   Not fixed here: the right value depends on which side is authoritative, and
   for `couch_block` the `Params` model is not wired to the SCAD at all. Anything
   laying out around these parts is wrong by the difference.

5. **Parameter names are not cross-checked.** `verify` catches a wrapper and its
   SCAD disagreeing about *size*, but a parameter declared in the `Params` model
   and absent from the SCAD file (or the reverse) is still undetected.

6. **Fixed: catalog leaves had no geometry path.** `to_scad_object()` built
   geometry only from `base`/`additions`/`children`, so every `part_ref` leaf
   raised and the whole `parts_library` site was unrenderable. One missing case
   emptied three viewer surfaces at once — canvas (422), contents, and the
   generated-OpenSCAD panel (500 on the layout route, so its placeholder never
   left). Catalog leaves now compile to `import()`.

## Next Steps
- [ ] Fix JSCAD import syntax and add regression test (e.g., `node --check`)
- [ ] Update packaging to include `parts/` and `templates/` in wheel
- [ ] Sanitize `/parts` payload to emit relative paths only
- [ ] Add OpenSCAD availability check to `apothecary check` command
- [ ] Reconcile the four drifted wrappers against their geometry
- [ ] Cross-check parameter *names* between each Params model and its SCAD file
- [ ] Wire `apothecary parts verify --all` into CI
- [ ] Consider WASM OpenSCAD for browser-side STL generation
