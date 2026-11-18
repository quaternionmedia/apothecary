/* Measure in the world: the measurement layer's scene objects, its clicks and its readings
 * (docs/viewer.md, "Measure"); measure.js is its arithmetic. Its logic is plain functions
 * node can hold (tests/test_measure_world.py); mountMeasureWorld is given the viewer's
 * scene, camera, canvas and pick function as arguments and reaches into nothing else.
 *
 * Shown, the layer is a mode: a click in the world drops a point (the nearest vertex of the
 * face under it within SNAP_PX, else the surface point), through the one pick path (the
 * viewer's raycastHits, so what a click passes through it passes through), and selects
 * nothing; a piece is still selected from Site's rows. The selection wears a dimension line
 * along each of its own axes. Every number says where it comes from: the part's declared
 * footprint, the envelope of its pieces, the mesh as loaded, or a stand-in box.
 *
 * A click also reads what is under it, from the mesh drawn (measure_features.js is that
 * arithmetic): a curved face the round it is a facet of, its diameter drawn as a circle and a
 * line across it; a flat face the wall behind it and the gap in front of it, each drawn as a
 * line; a face it cannot decide on, why. A round on a part that declares its interfaces is
 * read beside the declared one on the same axis. Two vertices along one edge of the mesh read
 * that edge, and two flat faces the angle between them.
 *
 *   sourceOf({ placeholder, moving, footprint, envelope })   where a selection's size comes
 *                                  from, in the words its reading says
 *   tokenOf(source)                the word a dimension line's label says of that source
 *   pointsAfter(points, point)     the points once a click drops another: a third starts again
 *   readingsOf({ points, selection, selectedKey, nodeOf, envelopeOf, frameOf, pair,
 *               declaredOf })      the readings as text, most recent first: the points and
 *                                  what is under them, then the selection
 *   inPartFrame(round, centredFrom)   a round read in its mesh's frame, in its part's own
 *   featureWords(feature)          what a click read under it, as the reading says it
 *   declaredWords(declared, { variant })   the declared round beside it
 *   pairWords({ edge, angle })     an edge between two points, and the angle of two faces
 *   featureBrief(feature), hintAfter(feature)   what a first click read and how to get the
 *                                  other readings, as the status line says them
 *   mountMeasureWorld(world)       the layer's state ({ points, group, lines, ... }) and what
 *                                  it does: on, click, snap, clear, soon, selection,
 *                                  readings, draw, place, layersApplied
 */

import * as THREE from "three";
import { MEASURE } from "/static/pick_scope.js";
import { siteAt } from "/static/frames.js";
import { layerColour, layerHex } from "/static/layer_colours.js";
import { ownExtents, sizeFromSceneBox, turnedExtents, between, gap as gapBetween, nearestWithin, length as mmText, layLabels } from "/static/measure.js";
import { meshFrom, featureAt, edgeBetween, faceAngle, declaredOn } from "/static/measure_features.js";

export const SNAP_PX = 12;      // a measured point snaps to a vertex this near the pointer
// A measurement's lines, the points at their ends and its labels' text, in pixels on screen
// whatever the distance: drawn thick enough to read over a mesh.
export const ROD_PX = 3;
export const END_PX = 7;
export const LABEL_PX = 13;
// A round's circle is drawn as this many rods.
export const CIRCLE_RODS = 48;

export function sourceOf({ placeholder, moving = 0, footprint, envelope }) {
    return !placeholder ? (moving ? `the drawn mesh, as loaded, its ${moving} moving piece${moving === 1 ? "" : "s"} with it` : "the drawn mesh, as loaded")
        : footprint ? "declared footprint"
        : envelope ? "envelope of its pieces" : "a stand-in box, no size declared";
}

export function tokenOf(source) {
    return source.startsWith("the drawn") ? "mesh" : source.split(" ")[0];
}

export function pointsAfter(points, point) {
    return [...(points.length >= 2 ? [] : points), point];
}

