/* Measure's features: what a click on a mesh reads of the shape under it -- a round's
 * diameter, a wall's thickness and the gap across it, an edge's length, the angle two
 * flat faces make (docs/viewer.md, "Measure"). A reading is of the mesh drawn, fitted to
 * its vertices and faces, and says what it was fitted to and how well.
 *
 * Pure arithmetic on plain arrays -- a mesh's vertex positions and its triangles -- with
 * no three.js and no DOM, so node holds it (tests/test_measure_features.py). Lengths are
 * the mesh's own units, millimetres, in whatever frame the positions are given in.
 *
 *   meshFrom(positions, index)     the mesh: its vertices welded where they coincide, each
 *                                  triangle's normal, area and middle, and the triangles
 *                                  across each edge. `positions` is [x, y, z, ...], `index`
 *                                  the triangles' corners, or null for a triangle soup (an
 *                                  STL: triangle i is corners 3i, 3i + 1, 3i + 2)
 *   facetOf(mesh, t)               the flat facet triangle t is in: the triangles joined to
 *                                  it that lie in its plane; its normal, area and width
 *   roundAt(mesh, t)               the round t is a facet of: its axis, from the faces'
 *                                  normals, and the circle fitted to their vertices across it,
 *                                  its radius running along the axis where it is a taper
 *   wallAt(mesh, t, point)         from a point of a flat face, the wall behind it (cast along
 *                                  the inward normal to the face that closes it; and a step
 *                                  in toward the face's middle, where that reads thinner: by
 *                                  a face's edge the cast runs down a wall meeting it) and the
 *                                  gap in front of it (cast outward to the face that faces it)
 *   featureAt(mesh, t, point, { pixel })   what a click reads: a round, a flat face, or that
 *                                  it cannot tell, and why
 *   edgeBetween(mesh, va, vb)      whether two vertices are the ends of one edge of the mesh
 *                                  -- a line of mesh edges between faces not in one plane
 *   faceAngle(n1, n2)              the angle two flat faces make, from their normals
 *   declaredOn(round, interfaces)  of a part's declared interfaces (GET /parts/{name}/
 *                                  interfaces), the round one on the same axis, the same way
 *                                  round (a hole a socket's or a bolt hole's, a boss a
 *                                  spigot's), in the same frame as the round
 */

// Two triangles lie in one plane when their normals are this near (degrees).
export const COPLANAR_DEG = 1;
// A round's facets turn by less than this from one to the next (degrees): a hexagon's 60
// does, a square's 90 does not, so a box's sides are walls and a hexagonal boss is round.
export const MAX_STEP_DEG = 65;
// An edge runs along an axis, and a facet's normal stands across it, within this (degrees).
export const AXIAL_DEG = 5;
// The facets of one round are as wide as each other within this ratio: a flat face beside a
// fillet, much wider than the fillet's facets, is not one of them.
export const CHORD_RATIO = 2.5;
// A round is read from at least this many facets, turning through at least this arc.
export const MIN_FACETS = 3;
export const MIN_ARC_DEG = 20;
// A circle fits when its vertices' distance from it, root mean square, is within this share
// of its radius.
export const MAX_RESIDUAL = 0.02;
// A round whose faces lean to its axis by this much or more is a taper (degrees).
export const TAPER_DEG = 0.25;
// Two faces are parallel within this (degrees).
export const PARALLEL_DEG = 0.5;
// A face narrower than this many pixels is too small for a pointer to have chosen.
export const MIN_FACE_PX = 2;

const DEG = 180 / Math.PI;
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scale = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => Math.hypot(a[0], a[1], a[2]);
const unit = (a) => { const l = norm(a); return l > 0 ? [a[0] / l, a[1] / l, a[2] / l] : null; };
const degrees = (cos) => Math.acos(Math.max(-1, Math.min(1, cos))) * DEG;

