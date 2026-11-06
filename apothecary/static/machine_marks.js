/* What a printer wears in a three.js scene, wherever that scene is: the
 * build volume as a wire box on the printer's base, the bed plane, a nozzle
 * marker at the position the board last reported, and -- when there is a
 * bed reading -- the mesh as a relief over the bed. A router wears the same:
 * its working area, its table and its tool, placed by the position the page
 * computes from its controller's (toolPosition below).
 *
 * One group, in the printer's own frame (apothecary's z-up, relative to the
 * printer's origin); the caller places it: the world scene at the printer's
 * world position, the monitor's small scene at its origin. The marker moves
 * rather than jumps: setPosition sets a target and tick() moves the drawn
 * position a fraction of the way each frame, so a poll tweens it and a jog
 * sent from a page moves it ahead of the poll that confirms it.
 *
 * And the board's badge (makeBoardBadge, sayBoard): ⚡ at the board's own spot,
 * its words what the board model says of it, on the anchors layer's badges.
 */

import * as THREE from "three";
import { esc } from "/static/board_text.js";

export const VOLUME_COLOR = 0x6fb3e8;
export const NOZZLE_COLOR = 0xff8080;
export const BED_COLOR = 0x2a302a;
// What each kind of move is drawn in (apothecary/preview/process.py names them): what
// makes the part stands out, a move through the air stays back. The page's ok, warn and
// bad, as colours three.js can take (static/tokens.css).
const MOVE_COLORS = { extrude: 0x6fdb75, cut: 0xffcc66, plunge: 0xff8080, travel: 0x4a564a, rapid: 0x4a564a };
const MESH_LOW = [0x6f, 0xb3, 0xe8];   // the bed card's blue, below the mean
const MESH_HIGH = [0xe8, 0xb0, 0x4a];  // its amber, above
const MESH_INSET = 10;                 // Marlin's default MESH_INSET, mm from the probeable edge

// apothecary (x, y, z) z-up -> three.js (x, z, -y) y-up: a quarter turn about x, as the
// viewer's sceneAt turns it.
export const toScene = (p) => new THREE.Vector3(p.x, p.z, -p.y);

// Where a G-code file's (0, 0, 0) stands in the machine's volume: a printer's file is
// in the bed's coordinates; a router's counts from the work zero, which the controller
// reports as an offset from its machine coordinates (mpos = wpos + wco, and the volume
// at mpos + travel, as below).
export function fileOrigin(st, volume) {
    if (!st || st.dialect !== "grbl") return { x: 0, y: 0, z: 0 };
    const [vx, vy, vz] = volume || [0, 0, 0];
    const w = st.work_offset || { x: 0, y: 0, z: 0 };
    return { x: w.x + vx, y: w.y + vy, z: w.z + vz };
}

// Where a poll puts the tool in the machine's volume: a printer's position as it
// is; a router's from the machine position its controller reports, since a Grbl
// machine homed to its maximum switches counts down from that corner, so the tool
// is at mpos + travel. `volume` is the working area; null for no position.
export function toolPosition(st, volume) {
    const p = st && st.position;
    if (!p) return null;
    if (st.dialect !== "grbl") return p;
    const [vx, vy, vz] = volume || [0, 0, 0];
    return { x: p.x + vx, y: p.y + vy, z: p.z + vz };
}

/* Where the mesh points lie, in bed coordinates. Marlin prints the grid
 * without its positions; the probeable rectangle is the bed less what the
 * probe's offset from the nozzle puts out of reach, and the default mesh
 * sits MESH_INSET inside that. An estimate, and said to be one. */
export function meshBounds(volume, probeOffset, inset = MESH_INSET) {
    const [sx, sy] = volume;
    const ox = probeOffset ? probeOffset.x || 0 : 0;
    const oy = probeOffset ? probeOffset.y || 0 : 0;
    return {
        min: { x: Math.max(0, ox) + inset, y: Math.max(0, oy) + inset },
        max: { x: Math.min(sx, sx + ox) - inset, y: Math.min(sy, sy + oy) - inset },
    };
}

/* How much to stretch the mesh's Z so its shape reads: a flat bed stays
 * nearly flat, a bad one is unmistakable, and the number is shown. */
export function meshExaggeration(range) {
    if (!range || range <= 0) return 10;
    return Math.round(Math.min(50, Math.max(10, 40 / range)));
}

