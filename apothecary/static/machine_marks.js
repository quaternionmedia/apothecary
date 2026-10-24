/* What a printer wears in a three.js scene, wherever that scene is: the
 * build volume as a wire box on the printer's base, the bed plane, a nozzle
 * marker at the position the board last reported, and -- when there is a
 * bed reading -- the mesh as a relief over the bed.
 *
 * One group, in the printer's own frame (apothecary's z-up, relative to the
 * printer's origin); the caller places it: the world scene at the printer's
 * world position, the monitor's small scene at its origin. The marker moves
 * rather than jumps: setPosition sets a target and tick() moves the drawn
 * position a fraction of the way each frame, so a poll tweens it and a jog
 * sent from a page moves it ahead of the poll that confirms it.
 */

import * as THREE from "three";

export const VOLUME_COLOR = 0x6fb3e8;
export const NOZZLE_COLOR = 0xff8080;
export const BED_COLOR = 0x2a302a;
const MESH_LOW = [0x6f, 0xb3, 0xe8];   // the bed card's blue, below the mean
const MESH_HIGH = [0xe8, 0xb0, 0x4a];  // its amber, above
const MESH_INSET = 10;                 // Marlin's default MESH_INSET, mm from the probeable edge

// apothecary (x, y, z) z-up -> three.js (x, z, y) y-up.
export const toScene = (p) => new THREE.Vector3(p.x, p.z, p.y);

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

    return {
        group,
        volumeOrigin,
        setPosition(p, { immediate = false } = {}) {
            if (!p) return;
            for (const k of ["x", "y", "z"]) if (typeof p[k] === "number") target[k] = p[k];
            if (immediate) { Object.assign(current, target); place(); }
        },
        tick() {
            for (const k of ["x", "y", "z"]) current[k] += (target[k] - current[k]) * 0.18;
            place();
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
            group.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
            if (group.parent) group.parent.remove(group);
        },
    };
}