/* Two directions across a unit vector `n`, at right angles to it and to each other. */
function across(n) {
    const ref = Math.abs(n[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    const u = unit(cross(n, ref));
    return [u, cross(n, u)];
}

export function meshFrom(positions, index = null) {
    const count = index ? index.length / 3 : positions.length / 9;
    const corner = (t, k) => (index ? index[3 * t + k] : 3 * t + k);
    // Vertices welded where they coincide (to a ten-thousandth of a millimetre): an STL
    // writes a vertex once for each triangle that has it.
    const weld = new Int32Array(positions.length / 3);
    const points = [];
    const seen = new Map();
    for (let i = 0; i < weld.length; i++) {
        const p = [positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]];
        const key = `${Math.round(p[0] * 1e4)},${Math.round(p[1] * 1e4)},${Math.round(p[2] * 1e4)}`;
        let id = seen.get(key);
        if (id === undefined) { id = points.length; seen.set(key, id); points.push(p); }
        weld[i] = id;
    }
    const tris = [];
    const edges = new Map();
    const edgeKey = (a, b) => (a < b ? `${a},${b}` : `${b},${a}`);
    for (let t = 0; t < count; t++) {
        const v = [weld[corner(t, 0)], weld[corner(t, 1)], weld[corner(t, 2)]];
        const [a, b, c] = v.map((i) => points[i]);
        const n = cross(sub(b, a), sub(c, a));
        const twice = norm(n);
        tris.push({ v, normal: twice > 0 ? scale(n, 1 / twice) : null, area: twice / 2, middle: scale(add(add(a, b), c), 1 / 3) });
        if (!(twice > 0) || v[0] === v[1] || v[1] === v[2] || v[0] === v[2]) continue;
        for (let k = 0; k < 3; k++) {
            const key = edgeKey(v[k], v[(k + 1) % 3]);
            if (!edges.has(key)) edges.set(key, []);
            edges.get(key).push(t);
        }
    }
    const around = points.map(() => new Set());
    for (const key of edges.keys()) {
        const [a, b] = key.split(",").map(Number);
        around[a].add(b);
        around[b].add(a);
    }
    let reach = 0;
    for (const p of points) reach = Math.max(reach, Math.abs(p[0]), Math.abs(p[1]), Math.abs(p[2]));
    return { points, weld, tris, edges, around, edgeKey, size: Math.max(reach, 1) };
}

/* The triangles across each edge of triangle t: [{ u, a, b }], u the triangle across the
 * edge from vertex a to vertex b; none where the edge is the mesh's boundary. */
function neighbours(mesh, t) {
    const out = [];
    const v = mesh.tris[t].v;
    for (let k = 0; k < 3; k++) {
        const a = v[k], b = v[(k + 1) % 3];
        for (const u of mesh.edges.get(mesh.edgeKey(a, b)) || []) if (u !== t) out.push({ u, a, b });
    }
    return out;
}

const turnBetween = (mesh, t, u) => {
    const [n, m] = [mesh.tris[t].normal, mesh.tris[u].normal];
    return n && m ? degrees(dot(n, m)) : 180;
};

export function facetOf(mesh, t) {
    const seed = mesh.tris[t];
    const tris = new Set([t]);
    if (!seed.normal) return { tris, normal: null, area: 0, width: 0, corners: [] };
    // Joined across an edge and facing as the seed does, a triangle is in its plane.
    const queue = [t];
    while (queue.length) {
        const s = queue.pop();
        for (const { u } of neighbours(mesh, s)) {
            const other = mesh.tris[u];
            if (tris.has(u) || !other.normal) continue;
            if (degrees(dot(other.normal, seed.normal)) >= COPLANAR_DEG) continue;
            tris.add(u);
            queue.push(u);
        }
    }
    let area = 0, sum = [0, 0, 0];
    for (const s of tris) { area += mesh.tris[s].area; sum = add(sum, scale(mesh.tris[s].normal, mesh.tris[s].area)); }
    const normal = unit(sum) || seed.normal;
    // How wide it is: its area over its longest reach, which for a strip is its width. A
    // facet of many corners takes the diagonal of the box round them for its reach.
    const corners = [...new Set([...tris].flatMap((s) => mesh.tris[s].v))].map((i) => mesh.points[i]);
    let longest = 0;
    if (corners.length <= 300) {
        for (let i = 0; i < corners.length; i++) for (let j = i + 1; j < corners.length; j++) longest = Math.max(longest, norm(sub(corners[i], corners[j])));
    } else {
        longest = norm([0, 1, 2].map((k) => Math.max(...corners.map((p) => p[k])) - Math.min(...corners.map((p) => p[k]))));
    }
    return { tris, normal, area, width: longest > 0 ? area / longest : 0, corners };
}

/* How wide a facet is across the axis `a`: its reach along the direction in its plane
 * across the axis. */
function chordOf(facet, a) {
    const w = unit(cross(a, facet.normal));
    if (!w) return 0;
    let lo = Infinity, hi = -Infinity;
    for (const p of facet.corners) { const s = dot(p, w); lo = Math.min(lo, s); hi = Math.max(hi, s); }
    return hi - lo;
}

/* The facets about the axis `a` reached from `seed` across edges that run along it, each as
 * wide as the seed is within CHORD_RATIO and standing across the axis. */
function growAbout(mesh, seed, a) {
    const facets = [seed];
    const taken = new Set(seed.tris);
    const width = chordOf(seed, a);
    const cosAxial = Math.cos(AXIAL_DEG / DEG), sinAxial = Math.sin(AXIAL_DEG / DEG);
    const queue = [seed];
    while (queue.length) {
        const facet = queue.pop();
        for (const t of facet.tris) {
            for (const { u, a: va, b: vb } of neighbours(mesh, t)) {
                if (taken.has(u) || !mesh.tris[u].normal) continue;
                const along = unit(sub(mesh.points[vb], mesh.points[va]));
                if (!along || Math.abs(dot(along, a)) < cosAxial) continue;
                if (turnBetween(mesh, t, u) >= MAX_STEP_DEG) continue;
                const next = facetOf(mesh, u);
                if ([...next.tris].some((s) => taken.has(s))) continue;
                if (Math.abs(dot(next.normal, a)) > sinAxial) continue;
                const chord = chordOf(next, a);
                if (!(chord <= width * CHORD_RATIO && chord >= width / CHORD_RATIO)) continue;
                for (const s of next.tris) taken.add(s);
                facets.push(next);
                queue.push(next);
            }
        }
    }
    return facets;
}

/* The unit vector `a` along which the weighted normals spread least about their mean: the
 * axis they all make one angle with -- a right angle for a cylinder's, less for a taper's --
 * by Jacobi's rotations of their 3x3 spread. */
function leastAcross(normals, weights) {
    const total = weights.reduce((s, w) => s + w, 0) || 1;
    const mean = normals.reduce((s, n, k) => add(s, scale(n, weights[k] / total)), [0, 0, 0]);
    const m = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    normals.forEach((n0, k) => { const n = sub(n0, mean); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) m[i][j] += weights[k] * n[i] * n[j]; });
    const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    for (let sweep = 0; sweep < 50; sweep++) {
        const off = Math.abs(m[0][1]) + Math.abs(m[0][2]) + Math.abs(m[1][2]);
        if (off < 1e-15) break;
        for (const [p, q] of [[0, 1], [0, 2], [1, 2]]) {
            if (Math.abs(m[p][q]) < 1e-18) continue;
            const theta = (m[q][q] - m[p][p]) / (2 * m[p][q]);
            const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
            const c = 1 / Math.sqrt(t * t + 1), s = t * c;
            for (let k = 0; k < 3; k++) {
                const [mkp, mkq] = [m[k][p], m[k][q]];
                m[k][p] = c * mkp - s * mkq; m[k][q] = s * mkp + c * mkq;
            }
            for (let k = 0; k < 3; k++) {
                const [mpk, mqk] = [m[p][k], m[q][k]];
                m[p][k] = c * mpk - s * mqk; m[q][k] = s * mpk + c * mqk;
            }
            for (let k = 0; k < 3; k++) {
                const [vkp, vkq] = [v[k][p], v[k][q]];
                v[k][p] = c * vkp - s * vkq; v[k][q] = s * vkp + c * vkq;
            }
        }
    }
    let least = 0;
    for (let i = 1; i < 3; i++) if (m[i][i] < m[least][least]) least = i;
    return unit([v[0][least], v[1][least], v[2][least]]);
}

