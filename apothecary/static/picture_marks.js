/* What pictures and cameras wear in the world.
 *
 * A view is a picture lying on a place -- a host, a root structure of the site,
 * or the floor (host "") -- or, a camera's that landed on a wall or the sky, on
 * no place (host null), with the shapes a finder saw in it once Find shapes has
 * run (GET /sites/{s}/attached; apothecary/vision/views.py). A camera is a part
 * of the site (apothecary/vision/cameras.py): its body is the page's node, and
 * here it wears its badge, its pyramid and its pictures.
 *
 * One mapping: every point of a picture lies where its view's homography puts
 * it (the server's `mat.homography`, in the site's frame at the mat's height:
 * (u, v, 1) multiplied out is (x * w, y * w, w)). The mat is a mesh subdivided
 * in the picture's own fractions, each vertex laid through it and textured at
 * the fraction it came from, so a tilted camera's picture lies as the trapezoid
 * it is and its texture is not sheared; a vertex past the horizon is left out.
 * A shape's outline is laid the same way, and one past the horizon (`beyond`) is
 * not drawn. A view nobody sized has no homography: it is laid flat, fitted to
 * its host's top (a fixed width on the floor), its border dashed to say so. The
 * pinhole the server lays a camera's picture through is written here once more
 * (pinhole, axes) for what has no view: live video and the pyramid.
 *
 * Drawn for each place: its drawn view's mat (the newest, or one a person
 * picked), its outlines, and one place badge, ▣, at the mat's top-left corner.
 * For each camera: a 📷 badge above its body, its words on hover or while it
 * is selected (its device, its lens, where its next picture lands); its
 * pyramid, from its lens to where its view's corners land, only while it is
 * selected or live; its newest picture, when that one landed nowhere, drawn on
 * the camera, in front of its lens; and while it is live, its video through its
 * own projection where its next picture would lie.
 *
 * Mats and outlines are drawn at the site's top level only; a badge and a
 * pyramid follow their thing's level. The mat's texture comes from GET
 * /photos/pictures/file?px= (answered no-store): made once per view, reused
 * across redraws, disposed when the view goes or the site changes. Why this on
 * a made piece (trace) draws the view it came from, lights its outline and
 * draws a thread to it; with the view gone, the outline is laid through the
 * homography the piece keeps.
 *
 * mountPictureMarks({ scene, anchors, base, hostBounds, hostInView,
 * atTopLevel, floorPoint, onSelect, isSelected, onChange }):
 *   hostBounds(path) -> {min:[x,y,z], max:[x,y,z]} in the site's frame, or null;
 *   hostInView(path) -> whether the thing is at the level being looked at;
 *   atTopLevel() -> whether the site's top level is on screen;
 *   floorPoint(made) -> [x,y,z] where the floor's things stand when no view says;
 *   onSelect(path) -> the page selects a host ("" is the floor) or a camera;
 *   isSelected(path) -> whether that is the selection;
 *   onChange(attached) -> after every fetch that answered.
 */

import * as THREE from "three";

// apothecary (x, y, z) z-up -> three.js (x, z, y) y-up.
const toScene = (x, y, z) => new THREE.Vector3(x, z, y);
// A badge's words are markup: a device's label and a picture's name are text in it.
const escapeText = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export const FOUND_COLOR = 0xffcc66;
export const MADE_COLOR = 0x6fdb75;
export const ALREADY_COLOR = 0x9a9a9a;
export const CHOSEN_COLOR = 0x66ccff;
export const TRACE_COLOR = 0xff66cc;
export const PYRAMID_COLOR = 0xffcc66;

const MAT_LIFT = 1.0;      // mm above the top: the mat
const OUTLINE_LIFT = 2.0;  // the outlines and their pick meshes, over the mat
const BADGE_LIFT = 6.0;    // the badge's point, over both, so neither dims it
const FLOOR_UNSIZED_MM = 600;  // an unsized floor mat's drawing width
const TEXTURE_PX = 1024;   // the long side a mat's texture is asked at
const GRID = 16;           // a mat's subdivisions along each side of its picture
const REACH_MM = 20000;    // a mat's vertex further than this from its middle is not drawn
const ON_CAMERA_MM = 120;  // a picture drawn on its camera stands this far in front of the lens
const PYRAMID_MM = 600;    // a corner ray that lands nowhere is drawn this long
const GRAZING = 1e-9;

export const FLOOR = "";
const placeKey = (host) => `place:${host === FLOOR ? "@floor" : host}`;
const cameraKey = (name) => `camera:${name}`;

// --- the one mapping, as the server has it (apothecary/vision/projection.py) --------------

