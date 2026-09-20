/* The board in its printer: a small three.js view for the monitor and
 * firmware pages.
 *
 * Draws the printer's own OpenSCAD geometry translucent, the board's solid,
 * the build volume as a wire box, a nozzle marker at the position the
 * board last reported, and -- when the page has a bed reading -- the mesh
 * as a surface over the bed, exaggerated so a couple of millimetres of tilt
 * can be seen at all, in the card's own two hues. The marker moves rather
 * than jumps: a poll tweens it to the new position, and a jog sent from
 * the page moves it ahead of the poll that confirms it, so the control
 * page shows the motion it commands.
 * What it draws is what the viewer draws -- the same STL routes, the same
 * z-up to y-up swap (the reflection, with the winding fixed) the fractal
 * viewer documents beside applyScadAxisSwap -- so a board in the garage looks
 * the same here as there.
 *
 * Needs the page's import map for `three` and `three/addons/`, as the viewer
 * has. Without OpenSCAD on the server the STL routes answer 503; the view then
 * shows the build volume and the marker alone and says so.
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";

const PRINTER_COLOR = 0x6f7f76;
const BOARD_COLOR = 0xe8b04a;
const VOLUME_COLOR = 0x6fb3e8;
const NOZZLE_COLOR = 0xff8080;
const BED_COLOR = 0x2a302a;
const MESH_LOW = [0x6f, 0xb3, 0xe8];   // the bed card's blue, below the mean
const MESH_HIGH = [0xe8, 0xb0, 0x4a];  // its amber, above
const MESH_INSET = 10;                 // Marlin's default MESH_INSET, mm from the probeable edge

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

function scadAxisSwap(geometry) {
    const position = geometry.attributes.position;
    for (let i = 0; i < position.count; i++) {
        const y = position.getY(i);
        const z = position.getZ(i);
        position.setY(i, z);
        position.setZ(i, y);
    }
    for (let i = 0; i + 2 < position.count; i += 3) {
        for (const [get, set] of [["getX", "setX"], ["getY", "setY"], ["getZ", "setZ"]]) {
            const b = position[get](i + 1);
            const c = position[get](i + 2);
            position[set](i + 1, c);
            position[set](i + 2, b);
        }
    }
    position.needsUpdate = true;
    geometry.computeVertexNormals();
    return geometry;
}

// apothecary (x, y, z) z-up -> three.js (x, z, y) y-up.
const toScene = (p) => new THREE.Vector3(p.x, p.z, p.y);

/* Mount the view into `el`. `where` is what GET /firmware/printers/where
 * answers: the site, the board's path and world position, the printer's
 * (the status-bearing ancestor's) path, position, footprint and build
 * volume. Returns { setPosition, position, destroy, ready }. */