/* The circle through points [[x, y]] by least squares (Kasa's): its middle and radius, and
 * how far the points stand from it, root mean square and at the most. */
function circleThrough(points) {
    // x^2 + y^2 + D x + E y + F = 0, solved by its normal equations.
    const A = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], B = [0, 0, 0];
    const [mx, my] = [points.reduce((s, p) => s + p[0], 0) / points.length, points.reduce((s, p) => s + p[1], 0) / points.length];
    for (const [x0, y0] of points) {
        const [x, y] = [x0 - mx, y0 - my];
        const row = [x, y, 1], z = -(x * x + y * y);
        for (let i = 0; i < 3; i++) { B[i] += row[i] * z; for (let j = 0; j < 3; j++) A[i][j] += row[i] * row[j]; }
    }
    const solved = solve3(A, B);
    if (!solved) return null;
    const [D, E, F] = solved;
    const middle = [-D / 2 + mx, -E / 2 + my];
    const r2 = (D * D + E * E) / 4 - F;
    if (!(r2 > 0)) return null;
    const radius = Math.sqrt(r2);
    let squares = 0, most = 0;
    for (const p of points) {
        const d = Math.abs(Math.hypot(p[0] - middle[0], p[1] - middle[1]) - radius);
        squares += d * d; most = Math.max(most, d);
    }
    return { middle, radius, residual: Math.sqrt(squares / points.length), worst: most };
}

