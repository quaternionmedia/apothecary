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

## Gates that exist on paper but run nowhere

Found by asking what the checks do *not* cover, 2026-08-20. An unwired gate is
indistinguishable from a passing one.

7. **`.pre-commit-config.yaml` configures black, ruff, ruff-format,
   end-of-file-fixer and trailing-whitespace, and no workflow runs
   pre-commit.** Style is enforced only for contributors who installed the
   hooks. `ruff check apothecary/ tests/` currently reports 46 violations —
   25 E501, 9 B904, 8 I001, 2 F401, 2 B011 — which is the proof they are not
   running. Ten of those are auto-fixable. Wiring the gate means either fixing
   all 46 first or scoping it to changed files; both are a decision, which is
   why this is written down rather than done.

8. **`apothecary parts verify --all` gates nothing.** Five of the twelve parts
   that declare bounds report an envelope their geometry does not have:
   `V-Slot`, `couch_block`, `dryerknob`, `gridfinity`, `parametric_star`.
   Anything laying out around them is wrong by the difference. datum's CI
   verifies `datum-core` only, because that is the part it depends on. Wiring
   `--all` here fails until those five are reconciled — see item 4.

## Build-readiness triage, 2026-08-20

`apothecary parts checklist --all --build-volume 220,220,250`, every part
rendered first. **0 of 16 ready.** Grouped by what it would take to clear:

**Fixable here, no decision needed**

| Blocker | Parts | What to do |
|---|---|---|
| Declares no bounds | 7 — contranot, `datum`, fifel, footpedal, matboard cutter mount, solderfan, star-cookiecutter | give each wrapper a `get_bounds`; until then nothing can lay out around them |
| Bounds drift from geometry | 4 — V-Slot, couch_block, dryerknob, parametric_star | reconcile wrapper and SCAD (item 8) |
| No print settings | 11 | set `print_settings`; `datum-core` and `datum-cap` now carry the house constants |

Note the checklist blocks on "declares no bounds" where `parts verify` skips
it. Both are right for their question: a drift check has nothing to compare,
but a part that cannot say how big it is is not ready to build.

**Needs a decision, not a commit**

| Blocker | Parts | Waiting on |
|---|---|---|
| Disputed dimensions | 2 — datum-core, datum-cap | which of `walls`/`tolerence`/`board_y` is authoritative |

**Needs measurement, not code**

| Blocker | Parts | Waiting on |
|---|---|---|
| Fitted to guessed envelopes | 16, all of them | the board outline and the mounting surface are `StubProvider` values. A `KiCadProvider` fed a real schematic clears it |

Two parts still cannot render (`elephant_walk` depends on sibling STLs;
`gridfinity` needs its submodule and a long render), which is why they show
extra unanswered checks rather than blocks.

## Next Steps
- [ ] Fix JSCAD import syntax and add regression test (e.g., `node --check`)
- [ ] Update packaging to include `parts/` and `templates/` in wheel
- [ ] Sanitize `/parts` payload to emit relative paths only
- [ ] Add OpenSCAD availability check to `apothecary check` command
- [ ] Reconcile the five drifted wrappers against their geometry, then wire
      `apothecary parts verify --all` into CI
- [ ] Decide how pre-commit gets enforced, and wire it
- [ ] Cross-check parameter *names* between each Params model and its SCAD file
- [ ] Wire `apothecary parts verify --all` into CI
- [ ] Consider WASM OpenSCAD for browser-side STL generation