export function mountBoardView(el, { base, where, onNote } = {}) {
    // `key` lets a page replace a note rather than add one (the mesh note changes with each reading).
    const note = (text, key) => { if (onNote) onNote(text, key); };
    const width = el.clientWidth || 320;
    const height = el.clientHeight || 220;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x141614);
    const camera = new THREE.PerspectiveCamera(40, width / height, 1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(width, height);
    el.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x223322, 1.1));
    const key = new THREE.DirectionalLight(0xffffff, 0.8);
    key.position.set(200, 400, 300);
    scene.add(key);

    const printer = where && where.printer ? where.printer : null;
    const board = where && where.board ? where.board : null;
    const origin = printer ? printer.position : (board ? board.position : { x: 0, y: 0, z: 0 });
    const world = new THREE.Group(); // everything relative to the printer's origin
    scene.add(world);

    // The build volume, drawn on the printer's base and centred on its
    // footprint -- the site's printers say how big it is, not where; this
    // is where a bed sits on every desktop printer.
    let volume = null;
    let volumeOrigin = { x: 0, y: 0, z: 0 };
    if (printer && printer.build_volume && printer.footprint) {
        const [vx, vy, vz] = printer.build_volume;
        const fp = printer.footprint;
        const fw = fp.max[0] - fp.min[0], fd = fp.max[1] - fp.min[1];
        volumeOrigin = { x: fp.min[0] + (fw - vx) / 2, y: fp.min[1] + (fd - vy) / 2, z: fp.min[2] + (printer.base_height || 0) };
        const box = new THREE.Mesh(new THREE.BoxGeometry(vx, vz, vy), new THREE.MeshBasicMaterial({ visible: false }));
        volume = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry), new THREE.LineBasicMaterial({ color: VOLUME_COLOR, transparent: true, opacity: 0.6 }));
        volume.position.copy(toScene({ x: volumeOrigin.x + vx / 2, y: volumeOrigin.y + vy / 2, z: volumeOrigin.z + vz / 2 }));
        world.add(volume);
        const bed = new THREE.Mesh(new THREE.PlaneGeometry(vx, vy), new THREE.MeshBasicMaterial({ color: BED_COLOR, side: THREE.DoubleSide, transparent: true, opacity: 0.5 }));
        bed.rotation.x = -Math.PI / 2;
        bed.position.copy(toScene({ x: volumeOrigin.x + vx / 2, y: volumeOrigin.y + vy / 2, z: volumeOrigin.z + 0.2 }));
        world.add(bed);
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
    world.add(nozzle);

    // The bed reading, drawn as a height field over the probed area, and
    // replaced whenever the page shows another reading.
    let meshGroup = null;
    let meshDrawn = null;
    function clearMesh() {
        if (meshGroup) {
            world.remove(meshGroup);
            meshGroup.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
            meshGroup = null;
        }
        meshDrawn = null;
    }
    function setMesh(record) {
        clearMesh();
        const rows = record && record.mesh;
        if (!rows || !rows.length || !rows[0].length || !printer || !printer.build_volume) return;
        const nRows = rows.length, nCols = rows[0].length;
        const flat = rows.flat();
        const lo = Math.min(...flat), hi = Math.max(...flat);
        const range = hi - lo;
        const exaggeration = meshExaggeration(range);
        const bounds = meshBounds(printer.build_volume, record.probe_offset);
        const stepX = nCols > 1 ? (bounds.max.x - bounds.min.x) / (nCols - 1) : 0;
        const stepY = nRows > 1 ? (bounds.max.y - bounds.min.y) / (nRows - 1) : 0;
        // Vertices in apothecary's frame relative to the printer: the bed at
        // the volume's floor, the lowest point of the mesh resting on it, each
        // other point lifted by its height above that, stretched -- a relief
        // of the bed, not a plot around its mean.
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
        for (const [j, i] of [[0, 0], [0, nCols - 1], [nRows - 1, 0], [nRows - 1, nCols - 1]]) {
            const k = (j * nCols + i) * 3;
            posts.push(new THREE.Vector3(positions[k], toScene({ x: 0, y: 0, z: volumeOrigin.z }).y, positions[k + 2]), new THREE.Vector3(positions[k], positions[k + 1], positions[k + 2]));
        }
        meshGroup.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(posts), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 })));
        world.add(meshGroup);
        meshDrawn = {
            rows: nRows, cols: nCols, range, exaggeration, bounds,
            z: { min: volumeOrigin.z + 0.4, max: volumeOrigin.z + 0.4 + range * exaggeration },
            record_id: record.id || null,
        };
        note(`mesh ${range.toFixed(3)} mm range, drawn ×${exaggeration}`, "mesh");
    }

    // Position bookkeeping: `current` is what is drawn, `target` what was last
    // asked for; each frame moves current a fraction of the way -- a tween
    // that finishes in about a third of a second whatever the distance.
    const current = { x: 0, y: 0, z: 0 };
    const target = { x: 0, y: 0, z: 0 };
    function place() {
        nozzle.position.copy(toScene({ x: volumeOrigin.x + current.x, y: volumeOrigin.y + current.y, z: volumeOrigin.z + current.z }));
        cross.position.y = -current.z; // the crosshair stays on the bed
    }
    place();

    // A node's STL comes in its parent's frame (the route renders the node's
    // own translate too: a printer on the bench arrives at x 100..400, its
    // board at the printer-relative 20..122). The viewer centres each body
    // and places it at the node's envelope, so this does the same: the
    // envelope is the world position plus the footprint, relative to the
    // printer's origin, and the geometry's own coordinates are not trusted.
    const bodies = {};
    function envelopeCentre(node) {
        const fp = node.footprint;
        const rel = { x: node.position.x - origin.x, y: node.position.y - origin.y, z: node.position.z - origin.z };
        if (!fp) return rel;
        return { x: rel.x + (fp.min[0] + fp.max[0]) / 2, y: rel.y + (fp.min[1] + fp.max[1]) / 2, z: rel.z + (fp.min[2] + fp.max[2]) / 2 };
    }
    const loader = new STLLoader();
    let missing = 0;
    function load(node, material, done) {
        if (!where || !where.site || !node || !node.path) { done && done(false); return; }
        loader.load(
            `${base}/sites/${encodeURIComponent(where.site)}/nodes/${encodeURIComponent(node.path)}/stl`,
            (geometry) => {
                scadAxisSwap(geometry);
                geometry.center();
                const mesh = new THREE.Mesh(geometry, material);
                mesh.position.copy(toScene(envelopeCentre(node)));
                world.add(mesh);
                if (material.transparent) {
                    // A translucent body reads as nothing on a dark page; its edges say where it is.
                    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), new THREE.LineBasicMaterial({ color: PRINTER_COLOR, transparent: true, opacity: 0.55 }));
                    edges.position.copy(mesh.position);
                    world.add(edges);
                }
                geometry.computeBoundingBox();
                const box = geometry.boundingBox.clone().translate(mesh.position);
                bodies[node.path] = { min: { x: box.min.x, y: box.min.z, z: box.min.y }, max: { x: box.max.x, y: box.max.z, z: box.max.y } };
                done && done(true);
            },
            undefined,
            () => { missing += 1; done && done(false); },
        );
    }
    let ready = new Promise((resolve) => {
        let left = 0;
        const finish = () => { left -= 1; if (left <= 0) resolve(missing === 0); };
        if (printer) {
            left += 1;
            load(printer, new THREE.MeshStandardMaterial({ color: PRINTER_COLOR, transparent: true, opacity: 0.3, depthWrite: false }), finish);
        }
        if (board) {
            left += 1;
            load(board, new THREE.MeshStandardMaterial({ color: BOARD_COLOR, metalness: 0.1, roughness: 0.6 }), finish);
        }
        if (left === 0) resolve(false);
    });
    ready.then((all) => {
        if (!all) note(missing ? "shape not available (OpenSCAD not on the server?) -- showing the build volume and the nozzle" : "no board bound");
    });

    // Frame the printer's footprint, or the board, or the volume.
    const extent = printer && printer.footprint
        ? Math.max(printer.footprint.max[0] - printer.footprint.min[0], printer.footprint.max[2] - printer.footprint.min[2])
        : (board && board.footprint ? Math.max(board.footprint.max[0] - board.footprint.min[0], 60) : 250);
    const centre = printer && printer.footprint
        ? toScene({ x: (printer.footprint.min[0] + printer.footprint.max[0]) / 2, y: (printer.footprint.min[1] + printer.footprint.max[1]) / 2, z: (printer.footprint.min[2] + printer.footprint.max[2]) / 2 })
        : toScene({ x: 0, y: 0, z: 0 });
    camera.position.set(centre.x + extent * 1.1, centre.y + extent * 0.9, centre.z + extent * 1.4);
    controls.target.copy(centre);

    let alive = true;
    function frame() {
        if (!alive) return;
        for (const k of ["x", "y", "z"]) current[k] += (target[k] - current[k]) * 0.18;
        place();
        controls.update();
        renderer.render(scene, camera);
        requestAnimationFrame(frame);
    }
    frame();

    const onResize = () => {
        const w = el.clientWidth || width, h = el.clientHeight || height;
        camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return {
        ready,
        setPosition(p, { immediate = false } = {}) {
            if (!p) return;
            for (const k of ["x", "y", "z"]) if (typeof p[k] === "number") target[k] = p[k];
            if (immediate) Object.assign(current, target);
        },
        position() { return { ...current }; },
        target() { return { ...target }; },
        // Where each body was drawn, in apothecary's z-up frame relative to the
        // printer's origin, and where the build volume sits -- for tests to
        // check the printer encloses its board and its volume.
        setMesh,
        // What the mesh surface was drawn from: its size, the range it spans,
        // how much it was stretched, and where it lies on the bed.
        mesh() { return meshDrawn ? JSON.parse(JSON.stringify(meshDrawn)) : null; },
        bodies() { return JSON.parse(JSON.stringify(bodies)); },
        volume() {
            if (!printer || !printer.build_volume) return null;
            const [vx, vy, vz] = printer.build_volume;
            return { min: { ...volumeOrigin }, max: { x: volumeOrigin.x + vx, y: volumeOrigin.y + vy, z: volumeOrigin.z + vz } };
        },
        destroy() {
            alive = false;
            clearMesh();
            window.removeEventListener("resize", onResize);
            renderer.dispose();
            el.innerHTML = "";
        },
    };
}

/* Ask the server where a port is pinned, in the shape mountBoardView wants.
 * null when it is pinned nowhere. */
export async function whereIs(base, port) {
    const r = await fetch(`${base}/firmware/printers/where?port=${encodeURIComponent(port)}`);
    if (!r.ok) return null;
    const data = await r.json();
    return data.board ? data : null;
}