/* The round through points [[x, y]] across an axis, each `along` it by its own amount: a
 * middle, and a radius that may run along the axis (a taper's) -- radius + slope * t at t
 * from the middle of their run. From the circle through them, the middle moved and the
 * radius's line fitted in turn until they hold (Landau's way, a line for the radius). Its
 * residual is the points' distance from it, root mean square, and at the most. */
function roundThrough(flat, along) {
    const circle = circleThrough(flat);
    if (!circle) return null;
    const mid = (Math.min(...along) + Math.max(...along)) / 2;
    const t = along.map((s) => s - mid);
    const mean = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;
    const tm = mean(t), stt = t.reduce((s, x) => s + (x - tm) * (x - tm), 0);
    let c = circle.middle, radius = circle.radius, slope = 0, d = [];
    for (let round = 0; round < 100; round++) {
        d = flat.map((p) => Math.hypot(p[0] - c[0], p[1] - c[1]));
        const dm = mean(d);
        slope = stt > 1e-12 ? t.reduce((s, x, i) => s + (x - tm) * (d[i] - dm), 0) / stt : 0;
        radius = dm - slope * tm;
        const next = [0, 1].map((k) => mean(flat.map((p, i) => p[k] - ((radius + slope * t[i]) * (p[k] - c[k])) / (d[i] || 1))));
        const moved = Math.hypot(next[0] - c[0], next[1] - c[1]);
        c = next;
        if (moved < 1e-12) break;
    }
    d = flat.map((p) => Math.hypot(p[0] - c[0], p[1] - c[1]));
    let squares = 0, most = 0;
    d.forEach((di, i) => { const off = Math.abs(di - (radius + slope * t[i])); squares += off * off; most = Math.max(most, off); });
    return { middle: c, radius, slope, mid, residual: Math.sqrt(squares / flat.length), worst: most };
}

function solve3(A, B) {
    const det = (m) => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
    const d = det(A);
    if (!(Math.abs(d) > 1e-18)) return null;
    return [0, 1, 2].map((k) => det(A.map((row, i) => row.map((v, j) => (j === k ? B[i] : v)))) / d);
}