const fixed = (v, places = 2) => (Math.abs(v) < 0.5 * 10 ** -places ? 0 : v).toFixed(places);
const triple = (v) => `(${v.map((x) => fixed(x)).join(", ")})`;
const degrees = (v) => `${fixed(v, 1)} degrees`;

export function inPartFrame(round, centredFrom) {
    // three.js's (x, y, z) is the site's (x, -z, y): the part's own letters, z up.
    const site = (v) => [v[0], -v[2], v[1]];
    let axis = site(round.axis), slope = round.slope, ends = round.ends;
    // Either way along the axis is the axis: written with its largest part positive, and
    // the taper's run and ends read the same way.
    const largest = axis.reduce((k, v, i) => (Math.abs(v) > Math.abs(axis[k]) + 1e-9 ? i : k), 0);
    if (axis[largest] < 0) { axis = axis.map((v) => -v); slope = -slope; ends = [...ends].reverse(); }
    return { ...round, axis, slope, ends, middle: site(round.middle).map((v, i) => v + centredFrom[i]), across: site(round.across) };
}

export function featureWords(f) {
    if (!f) return null;
    if (f.kind === "unknown") return `cannot tell a diameter or a wall here: ${f.why}`;
    if (f.kind === "flat") {
        const w = f.wall;
        let words = w && w.thickness !== undefined
            ? `a flat face, its wall ${mmText(w.thickness)} thick (cast from the click along the face's inward normal to the face behind it, ${w.parallel ? "parallel to it" : `${degrees(w.off)} off parallel`}; the drawn mesh)`
            : `a flat face, but no wall read behind it: ${w ? w.why : "nothing is behind it"}`;
        if (f.gap) words += `; across it a gap of ${mmText(f.gap.width)} to the face that faces it, ${f.gap.parallel ? "parallel" : `${degrees(f.gap.off)} off parallel`}`;
        return words;
    }
    const whole = f.closed ? `the whole round, ${f.facets} facets` : `an arc of ${fixed(f.arc, 0)} degrees of it, ${f.facets} facets`;
    let words = `a ${f.sense} ⌀ ${mmText(f.diameter)} across its vertices (fitted to the drawn mesh: ${f.vertices} vertices of ${whole}; ${mmText(f.residual)} from the circle, root mean square)`;
    if (f.taper) words += `; a taper, its faces leaning ${degrees(Math.abs(f.lean))} to its axis, ⌀ ${mmText(f.ends[0])} at one end to ⌀ ${mmText(f.ends[1])} at the other, ${mmText(f.length)} apart: the figure above is its middle's`;
    if (mmText(f.flats) !== mmText(f.diameter)) words += `; across its flats ⌀ ${mmText(f.flats)}, a regular ${f.sides}-gon's, ${f.sense === "hole" ? "nearer what a printed hole takes" : "what calipers across two flats read"}`;
    words += `; its axis ${triple(f.axis)} through ${triple(f.middle)} mm in ${f.frame || "its mesh's frame"}`;
    if (f.wall && f.wall.thickness !== undefined) words += `; its wall ${mmText(f.wall.thickness)} thick, cast from the click to the face beyond`;
    return words;
}

export function declaredWords(declared, { variant = false } = {}) {
    if (!declared || !declared.round) return null;
    const note = variant ? "; declared at the part's defaults, and the mesh drawn is a variant" : "";
    if (!declared.match) return `declared: none of its ${declared.round} round interface${declared.round === 1 ? "" : "s"} lies on this axis, this way round${note}`;
    const d = declared.match;
    const apart = Math.abs(d.apart) < 0.005 ? "the same" : `${mmText(Math.abs(d.apart))} ${d.apart > 0 ? "wider" : "narrower"}`;
    return `declared: ${d.name}, a ${d.type.replace("_", " ")} ⌀ ${mmText(d.diameter)} (${d.where}; the part's interface, source ${d.source}${d.cite ? `, ${d.cite}` : ""}); the mesh reads ⌀ ${mmText(d.mesh)} there, ${apart}${note}`;
}

