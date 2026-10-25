# CodeMirror 6, kept here rather than fetched

The part editor's SCAD editor (`apothecary/static/widgets/scad_editor.js`) is
CodeMirror 6, with a small OpenSCAD mode of apothecary's own. Like three.js
beside it, it is copied in so the page needs no network: a page here may load
nothing from another origin (`apothecary/stays_local.py`).

Twelve packages -- CodeMirror's state, view, language, commands and lint, and
everything they import -- each the registry's own `dist/index.js`, unchanged
and unminified, with its `LICENSE` beside it. Every one is MIT, copyright
Marijn Haverbeke and others. `packages.json` names each one's version and the
registry's integrity hash of the tarball it came from. Together about 1 MB
(`du -sb` here), about a quarter of that gzipped; the page loads none of it
until a part's editor first opens.

The page's import map names each package's folder, so the modules import one
another by their own names, as they were published.

## Updating

For each package in `packages.json`, fetch the version you want from the
registry and copy the same two files:

    npm pack @codemirror/view@<version>
    tar xzf codemirror-view-<version>.tgz
    cp package/dist/index.js  view/index.js
    cp package/LICENSE        view/LICENSE

and record the new version and its `dist.integrity` in `packages.json`. A
package that starts importing another means a new folder and a new entry in the
import map (`templates/fractal_viewer.html.j2`). Then check that the editor
opens with the network off.