/* `printer` is what GET /firmware/printers/where answers for the printer:
 * footprint, build_volume, build_origin or base_height (position is the
 * caller's to apply). `drawVolume: false` leaves the wire box to a scene
 * that already has one. */
export function makeMachineMarks(printer, { drawVolume = true, onNote } = {}) {
    const note = (text, key) => { if (onNote) onNote(text, key); };
    const group = new THREE.Group();
    const hasVolume = !!(printer && printer.build_volume && (printer.footprint || printer.build_origin));
    let volumeOrigin = { x: 0, y: 0, z: 0 };
    if (hasVolume) {
        const [vx, vy, vz] = printer.build_volume;
        if (printer.build_origin) {
            // A machine drawn as it is says where its volume starts.
            const [ox, oy, oz] = printer.build_origin;
            volumeOrigin = { x: ox, y: oy, z: oz };
        } else {
            // A block: the build volume sits on the printer's base and centred
            // on its footprint -- the site's printers say how big it is, not where.
            const fp = printer.footprint;
            const fw = fp.max[0] - fp.min[0], fd = fp.max[1] - fp.min[1];
            volumeOrigin = { x: fp.min[0] + (fw - vx) / 2, y: fp.min[1] + (fd - vy) / 2, z: fp.min[2] + (printer.base_height || 0) };
        }
        if (drawVolume) {
            const box = new THREE.BoxGeometry(vx, vz, vy);
            const volume = new THREE.LineSegments(new THREE.EdgesGeometry(box), new THREE.LineBasicMaterial({ color: VOLUME_COLOR, transparent: true, opacity: 0.6 }));
            box.dispose();
            volume.position.copy(toScene({ x: volumeOrigin.x + vx / 2, y: volumeOrigin.y + vy / 2, z: volumeOrigin.z + vz / 2 }));
            group.add(volume);
        }
        const bed = new THREE.Mesh(new THREE.PlaneGeometry(vx, vy), new THREE.MeshBasicMaterial({ color: BED_COLOR, side: THREE.DoubleSide, transparent: true, opacity: 0.5 }));
        bed.rotation.x = -Math.PI / 2;
        bed.position.copy(toScene({ x: volumeOrigin.x + vx / 2, y: volumeOrigin.y + vy / 2, z: volumeOrigin.z + 0.2 }));
        group.add(bed);
    }

    // The nozzle: a small cone pointing down, plus a crosshair on the bed.
    const nozzle = new THREE.Group();
    const cone = new THREE.Mesh(new THREE.ConeGeometry(4, 14, 16), new THREE.MeshStandardMaterial({ color: NOZZLE_COLOR, emissive: 0x552222 }));
    cone.rotation.x = Math.PI;
    cone.position.y = 7;
    nozzle.add(cone);
    const cross = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(-12, 0, 0), new THREE.Vector3(12, 0, 0),
            new THREE.Vector3(0, 0, -12), new THREE.Vector3(0, 0, 12),
        ]),
        new THREE.LineBasicMaterial({ color: NOZZLE_COLOR, transparent: true, opacity: 0.8 }),
    );
    nozzle.add(cross);
    group.add(nozzle);

    // `current` is what is drawn, `target` what was last asked for; each
    // tick moves current a fraction of the way -- a tween that finishes in
    // about a third of a second whatever the distance.
    const current = { x: 0, y: 0, z: 0 };
    const target = { x: 0, y: 0, z: 0 };
    function place() {
        nozzle.position.copy(toScene({ x: volumeOrigin.x + current.x, y: volumeOrigin.y + current.y, z: volumeOrigin.z + current.z }));
        cross.position.y = -current.z; // the crosshair stays on the bed
    }
    place();

    // The bed reading, drawn as a height field over the probed area, and
    // replaced whenever the page shows another reading.
    let meshGroup = null;
    let meshDrawn = null;
    function clearMesh() {
        if (meshGroup) {
            group.remove(meshGroup);
            meshGroup.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
            meshGroup = null;
        }
        meshDrawn = null;
    }
    function setMesh(record) {
        clearMesh();
        const rows = record && record.mesh;
        if (!rows || !rows.length || !rows[0].length || !hasVolume) return;
        const nRows = rows.length, nCols = rows[0].length;
        const flat = rows.flat();
        const lo = Math.min(...flat), hi = Math.max(...flat);
        const range = hi - lo;
        const exaggeration = meshExaggeration(range);
        const bounds = meshBounds(printer.build_volume, record.probe_offset);
        const stepX = nCols > 1 ? (bounds.max.x - bounds.min.x) / (nCols - 1) : 0;
        const stepY = nRows > 1 ? (bounds.max.y - bounds.min.y) / (nRows - 1) : 0;
        // Vertices in the printer's frame: the bed at the volume's floor, the
        // lowest point of the mesh resting on it, each other point lifted by
        // its height above that, stretched -- a relief of the bed.
        const positions = new Float32Array(nRows * nCols * 3);
        const colors = new Float32Array(nRows * nCols * 3);
        for (let j = 0; j < nRows; j++) {
            for (let i = 0; i < nCols; i++) {
                const v = rows[j][i];
                const p = toScene({
                    x: volumeOrigin.x + bounds.min.x + i * stepX,
                    y: volumeOrigin.y + bounds.min.y + j * stepY,
                    z: volumeOrigin.z + 0.4 + (v - lo) * exaggeration,
                });
                const k = (j * nCols + i) * 3;
                positions[k] = p.x; positions[k + 1] = p.y; positions[k + 2] = p.z;
                const t = range > 0 ? (v - lo) / range : 0.5;
                for (let c = 0; c < 3; c++) colors[k + c] = (MESH_LOW[c] + (MESH_HIGH[c] - MESH_LOW[c]) * t) / 255;
            }
        }
        const index = [];
        for (let j = 0; j + 1 < nRows; j++) {
            for (let i = 0; i + 1 < nCols; i++) {
                const a = j * nCols + i, b = a + 1, c = a + nCols, d = c + 1;
                index.push(a, c, b, b, c, d);
            }
        }
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
        geometry.setIndex(index);
        geometry.computeVertexNormals();
        meshGroup = new THREE.Group();
        meshGroup.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, transparent: true, opacity: 0.75, roughness: 0.9 })));
        meshGroup.add(new THREE.LineSegments(new THREE.WireframeGeometry(geometry), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.25 })));
        // A post at each corner from the bed to the surface, so height reads against the bed.
        const posts = [];
        const bedY = toScene({ x: 0, y: 0, z: volumeOrigin.z }).y;
        for (const [j, i] of [[0, 0], [0, nCols - 1], [nRows - 1, 0], [nRows - 1, nCols - 1]]) {
            const k = (j * nCols + i) * 3;
            posts.push(new THREE.Vector3(positions[k], bedY, positions[k + 2]), new THREE.Vector3(positions[k], positions[k + 1], positions[k + 2]));
        }
        meshGroup.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(posts), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 })));
        group.add(meshGroup);
        meshDrawn = {
            rows: nRows, cols: nCols, range, exaggeration, bounds,
            z: { min: volumeOrigin.z + 0.4, max: volumeOrigin.z + 0.4 + range * exaggeration },
            record_id: record.id || null,
        };
        note(`mesh ${range.toFixed(3)} mm range, drawn ×${exaggeration}`, "mesh");
    }

    // A G-code file's path, from the preview's segments, in the file's coordinates:
    // one set of lines, of which the first `upto` segments are drawn, placed by where
    // the file's zero stands in the volume. Never in the way of a click on the machine.
    let path = null, pathOf = null, pathOrigin = null;
    function clearPath() {
        if (!path) return;
        group.remove(path);
        path.geometry.dispose();
        path.material.dispose();
        path = pathOf = pathOrigin = null;
    }
    function setToolpath(preview, { upto = null, origin = null } = {}) {
        if (!preview) { clearPath(); return; }
        if (preview !== pathOf) {
            clearPath();
            const count = preview.kind_of.length;
            const positions = new Float32Array(count * 6), colors = new Float32Array(count * 6);
            const palette = preview.kinds.map((kind) => new THREE.Color(MOVE_COLORS[kind]));
            for (let i = 0; i < count; i++) {
                const at = i * 6, color = palette[preview.kind_of[i]];
                for (const v of [0, 3]) {
                    const scene = toScene({ x: preview.points[at + v], y: preview.points[at + v + 1], z: preview.points[at + v + 2] });
                    positions.set([scene.x, scene.y, scene.z], at + v);
                    colors.set([color.r, color.g, color.b], at + v);
                }
            }
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
            geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
            path = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true }));
            path.raycast = () => {};
            path.renderOrder = 2;
            group.add(path);
            pathOf = preview;
        }
        if (upto !== null) path.geometry.setDrawRange(0, upto * 2);
        if (origin) {
            pathOrigin = { ...origin };
            path.position.copy(toScene({ x: volumeOrigin.x + origin.x, y: volumeOrigin.y + origin.y, z: volumeOrigin.z + origin.z }));
        }
    }

    return {
        group,
        volumeOrigin,
        setToolpath,
        // What is drawn of a file's path: for the page's status, and its tests.
        toolpath() {
            if (!path) return null;
            return { segments: pathOf.kind_of.length, drawn: path.geometry.drawRange.count / 2, process: pathOf.process, origin: pathOrigin && { ...pathOrigin } };
        },
        // The whole path's box in the world, where it stands now, for the page to
        // frame; null with no path, or one that moves nothing.
        toolpathBox() {
            if (!path || !pathOf.kind_of.length) return null;
            path.updateWorldMatrix(true, false);
            return new THREE.Box3().setFromObject(path);
        },
        setPosition(p, { immediate = false } = {}) {
            if (!p) return;
            for (const k of ["x", "y", "z"]) if (typeof p[k] === "number") target[k] = p[k];
            if (immediate) { Object.assign(current, target); place(); }
        },
        // A step of the tween, and whether the nozzle moved: within a thousandth of a
        // millimetre it is where it was asked to be, and stays (the page draws only
        // while something moves).
        tick() {
            let moved = false;
            for (const k of ["x", "y", "z"]) {
                const gap = target[k] - current[k];
                if (gap === 0) continue;
                current[k] = Math.abs(gap) < 1e-3 ? target[k] : current[k] + gap * 0.18;
                moved = true;
            }
            if (moved) place();
            return moved;
        },
        position() { return { ...current }; },
        target() { return { ...target }; },
        setMesh,
        mesh() { return meshDrawn ? JSON.parse(JSON.stringify(meshDrawn)) : null; },
        volume() {
            if (!hasVolume) return null;
            const [vx, vy, vz] = printer.build_volume;
            return { min: { ...volumeOrigin }, max: { x: volumeOrigin.x + vx, y: volumeOrigin.y + vy, z: volumeOrigin.z + vz } };
        },
        destroy() {
            clearMesh();
            clearPath();
            group.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
            if (group.parent) group.parent.remove(group);
        },
    };
}

