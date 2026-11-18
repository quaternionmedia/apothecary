/* The universe's orbitals as the world draws them (docs/viewer.md, "Apothecary is the
 * universe"): each shell's rings, the outline round each category's cluster on its shell,
 * and a line from a part to each part it is built from. Pure arithmetic in the site's
 * frame (x, y, z; z up), no three.js and no DOM, so node can hold it
 * (tests/test_orbits_drawn.py); the page turns each point into three.js's (sceneAt) and
 * draws it in its layer's colour.
 *
 *   middleOf(node)                 the middle of a node's world box
 *   shellsOf(nodes)                [{ shell, radius }], innermost first: how far a shell's
 *                                  nodes' middles stand from the centre
 *   ringsOf(radius, count)         `count` great circles of a sphere, each a closed loop
 *                                  of points, tilted as an atom's orbits are: every shell
 *                                  in the same planes, so the shells' rings nest
 *   clustersOf(nodes)              [{ shell, category, centre, angle, radius, members }]:
 *                                  the cap of its shell that holds a category's nodes
 *   capOutline(cluster, segments)  the cap's edge, a closed loop on its shell
 *   linksOf(nodes)                 [{ from, to }]: a node's key to each node it is built
 *                                  from, both drawn
 *   shellLabel(shell, nodes)       what a shell is, in a few words: built from nothing, built
 *                                  from those inside it, or the sites
 *   clusterLabel(cluster, clusters)   a cluster's category, and its shell where the
 *                                  category has clusters on more than one
 *   limbOf(radius, eye)            the edge of a shell's sphere as the eye sees it: a circle,
 *                                  none from inside
 *   facesEye(eye, point)           whether a point of a sphere is on the side the eye sees
 *   pieceNear(points, x, y, px)    of pieces on screen ({ key, sx, sy, off, depth }), the one
 *                                  nearest (x, y) within `px`; of those about as near, the
 *                                  one nearer the eye
 *   nearestLoop(loops, x, y, px)   of loops of points on screen ({ sx, sy }, `off` where
 *                                  a point is behind the eye), the index of the one that
 *                                  passes nearest (x, y) within `px`, or -1
 */

// A ring's tilt from the equator, and how much wider than its pieces a cluster's outline
// is drawn (radians), so it stands clear of them.
export const RING_TILT = (60 * Math.PI) / 180;
export const CLUSTER_MARGIN = 0.03;

import { nearestWithin } from "./measure.js";

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const length = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const l = length(a); return l > 0 ? [a[0] / l, a[1] / l, a[2] / l] : null; };
const angleBetween = (a, b) => Math.acos(Math.max(-1, Math.min(1, dot(a, b))));

export function middleOf(node) {
    const b = node.world_bounds;
    return b ? [0, 1, 2].map((i) => (b.min[i] + b.max[i]) / 2) : null;
}

/* Half the diagonal of a node's own footprint: the sphere about its middle that holds it. */
function reachOf(node) {
    const b = node.footprint || node.world_bounds;
    return b ? length(sub(b.max, b.min)) / 2 : 0;
}

export function shellsOf(nodes) {
    const found = new Map();
    for (const node of nodes) {
        const at = middleOf(node);
        if (!Number.isInteger(node.shell) || !at) continue;
        const r = found.get(node.shell) || [];
        r.push(length(at));
        found.set(node.shell, r);
    }
    return [...found.entries()].sort((a, b) => a[0] - b[0])
        .map(([shell, rs]) => ({ shell, radius: rs.reduce((s, v) => s + v, 0) / rs.length }));
}