/* The round about the axis `a` that the facets are of, fitted; or why there is none. */
function fitRound(mesh, facets, a0) {
    const weights = facets.map((f) => f.area);
    const normals = facets.map((f) => f.normal);
    let a = facets.length >= MIN_FACETS ? leastAcross(normals, weights) || a0 : a0;
    // Either way along the axis is the axis: written with its largest part positive.
    const largest = a.reduce((k, v, i) => (Math.abs(v) > Math.abs(a[k]) + 1e-9 ? i : k), 0);
    if (a[largest] < 0) a = scale(a, -1);
    const [u, v] = across(a);
    // Each facet's normal's direction about the axis, and the arc they turn through.
    const turns = normals.map((n) => Math.atan2(dot(n, v), dot(n, u)) * DEG).sort((x, y) => x - y);
    const distinct = [];
    for (const d of turns) if (!distinct.length || d - distinct[distinct.length - 1] > 0.2) distinct.push(d);
    if (distinct.length > 1 && distinct[0] + 360 - distinct[distinct.length - 1] <= 0.2) distinct.pop();
    const gaps = distinct.map((d, i) => (i + 1 < distinct.length ? distinct[i + 1] - d : distinct[0] + 360 - d));
    const steps = [...gaps].sort((x, y) => x - y);
    const step = steps.length ? steps[Math.floor((steps.length - 1) / 2)] : 360;
    const widest = Math.max(...gaps);
    const closed = distinct.length >= MIN_FACETS && widest <= 1.5 * step;
    // The arc the facets cover: their normals' spread and half a step past each end.
    const arc = closed ? 360 : distinct.length > 1 ? Math.min(360, 360 - widest + step) : 0;
    const facetCount = distinct.length;
    if (facetCount < MIN_FACETS || arc < MIN_ARC_DEG) {
        return { found: false, facets: facetCount, arc, why: `the faces around the click turn about no one axis (${facetCount} facet${facetCount === 1 ? "" : "s"} along one, through ${arc.toFixed(0)} degrees): a steep cone, a sphere or a blend` };
    }
    const ids = [...new Set(facets.flatMap((f) => [...f.tris].flatMap((t) => mesh.tris[t].v)))];
    const flat = ids.map((i) => [dot(mesh.points[i], u), dot(mesh.points[i], v)]);
    const along = ids.map((i) => dot(mesh.points[i], a));
    const circle = roundThrough(flat, along);
    if (!circle || !(circle.radius > 0)) return { found: false, facets: facetCount, arc, why: "its vertices fit no circle across the axis" };
    if (circle.residual > MAX_RESIDUAL * circle.radius) {
        return { found: false, facets: facetCount, arc, residual: circle.residual, radius: circle.radius, why: `its facets turn about one axis, but their vertices are not on one circle: ${circle.residual.toFixed(2)} mm from it, root mean square, on a radius of ${circle.radius.toFixed(2)} mm` };
    }
    // A hole's faces face its axis; a boss's face away from it.
    let toward = 0, away = 0;
    for (const f of facets) {
        const m = [dot(f.corners.reduce((s, p) => add(s, p), [0, 0, 0]), u) / f.corners.length, dot(f.corners.reduce((s, p) => add(s, p), [0, 0, 0]), v) / f.corners.length];
        const out = [m[0] - circle.middle[0], m[1] - circle.middle[1]];
        const facing = dot([out[0], out[1], 0], [dot(f.normal, u), dot(f.normal, v), 0]);
        if (facing < 0) toward += f.area; else away += f.area;
    }
    const total = toward + away;
    if (Math.min(toward, away) > 0.1 * total) {
        return { found: false, facets: facetCount, arc, why: "its facets face both toward its axis and away from it, so it is neither a hole nor a boss" };
    }
    const [lo, hi] = [Math.min(...along), Math.max(...along)];
    const middle = add(add(scale(u, circle.middle[0]), scale(v, circle.middle[1])), scale(a, circle.mid));
    const sides = closed ? facetCount : Math.round(360 / step);
    const R = circle.radius;
    // How far its faces lean to the axis: a taper's radius runs along it.
    const lean = Math.atan(circle.slope) * DEG;
    return {
        found: true,
        sense: toward > away ? "hole" : "boss",
        diameter: 2 * R,
        radius: R,
        // A regular polygon's vertices lie on the circle and its flats inside it.
        flats: 2 * R * Math.cos(Math.PI / sides),
        sides,
        facets: facetCount,
        closed,
        arc,
        vertices: ids.length,
        residual: circle.residual,
        worst: circle.worst,
        axis: a,
        middle,
        length: hi - lo,
        across: u,
        // The radius at t along the axis from the middle is radius + slope * t.
        slope: circle.slope,
        lean,
        taper: Math.abs(lean) >= TAPER_DEG,
        ends: [2 * (R + circle.slope * (lo - circle.mid)), 2 * (R + circle.slope * (hi - circle.mid))],
    };
}