/* A camera's right, its picture's down and where it looks, in the site's frame. */
export function axes(turn, tilt) {
    const t = (tilt * Math.PI) / 180, k = (turn * Math.PI) / 180;
    const ct = Math.cos(t), st = Math.sin(t), ck = Math.cos(k), sk = Math.sin(k);
    const turned = ([x, y, z]) => [x * ck - y * sk, x * sk + y * ck, z];
    return { right: turned([1, 0, 0]), down: turned([0, -ct, -st]), forward: turned([0, st, -ct]) };
}

/* A camera's picture onto the plane z = 0, its lens at eye (eye[2] above the plane). */
export function pinhole(eye, turn, tilt, fov, tallness) {
    const { right, down, forward } = axes(turn, tilt);
    const half = Math.tan((fov * Math.PI) / 360), deep = half * tallness;
    const a = right.map((r) => 2 * half * r), b = down.map((d) => 2 * deep * d);
    const c = forward.map((f, i) => f - half * right[i] - deep * down[i]);
    const [ex, ey, ez] = eye;
    return [
        [ez * a[0] - ex * a[2], ez * b[0] - ex * b[2], ez * c[0] - ex * c[2]],
        [ez * a[1] - ey * a[2], ez * b[1] - ey * b[2], ez * c[1] - ey * c[2]],
        [-a[2], -b[2], -c[2]],
    ];
}

/* A picture laid flat, width across, its middle at (cx, cy). */
export function flat(width, tallness, cx, cy) {
    const depth = width * tallness;
    return [[width, 0, cx - width / 2], [0, -depth, cy + depth / 2], [0, 0, 1]];
}

/* Where (u, v) of a picture lands through H; null where it never does. */
export function onto(H, u, v) {
    const w = H[2][0] * u + H[2][1] * v + H[2][2];
    if (w <= GRAZING) return null;
    return [(H[0][0] * u + H[0][1] * v + H[0][2]) / w, (H[1][0] * u + H[1][1] * v + H[1][2]) / w];
}