/* Two directions across a unit vector `n`, at right angles to it and to each other. */
function across(n) {
    const ref = Math.abs(n[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    const u = unit(cross(n, ref));
    return [u, cross(n, u)];
}

function loop(centre, u, v, radius, segments) {
    const points = [];
    for (let i = 0; i < segments; i++) {
        const t = (2 * Math.PI * i) / segments;
        points.push([0, 1, 2].map((k) => centre[k] + radius * (Math.cos(t) * u[k] + Math.sin(t) * v[k])));
    }
    return points;
}

export function ringsOf(radius, count = 3, segments = 128) {
    const rings = [];
    for (let k = 0; k < count; k++) {
        const azimuth = (2 * Math.PI * k) / count;
        const normal = [Math.sin(RING_TILT) * Math.cos(azimuth), Math.sin(RING_TILT) * Math.sin(azimuth), Math.cos(RING_TILT)];
        const [u, v] = across(normal);
        rings.push(loop([0, 0, 0], u, v, radius, segments));
    }
    return rings;
}

export function clustersOf(nodes) {
    const groups = new Map();
    for (const node of nodes) {
        const at = middleOf(node);
        if (!Number.isInteger(node.shell) || !node.category || !at || !length(at)) continue;
        const id = `${node.shell}\u0000${node.category}`;
        if (!groups.has(id)) groups.set(id, { shell: node.shell, category: node.category, members: [] });
        groups.get(id).members.push({ key: node.key, at, reach: reachOf(node) });
    }
    const out = [];
    for (const group of groups.values()) {
        const radius = group.members.reduce((s, m) => s + length(m.at), 0) / group.members.length;
        const sum = group.members.reduce((s, m) => s.map((v, i) => v + m.at[i] / length(m.at)), [0, 0, 0]);
        const centre = unit(sum) || unit(group.members[0].at);
        let angle = 0;
        for (const m of group.members) {
            const own = Math.asin(Math.min(1, m.reach / Math.max(radius, m.reach)));
            angle = Math.max(angle, angleBetween(centre, unit(m.at)) + own);
        }
        out.push({
            shell: group.shell, category: group.category, centre, radius,
            angle: Math.min(Math.PI - CLUSTER_MARGIN, angle + CLUSTER_MARGIN),
            members: group.members.map((m) => m.key).sort(),
        });
    }
    return out.sort((a, b) => a.shell - b.shell || (a.category < b.category ? -1 : a.category > b.category ? 1 : 0));
}

export function capOutline(cluster, segments = 96) {
    const { centre, angle, radius } = cluster;
    const [u, v] = across(centre);
    const middle = centre.map((c) => c * radius * Math.cos(angle));
    return loop(middle, u, v, radius * Math.sin(angle), segments);
}

export function linksOf(nodes) {
    const keys = new Set(nodes.map((n) => n.key));
    const out = [];
    for (const node of nodes) {
        for (const name of node.built_from || []) {
            if (keys.has(name) && name !== node.key) out.push({ from: node.key, to: name });
        }
    }
    return out;
}

/* The distance from (x, y) to the segment a-b, on screen. */
function toSegment(x, y, a, b) {
    const dx = b.sx - a.sx, dy = b.sy - a.sy;
    const span = dx * dx + dy * dy;
    const t = span ? Math.max(0, Math.min(1, ((x - a.sx) * dx + (y - a.sy) * dy) / span)) : 0;
    return Math.hypot(x - (a.sx + t * dx), y - (a.sy + t * dy));
}

export function nearestLoop(loops, x, y, px) {
    let best = -1, bestAt = px;
    loops.forEach((points, index) => {
        for (let i = 0; i < points.length; i++) {
            const a = points[i], b = points[(i + 1) % points.length];
            if (a.off || b.off) continue;
            const d = toSegment(x, y, a, b);
            if (d <= bestAt && (best === -1 || d < bestAt)) { best = index; bestAt = d; }
        }
    });
    return best;
}

/* What a shell is, as the docs say it: the innermost holds parts built from no other, each
 * shell out holds those built from the shells inside it, and the outermost, where the
 * sites stand, is the sites. */
export function shellLabel(shell, nodes) {
    const here = nodes.filter((n) => n.shell === shell);
    const sites = here.length > 0 && here.every((n) => n.site_ref);
    const what = sites ? "sites" : shell === 0 ? "built from nothing" : "built from those inside";
    return `Shell ${shell} \u00b7 ${what}`;
}

/* What a cluster's outline is labelled: its category, and where the category has a
 * cluster on more than one shell, which shell this one is on, so two outlines of one
 * category are told apart. `clusters` is every cluster drawn (clustersOf). */
export function clusterLabel(cluster, clusters) {
    const shells = new Set(clusters.filter((c) => c.category === cluster.category).map((c) => c.shell));
    return shells.size > 1 ? `${cluster.category} · shell ${cluster.shell}` : cluster.category;
}

/* The circle a sphere of `radius` about the middle shows an eye at `eye` ([x, y, z]):
 * where its edge is seen, { centre, radius, normal } -- the circle round the eye's line
 * to the middle, where the lines from the eye touch the sphere; null for an eye inside
 * the sphere or on it, which sees no edge. */
export function limbOf(radius, eye) {
    const d = length(eye);
    if (!(d > radius)) return null;
    const normal = eye.map((v) => v / d);
    return { centre: normal.map((v) => (v * radius * radius) / d), radius: radius * Math.sqrt(1 - (radius * radius) / (d * d)), normal };
}

/* Whether a point of the sphere is on the side an eye sees (both as [x, y, z] about the
 * sphere's middle): past the horizon from the eye a point is behind the sphere; an eye
 * inside the sphere, or on it, sees every point. */
export function facesEye(eye, point) {
    const reach = dot(point, point);
    return dot(eye, eye) <= reach || dot(point, eye) > reach;
}

/* The piece a pointer is on, at any distance: of `points` ({ key, sx, sy, off, depth }),
 * those not `off` within `px` of (x, y), the nearest, a nearer-the-eye one taking it
 * from one that is only a pixel or two nearer the pointer. null when none. */
export function pieceNear(points, x, y, px, slack = 3) {
    const seen = points.filter((p) => !p.off);
    const first = nearestWithin(seen, x, y, px);
    if (!first) return null;
    const reach = Math.hypot(first.sx - x, first.sy - y) + slack;
    let best = first;
    for (const p of seen) {
        if (Math.hypot(p.sx - x, p.sy - y) <= Math.min(px, reach) && p.depth < best.depth) best = p;
    }
    return best.key;
}