export function roundAt(mesh, t) {
    const seed = facetOf(mesh, t);
    if (!seed.normal) return { found: false, curved: false, why: "the face under the click has no area" };
    // An axis is an edge of the seed facet along which it turns, by less than a round's
    // step, onto the facet beside it.
    const axes = [];
    for (const s of seed.tris) {
        for (const { u, a, b } of neighbours(mesh, s)) {
            if (seed.tris.has(u)) continue;
            const turn = turnBetween(mesh, s, u);
            if (turn < COPLANAR_DEG || turn >= MAX_STEP_DEG) continue;
            const along = unit(sub(mesh.points[b], mesh.points[a]));
            if (along && !axes.some((x) => Math.abs(dot(x, along)) > Math.cos(2 / DEG))) axes.push(along);
        }
    }
    let best = null, curved = false;
    for (const a of axes) {
        const facets = growAbout(mesh, seed, a);
        if (facets.length > 1) curved = true;
        const fit = fitRound(mesh, facets, a);
        const better = !best || (fit.found && !best.found) || (fit.found === best.found && fit.facets > best.facets);
        if (better) best = fit;
    }
    if (!best) return { found: false, curved: false, why: "the face under the click is flat: nothing beside it turns about an axis" };
    return { ...best, curved: curved || best.found };
}

/* From `origin` along the unit `dir`, the nearest triangle met past a hair's breadth, not
 * one of `skip`: { t, distance, at }; null where it meets none. Both sides of a triangle
 * are met (Moller and Trumbore's test). */
function cast(mesh, origin, dir, skip) {
    const hair = 1e-6 * mesh.size;
    let best = null;
    mesh.tris.forEach((tri, t) => {
        if (skip.has(t) || !tri.normal) return;
        const [a, b, c] = tri.v.map((i) => mesh.points[i]);
        const e1 = sub(b, a), e2 = sub(c, a);
        const p = cross(dir, e2);
        const det = dot(e1, p);
        if (Math.abs(det) < 1e-12) return;
        const inv = 1 / det;
        const s = sub(origin, a);
        const bu = dot(s, p) * inv;
        if (bu < -1e-9 || bu > 1 + 1e-9) return;
        const q = cross(s, e1);
        const bv = dot(dir, q) * inv;
        if (bv < -1e-9 || bu + bv > 1 + 1e-9) return;
        const distance = dot(e2, q) * inv;
        if (distance > hair && (!best || distance < best.distance)) best = { t, distance };
    });
    if (best) best.at = add(origin, scale(dir, best.distance));
    return best;
}

/* From `point` on a face whose outward normal is `n`, the wall behind it: cast along the
 * inward normal to the face that closes it. */
function wallFrom(mesh, point, n, skip) {
    const inward = scale(n, -1);
    const behind = cast(mesh, point, inward, skip);
    if (!behind) return { why: "a cast along its inward normal leaves the piece without meeting another face: the mesh is open there" };
    const m = mesh.tris[behind.t].normal;
    // Leaving the piece, the face met looks the way the cast goes.
    if (dot(m, inward) <= 0) return { why: "the first face met inside looks back toward the click: the mesh is not closed there, or overlaps itself" };
    const off = degrees(dot(m, inward));
    return { thickness: behind.distance, far: behind.at, off, parallel: off < PARALLEL_DEG };
}

