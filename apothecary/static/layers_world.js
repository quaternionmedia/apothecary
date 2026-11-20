/* Layers in the world: what the pick scope (pick_scope.js) does to what the world draws
 * (docs/viewer.md, "Layers"). The Layers window is widgets/layers.js; this is the world's
 * side of the same choice. Its logic is plain functions node can hold
 * (tests/test_layers_world.py); mountLayersWorld is given the viewer's pieces as arguments
 * and reaches into nothing else.
 *
 *   hideFor(object, reason, hide)   whether a drawn thing is shown, decided in one place:
 *                                   hidden while any reason holds it -- a layer not shown, a
 *                                   failed render drawn in its place, a comparison drawn in
 *                                   its place -- each reason taken back on its own, so letting
 *                                   one go shows the thing only when no other still holds it
 *   gridWanted(scope, place)        whether the level's grid is drawn -- the floor's, or a
 *                                   machine's bed's when one is stepped into -- the one rule
 *                                   every grid is drawn by: the alignment grid layer shown,
 *                                   and a level with a floor at all: the universe's own level,
 *                                   a sphere of shells a floor would cut through, has none
 *   layerKinds(tree)                the shells the site's pieces are on, innermost first, and
 *                                   the categories they are of: the Layers window's rows
 *   redrawsLevel(what)              whether a change to the scope draws the level again: a
 *                                   depth, a reset, a scope read back
 *   layersSaid(what, { wallsSaid }) what the status line says of a change to the scope
 *   mountLayersWorld(world)         { apply, changed, gridWanted }: every drawn thing put as
 *                                   the layers say, and a change to the scope answered
 */

import { GRID, MEASURE, WALL } from "/static/pick_scope.js";
import { layerLabel } from "/static/widgets/layers.js";

// The reason a layer not shown hides a drawn thing (hideFor).
export const BY_LAYER = "layer";

export function hideFor(object, reason, hide) {
    const by = object.userData.hiddenBy || (object.userData.hiddenBy = new Set());
    if (hide) by.add(reason);
    else by.delete(reason);
    object.visible = by.size === 0;
}

/* `place` is { site, universe, focusPath }: the site in view, the universe's name, and the
 * path of the level in view below the site's own. */
export function gridWanted(scope, { site, universe, focusPath }) {
    return scope.isShown(GRID) && !(site === universe && focusPath.length === 0);
}

export function layerKinds(tree) {
    const shells = new Set(), categories = new Set();
    const walk = (node) => {
        if (Number.isInteger(node.shell)) shells.add(node.shell);
        if (node.category) categories.add(node.category);
        for (const child of node.children || []) walk(child);
    };
    if (tree) for (const child of tree.children || []) walk(child);
    return { shells: [...shells].sort((a, b) => a - b), categories: [...categories].sort() };
}

export function redrawsLevel(what) {
    return !!(what && (what.depth !== undefined || what.reset || what.loaded));
}

/* `wallsSaid` is the words Select walls says of itself, the wall layer's Selectable tick. */
export function layersSaid(what, { wallsSaid }) {
    if (!what) return null;
    if (what.reset) return "Layers: back to depth 1, every layer shown, every layer selectable but walls";
    if (what.depth !== undefined) return `Depth: ${what.depth} level${what.depth === 1 ? "" : "s"} below this one, drawn and reached by a click`;
    if (what.layer === WALL && what.selectable !== undefined) return wallsSaid();
    if (what.layer === MEASURE && what.shown !== undefined) {
        return what.shown
            ? "Measure: on. A click drops a point and reads the diameter or the wall under it, selecting nothing; a second reads the distance, a third starts again (Escape too)"
            : "Measure: off, a click selects again";
    }
    if (what.only) return `${layerLabel(what.layer)} alone of its kind shown: the others hidden, and a click passes through them`;
    if (what.all) return `Every one shown: ${what.layers.map(layerLabel).join(", ")}`;
    if (what.shown !== undefined) return `${layerLabel(what.layer)}: ${what.shown ? "shown" : "hidden, and a click passes through it"}`;
    if (what.selectable !== undefined) return `${layerLabel(what.layer)}: ${what.selectable ? "a click picks it" : "a click passes through it"}`;
    return null;
}

/* The world's side of the layers, given the viewer's pieces:
 *   scope                 the pick scope
 *   meshes(), overlays(), volumes()   the pieces' meshes and the outlines round them, by
 *                         key, and the machines' build-volume boxes
 *   nodeOf(key)           the node a key draws
 *   grid()                the level's grid as drawn now
 *   place()               { site, focusPath }: where the view is; `universe` the universe's name
 *   orbits(), anchors(), measure(), invalidate()   what is put again after the pieces, in
 *                         that order: the universe's orbitals, the badges, the measurement
 *                         layer, and a frame asked for
 *   walls()               the Select walls tick set from the wall layer's
 *   redraw()              the level drawn again
 *   say(words)            the status line
 *   wallsSaid()           what Select walls says of itself */
export function mountLayersWorld({ scope, meshes, overlays, volumes, nodeOf, grid, place, universe, orbits, anchors, measure, invalidate, walls, redraw, say, wallsSaid }) {
    const wanted = () => gridWanted(scope, { ...place(), universe });

    // Every drawn thing put as the layers say: pieces and the outlines round them, the
    // alignment grid and the build volumes.
    function apply() {
        for (const [key, mesh] of Object.entries(meshes())) hideFor(mesh, BY_LAYER, !scope.drawn(nodeOf(key)));
        for (const [key, overlay] of Object.entries(overlays())) hideFor(overlay, BY_LAYER, !scope.drawn(nodeOf(key)));
        for (const box of Object.values(volumes())) hideFor(box, BY_LAYER, !scope.isShown(GRID));
        orbits();
        grid().visible = wanted();
        anchors();
        measure();
        invalidate();
    }

    // The pick scope changed: a depth redraws the level; a layer is put as it says, and the
    // Select walls tick follows the wall layer's.
    function changed(what) {
        walls();
        if (redrawsLevel(what)) redraw();
        apply();
        const said = layersSaid(what, { wallsSaid });
        if (said) say(said);
    }

    return { apply, changed, gridWanted: wanted };
}