export function pairWords({ edge = null, angle = null } = {}) {
    const lines = [];
    if (edge) lines.push(`an edge of the mesh from point 1 to point 2, ${mmText(edge.length)}, ${edge.meet === null ? "along the mesh's open boundary" : `between faces meeting at ${degrees(edge.meet)}`}`);
    if (angle) {
        lines.push(angle.parallel ? `the faces at point 1 and point 2 are parallel, facing ${angle.facing}`
            : `the faces at point 1 and point 2 stand at ${degrees(angle.angle)} to each other (their normals ${degrees(angle.between)} apart)`);
    }
    return lines;
}

// The status line's words for what a first click read: short, so the line no longer than
// Measure's own words wraps no further, and the world above it does not move under a
// second click. The Layers window has the whole reading.
export function featureBrief(f) {
    if (!f) return null;
    if (f.kind === "unknown") return "cannot tell";
    if (f.kind === "flat") return f.wall && f.wall.thickness !== undefined ? `a wall ${mmText(f.wall.thickness)} thick` : "a flat face, no wall behind it";
    return `a ${f.sense} ⌀ ${mmText(f.diameter)} across its vertices`;
}

export function hintAfter(f) {
    if (f && f.kind === "round") return "a flat face reads its wall, a second click the distance";
    if (f && f.kind === "flat") return "a curved face reads its diameter, a second click the distance or the angle";
    return "a curved face reads a diameter, a flat face a wall, a second click the distance";
}

export function readingsOf({ points, selection, selectedKey, nodeOf, envelopeOf, frameOf, pair = {}, declaredOf = () => null }) {
    const lines = [], p = points;
    const at = (q) => q.site.map((v) => v.toFixed(2)).join(", ");
    const named = (q, i) => `point ${i + 1} (${q.kind}) on ${q.key} at ${at(q)} mm`;
    // What the click read under a point, and the round the part declares beside it.
    const under = (q, i) => {
        const words = featureWords(q.feature);
        if (!words) return;
        lines.push(`point ${i + 1} on ${q.key}: ${words}`);
        const declared = declaredWords(declaredOf(q), { variant: q.variant });
        if (declared) lines.push(`point ${i + 1} on ${q.key}, ${declared}`);
    };
    if (p.length === 1) {
        under(p[0], 0);
        lines.push(`${named(p[0], 0)}; click a second point (Escape starts again)`);
    }
    if (p.length === 2) {
        const d = between(p[0].site, p[1].site);
        lines.push(`${mmText(d.length)} between ${named(p[0], 0)} and ${named(p[1], 1)}: dx ${mmText(d.dx)}, dy ${mmText(d.dy)}, dz ${mmText(d.dz)} (site frame; a reading of the model, a ${p.map((q) => q.kind).join(" and a ")} point)`);
        lines.push(...pairWords(pair));
        const [a, b] = p.map((q) => envelopeOf(nodeOf(q.key)));
        if (p[0].key !== p[1].key && a && b) {
            const g = gapBetween(a, b);
            const word = g.overlap ? "overlap" : g.touching ? "touching" : mmText(g.gap);
            lines.push(`gap between ${p[0].key} and ${p[1].key}: ${word} (clear distance between their declared bounds`
                + `${g.overlap ? "; they share volume" : ""}; along x ${mmText(g.axes.x)}, y ${mmText(g.axes.y)}, z ${mmText(g.axes.z)}, negative where they run into each other)`);
        }
        under(p[1], 1);
        under(p[0], 0);
    }
    if (selection) {
        const { key, node, size, source } = selection;
        const sized = (b) => ["x", "y", "z"].map((k) => `${k} ${mmText(b[k])}`).join(" × ");
        let line = `${key} measures ${sized(size)} along its own axes (${source})`;
        // The turn to a hundredth of a degree, as a length is to a hundredth of a mm.
        if (node.turn) line += `; turned [${node.turn.map((a) => +a.toFixed(2)).join(", ")}] degrees, its world box ${sized(turnedExtents(size, node.turn))}`;
        lines.push(line);
        // A site's piece is its site drawn small: the reading says so, and how large.
        if (node.site_ref && node.site_size) lines.push(`${key} is the site ${node.site_ref} in miniature, not to scale beside the parts: the site itself measures ${sized({ x: node.site_size[0], y: node.site_size[1], z: node.site_size[2] })} (its pieces' extent)`);
        if (node.footprint && source.startsWith("the drawn mesh")) lines.push(`${key} declares ${sized(ownExtents(node.footprint))} (declared footprint); the mesh above is what is drawn, and the two can differ`);
        const frame = frameOf(key, node);
        if (frame && frame.volume) lines.push(`${key}'s working volume ${frame.volume.map(mmText).join(" × ")} (its frame, from ${frame.volume_from === "controller" ? "the machine's controller" : "the site's declaration"})`);
    } else if (selectedKey && nodeOf(selectedKey)) {
        lines.push(`${selectedKey} is not drawn here, so there is nothing of it to measure`);
    }
    return lines;
}

