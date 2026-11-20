/* What a printer wears in a three.js scene, wherever that scene is: the
 * build volume as a wire box on the printer's base, the bed plane, a nozzle
 * marker at the position the board last reported, and -- when there is a
 * bed reading -- the mesh as a relief over the bed. A router wears the same:
 * its working area, its table and its tool, placed by the position the page
 * computes from its controller's (toolPosition below), and its table map as
 * the relief, where the map says its points were probed. A reading is laid
 * over the marks of the kind of machine that took it, by its caller.
 *
 * One group, in the printer's own frame (apothecary's z-up, relative to the
 * printer's origin), laid out by the machine's frame (api.machine_frame, the
 * `frame` GET /firmware/printers/where gives the printer): where its volume
 * starts, how big it is, whether its bed carries Y. The caller places the group
 * at the printer's position in the site. The marker moves rather than jumps:
 * setPosition sets a target and tick() moves the drawn position a fraction of
 * the way each frame, so a poll tweens it and a jog sent from a page moves it
 * ahead of the poll that confirms it. Until a position is known the marker is
 * not drawn, and the bed stands where the part's own axes put it (its
 * kinematics' rest), as the machine's pieces do.
 *
 * And the board's badge (makeBoardBadge, sayBoard): ⚡ at the board's own spot,
 * its words what the board model says of it, on the anchors layer's badges.
 */

import * as THREE from "three";
import { esc } from "/static/board_text.js";
import { toScene } from "/static/frames.js";

export const VOLUME_COLOR = 0x6fb3e8;
export const NOZZLE_COLOR = 0xff8080;
// The nozzle's cone is drawn after the world's meshes, what is seen through them, and the
// measurement (10 to 12).
export const NOZZLE_ORDER = 20;
export const BED_COLOR = 0x2a302a;
// What each kind of move is drawn in (apothecary/preview/process.py names them): what
// makes the part in the page's ok, warn and bad, as colours three.js can take
// (static/tokens.css), and a move through the air in a blue of its own, a step dimmer,
// so it is told from the part at a glance. The Print and Cut card's key reads these.
export const MOVE_COLORS = { extrude: 0x6fdb75, cut: 0xffcc66, plunge: 0xff8080, travel: 0x6c78c4, rapid: 0x6c78c4 };
const MESH_LOW = [0x6f, 0xb3, 0xe8];   // the bed card's blue, below the mean
const MESH_HIGH = [0xe8, 0xb0, 0x4a];  // its amber, above
const MESH_INSET = 10;                 // Marlin's default MESH_INSET, mm from the probeable edge

// apothecary (x, y, z) z-up -> three.js (x, z, -y) y-up (frames.js).
export { toScene };

// Where a G-code file's (0, 0, 0) stands in the machine's volume, or null where that is
// not known. A printer's file is in the bed's coordinates. A router's counts from the
// work zero, which the controller reports as an offset from its machine coordinates
// (mpos = wpos + wco), each axis placed in the volume by the way it homes: one that
// homes to its maximum counts down from there, one that homes to its minimum (the
// AnoleX's X) up. That is the poll's word (`work_origin`, grbl.in_volume), else the
// machine's frame's (api.machine_frame: `homing`, `volume`) with the poll's offset;
// until one of them says, no place -- no path drawn rather than one a travel off.
// `router` is whether the file is a router's, for a machine whose poll has not come.
export function fileOrigin(st, frame = null, { router = !!(st && st.dialect === "grbl") } = {}) {
    if (!router) return { x: 0, y: 0, z: 0 };
    if (st && st.work_origin) return st.work_origin;
    const homing = frame && frame.homing, volume = frame && frame.volume, w = st && st.work_offset;
    if (!homing || !volume || !w) return null;
    const origin = {};
    for (const [i, k] of ["x", "y", "z"].entries()) {
        if (typeof w[k] !== "number" || !["min", "max"].includes(homing[k])) return null;
        origin[k] = w[k] + (homing[k] === "min" ? 0 : volume[i]);
    }
    return origin;
}

// Where a poll puts the tool in the machine's volume: the server's word, which counts
// each axis the way its controller homes it (grbl.in_volume, the frame's `homing`); a
// printer's position as it is. A router's machine position is no place in its volume
// until its controller's settings have said which way each axis homes -- the AnoleX's
// X homes to its minimum, its Y and Z to their maximum -- so null until then: no tool
// drawn rather than one a whole travel off.
export function toolPosition(st) {
    const p = st && st.position;
    if (!p) return null;
    if (st.tool_position) return st.tool_position;
    return st.dialect === "grbl" ? null : p;
}

