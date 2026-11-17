/* Measure: the arithmetic of the page's measurement layer (docs/viewer.md, "Layers").
 *
 * Pure functions on numbers, no three.js and no DOM, so each can be held under node
 * (tests/test_measure.py). Lengths are millimetres, in the site's frame (x, y, z, z up)
 * unless a function says it is given three.js's.
 *
 *   ownExtents(bounds)           a box's size along its own axes: for a turned node, its
 *                                footprint, which is in the node's own frame
 *   sizeFromSceneBox(size)       three.js's box size read in the site's letters
 *   turnedExtents(size, turn)    the size of the box that contains a box turned by
 *                                [rx, ry, rz] degrees, OpenSCAD's rotate order
 *   between(a, b)                the straight distance between two points, and dx, dy, dz
 *   gap(boxA, boxB)              the clear distance between two boxes, 0 when they touch
 *                                or overlap, and which of the two it was
 *   nearestWithin(points, x, y, radius)   the vertex nearest a pointer, within a radius
 *   length(mm)                   a length as it is written
 */

export const AXES = ["x", "y", "z"];

/* A box { min: [x, y, z], max: [x, y, z] }'s size along its own axes. */
export function ownExtents(bounds) {
    return { x: bounds.max[0] - bounds.min[0], y: bounds.max[1] - bounds.min[1], z: bounds.max[2] - bounds.min[2] };
}

/* three.js's size [sx, sy, sz] of a box (y up, the site's y running along -z) as the
 * site's { x, y, z }: its height is z, its depth y. */
export function sizeFromSceneBox(size) {
    return { x: size[0], y: size[2], z: size[1] };
}

/* The rotation of OpenSCAD's rotate([rx, ry, rz]) -- x, then y, then z -- by rows. */
export function turnRows(turn) {
    const [rx, ry, rz] = turn.map((a) => (a * Math.PI) / 180);
    const [cx, sx, cy, sy, cz, sz] = [Math.cos(rx), Math.sin(rx), Math.cos(ry), Math.sin(ry), Math.cos(rz), Math.sin(rz)];
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ];
}

/* The size { x, y, z } of the box that contains `size`, a box about its own middle,
 * once turned; the node's world bounds as a viewer reads them. Without a turn, the size. */
export function turnedExtents(size, turn) {
    if (!turn) return { ...size };
    const r = turnRows(turn);
    const half = AXES.map((k) => size[k] / 2);
    const out = {};
    AXES.forEach((k, i) => { out[k] = 2 * r[i].reduce((sum, v, j) => sum + Math.abs(v) * half[j], 0); });
    return out;
}

/* From point a to point b ([x, y, z] each): the components and the straight length. */
export function between(a, b) {
    const [dx, dy, dz] = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    return { dx, dy, dz, length: Math.hypot(dx, dy, dz) };
}

/* The clear distance between two boxes ({ min, max }, the site's frame): the length of
 * the shortest line from one to the other, which is 0 when they touch or overlap. `overlap`
 * is true when they share volume; `touching` when they meet and share none. `axes` is how
 * far apart they stand along each axis (negative: how far they run into each other). */
export function gap(a, b) {
    const axes = [0, 1, 2].map((i) => Math.max(b.min[i] - a.max[i], a.min[i] - b.max[i]));
    const clear = Math.hypot(...axes.map((v) => Math.max(0, v)));
    const overlap = axes.every((v) => v < 0);
    return { gap: clear, overlap, touching: clear === 0 && !overlap, axes: { x: axes[0], y: axes[1], z: axes[2] } };
}

/* Of `points` ({ sx, sy } on screen, and whatever else is carried), the one nearest the
 * pointer within `radius` pixels; null when none is. A tie goes to the first. */
export function nearestWithin(points, x, y, radius) {
    let best = null, bestAt = radius;
    for (const p of points) {
        const d = Math.hypot(p.sx - x, p.sy - y);
        if (d <= bestAt && (best === null || d < bestAt)) { best = p; bestAt = d; }
    }
    return best;
}

/* A length as it is written: millimetres to two places. */
export function length(mm) {
    return `${(Math.abs(mm) < 0.005 ? 0 : mm).toFixed(2)} mm`;
}