/* Whether `p`, a point of the facet's plane, lies on one of its triangles. */
function onFacet(mesh, facet, p) {
    for (const s of facet.tris) {
        const [a, b, c] = mesh.tris[s].v.map((i) => mesh.points[i]);
        const n = mesh.tris[s].normal;
        if (!n) continue;
        const inside = [[a, b], [b, c], [c, a]].every(([u, v]) => dot(cross(sub(v, u), sub(p, u)), n) >= -1e-9);
        if (inside) return true;
    }
    return false;
}

/* A step in from the click, toward the middle of its face -- as far as the wall read there
 * is thick, or to the middle -- and the wall read there, where it is a twentieth thinner or
 * more: a click by a face's edge casts down whatever wall meets the face under that edge
 * (a hollow box's top, by its corner, casts down its side), and a step in reads the face's
 * own. Null where the step leaves the face, or reads no thinner. */
function stepIn(mesh, facet, point, wall) {
    let middle = [0, 0, 0];
    for (const s of facet.tris) middle = add(middle, scale(mesh.tris[s].middle, mesh.tris[s].area / facet.area));
    // The middle, laid in the plane through the click.
    middle = sub(middle, scale(facet.normal, dot(sub(middle, point), facet.normal)));
    const toward = sub(middle, point), far = norm(toward);
    if (!(far > 1e-6 * mesh.size)) return null;
    const at = add(point, scale(toward, Math.min(1, wall.thickness / far)));
    if (!onFacet(mesh, facet, at)) return null;
    const there = wallFrom(mesh, at, facet.normal, facet.tris);
    if (there.thickness === undefined || there.thickness > 0.95 * wall.thickness) return null;
    return { thickness: there.thickness, at, far: there.far };
}

export function wallAt(mesh, t, point) {
    const facet = facetOf(mesh, t);
    const n = facet.normal;
    if (!n) return { normal: null, wall: { why: "the face under the click has no area" }, gap: null };
    const wall = wallFrom(mesh, point, n, facet.tris);
    if (wall.thickness !== undefined) {
        const inner = stepIn(mesh, facet, point, wall);
        if (inner) wall.stepIn = inner;
    }
    const ahead = cast(mesh, point, n, facet.tris);
    let gap = null;
    if (ahead) {
        const m = mesh.tris[ahead.t].normal;
        // Across open space, the face met looks back at the click.
        if (dot(m, n) < 0) {
            const off = degrees(-dot(m, n));
            gap = { width: ahead.distance, far: ahead.at, off, parallel: off < PARALLEL_DEG };
        }
    }
    return { normal: n, width: facet.width, area: facet.area, wall, gap };
}

export function featureAt(mesh, t, point, { pixel = 0 } = {}) {
    if (!(t >= 0 && t < mesh.tris.length)) return { kind: "unknown", why: "the click met no face of the mesh" };
    const round = roundAt(mesh, t);
    // A round's wall too: from the click into what it is made of, to the face beyond.
    if (round.found) return { kind: "round", ...round, wall: wallAt(mesh, t, point).wall };
    if (round.curved) return { kind: "unknown", why: round.why };
    const facet = facetOf(mesh, t);
    if (!facet.normal) return { kind: "unknown", why: "the face under the click has no area" };
    if (pixel > 0 && facet.width < MIN_FACE_PX * pixel) {
        return { kind: "unknown", why: `the face under the pointer is ${facet.width.toFixed(2)} mm across, about ${(facet.width / pixel).toFixed(1)} pixels here, too small to tell which face was meant: come nearer` };
    }
    return { kind: "flat", ...wallAt(mesh, t, point) };
}