// The grid on a machine's bed: a line every `pitch` mm of its volume's own X and Y,
// every fifth a shade brighter, over the whole volume from its low corner, so the
// lines read as the machine's millimetres. In the volume's frame: its caller stands
// it at the bed's origin (frames.js volumeToSite).
export function makeBedGrid(volume, pitch = 10) {
    const [vx, vy] = volume;
    const fine = [], bold = [];
    const lines = (span, along) => {
        const n = Math.ceil(span / pitch - 1e-6);
        for (let i = 0; i <= n; i++) {
            const at = Math.min(i * pitch, span);
            (i % 5 ? fine : bold).push(...along(at));
        }
    };
    lines(vx, (x) => [toScene({ x, y: 0, z: 0 }), toScene({ x, y: vy, z: 0 })]);
    lines(vy, (y) => [toScene({ x: 0, y, z: 0 }), toScene({ x: vx, y, z: 0 })]);
    const grid = new THREE.Group();
    grid.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(fine), new THREE.LineBasicMaterial({ color: 0x2a2a2a })));
    grid.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(bold), new THREE.LineBasicMaterial({ color: 0x444444 })));
    grid.userData.pitch = pitch;
    grid.userData.volume = [vx, vy];
    return grid;
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

/* `printer` is what GET /firmware/printers/where answers for the printer; its
 * `frame` (api.machine_frame) is what the marks are laid out by (its position
 * is the caller's to apply). `drawVolume: false` leaves the wire box to a scene
 * that already has one. */
