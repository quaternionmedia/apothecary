# GoldenLayout 2, kept here rather than fetched

The page's windows -- the world, Site, Selected, Pictures, the Bench, Settings, a
board's Machine, an armed printer's control pad -- are GoldenLayout components
(`apothecary/static/panels.js`). Like three.js and CodeMirror beside it, it is
copied in so the page needs no network: a page here may load nothing from another
origin (`apothecary/stays_local.py`).

golden-layout 2.6.0 from the npm registry (integrity in `package.json` here), MIT,
copyright deepstream.io (`LICENSE`). Its `dist/esm/` is copied as it is but for two
mechanical changes, so a browser can load it without a bundler: every relative
import names its file with `.js` (the build leaves the extension off), and the
source-map comment at each file's end is dropped -- and one fix, below. `css/` holds
its base stylesheet and its dark theme, the theme's icon paths pointing at `img/`
here rather than two folders up as in the package.

The page's import map names `golden-layout` as `index.js` here.

## The one fix

`ts/items/row-or-column.js`, `onSplitterDragStart`: the least size of the item on
either side of a splitter is taken by `calculateSplitItemMinSize`, added there. For a
stack it is the largest of its tabs' least sizes; upstream adds them all up, though a
stack's tabs lie over one another, so a stack of five tabs could not be dragged
smaller than five tabs' worth. An update carries it over.

## Updating

    npm pack golden-layout@<version>
    tar xzf golden-layout-<version>.tgz

then copy `package/dist/esm/**/*.js` here adding `.js` to each relative import,
`dist/css/goldenlayout-base.css` and `dist/css/themes/goldenlayout-dark-theme.css`
into `css/` (its `url('../../img/` becoming `url('../img/`), `dist/img/*.png` into
`img/` and `LICENSE`; record the version and its `dist.integrity` in `package.json`;
carry the fix above over, unless the new version has it. Then check the page opens
with the network off.
