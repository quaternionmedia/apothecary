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
import { makeMachineMarks, toScene } from "./machine_marks.js";

export { meshBounds, meshExaggeration } from "./machine_marks.js";

const PRINTER_COLOR = 0x6f7f76;
const BOARD_COLOR = 0xe8b04a;

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

    // The volume, the bed, the nozzle marker and the bed relief are the
    // machine's marks, shared with the world scene; here at the origin.
    const marks = makeMachineMarks(printer, { onNote: note });
    world.add(marks.group);

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
        marks.tick();
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
        setPosition: (p, opts) => marks.setPosition(p, opts),
        position: () => marks.position(),
        target: () => marks.target(),
        setMesh: (record) => marks.setMesh(record),
        // What the mesh surface was drawn from: its size, the range it spans,
        // how much it was stretched, and where it lies on the bed.
        mesh: () => marks.mesh(),
        bodies() { return JSON.parse(JSON.stringify(bodies)); },
        volume: () => marks.volume(),
        destroy() {
            alive = false;
            marks.destroy();
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