export function mountPictureMarks({ scene, anchors, base = "", hostBounds, hostInView, atTopLevel, floorPoint, onSelect, isSelected = () => false, onChange }) {
    let site = null;
    let attached = null;           // the last answer of GET /sites/{s}/attached
    let generation = 0;            // a site change makes answers still in flight stale
    let inflight = null, queued = null;
    const drawnPick = new Map();   // host -> view id a person picked to draw
    let chosen = null;             // { view, index }
    let live = null;               // { camera, video, texture }: a camera live where it looks
    let traced = null;             // { piece, view, index }: Why this, from a made piece
    let traceGroup = null;         // the thread, and the outline laid from a piece's copy
    const poses = new Map();       // camera -> a pose being dragged, ahead of the server
    const textures = new Map();    // view id -> THREE.Texture, for the page's time on the site
    const groups = new Map();      // host -> { mats: Group, view, lay }
    const cameraMarks = new Map(); // camera -> { pyramid, onCamera, live }
    const pickables = [];

    // --- what is known ------------------------------------------------------------------
    const views = () => (attached ? attached.views : []);
    const cameras = () => (attached ? attached.cameras : []);
    const viewsAt = (host) => views().filter((v) => v.host === host);
    const viewsBy = (name) => views().filter((v) => v.camera === name);
    function drawnAt(host) {
        const here = viewsAt(host);
        if (!here.length) return null;
        const picked = drawnPick.get(host);
        return here.find((v) => v.id === picked) || here[here.length - 1];  // the newest, oldest first
    }
    // A camera as it stands now: as the server answered, or as a drag has it.
    function cameraNamed(name) {
        const cam = cameras().find((c) => c.name === name);
        if (!cam) return null;
        const pose = poses.get(name);
        return pose ? { ...cam, ...pose } : cam;
    }
    function hosts() {
        const set = new Set();
        for (const v of views()) if (v.host !== null && v.host_found) set.add(v.host);
        return [...set];
    }
    function madeNames() { return attached ? Object.keys(attached.made || {}) : []; }

    // --- where a picture lies -----------------------------------------------------------
    // A view's lay: its homography in the site's frame, the height it lies at,
    // and whether it was sized. A view nobody sized is laid flat, fitted to its
    // host's top (a fixed width on the floor), for drawing only.
    function layOf(view) {
        if (!view || !view.mat) return null;
        const tall = view.pixel_height / view.pixel_width;
        const [cx, cy, cz] = view.mat.centre;
        if (view.mat.homography) return { H: view.mat.homography, z: cz, sized: true, tall };
        let width;
        let mx = cx;
        if (view.host === FLOOR) {
            width = FLOOR_UNSIZED_MM;
            mx += width / 2;  // the anchor is the near edge; unsized, the server reports it as the centre
        } else {
            const b = hostBounds(view.host);
            if (!b) return null;
            const w = b.max[0] - b.min[0], d = b.max[1] - b.min[1];
            width = Math.max(1, Math.min(w, d / tall));
        }
        return { H: flat(width, tall, mx, cy), z: cz, sized: false, tall };
    }
    // A camera's projection as it stands now, onto the plane its centre ray meets
    // (its next picture's place); null when it looks at nothing.
    function aimOf(cam, tall) {
        if (!cam || !cam.lands) return null;
        const z = cam.lands.point[2];
        const [x, y, ez] = cam.position;
        return { H: pinhole([x, y, ez - z], cam.turn, cam.tilt, cam.fov, tall), z, sized: true, tall };
    }
    // A point of a picture on its lay, in the site's frame, or null.
    function on(lay, u, v, lift) {
        const p = onto(lay.H, u, v);
        if (!p) return null;
        const mid = onto(lay.H, 0.5, 0.5);
        if (mid && Math.hypot(p[0] - mid[0], p[1] - mid[1]) > REACH_MM) return null;
        return [p[0], p[1], lay.z + lift];
    }

    // --- drawing ------------------------------------------------------------------------
    function textureFor(view) {
        let tex = textures.get(view.id);
        if (tex) return tex;
        const url = `${base}/photos/pictures/file?path=${encodeURIComponent(view.picture)}&px=${TEXTURE_PX}`;
        tex = new THREE.TextureLoader().load(
            url,
            (t) => { t.userData.loaded = true; },
            undefined,
            () => { tex.userData.failed = true; },
        );
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.userData = { url, loaded: false, failed: false };
        textures.set(view.id, tex);
        return tex;
    }

    // The picture, subdivided in its own fractions and laid vertex by vertex: the
    // surface mesh, the border along its edges, and its four corners (null where
    // one lands nowhere). Null when nothing of it lands.
    function surface(lay, lift) {
        const n = GRID, at = [];
        for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) at.push(on(lay, i / n, j / n, lift));
        const index = (i, j) => j * (n + 1) + i;
        const positions = [], uvs = [], faces = [];
        const slot = new Map();
        const use = (k, i, j) => {
            if (!slot.has(k)) {
                const p = toScene(...at[k]);
                slot.set(k, positions.length / 3);
                positions.push(p.x, p.y, p.z);
                uvs.push(i / n, 1 - j / n);  // the picture's top is the texture's top
            }
            return slot.get(k);
        };
        for (let j = 0; j < n; j++) {
            for (let i = 0; i < n; i++) {
                const k = [index(i, j), index(i + 1, j), index(i + 1, j + 1), index(i, j + 1)];
                if (k.some((q) => !at[q])) continue;
                const [a, b, c, d] = [use(k[0], i, j), use(k[1], i + 1, j), use(k[2], i + 1, j + 1), use(k[3], i, j + 1)];
                faces.push(a, d, c, a, c, b);
            }
        }
        if (!faces.length) return null;
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        g.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
        g.setIndex(faces);
        g.computeBoundingSphere();
        // The border: each edge of the picture, where it lands.
        const edge = [];
        const walk = (pts) => { for (let q = 0; q + 1 < pts.length; q++) if (pts[q] && pts[q + 1]) edge.push(toScene(pts[q][0], pts[q][1], pts[q][2] + 0.5), toScene(pts[q + 1][0], pts[q + 1][1], pts[q + 1][2] + 0.5)); };
        const row = (j) => Array.from({ length: n + 1 }, (_, i) => at[index(i, j)]);
        const col = (i) => Array.from({ length: n + 1 }, (_, j) => at[index(i, j)]);
        walk(row(0)); walk(row(n)); walk(col(0)); walk(col(n));
        return { geometry: g, border: edge, corners: [at[index(0, 0)], at[index(n, 0)], at[index(n, n)], at[index(0, n)]] };
    }

    function colourOf(view, shape) {
        if (traced && traced.view === view.id && traced.index === shape.index) return TRACE_COLOR;
        if (chosen && chosen.view === view.id && chosen.index === shape.index) return CHOSEN_COLOR;
        if (shape.status === "made") return MADE_COLOR;
        if (shape.status === "already_made") return ALREADY_COLOR;
        return FOUND_COLOR;
    }
    const outlineOf = (shape) => (shape.points && shape.points.length >= 3
        ? shape.points
        : [[shape.min[0], shape.min[1]], [shape.max[0], shape.min[1]], [shape.max[0], shape.max[1]], [shape.min[0], shape.max[1]]]);

    function drawMat(host, view, lay, map) {
        const laid = surface(lay, MAT_LIFT);
        if (!laid) return null;
        const group = new THREE.Group();
        group.name = view ? `view:${view.id}` : `live:${host}`;
        const picture = new THREE.Mesh(
            laid.geometry,
            new THREE.MeshBasicMaterial({ map, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }),
        );
        picture.userData.pick = { host, view: view ? view.id : null, index: null };
        picture.userData.live = !view;
        group.add(picture);
        pickables.push(picture);
        const border = new THREE.LineSegments(
            new THREE.BufferGeometry().setFromPoints(laid.border),
            lay.sized
                ? new THREE.LineBasicMaterial({ color: 0xdddddd, transparent: true, opacity: 0.6 })
                : new THREE.LineDashedMaterial({ color: 0xdddddd, dashSize: 20, gapSize: 14 }),
        );
        if (!lay.sized) border.computeLineDistances();
        group.add(border);
        group.userData.corners = laid.corners;
        if (!view) return group;
        // The outlines, laid as the picture is, and a pick mesh under each one not
        // made into a piece; a shape past the horizon is not drawn.
        for (const shape of view.shapes) {
            if (shape.status === "beyond") continue;
            const world = outlineOf(shape).map(([fx, fy]) => on(lay, fx, fy, OUTLINE_LIFT));
            if (world.some((p) => !p)) continue;
            const colour = colourOf(view, shape);
            const material = shape.status === "already_made"
                ? new THREE.LineDashedMaterial({ color: colour, dashSize: 8, gapSize: 6 })
                : new THREE.LineBasicMaterial({ color: colour });
            const outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(world.map((c) => toScene(...c))), material);
            if (shape.status === "already_made") outline.computeLineDistances();
            outline.userData.shape = { view: view.id, index: shape.index, status: shape.status };
            group.add(outline);
            if (shape.status === "made") continue;
            const flatShape = new THREE.ShapeGeometry(new THREE.Shape(world.map((c) => new THREE.Vector2(c[0], c[1]))));
            // ShapeGeometry lies in its own xy plane: carried into the site's frame at the outline's height.
            const pos = flatShape.getAttribute("position");
            for (let i = 0; i < pos.count; i++) {
                const v = toScene(pos.getX(i), pos.getY(i), world[0][2]);
                pos.setXYZ(i, v.x, v.y, v.z);
            }
            flatShape.computeBoundingSphere();
            const pick = new THREE.Mesh(flatShape, new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide }));
            pick.userData.pick = { host, view: view.id, index: shape.index };
            group.add(pick);
            pickables.push(pick);
        }
        return group;
    }

    // A picture on its camera: the camera's view cut at ON_CAMERA_MM in front of
    // its lens, facing it, for a picture that landed nowhere (or live video aimed
    // at nothing).
    function drawOnCamera(cam, map, tall, name) {
        const { right, down, forward } = axes(cam.turn, cam.tilt);
        const half = Math.tan((cam.fov * Math.PI) / 360) * ON_CAMERA_MM, deep = half * tall;
        const at = (u, v) => cam.position.map((p, i) => p + ON_CAMERA_MM * forward[i] + (2 * u - 1) * half * right[i] + (2 * v - 1) * deep * down[i]);
        const corners = [at(0, 0), at(1, 0), at(1, 1), at(0, 1)];
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(corners.flatMap((c) => { const v = toScene(...c); return [v.x, v.y, v.z]; }), 3));
        g.setAttribute("uv", new THREE.Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2));
        g.setIndex([0, 3, 2, 0, 2, 1]);
        const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map, side: THREE.DoubleSide }));
        mesh.name = name;
        mesh.userData.corners = corners;
        return mesh;
    }

    // A camera's pyramid: from its lens along its corner rays to the plane its
    // next picture lies on, or PYRAMID_MM along them where they land nowhere.
    function drawPyramid(cam, tall) {
        const { right, down, forward } = axes(cam.turn, cam.tilt);
        const half = Math.tan((cam.fov * Math.PI) / 360), deep = half * tall;
        const plane = cam.lands ? cam.lands.point[2] : null;
        const apex = cam.position;
        const ends = [[0, 0], [1, 0], [1, 1], [0, 1]].map(([u, v]) => {
            const d = forward.map((f, i) => f + (2 * u - 1) * half * right[i] + (2 * v - 1) * deep * down[i]);
            const t = plane !== null && d[2] < -GRAZING ? (plane + OUTLINE_LIFT - apex[2]) / d[2] : null;
            const len = t !== null && t > 0 && t * Math.hypot(...d) < REACH_MM ? t : PYRAMID_MM / Math.hypot(...d);
            return apex.map((p, i) => p + len * d[i]);
        });
        const pts = [];
        for (let i = 0; i < 4; i++) pts.push(toScene(...apex), toScene(...ends[i]), toScene(...ends[i]), toScene(...ends[(i + 1) % 4]));
        const lines = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: PYRAMID_COLOR, transparent: true, opacity: 0.8 }));
        lines.name = `pyramid:${cam.name}`;
        lines.userData.ends = ends;
        return lines;
    }

    // --- badges -------------------------------------------------------------------------
    function placeWords(host) {
        const view = drawnAt(host);
        if (!view) return host === FLOOR ? "floor" : host;
        const shapes = view.finder === null ? "Find shapes next" : `${view.shapes.length} shape${view.shapes.length === 1 ? "" : "s"}`;
        const by = view.camera ? ` · by ${view.camera}` : "";
        return `${host === FLOOR ? "floor" : host} · ${view.picture.split("/").pop()} · ${shapes}${view.mat && view.mat.width ? "" : " · unsized"}${by}`;
    }
    // The place's own spot: the drawn picture's top-left corner, or with none
    // drawn, the same corner of the host's top.
    function placePoint(host) {
        if (!hostInView(host)) return null;
        const g = groups.get(host);
        if (g && g.lay) {
            const c = on(g.lay, 0, 0, BADGE_LIFT) || on(g.lay, 0.5, 0.5, BADGE_LIFT);
            if (c) return toScene(...c);
        }
        if (host === FLOOR) {
            const p = floorPoint(madeNames());
            return toScene(p[0], p[1] + FLOOR_UNSIZED_MM / 2, p[2] + BADGE_LIFT);
        }
        const b = hostBounds(host);
        return b ? toScene(b.min[0], b.max[1], b.max[2] + BADGE_LIFT) : null;
    }
    // A camera's words: its device, its lens, and where its next picture lands.
    function cameraWords(cam) {
        const device = cam.device ? `device ${cam.device.label}` : "no device yet (Device, on its ring)";
        const lens = `lens ${Number(cam.fov).toFixed(0)}°${cam.fov_taught ? ", taught" : ", as it started"}`;
        const lands = cam.lands ? `next picture lands on ${cam.lands.host === FLOOR ? "the floor" : cam.lands.host}` : "next picture lands nowhere: aim it down";
        return `<b>${escapeText(cam.name)}</b><br>${escapeText(device)}<br>${escapeText(lens)}<br>${escapeText(lands)}`;
    }
    function cameraPoint(name) {
        if (!hostInView(name)) return null;
        const b = hostBounds(name);
        return b ? toScene((b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, b.max[2] + BADGE_LIFT) : null;
    }

    // --- one redraw ---------------------------------------------------------------------
    function dispose(o) {
        if (!o) return;
        scene.remove(o);
        o.traverse((x) => { x.geometry?.dispose(); if (x.material) x.material.dispose(); });  // textures are kept
    }
    function clearDrawn() {
        for (const g of groups.values()) dispose(g.mats);
        groups.clear();
        for (const m of cameraMarks.values()) { dispose(m.pyramid); dispose(m.onCamera); dispose(m.live); }
        cameraMarks.clear();
        pickables.length = 0;
    }
    const tallOf = (name) => {
        if (live && live.camera === name && live.video && live.video.videoWidth) return live.video.videoHeight / live.video.videoWidth;
        const newest = viewsBy(name).slice(-1)[0];
        return newest ? newest.pixel_height / newest.pixel_width : 0.75;
    };

    function drawCamera(name) {
        const cam = cameraNamed(name);
        const old = cameraMarks.get(name);
        if (old) { dispose(old.pyramid); dispose(old.onCamera); dispose(old.live); }
        if (!cam) { cameraMarks.delete(name); return; }
        const tall = tallOf(name);
        const entry = { pyramid: drawPyramid(cam, tall), onCamera: null, live: null };
        scene.add(entry.pyramid);
        const liveHere = live && live.camera === name;
        if (liveHere) {
            const aim = aimOf(cam, tall);
            entry.live = aim ? drawMat(cam.lands.host, null, aim, live.texture) : drawOnCamera(cam, live.texture, tall, `live:${name}`);
            if (entry.live) scene.add(entry.live);
        } else {
            // Its newest picture, when that one landed nowhere: drawn on the camera.
            const newest = viewsBy(name).slice(-1)[0];
            if (newest && newest.host === null) {
                entry.onCamera = drawOnCamera(cam, textureFor(newest), newest.pixel_height / newest.pixel_width, `on-camera:${newest.id}`);
                entry.onCamera.userData.view = newest.id;
                scene.add(entry.onCamera);
            }
        }
        cameraMarks.set(name, entry);
    }

    function redraw() {
        clearDrawn();
        const wanted = new Set();
        for (const host of hosts()) {
            const view = drawnAt(host);
            const lay = layOf(view);
            const entry = { mats: null, view, lay };
            if (lay && view) { entry.mats = drawMat(host, view, lay, textureFor(view)); if (entry.mats) scene.add(entry.mats); }
            groups.set(host, entry);
            const key = placeKey(host);
            wanted.add(key);
            let badge = anchors.get(key);
            if (!badge) {
                badge = anchors.badge(key, () => placePoint(host), { className: "place-mark", selected: () => isSelected(host) });
                badge.dataset.host = host;
                badge.setAttribute("aria-label", host === FLOOR ? "Select the floor" : `Select ${host}`);
                badge.addEventListener("click", () => onSelect(host));
            }
            anchors.say(key, { icon: "▣", words: escapeText(placeWords(host)) });
        }
        for (const cam of cameras()) {
            drawCamera(cam.name);
            const key = cameraKey(cam.name);
            wanted.add(key);
            let badge = anchors.get(key);
            if (!badge) {
                badge = anchors.badge(key, () => cameraPoint(cam.name), { className: "camera-mark", selected: () => isSelected(cam.name) });
                badge.dataset.camera = cam.name;
                badge.setAttribute("aria-label", `Select ${cam.name}`);
                badge.addEventListener("click", () => onSelect(cam.name));
            }
            badge.classList.toggle("has-device", !!cam.device);
            anchors.say(key, { icon: "📷", words: cameraWords(cameraNamed(cam.name)) });
        }
        for (const key of anchors.keys()) if ((key.startsWith("place:") || key.startsWith("camera:")) && !wanted.has(key)) anchors.remove(key);
        // A texture is kept while its view is pinned here, and no longer.
        const pinned = new Set(views().map((v) => v.id));
        for (const [id, tex] of textures) if (!pinned.has(id)) { tex.dispose(); textures.delete(id); }
        if (chosen && !views().some((v) => v.id === chosen.view && v.shapes.some((s) => s.index === chosen.index && s.status !== "made"))) chosen = null;
        drawTrace();
        sync();
    }

    // Why this: a thread from a made piece's top to its outline, the outline lit
    // on its view's mat, or laid through the homography the piece keeps when the
    // view is gone (in its extent's frame: from its host's top-centre, or the
    // site's at the floor).
    function clearTrace() { dispose(traceGroup); traceGroup = null; }
    function drawTrace() {
        clearTrace();
        if (!traced) return;
        const record = attached && attached.made ? attached.made[traced.piece] : null;
        const top = hostBounds(traced.piece);
        if (!record || !top) { traced = null; return; }
        const group = new THREE.Group();
        group.name = `trace:${traced.piece}`;
        const g = groups.get(record.host);
        const shown = !!(g && g.view && g.view.id === record.view && g.lay && g.mats && g.view.shapes.some((s) => s.index === record.shape_index));
        const shape = shown ? g.view.shapes.find((s) => s.index === record.shape_index) : record.shape;
        let lay = shown ? g.lay : null;
        if (!lay) {
            let ox = 0, oy = 0, oz = 0;
            if (record.host !== FLOOR) {
                const hb = hostBounds(record.host);
                if (hb) { ox = (hb.min[0] + hb.max[0]) / 2; oy = (hb.min[1] + hb.max[1]) / 2; oz = hb.max[2]; }
            }
            const [r0, r1, r2] = record.homography;
            lay = { H: [r0.map((h, i) => h + ox * r2[i]), r1.map((h, i) => h + oy * r2[i]), r2], z: oz, sized: true };
        }
        const points = outlineOf(shape).map(([fx, fy]) => on(lay, fx, fy, OUTLINE_LIFT)).filter(Boolean);
        if (!points.length) { traced = null; return; }
        if (!shown) {
            const ghost = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points.map((c) => toScene(...c))), new THREE.LineDashedMaterial({ color: TRACE_COLOR, dashSize: 10, gapSize: 6 }));
            ghost.computeLineDistances();
            ghost.userData.ghost = true;
            group.add(ghost);
        }
        const mid = points.reduce((a, c) => [a[0] + c[0] / points.length, a[1] + c[1] / points.length, a[2] + c[2] / points.length], [0, 0, 0]);
        const from = [(top.min[0] + top.max[0]) / 2, (top.min[1] + top.max[1]) / 2, top.max[2] + BADGE_LIFT];
        const thread = new THREE.Line(new THREE.BufferGeometry().setFromPoints([toScene(...from), toScene(...mid)]), new THREE.LineBasicMaterial({ color: TRACE_COLOR }));
        thread.userData.thread = true;
        group.add(thread);
        traced.shown = shown;
        traced.outline = mid;
        traceGroup = group;
        scene.add(group);
    }

    // Mats at the top level only, and a place's put away while a camera is live
    // on it (its video lies there instead); a camera's marks while it is in view,
    // its pyramid only while it is selected or live.
    function sync() {
        const top = atTopLevel();
        const liveCam = live ? cameraNamed(live.camera) : null;
        const liveOn = liveCam && liveCam.lands ? liveCam.lands.host : null;
        for (const [host, g] of groups) if (g.mats) g.mats.visible = top && host !== liveOn;
        for (const [name, m] of cameraMarks) {
            const here = hostInView(name);
            if (m.pyramid) m.pyramid.visible = here && (isSelected(name) || !!(live && live.camera === name));
            if (m.onCamera) m.onCamera.visible = here;
            if (m.live) m.live.visible = here;
        }
        if (traceGroup) traceGroup.visible = top;
    }

    // --- fetching: one request at a time, a second ask folded into one more ---------------
    function fetchOnce() {
        const asked = generation, name = site;
        const p = (async () => {
            let answer = null;
            try {
                const r = await fetch(`${base}/sites/${encodeURIComponent(name)}/attached`);
                answer = r.ok ? await r.json() : null;
            } catch (e) { answer = null; }
            if (asked === generation) {
                attached = answer || { site: name, cameras: [], views: [], made: {} };
                poses.clear();
                redraw();
                if (onChange) onChange(attached);
            }
            return attached;
        })().finally(() => { if (inflight === p) inflight = null; });
        inflight = p;
        return p;
    }
    function refresh() {
        if (!site) return Promise.resolve(null);
        if (!inflight) return fetchOnce();
        if (!queued) {
            const asked = generation;
            queued = inflight.catch(() => {}).then(() => {
                queued = null;
                return asked === generation ? fetchOnce() : attached;
            });
        }
        return queued;
    }

    function load(name) {
        if (name !== site) {
            generation += 1;
            site = name;
            attached = null;
            chosen = null;
            traced = null;
            if (live) { live.texture.dispose(); live = null; }
            drawnPick.clear();
            poses.clear();
            clearDrawn();
            clearTrace();
            for (const tex of textures.values()) tex.dispose();
            textures.clear();
            for (const key of anchors.keys()) if (key.startsWith("place:") || key.startsWith("camera:")) anchors.remove(key);
            queued = null;
            inflight = null;
        }
        return refresh();
    }

    function visiblePickables() {
        return pickables.filter((m) => { for (let o = m; o; o = o.parent) if (!o.visible) return false; return true; });
    }
    const siteCorners = (corners) => (corners ? corners.map((c) => (c ? [c[0], c[1], c[2]] : null)) : null);
    // How far apart two points of a picture lie on its lay, in mm (null unless both land).
    const apart = (lay, p, q) => {
        const a = onto(lay.H, ...p), b = onto(lay.H, ...q);
        return a && b ? Math.hypot(b[0] - a[0], b[1] - a[1]) : null;
    };

    return {
        load,
        refresh,
        sync,
        /* The meshes a click can land on, to raycast with the nodes' own. */
        pickables: visiblePickables,
        /* What a pick mesh stands for: { host, view, index } (index null: the mat). */
        picked(object) { return (object && object.userData && object.userData.pick) || null; },
        choose(viewId, index) {
            const view = views().find((v) => v.id === viewId);
            const shape = view && view.shapes.find((s) => s.index === index);
            if (!shape || shape.status === "made" || shape.status === "beyond") return false;
            chosen = { view: viewId, index };
            redraw();
            return true;
        },
        unchoose() { if (!chosen) return; chosen = null; redraw(); },
        /* Draw one of a place's views: a change of what is drawn, never a site switch. */
        draw(host, viewId) {
            if (!viewsAt(host).some((v) => v.id === viewId)) return false;
            drawnPick.set(host, viewId);
            if (chosen && chosen.view !== viewId) chosen = null;
            redraw();
            return true;
        },
        /* A camera's video where it looks (null: its pictures again). */
        setLive(camera, video) {
            if (live) { live.texture.dispose(); live = null; }
            if (video) {
                const texture = new THREE.VideoTexture(video);
                texture.colorSpace = THREE.SRGBColorSpace;
                live = { camera, video, texture };
            }
            redraw();
        },
        liveAt() { return live ? live.camera : null; },
        /* A camera's pose as a drag has it, ahead of the server: its pyramid and live
         * video follow (null forgets it). */
        posePreview(name, pose) {
            if (pose) poses.set(name, { ...(poses.get(name) || {}), ...pose }); else poses.delete(name);
            drawCamera(name);
            sync();
        },
        /* Why this, from a made piece: its view drawn, its outline lit, a thread to it. */
        trace(piece) {
            const record = attached && attached.made ? attached.made[piece] : null;
            if (!record) return null;
            if (record.view_pinned) drawnPick.set(record.host, record.view);
            traced = { piece, view: record.view, index: record.shape_index };
            redraw();
            return traced ? { ...record, shown: traced.shown, outline: traced.outline } : null;
        },
        untrace() { if (!traced) return; traced = null; clearTrace(); },
        traced() {
            if (!traced || !traceGroup) return null;
            return { piece: traced.piece, view: traced.view, index: traced.index, shown: traced.shown, outline: traced.outline, visible: traceGroup.visible };
        },
        chosen() { return chosen ? { ...chosen } : null; },
        attached() { return attached; },
        cameras,
        camera: cameraNamed,
        viewsAt,
        viewsBy,
        drawnAt,
        madeRecord(piece) { return attached && attached.made ? attached.made[piece] || null : null; },
        /* A shape's long side on its surface, in mm, through its view's mapping, as
         * the server reads it (projection.long_side_on): along its own long side when
         * that was measured, else its upright box's longer side. Null until the view
         * is sized, or where an end lands nowhere. */
        longSide(viewId, index) {
            const view = views().find((v) => v.id === viewId);
            const shape = view && view.shapes.find((s) => s.index === index);
            const lay = shape ? layOf(view) : null;
            if (!lay || !lay.sized) return null;
            const tall = lay.tall;
            const cx = (shape.min[0] + shape.max[0]) / 2, cy = (shape.min[1] + shape.max[1]) / 2;
            if (shape.long_side > 0 && shape.short_side > 0) {
                const turn = shape.turned_degrees * Math.PI / 180;
                const du = Math.cos(turn) * shape.long_side / 2, dv = Math.sin(turn) * shape.long_side / 2 / tall;
                return apart(lay, [cx - du, cy - dv], [cx + du, cy + dv]);
            }
            const w = shape.max[0] - shape.min[0], h = shape.max[1] - shape.min[1];
            return w >= h * tall
                ? apart(lay, [shape.min[0], cy], [shape.max[0], cy])
                : apart(lay, [cx, shape.min[1]], [cx, shape.max[1]]);
        },
        /* A point of a drawn view's picture (fractions, y down) in scene coordinates. */
        scenePoint(viewId, fx, fy) {
            for (const g of groups.values()) {
                if (g.view && g.view.id === viewId && g.lay) {
                    const p = on(g.lay, fx, fy, MAT_LIFT);
                    return p ? toScene(...p) : null;
                }
            }
            return null;
        },
        /* What is drawn at each place, for tests and for the status line: its mat
         * (its corners as laid on the page, in the site's frame) and its outlines. */
        state() {
            return [...groups.entries()].map(([host, g]) => ({
                host,
                view: g.view ? g.view.id : null,
                camera: g.view ? g.view.camera : null,
                mat: g.mats ? {
                    visible: g.mats.visible,
                    centre: on(g.lay, 0.5, 0.5, 0) || g.view.mat.centre,
                    width: apart(g.lay, [0, 0.5], [1, 0.5]),
                    depth: apart(g.lay, [0.5, 0], [0.5, 1]),
                    sized: g.lay.sized,
                    corners: siteCorners(g.mats.userData.corners),
                } : null,
                outlines: g.mats ? g.mats.children.filter((o) => o.userData.shape).map((o) => ({ ...o.userData.shape, colour: o.material.color.getHex() })) : [],
                texture: g.view && textures.get(g.view.id) ? { ...textures.get(g.view.id).userData } : null,
            }));
        },
        /* What each camera wears, for tests: its pyramid (shown or not, and where its
         * corner rays end), a picture drawn on it, and its live video. */
        cameraState() {
            return [...cameraMarks.entries()].map(([name, m]) => ({
                camera: name,
                pyramid: m.pyramid ? { visible: m.pyramid.visible, ends: m.pyramid.userData.ends } : null,
                onCamera: m.onCamera ? { view: m.onCamera.userData.view, visible: m.onCamera.visible } : null,
                live: m.live ? { visible: m.live.visible, corners: siteCorners(m.live.userData.corners) } : null,
            }));
        },
        destroy() {
            clearDrawn();
            clearTrace();
            for (const tex of textures.values()) tex.dispose();
            textures.clear();
            for (const key of anchors.keys()) if (key.startsWith("place:") || key.startsWith("camera:")) anchors.remove(key);
            site = null; attached = null;
        },
    };
}
