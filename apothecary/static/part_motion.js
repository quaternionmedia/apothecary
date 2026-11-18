/* A part's motion on the page: the arithmetic between two rows of its table.
 *
 * The table is the server's (GET /parts/{name}/motion, motion/1, apothecary/motion.py):
 * each moving piece's pose -- [x, y, turn] in the part's frame, mm and degrees -- at each
 * sample of the motion's parameter, a bent piece's outlines at each, and each gap's
 * marks at each, measured there. This module computes nothing of a part: between two
 * rows it takes each number in proportion (interpolate, as motion.py's), and it shows a
 * gap as the nearest row says it (nearest). tests/test_part_motion_js.py runs it in node
 * and holds it to motion.py.
 *
 * Pure: no DOM, no three.js. A piece's place is said in three.js's axes (the site's
 * (x, y, z) stands at (x, z, -y), as static/frames.js's sceneAt), so the widget that
 * draws it only copies numbers.
 *
 * bracket(samples, v) -> [i, t]; interpolate(samples, rows, v) -> row; nearest(samples, v) -> i
 * poseAt(table, piece, v, cycle) -> [x, y, turn], turned on by `per_cycle` each cycle
 * outlinesAt(table, bent, v) -> [[[x, y], ...], ...]
 * placeIn(pose, centre, still) -> { position: [X, Y, Z], angle } of a piece drawn centred
 *   on `centre` (its measured box's middle, in its own frame), in the still piece's
 *   frame, whose middle is `still`; angle about three.js's y, in radians
 * gapsAt(table, v) -> each gap as the nearest row says it
 * advance(table, state, seconds) -> the next state while it plays: a cyclic motion goes
 *   round again, a turn on per cycle; any other goes back and forth
 * stepFrom(table, v, way) -> the sample after (way 1) or before (way -1) v
 */

export function bracket(samples, value) {
    const last = samples.length - 1;
    if (last <= 0 || value <= samples[0]) return [0, 0];
    if (value >= samples[last]) return [Math.max(0, last - 1), 1];
    let lo = 0, hi = last;
    while (hi - lo > 1) {
        const mid = (lo + hi) >> 1;
        if (samples[mid] <= value) lo = mid; else hi = mid;
    }
    return [lo, (value - samples[lo]) / (samples[lo + 1] - samples[lo])];
}

export function interpolate(samples, rows, value) {
    if (rows.length === 1) return rows[0].slice();
    const [i, t] = bracket(samples, value);
    return rows[i].map((x, k) => x + t * (rows[i + 1][k] - x));
}

export function nearest(samples, value) {
    const [i, t] = bracket(samples, value);
    return t > 0.5 && i + 1 < samples.length ? i + 1 : i;
}

export function poseAt(table, piece, value, cycle = 0) {
    const [x, y, turn] = interpolate(table.samples, piece.poses, value);
    return [x, y, turn + cycle * (piece.per_cycle || 0)];
}

export function outlinesAt(table, bent, value) {
    const [i, t] = bracket(table.samples, value);
    const a = bent.outlines[i], b = bent.outlines[Math.min(i + 1, bent.outlines.length - 1)];
    return a.map((shape, s) => shape.map(([x, y], k) => [x + t * (b[s][k][0] - x), y + t * (b[s][k][1] - y)]));
}

// The site's (x, y, z) in three.js's axes.
const scene = (x, y, z) => [x, z, -y];

export function placeIn([x, y, turn], centre, still) {
    const a = (turn * Math.PI) / 180;
    const c = Math.cos(a), s = Math.sin(a);
    // The piece's middle, carried by its pose: turned about its own origin, then moved.
    const cx = x + c * centre[0] - s * centre[1], cy = y + s * centre[0] + c * centre[1];
    return { position: scene(cx - still[0], cy - still[1], centre[2] - still[2]), angle: a };
}

export function gapsAt(table, value) {
    const i = nearest(table.samples, value);
    return table.gaps.map((g) => ({ name: g.name, label: g.label, unit: g.unit, z: g.z, sample: i, at: table.samples[i], least: g.least[i], marks: g.marks[i] }));
}

export function stepFrom(table, value, way) {
    const s = table.samples;
    if (way > 0) return s.find((v) => v > value + 1e-9) ?? s[s.length - 1];
    for (let k = s.length - 1; k >= 0; k--) if (s[k] < value - 1e-9) return s[k];
    return s[0];
}

export function advance(table, { value, cycle = 0, way = 1 }, seconds, span = 6) {
    const [lo, hi] = table.range;
    const width = hi - lo;
    let v = value + way * (width / span) * seconds;
    if (table.cyclic) {
        while (v > hi) { v -= width; cycle += 1; }
        while (v < lo) { v += width; cycle -= 1; }
        return { value: v, cycle, way };
    }
    if (v > hi) { v = hi - (v - hi); way = -1; }
    if (v < lo) { v = lo + (lo - v); way = 1; }
    return { value: Math.min(hi, Math.max(lo, v)), cycle, way };
}