export function edgeBetween(mesh, va, vb) {
    const [a, b] = [mesh.weld[va], mesh.weld[vb]];
    if (a === undefined || b === undefined || a === b) return null;
    const [pa, pb] = [mesh.points[a], mesh.points[b]];
    const span = norm(sub(pb, pa));
    const along = unit(sub(pb, pa));
    if (!along) return null;
    const tolerance = 1e-5 * mesh.size;
    // The mesh's edges from a toward b, each lying on the line between them, each a crease
    // (its two faces not in one plane) or the mesh's boundary.
    let at = a, travelled = 0, pieces = 0, turns = [];
    while (at !== b) {
        let next = null;
        for (const x of mesh.around[at]) {
            const d = sub(mesh.points[x], pa);
            const s = dot(d, along);
            if (s <= dot(sub(mesh.points[at], pa), along) + tolerance || s > span + tolerance) continue;
            if (norm(sub(d, scale(along, s))) > tolerance) continue;
            const faces = mesh.edges.get(mesh.edgeKey(at, x)) || [];
            const turn = faces.length === 2 ? turnBetween(mesh, faces[0], faces[1]) : null;
            if (faces.length === 2 && turn < COPLANAR_DEG) continue;
            if (!next || s < next.s) next = { x, s, turn };
        }
        if (!next) return null;
        travelled = next.s;
        pieces += 1;
        if (next.turn !== null) turns.push(next.turn);
        at = next.x;
    }
    const turn = turns.length ? turns.reduce((s, v) => s + v, 0) / turns.length : null;
    return { length: travelled, pieces, turn, meet: turn === null ? null : 180 - turn, boundary: turns.length < pieces };
}

export function faceAngle(n1, n2) {
    const between = degrees(dot(unit(n1), unit(n2)));
    return {
        between,
        // As a wedge's: where the faces would meet, the angle between them.
        angle: 180 - between,
        parallel: between < PARALLEL_DEG || between > 180 - PARALLEL_DEG,
        facing: between < 90 ? "the same way" : "apart",
    };
}

// What each type of round interface declares, where along it, and which way round it is.
const xyz = (v) => [v.x, v.y, v.z];
const ROUND_TYPES = {
    socket: { sense: "hole", figures: (i) => [{ diameter: i.diameter, where: "its bore at the mouth", at: xyz(i.position) }] },
    bolt_hole: { sense: "hole", figures: (i) => [{ diameter: i.diameter, where: "its hole", at: xyz(i.position) }] },
    spigot: {
        sense: "boss",
        figures: (i) => {
            const tip = add(xyz(i.position), scale(unit(xyz(i.normal)), i.length));
            return Math.abs(i.d_base - i.d_tip) < 1e-6 ? [{ diameter: i.d_base, where: "its outside", at: xyz(i.position) }]
                : [{ diameter: i.d_base, where: "its outside at the base", at: xyz(i.position) }, { diameter: i.d_tip, where: "its outside at the tip", at: tip }];
        },
    },
};

export function declaredOn(round, interfaces) {
    if (!round || !round.found || !Array.isArray(interfaces)) return { round: 0, match: null };
    let roundCount = 0, match = null;
    for (const i of interfaces) {
        const kind = ROUND_TYPES[i.type];
        if (!kind || !i.position || !i.normal) continue;
        roundCount += 1;
        if (kind.sense !== round.sense) continue;
        const n = unit(xyz(i.normal));
        if (!n || Math.abs(dot(n, round.axis)) < Math.cos(2 / DEG)) continue;
        const d = sub(xyz(i.position), round.middle);
        const off = norm(sub(d, scale(round.axis, dot(d, round.axis))));
        if (off > Math.max(0.5, 0.05 * round.radius)) continue;
        for (const figure of kind.figures(i)) {
            // The mesh's diameter where the figure is declared: a taper's runs along it.
            const mesh = 2 * (round.radius + (round.slope || 0) * dot(sub(figure.at, round.middle), round.axis));
            const apart = mesh - figure.diameter;
            if (!match || Math.abs(apart) < Math.abs(match.apart)) {
                match = { name: i.name, type: i.type, source: i.source, cite: i.cite || null, diameter: figure.diameter, where: figure.where, mesh, apart, off };
            }
        }
    }
    return { round: roundCount, match };
}