export function makeMachineMarks(printer, { drawVolume = true, onNote } = {}) {
    const note = (text, key) => { if (onNote) onNote(text, key); };
    const group = new THREE.Group();
    // What the bed carries -- its plane, the reading's relief, a file's path -- in a group
    // of its own: on a machine whose bed carries Y (`bed_moves_y`, the Ender's bed and the
    // AnoleX's table), it is the bed that moves along Y, and the tool stands still there.
    const bedGroup = new THREE.Group();
    group.add(bedGroup);
    const frame = (printer && printer.frame) || null;
    const bedMovesY = frame && typeof frame.bed_moves_y === "number" ? frame.bed_moves_y : null;
    const hasVolume = !!frame;
    // Where the volume starts in the printer's frame: the frame's word, whether the
    // node said it (a machine drawn as it is) or it is centred on a block's footprint.
    const volumeOrigin = frame ? { x: frame.origin[0], y: frame.origin[1], z: frame.origin[2] } : { x: 0, y: 0, z: 0 };
    if (hasVolume) {
        const [vx, vy, vz] = frame.volume;
        if (drawVolume) {
            const box = new THREE.BoxGeometry(vx, vz, vy);
            const volume = new THREE.LineSegments(new THREE.EdgesGeometry(box), new THREE.LineBasicMaterial({ color: VOLUME_COLOR, transparent: true, opacity: 0.6 }));
            box.dispose();
            volume.position.copy(toScene({ x: volumeOrigin.x + vx / 2, y: volumeOrigin.y + vy / 2, z: volumeOrigin.z + vz / 2 }));
            bedGroup.add(volume);  // the working volume rides with what carries the work
        }
        const bed = new THREE.Mesh(new THREE.PlaneGeometry(vx, vy), new THREE.MeshBasicMaterial({ color: BED_COLOR, side: THREE.DoubleSide, transparent: true, opacity: 0.5 }));
        bed.rotation.x = -Math.PI / 2;
        bed.position.copy(toScene({ x: volumeOrigin.x + vx / 2, y: volumeOrigin.y + vy / 2, z: volumeOrigin.z + 0.2 }));
        bedGroup.add(bed);
    }

    // The nozzle: a small cone pointing down, plus a crosshair on the bed. The cone stands
    // where the tool's tip is, inside the drawn head that carries it: it is drawn after
    // everything and over it, so the mark (and the ⚡ that stands aside from it) is seen.
    // three.js draws what is seen through (`transparent`) after every solid thing, so the
    // cone is one of those, at full opacity, and the last of them by its order: a bed
    // reading's translucent mesh is drawn before it, not over it.
    const nozzle = new THREE.Group();
    const cone = new THREE.Mesh(new THREE.ConeGeometry(4, 14, 16),
        new THREE.MeshStandardMaterial({ color: NOZZLE_COLOR, emissive: 0x552222, depthTest: false, depthWrite: false, transparent: true }));
    cone.renderOrder = NOZZLE_ORDER;
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
    // The tool's mark, which its machine's board's badge stands aside from (anchors.js).
    nozzle.userData.toolMark = true;
    group.add(nozzle);

    // `current` is what is drawn, `target` what was last asked for; each
    // tick moves current a fraction of the way -- a tween that finishes in
    // about a third of a second whatever the distance. Both start at the part's
    // own axes (its kinematics' rest), where its pieces are drawn, and the marker
    // is not drawn until a position is known (`known`).
    const rest = frame && frame.kinematics && frame.kinematics.rest;
    const current = rest ? { x: rest.x || 0, y: rest.y || 0, z: rest.z || 0 } : { x: 0, y: 0, z: 0 };
    const target = { ...current };
    let known = false;
    nozzle.visible = false;
    function place() {
        // A bed that carries Y is moved so the work's Y under the tool is the poll's.
        const y = bedMovesY === null ? current.y : bedMovesY;
        nozzle.position.copy(toScene({ x: volumeOrigin.x + current.x, y: volumeOrigin.y + y, z: volumeOrigin.z + current.z }));
        if (bedMovesY !== null) bedGroup.position.copy(toScene({ x: 0, y: bedMovesY - current.y, z: 0 }));
        cross.position.y = -current.z; // the crosshair stays on the bed
    }
    place();

    // The bed reading, drawn as a height field over the probed area, and
    // replaced whenever the page shows another reading.
    let meshGroup = null;
    let meshDrawn = null;
    function clearMesh() {
        if (meshGroup) {
            bedGroup.remove(meshGroup);
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
        // Where the points lie: a router's map says (record.area, from the working area's
        // front-left corner, where its probe went); a printer's grid is placed by estimate.
        const bounds = record.area
            ? { min: { x: record.area.min.x, y: record.area.min.y }, max: { x: record.area.max.x, y: record.area.max.y } }
            : meshBounds(frame.volume, record.probe_offset);
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
        bedGroup.add(meshGroup);
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
        bedGroup.remove(path);
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
            bedGroup.add(path);
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
        frame,
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
        // A place for the tool, or null for none known: the marker goes until one is.
        // The first place after none is jumped to, not tweened from wherever it was.
        setPosition(p, { immediate = false } = {}) {
            if (!p) { known = false; nozzle.visible = false; return; }
            for (const k of ["x", "y", "z"]) if (typeof p[k] === "number") target[k] = p[k];
            if (immediate || !known) { Object.assign(current, target); place(); }
            known = true;
            nozzle.visible = true;
        },
        known() { return known; },
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
        // How far the bed stands moved along Y from where it rests (0 for a bed that stays).
        bedOffset() { return bedMovesY === null ? 0 : bedMovesY - current.y; },
        target() { return { ...target }; },
        setMesh,
        mesh() { return meshDrawn ? JSON.parse(JSON.stringify(meshDrawn)) : null; },
        volume() {
            if (!hasVolume) return null;
            const [vx, vy, vz] = frame.volume;
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
 * the node is), nor standing over its machine's tool mark: where it would hide
 * the nozzle or the tool, it stands beside it. Keyed by `key`, the machine it
 * stands for (the printer a board inside drives, else the board's node); the page
 * listens to it. `selected()` opens its words. */
export function makeBoardBadge(anchors, key, boardPath, { point, selected }) {
    const inside = (mesh) => {
        for (let o = mesh; o; o = o.parent) {
            const k = o.userData.key;
            if (k && (k === boardPath || boardPath.startsWith(`${k}.`))) return true;
        }
        return false;
    };
    const badge = anchors.badge(key, point, { group: "Machine", selected, ignore: inside, clearOf: key });
    badge.dataset.path = key;
    badge.dataset.board = boardPath;
    badge.setAttribute("aria-label", "Select this board and open its Machine");
    return badge;
}

/* What a board's badge says, from the board model's summary (board_text.js): a
 * printer's state, readings and job, and the time its arm has left while it is armed,
 * however it was armed; a devkit's label and sketch; and under them the board and its
 * port. */
export function sayBoard(anchors, key, sum, device) {
    const badge = anchors.get(key);
    if (!badge) return;
    badge.classList.remove("printing", "offline", "job", "mismatch", "heating", "armed");
    let line;
    if (sum.kind === "devkit") {
        line = `${sum.icon} ${esc(device.label)} · <span class="state">${esc(sum.short)}</span>`;
    } else {
        const parts = [`${sum.icon} <span class="state">${esc(sum.state)}</span>`];
        if (sum.readings) parts.push(sum.readings);
        parts.push(...sum.extra.map(esc));
        if (sum.armed) parts.push(`<span class="armed">🔓 armed ${esc(sum.armed)}</span>`);
        line = parts.join(" · ");
        if (sum.job) badge.classList.add("job");
        if (sum.armed) badge.classList.add("armed");
    }
    if (sum.cls) badge.classList.add(sum.cls);
    anchors.say(key, { icon: "⚡", words: `<div>${line}</div><div class="sub">${esc(device.port)} — click to open its Machine</div>` });
}