/* The measurement layer, given the viewer's pieces:
 *   scope                 the pick scope, whose Measure layer shown is the mode
 *   scene(), camera(), canvas()   the world's, as they are now
 *   pick(event)           what is drawn under the pointer, nearest first: the one pick path
 *   nodeOf(key), meshOf(key)      a piece's node and its drawn mesh
 *   selected()            the selection's key
 *   envelopeOf(node)      a node's bounds, or its pieces' together
 *   frameOf(key, node)    a machine's frame
 *   fallbackColour        the colour drawn where the layer has none
 *   dispose(object)       an object's GPU buffers let go, and those under it
 *   setStatus(words, kind), invalidate(), refresh()   the status line, a frame asked for,
 *                         and the Layers window's rows drawn again
 *   raycaster()           the ray the last pick cast, to tell which of a machine's pieces a
 *                         face under it is
 *   interfacesOf(part)    a part's declared interfaces (GET /parts/{name}/interfaces), or null
 * Answers the layer's state -- points ({ site, kind, key, at, feature, ... }), group, lines,
 * and what is drawn of it -- with what it does. */
export function mountMeasureWorld({ scope, scene, camera, canvas, pick, nodeOf, meshOf, selected, envelopeOf, frameOf, fallbackColour, dispose, setStatus, invalidate, refresh, raycaster = () => null, interfacesOf = () => null }) {
    const m = { points: [], group: null, lines: [], pending: false, say: false, rods: [], labels: [], status: null };
    const shapes = new WeakMap();   // a geometry, read as measure_features reads a mesh
    const declared = new Map();     // a part's interfaces: { done, interfaces }

    const on = () => scope.isShown(MEASURE);

    // How many millimetres a pixel of the canvas spans at a point of the world.
    const perPixel = (at) => {
        const cam = camera(), h = canvas().clientHeight || 1;
        return (2 * Math.tan((cam.fov * Math.PI) / 360) * at.distanceTo(cam.position)) / h;
    };

    function click(event) {
        const hit = pick(event).find((h) => nodeOf(h.object.userData.key));
        if (!hit) { setStatus("Measure: no piece under the pointer to measure from", "error"); return; }
        const rect = canvas().getBoundingClientRect();
        const { point, kind, vertex } = snap(hit, event.clientX - rect.left, event.clientY - rect.top);
        let read;
        try {
            read = featureOf(hit);
        } catch (error) {
            // A mesh the arithmetic cannot read leaves the point dropped, and says so.
            console.error(error);
            const why = `the mesh under it could not be read (${error.message})`;
            read = { owner: null, local: { kind: "unknown", why }, feature: { kind: "unknown", why } };
        }
        m.points = pointsAfter(m.points, { site: siteAt(point), kind, key: hit.object.userData.key, at: point, vertex, ...read });
        soon(true);
    }

    function shapeOf(geometry) {
        const position = geometry && geometry.attributes && geometry.attributes.position;
        if (!position) return null;
        let shape = shapes.get(geometry);
        if (!shape) {
            shape = meshFrom(position.array, geometry.index ? geometry.index.array : null);
            shapes.set(geometry, shape);
        }
        return shape;
    }

    // The mesh whose face the hit is: the piece hit, or of a machine drawn as its pieces the
    // one the same ray meets at that face and distance; null where none or more than one is.
    function ownerOf(hit) {
        const object = hit.object, moving = object.userData.kinematics && object.userData.kinematics.pieces;
        if (!moving || !moving.length) return object;
        const ray = raycaster();
        if (!ray) return null;
        const found = [object, ...moving].filter((candidate) => {
            const met = [];
            THREE.Mesh.prototype.raycast.call(candidate, ray, met);
            return met.some((h) => h.faceIndex === hit.faceIndex && Math.abs(h.distance - hit.distance) < 1e-6);
        });
        return found.length === 1 ? found[0] : null;
    }

    // What the click read under it, in its mesh's own frame (`local`, for drawing) and as the
    // reading says it (`feature`: a round in its part's own frame where the mesh says where
    // its STL's box stood).
    function featureOf(hit) {
        const unknown = (why, owner = null) => ({ owner, local: { kind: "unknown", why }, feature: { kind: "unknown", why } });
        const owner = ownerOf(hit);
        if (!owner) return unknown("a machine drawn as its pieces, and which piece the face under the click is could not be told");
        if (owner.userData.isPlaceholder) return unknown("a stand-in box is drawn here, not the part's mesh: there is no shape of it to fit", owner);
        if (owner.userData.isDot) return unknown("it is drawn as a dot here, not as its mesh", owner);
        const shape = shapeOf(owner.geometry);
        if (!shape || !Number.isInteger(hit.faceIndex)) return unknown("the face under the click is not a mesh's", owner);
        owner.updateWorldMatrix(true, false);
        const localPoint = owner.worldToLocal(hit.point.clone());
        const pixel = perPixel(hit.point) / Math.max(1e-9, Math.abs(owner.getWorldScale(new THREE.Vector3()).x));
        const local = featureAt(shape, hit.faceIndex, [localPoint.x, localPoint.y, localPoint.z], { pixel });
        const from = owner.userData.centredFrom;
        const feature = local.kind === "round" && from ? { ...inPartFrame(local, from), frame: "the part's own frame" } : local;
        return { owner, local, feature, localPoint, variant: !!owner.userData.drawnFromVariant };
    }

    // The round the part declares on the same axis, once its interfaces are in: asked for
    // the first time a round of it is read, and the readings written again when they come.
    function declaredOf(q) {
        const node = nodeOf(q.key), f = q.feature;
        if (!f || f.kind !== "round" || f.frame !== "the part's own frame" || !node || !node.part_ref) return null;
        const ref = node.part_ref;
        const entry = declared.get(ref);
        if (!entry) {
            declared.set(ref, { done: false });
            Promise.resolve(interfacesOf(ref)).catch(() => null).then((interfaces) => {
                declared.set(ref, { done: true, interfaces: Array.isArray(interfaces) ? interfaces : [] });
                soon(false);
            });
            return null;
        }
        return entry.done ? declaredOn(f, entry.interfaces) : null;
    }

    // An edge between two vertices of one mesh, and the angle of two flat faces.
    function pairOf() {
        const pair = {};
        if (m.points.length !== 2) return pair;
        const [a, b] = m.points;
        if (a.kind === "vertex" && b.kind === "vertex" && a.owner && a.owner === b.owner && a.vertex != null && b.vertex != null) {
            const shape = shapeOf(a.owner.geometry);
            if (shape) pair.edge = edgeBetween(shape, a.vertex, b.vertex);
        }
        if (a.local && b.local && a.local.kind === "flat" && b.local.kind === "flat" && a.local.normal && b.local.normal) {
            const n = (q) => { const v = new THREE.Vector3(...q.local.normal).transformDirection(q.owner.matrixWorld); return [v.x, v.y, v.z]; };
            pair.angle = faceAngle(n(a), n(b));
        }
        return pair;
    }

    // The vertex of the face hit nearest the pointer, in the world, when one is near
    // enough; a mesh drawn as moving pieces is not snapped (its faces are a piece's).
    function snap(hit, px, py) {
        const geometry = hit.object.geometry, position = geometry?.attributes?.position;
        if (!hit.face || !position || hit.object.userData.kinematics) return { point: hit.point.clone(), kind: "surface" };
        const w = canvas().clientWidth, h = canvas().clientHeight;
        const corners = [hit.face.a, hit.face.b, hit.face.c].map((i) => {
            const v = new THREE.Vector3().fromBufferAttribute(position, i).applyMatrix4(hit.object.matrixWorld);
            const s = v.clone().project(camera());
            return { v, sx: ((s.x + 1) / 2) * w, sy: ((1 - s.y) / 2) * h };
        });
        const near = nearestWithin(corners.map((c, k) => ({ ...c, i: [hit.face.a, hit.face.b, hit.face.c][k] })), px, py, SNAP_PX);
        return near ? { point: near.v, kind: "vertex", vertex: near.i } : { point: hit.point.clone(), kind: "surface", vertex: null };
    }

    // Escape: the points let go. False when there were none.
    function clear() {
        if (!on() || !m.points.length) return false;
        m.points = [];
        soon(false);
        setStatus("Measure: the points let go (Escape); click to drop a first", "success");
        return true;
    }

    // Redrawn, read and mirrored once, after whatever changed it has all happened; `say`:
    // the reading is also said on the status line.
    function soon(say) {
        m.say = m.say || say;
        if (m.pending) return;
        m.pending = true;
        queueMicrotask(() => {
            m.pending = false;
            const said = m.say;
            m.say = false;
            draw();
            if (said && on() && m.lines.length) setStatus(`Measure: ${m.status || m.lines[0]}`, "success");
        });
    }

    // The selected piece's own axes: the drawn mesh's box along them, corner and edges in
    // the world, with where the size comes from; null when nothing is drawn for it.
    function selection() {
        const key = selected(), node = nodeOf(key), mesh = meshOf(key);
        if (!node || !mesh || mesh.userData.isDot) return null;
        const geometry = mesh.geometry;
        if (!geometry.boundingBox) geometry.computeBoundingBox();
        // A machine drawn as its pieces measures all of them: the moving ones hang from the
        // still one, in its frame, wherever its tool has them now.
        const box = geometry.boundingBox.clone();
        const moving = (mesh.userData.kinematics && mesh.userData.kinematics.pieces) || [];
        for (const piece of moving) {
            if (!piece.geometry.boundingBox) piece.geometry.computeBoundingBox();
            piece.updateMatrix();
            box.union(piece.geometry.boundingBox.clone().applyMatrix4(piece.matrix));
        }
        mesh.updateWorldMatrix(true, false);
        const sceneSize = [0, 1, 2].map((i) => (box.max.getComponent(i) - box.min.getComponent(i)) * Math.abs(mesh.scale.getComponent(i)));
        const source = sourceOf({ placeholder: mesh.userData.isPlaceholder, moving: moving.length, footprint: node.footprint, envelope: !node.footprint && envelopeOf(node) });
        const corner = box.min.clone().applyMatrix4(mesh.matrixWorld);
        const edges = [0, 1, 2].map((i) => {
            const end = box.min.clone();
            end.setComponent(i, box.max.getComponent(i));
            return { from: corner, to: end.applyMatrix4(mesh.matrixWorld), mm: sceneSize[i], letter: ["x", "z", "y"][i] };
        });
        return { key, node, edges, source, size: sizeFromSceneBox(sceneSize) };
    }

    const readings = (sel) => readingsOf({ points: m.points, selection: sel, selectedKey: selected(), nodeOf, envelopeOf, frameOf, pair: pairOf(), declaredOf });

    // The dimension lines on the selection, the points and the line between them, each
    // number labelled with its source; and the readings, mirrored in Layers.
    function draw() {
        if (m.group) { scene().remove(m.group); dispose(m.group); m.group = null; }
        m.lines = [];
        m.rods = [];
        m.labels = [];
        m.status = null;
        if (on()) {
            const sel = selected() ? selection() : null;
            const group = new THREE.Group();
            const colour = layerColour(MEASURE, fallbackColour);
            // A line a few pixels thick at any distance: a rod, its thickness set each frame
            // (place), with a point at each end.
            const rod = (a, b) => {
                const r = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 8, 1, true),
                    new THREE.MeshBasicMaterial({ color: colour, depthTest: false }));
                r.position.copy(a).lerp(b, 0.5);
                r.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
                r.userData.span = a.distanceTo(b);
                group.add(r);
                m.rods.push(r);
            };
            const line = (a, b) => {
                rod(a, b);
                group.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints([a, b]),
                    new THREE.PointsMaterial({ color: colour, size: END_PX, sizeAttenuation: false, depthTest: false })));
            };
            // A label on a dark ground, its text in the layer's colour, the size of the page's
            // own text whatever the distance; where it stands is place's, past the far end of
            // its line.
            const label = (text, from, to) => {
                const board = document.createElement("canvas");
                const ctx = board.getContext("2d");
                const font = `600 ${LABEL_PX * 2}px sans-serif`;
                ctx.font = font;
                board.width = Math.ceil(ctx.measureText(text).width) + 20;
                board.height = LABEL_PX * 2 + 14;
                ctx.font = font;
                ctx.fillStyle = "rgba(16,18,16,0.88)"; ctx.fillRect(0, 0, board.width, board.height);
                ctx.strokeStyle = layerHex(MEASURE) || "#ffffff"; ctx.lineWidth = 2; ctx.strokeRect(1, 1, board.width - 2, board.height - 2);
                ctx.fillStyle = layerHex(MEASURE) || "#ffffff"; ctx.textBaseline = "middle"; ctx.fillText(text, 10, board.height / 2 + 1);
                const texture = new THREE.CanvasTexture(board);
                texture.colorSpace = THREE.SRGBColorSpace;
                const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false, sizeAttenuation: false }));
                sprite.userData = { from: from.clone(), to: to.clone(), w: board.width / 2, h: board.height / 2 };
                group.add(sprite);
                m.labels.push(sprite);
            };
            if (sel) {
                const token = tokenOf(sel.source);
                for (const e of sel.edges) {
                    line(e.from, e.to);
                    label(`${e.letter} ${mmText(e.mm)} · ${token}`, e.from, e.to);
                }
            }
            const p = m.points;
            if (p.length) {
                group.add(new THREE.Points(
                    new THREE.BufferGeometry().setFromPoints(p.map((q) => q.at)),
                    new THREE.PointsMaterial({ color: colour, size: 9, sizeAttenuation: false, depthTest: false })));
            }
            const pair = pairOf();
            if (p.length === 2) {
                line(p[0].at, p[1].at);
                label(`${pair.edge ? "edge " : ""}${mmText(between(p[0].site, p[1].site).length)} · ${p.map((q) => q.kind).join(", ")}`, p[0].at, p[1].at);
            }
            // What each click read under it: a round's circle and the line across it at the
            // click, a wall's line through to the face behind, a gap's across to the face
            // that faces it; each labelled, in the mesh's own frame turned into the world.
            for (const q of p) {
                const f = q.local, o = q.owner;
                if (!f || !o || !q.localPoint) continue;
                const world = (v) => o.localToWorld(new THREE.Vector3(v[0], v[1], v[2]));
                const lp = [q.localPoint.x, q.localPoint.y, q.localPoint.z];
                if (f.kind === "round") {
                    const ax = new THREE.Vector3(...f.axis), mid = new THREE.Vector3(...f.middle), click = new THREE.Vector3(...lp);
                    const t = click.clone().sub(mid).dot(ax);
                    const centre = mid.clone().addScaledVector(ax, t), R = f.radius + f.slope * t;
                    const d = click.clone().sub(centre).normalize();
                    if (!(d.lengthSq() > 0.5)) d.set(...f.across);
                    const e = ax.clone().cross(d);
                    const at = (k) => {
                        const th = (2 * Math.PI * k) / CIRCLE_RODS;
                        return world(centre.clone().addScaledVector(d, R * Math.cos(th)).addScaledVector(e, R * Math.sin(th)).toArray());
                    };
                    for (let k = 0; k < CIRCLE_RODS; k++) rod(at(k), at(k + 1));
                    const [near, far] = [world(centre.clone().addScaledVector(d, -R).toArray()), world(centre.clone().addScaledVector(d, R).toArray())];
                    line(near, far);
                    label(`⌀ ${mmText(2 * R)} · ${f.sense} · mesh`, near, far);
                } else if (f.kind === "flat") {
                    if (f.wall && f.wall.thickness !== undefined) {
                        line(world(f.wall.far), world(lp));
                        label(`wall ${mmText(f.wall.thickness)} · mesh`, world(f.wall.far), world(lp));
                    }
                    if (f.gap) {
                        line(world(lp), world(f.gap.far));
                        label(`gap ${mmText(f.gap.width)} · mesh`, world(lp), world(f.gap.far));
                    }
                }
            }
            group.traverse((o) => { o.renderOrder = 10; o.raycast = () => {}; });  // seen over the world, never hit
            scene().add(group);
            m.group = group;
            m.lines = readings(sel);
            // After a first click the status line says what it read and how to read the rest.
            if (p.length === 1 && p[0].feature) {
                const f = p[0].feature;
                m.status = `point 1 on ${p[0].key}: ${featureBrief(f)}; ${hintAfter(f)} (${f.kind === "unknown" ? "why" : "the rest"} in Layers)`;
            }
            place();
        }
        refresh();
        invalidate();
    }

    // Each frame, before it is drawn: the measurement's rods ROD_PX thick on screen, and its
    // labels past the far ends of their lines, clear of each other (measure.js's layLabels),
    // the size of the page's text.
    function place() {
        if (!m.group) return;
        const cam = camera(), h = canvas().clientHeight || 1, w = canvas().clientWidth || 1;
        for (const rod of m.rods) {
            const r = (ROD_PX / 2) * perPixel(rod.position);
            rod.scale.set(r, rod.userData.span, r);
        }
        const screen = (v) => { const s = v.clone().project(cam); return { x: ((s.x + 1) / 2) * w, y: ((1 - s.y) / 2) * h, z: s.z }; };
        const ends = m.labels.map((sprite) => {
            const a = screen(sprite.userData.from), b = screen(sprite.userData.to);
            return { x: b.x, y: b.y, dx: b.x - a.x, dy: b.y - a.y, w: sprite.userData.w, h: sprite.userData.h, z: b.z };
        });
        const laid = layLabels(ends, { width: w, height: h, gap: 6 });
        const k = (2 * Math.tan((cam.fov * Math.PI) / 360)) / h;
        m.labels.forEach((sprite, i) => {
            const at = laid[i], z = Math.min(0.999, ends[i].z);
            sprite.position.copy(new THREE.Vector3((at.cx / w) * 2 - 1, 1 - (at.cy / h) * 2, z).unproject(cam));
            sprite.scale.set(sprite.userData.w * k, sprite.userData.h * k, 1);
        });
    }

    // The layers were put again: a measurement not shown lets its points go, and is drawn
    // as it now is.
    function layersApplied() {
        if (!on()) m.points = [];
        soon(false);
    }

    return Object.assign(m, { on, click, snap, clear, soon, selection, readings, draw, place, layersApplied });
}
