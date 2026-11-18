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
 *   sourceOf({ placeholder, moving, footprint, envelope })   where a selection's size comes
 *                                  from, in the words its reading says
 *   tokenOf(source)                the word a dimension line's label says of that source
 *   pointsAfter(points, point)     the points once a click drops another: a third starts again
 *   readingsOf({ points, selection, selectedKey, nodeOf, envelopeOf, frameOf })   the
 *                                  readings as text, most recent first: the points, then
 *                                  the selection
 *   mountMeasureWorld(world)       the layer's state ({ points, group, lines, ... }) and what
 *                                  it does: on, click, snap, clear, soon, selection,
 *                                  readings, draw, place, layersApplied
 */

import * as THREE from "three";
import { MEASURE } from "/static/pick_scope.js";
import { siteAt } from "/static/frames.js";
import { layerColour, layerHex } from "/static/layer_colours.js";
import { ownExtents, sizeFromSceneBox, turnedExtents, between, gap as gapBetween, nearestWithin, length as mmText, layLabels } from "/static/measure.js";

export const SNAP_PX = 12;      // a measured point snaps to a vertex this near the pointer
// A measurement's lines, the points at their ends and its labels' text, in pixels on screen
// whatever the distance: drawn thick enough to read over a mesh.
export const ROD_PX = 3;
export const END_PX = 7;
export const LABEL_PX = 13;

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

export function readingsOf({ points, selection, selectedKey, nodeOf, envelopeOf, frameOf }) {
    const lines = [], p = points;
    const at = (q) => q.site.map((v) => v.toFixed(2)).join(", ");
    const named = (q, i) => `point ${i + 1} (${q.kind}) on ${q.key} at ${at(q)} mm`;
    if (p.length === 1) lines.push(`${named(p[0], 0)}; click a second point (Escape starts again)`);
    if (p.length === 2) {
        const d = between(p[0].site, p[1].site);
        lines.push(`${mmText(d.length)} between ${named(p[0], 0)} and ${named(p[1], 1)}: dx ${mmText(d.dx)}, dy ${mmText(d.dy)}, dz ${mmText(d.dz)} (site frame; a reading of the model, a ${p.map((q) => q.kind).join(" and a ")} point)`);
        const [a, b] = p.map((q) => envelopeOf(nodeOf(q.key)));
        if (p[0].key !== p[1].key && a && b) {
            const g = gapBetween(a, b);
            const word = g.overlap ? "overlap" : g.touching ? "touching" : mmText(g.gap);
            lines.push(`gap between ${p[0].key} and ${p[1].key}: ${word} (clear distance between their declared bounds`
                + `${g.overlap ? "; they share volume" : ""}; along x ${mmText(g.axes.x)}, y ${mmText(g.axes.y)}, z ${mmText(g.axes.z)}, negative where they run into each other)`);
        }
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
 * Answers the layer's state -- points ({ site, kind, key, at }), group, lines, and what is
 * drawn of it -- with what it does. */
export function mountMeasureWorld({ scope, scene, camera, canvas, pick, nodeOf, meshOf, selected, envelopeOf, frameOf, fallbackColour, dispose, setStatus, invalidate, refresh }) {
    const m = { points: [], group: null, lines: [], pending: false, say: false, rods: [], labels: [] };

    const on = () => scope.isShown(MEASURE);

    function click(event) {
        const hit = pick(event).find((h) => nodeOf(h.object.userData.key));
        if (!hit) { setStatus("Measure: no piece under the pointer to measure from", "error"); return; }
        const rect = canvas().getBoundingClientRect();
        const { point, kind } = snap(hit, event.clientX - rect.left, event.clientY - rect.top);
        m.points = pointsAfter(m.points, { site: siteAt(point), kind, key: hit.object.userData.key, at: point });
        soon(true);
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
        const near = nearestWithin(corners, px, py, SNAP_PX);
        return near ? { point: near.v, kind: "vertex" } : { point: hit.point.clone(), kind: "surface" };
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
            if (said && on() && m.lines.length) setStatus(`Measure: ${m.lines[0]}`, "success");
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

    const readings = (sel) => readingsOf({ points: m.points, selection: sel, selectedKey: selected(), nodeOf, envelopeOf, frameOf });

    // The dimension lines on the selection, the points and the line between them, each
    // number labelled with its source; and the readings, mirrored in Layers.
    function draw() {
        if (m.group) { scene().remove(m.group); dispose(m.group); m.group = null; }
        m.lines = [];
        m.rods = [];
        m.labels = [];
        if (on()) {
            const sel = selected() ? selection() : null;
            const group = new THREE.Group();
            const colour = layerColour(MEASURE, fallbackColour);
            // A line a few pixels thick at any distance: a rod, its thickness set each frame
            // (place), with a point at each end.
            const line = (a, b) => {
                const rod = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 8, 1, true),
                    new THREE.MeshBasicMaterial({ color: colour, depthTest: false }));
                rod.position.copy(a).lerp(b, 0.5);
                rod.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
                rod.userData.span = a.distanceTo(b);
                group.add(rod);
                m.rods.push(rod);
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
            if (p.length === 2) {
                line(p[0].at, p[1].at);
                label(`${mmText(between(p[0].site, p[1].site).length)} · ${p.map((q) => q.kind).join(", ")}`, p[0].at, p[1].at);
            }
            group.traverse((o) => { o.renderOrder = 10; o.raycast = () => {}; });  // seen over the world, never hit
            scene().add(group);
            m.group = group;
            m.lines = readings(sel);
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
        const perPixel = (at) => (2 * Math.tan((cam.fov * Math.PI) / 360) * at.distanceTo(cam.position)) / h;
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