/* A board's badge on the anchors layer (anchors.js): ⚡ at the board's own spot
 * -- `point()`, the top of its node, inside the printer it drives -- and never
 * dimmed by the node it is inside, nor by that node's marks (a group keyed as
 * the node is). Keyed by `key`, the machine it stands for (the printer a board
 * inside drives, else the board's node); the page listens to it. `selected()`
 * opens its words. */
export function makeBoardBadge(anchors, key, boardPath, { point, selected }) {
    const inside = (mesh) => {
        for (let o = mesh; o; o = o.parent) {
            const k = o.userData.key;
            if (k && (k === boardPath || boardPath.startsWith(`${k}.`))) return true;
        }
        return false;
    };
    const badge = anchors.badge(key, point, { selected, ignore: inside });
    badge.dataset.path = key;
    badge.dataset.board = boardPath;
    badge.setAttribute("aria-label", "Select this board and open its Machine");
    return badge;
}

/* What a board's badge says, from the board model's summary (board_text.js): a
 * printer's state, readings and job, a devkit's label and sketch, and under them
 * the board and its port. */
export function sayBoard(anchors, key, sum, device) {
    const badge = anchors.get(key);
    if (!badge) return;
    badge.classList.remove("printing", "offline", "job", "mismatch", "heating");
    let line;
    if (sum.kind === "devkit") {
        line = `${sum.icon} ${esc(device.label)} · <span class="state">${esc(sum.short)}</span>`;
    } else {
        const parts = [`${sum.icon} <span class="state">${esc(sum.state)}</span>`];
        if (sum.readings) parts.push(sum.readings);
        parts.push(...sum.extra.map(esc));
        line = parts.join(" · ");
        if (sum.job) badge.classList.add("job");
    }
    if (sum.cls) badge.classList.add(sum.cls);
    anchors.say(key, { icon: "⚡", words: `<div>${line}</div><div class="sub">${esc(device.port)} — click to open its Machine</div>` });
}
