/* Measure: the arithmetic of the page's measurement layer (docs/viewer.md, "Layers").
 *
 * Pure functions on numbers, no three.js and no DOM, so each can be held under node
 * (tests/test_measure.py). Lengths are millimetres, in the site's frame (x, y, z, z up)
 * unless a function says it is given three.js's.
 *
 *   ownExtents(bounds)           a box's size along its own axes: for a turned node, its
 *                                footprint, which is in the node's own frame
 *   sizeFromSceneBox(size)       three.js's box size read in the site's letters
 *   turnRows(turn)               the rotation of a node's turn, [rx, ry, rz] degrees in
 *                                OpenSCAD's rotate order, by rows: apothecary.orbitals'
 *                                turn_matrix, the one copy the page has of it
 *   turned(turn, point)          a point turned about the origin
 *   turnRowsInScene(turn)        the same rotation in three.js's frame (y up)
 *   turnedBounds(bounds, turn, at)   the box round a box turned about the origin, moved
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

/* `point` ([x, y, z]) turned about the origin by `turn`: apothecary.orbitals' turned. */
export function turned(turn, point) {
    return turnRows(turn).map((row) => row[0] * point[0] + row[1] * point[1] + row[2] * point[2]);
}

/* The rotation of `turn` in three.js's frame, which sceneAt (frames.js) turns the site's
 * into: S R S^-1, with S (x, y, z) = (x, z, -y). By rows. */
export function turnRowsInScene(turn) {
    const r = turnRows(turn);
    const rows = [r[0], r[2], r[1].map((v) => -v)];
    return rows.map((row) => [row[0], row[2], -row[1]]);
}

/* The box { min, max } round the eight corners of `bounds` turned about the origin by
 * `turn` and moved by `at`: a turned node's world bounds from its footprint and its
 * position, as apothecary/hierarchy.py makes them. */
export function turnedBounds(bounds, turn, at = [0, 0, 0]) {
    const corners = [];
    for (const x of [bounds.min[0], bounds.max[0]])
        for (const y of [bounds.min[1], bounds.max[1]])
            for (const z of [bounds.min[2], bounds.max[2]]) corners.push(turned(turn, [x, y, z]).map((v, i) => v + at[i]));
    return {
        min: [0, 1, 2].map((i) => Math.min(...corners.map((c) => c[i]))),
        max: [0, 1, 2].map((i) => Math.max(...corners.map((c) => c[i]))),
    };
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

/* A number as a field shows it: to two places at the most, no trailing zeros, so 1200
 * reads 1200 and 1663.4219857 reads 1663.42; the value the field stands for is kept
 * whole where it is held. */
export function fieldMm(mm) {
    const v = Number(mm);
    if (!Number.isFinite(v)) return "0";
    const shown = Number(v.toFixed(2));
    return String(Object.is(shown, -0) ? 0 : shown);
}

/* Whether two boxes ({ cx, cy, w, h }, pixels) come nearer than `gap` to each other. */
function crowds(a, b, gap) {
    return Math.abs(a.cx - b.cx) < (a.w + b.w) / 2 + gap && Math.abs(a.cy - b.cy) < (a.h + b.h) / 2 + gap;
}

/* Where each label of a measurement stands on screen: at the far end of its line, out
 * along the line past its end by `gap` pixels, so it is off the line and off what the
 * line measures from; nudged further out, then across, until it crowds no label placed
 * before it and covers no line's end; kept inside the canvas. `labels` is [{ x, y, dx, dy, w, h }]: the line's far
 * end, its direction on screen from its near end, and the label's size, in pixels (y
 * down). A line seen end on (no direction) puts its label below its end. Answers
 * [{ cx, cy }], each label's middle, in the order given. */
export function layLabels(labels, { width = Infinity, height = Infinity, gap = 6 } = {}) {
    const placed = [];
    const inside = (box) => ({
        ...box,
        cx: Math.min(Math.max(box.cx, box.w / 2), Math.max(box.w / 2, width - box.w / 2)),
        cy: Math.min(Math.max(box.cy, box.h / 2), Math.max(box.h / 2, height - box.h / 2)),
    });
    for (const label of labels) {
        const n = Math.hypot(label.dx, label.dy);
        const [dx, dy] = n > 1e-6 ? [label.dx / n, label.dy / n] : [0, 1];
        // How far from its middle the box reaches along the line's direction.
        const reach = Math.min(dx ? label.w / 2 / Math.abs(dx) : Infinity, dy ? label.h / 2 / Math.abs(dy) : Infinity);
        const at = (along, aside) => inside({
            cx: label.x + dx * along - dy * aside,
            cy: label.y + dy * along + dx * aside,
            w: label.w,
            h: label.h,
        });
        // Clear of every label placed before it, and of every line's end.
        const clear = (box) => !placed.some((p) => crowds(p, box, gap))
            && !labels.some((l) => crowds({ cx: l.x, cy: l.y, w: 0, h: 0 }, box, gap));
        let box = at(reach + gap, 0);
        const step = label.h + gap;
        for (let k = 1; k <= 40 && !clear(box); k++) {
            // Out along the line first, then to either side of it, a label's height at a time.
            const out = reach + gap + step * Math.ceil(k / 3);
            box = at(out, k % 3 === 0 ? 0 : (k % 3 === 1 ? 1 : -1) * step * Math.ceil(k / 3));
        }
        placed.push(box);
    }
    return placed.map(({ cx, cy }) => ({ cx, cy }));
}
