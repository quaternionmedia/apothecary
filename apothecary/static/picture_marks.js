/* What a picture wears in the world: a look drawn where it was pinned.
 *
 * A look is a picture pinned at a host -- a root structure of the site -- or
 * at the site's floor (host ""), with the shapes a finder saw in it
 * (GET /sites/{s}/attached; apothecary/vision/looks.py). Here it is drawn:
 *
 * - the mat: the picture itself, lying on the host's top (or on the floor
 *   beside the site), sized by the look's scale; an unsized look is fitted to
 *   the host's top for drawing only, and its border is dashed to say so;
 * - an outline per shape on the mat, with an invisible pick mesh the page
 *   raycasts together with the nodes' meshes, nearest first; a shape made
 *   into a piece is drawn green and not picked (its piece is), one already
 *   made from another look is drawn dashed;
 * - a camera's frustum looking down onto its host, its base the mat;
 * - one place badge (an anchor) per host that holds a camera or a look, the
 *   floor included. A click on it selects the host.
 *
 * Mats and outlines are drawn at the site's top level only; a frustum and a
 * badge follow their host's level, as a machine's badge does. The mat's
 * texture comes from GET /photos/pictures/file?px= (answered no-store, so it
 * never enters the browser's disk cache): made once per look, reused across
 * redraws, disposed when the look goes or the site changes. Nothing here
 * runs per frame; the anchors layer projects the badges.
 *
 * mountPictureMarks({ scene, anchors, base, hostBounds, hostInView,
 * atTopLevel, floorPoint, onSelect, onChange }):
 *   hostBounds(host) -> {min:[x,y,z], max:[x,y,z]} in the site's frame, or null;
 *   hostInView(host) -> whether the host is at the level being looked at;
 *   atTopLevel() -> whether the site's top level is on screen;
 *   floorPoint(made) -> [x,y,z] where the floor's things stand when no look says;
 *   onSelect(host) -> the page selects the host ("" is the floor);
 *   onChange(attached) -> after every fetch that answered.
 */

import * as THREE from "three";

// apothecary (x, y, z) z-up -> three.js (x, z, y) y-up.
const toScene = (x, y, z) => new THREE.Vector3(x, z, y);

export const FOUND_COLOR = 0xffcc66;
export const MADE_COLOR = 0x6fdb75;
export const ALREADY_COLOR = 0x9a9a9a;
export const CHOSEN_COLOR = 0x66ccff;
const FRUSTUM_COLOR = 0xffcc66;

const MAT_LIFT = 1.0;      // mm above the top: the mat
const OUTLINE_LIFT = 2.0;  // the outlines and their pick meshes, over the mat
const BADGE_LIFT = 6.0;    // the badge's point, over both, so neither dims it
const FLOOR_UNSIZED_MM = 600;  // an unsized floor mat's drawing width
const TEXTURE_PX = 1024;   // the long side a mat's texture is asked at

export const FLOOR = "";
const keyFor = (host) => `place:${host === FLOOR ? "@floor" : host}`;

export function mountPictureMarks({ scene, anchors, base = "", hostBounds, hostInView, atTopLevel, floorPoint, onSelect, onChange }) {
    let site = null;
    let attached = null;           // the last answer of GET /sites/{s}/attached
    let generation = 0;            // a site change makes answers still in flight stale
    let inflight = null, queued = null;
    const drawnPick = new Map();   // host -> look id a person picked to draw (Phase 4)
    let chosen = null;             // { look, index }
    const textures = new Map();    // look id -> THREE.Texture, for the page's time on the site
    const groups = new Map();      // host -> { mats: Group, frustum: LineSegments|null, look, mat }
    const pickables = [];

    // --- what is known ------------------------------------------------------------------
    const looks = () => (attached ? attached.looks : []);
    const cameras = () => (attached ? attached.cameras : []);
    const looksAt = (host) => looks().filter((l) => l.host === host);
    function drawnAt(host) {
        const here = looksAt(host);
        if (!here.length) return null;
        const picked = drawnPick.get(host);
        return here.find((l) => l.id === picked) || here[here.length - 1];  // the newest, oldest first
    }
    const cameraAt = (host) => cameras().find((c) => c.path === host && c.host_found !== false) || null;
    function hosts() {
        const set = new Set();
        for (const l of looks()) if (l.host_found) set.add(l.host);
        for (const c of cameras()) if (c.host_found) set.add(c.path);
        return [...set];
    }

    // Where a look's mat lies and how big it is drawn: its scale's width, or
    // fitted to the host's top (a fixed width at the floor) and said unsized.
    function matOf(look) {
        if (!look || !look.mat) return null;
        const tall = look.pixel_height / look.pixel_width;
        let [cx, cy, cz] = look.mat.centre;
        let width = look.mat.width, sized = true;
        if (!width) {
            sized = false;
            if (look.host === FLOOR) {
                width = FLOOR_UNSIZED_MM;
                cx += width / 2;  // the anchor is the near edge; unsized, the server reports it as the centre
            } else {
                const b = hostBounds(look.host);
                if (!b) return null;
                const w = b.max[0] - b.min[0], d = b.max[1] - b.min[1];
                width = Math.max(1, Math.min(w, d / tall));
            }
        }
        return { centre: [cx, cy, cz], width, depth: width * tall, sized };
    }
    // A point of the picture, as fractions (x right, y down), on its mat, in the site's frame.
    function onMat(mat, fx, fy, lift) {
        return [mat.centre[0] + (fx - 0.5) * mat.width, mat.centre[1] + (0.5 - fy) * mat.depth, mat.centre[2] + lift];
    }

    // --- drawing ------------------------------------------------------------------------
    function textureFor(look) {
        let tex = textures.get(look.id);
        if (tex) return tex;
        const url = `${base}/photos/pictures/file?path=${encodeURIComponent(look.picture)}&px=${TEXTURE_PX}`;
        tex = new THREE.TextureLoader().load(
            url,
            (t) => { t.userData.loaded = true; },
            undefined,
            () => { tex.userData.failed = true; },
        );
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.userData = { url, loaded: false, failed: false };
        textures.set(look.id, tex);
        return tex;
    }

    function quad(corners, uvs) {
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(corners.flatMap((c) => { const v = toScene(...c); return [v.x, v.y, v.z]; }), 3));
        if (uvs) g.setAttribute("uv", new THREE.Float32BufferAttribute(uvs.flat(), 2));
        g.setIndex([0, 1, 2, 0, 2, 3]);
        return g;
    }

    function colourOf(look, shape) {
        if (chosen && chosen.look === look.id && chosen.index === shape.index) return CHOSEN_COLOR;
        if (shape.status === "made") return MADE_COLOR;
        if (shape.status === "already_made") return ALREADY_COLOR;
        return FOUND_COLOR;
    }

    function drawMat(host, look, mat) {
        const group = new THREE.Group();
        group.name = `look:${look.id}`;
        // The picture: near-left is its bottom-left (picture y runs down, world y away).
        const corners = [
            onMat(mat, 0, 1, MAT_LIFT), onMat(mat, 1, 1, MAT_LIFT),
            onMat(mat, 1, 0, MAT_LIFT), onMat(mat, 0, 0, MAT_LIFT),
        ];
        const picture = new THREE.Mesh(
            quad(corners, [[0, 0], [1, 0], [1, 1], [0, 1]]),
            new THREE.MeshBasicMaterial({ map: textureFor(look), side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }),
        );
        picture.userData.pick = { host, look: look.id, index: null };
        group.add(picture);
        pickables.push(picture);
        // Its border: dashed while it has no size of its own.
        const border = new THREE.LineLoop(
            new THREE.BufferGeometry().setFromPoints(corners.map((c) => toScene(c[0], c[1], c[2] + 0.5))),
            mat.sized
                ? new THREE.LineBasicMaterial({ color: 0xdddddd, transparent: true, opacity: 0.6 })
                : new THREE.LineDashedMaterial({ color: 0xdddddd, dashSize: 20, gapSize: 14 }),
        );
        if (!mat.sized) border.computeLineDistances();
        group.add(border);
        // The outlines, and a pick mesh under each one not made into a piece.
        for (const shape of look.shapes) {
            const pts = shape.points && shape.points.length >= 3
                ? shape.points
                : [[shape.min[0], shape.min[1]], [shape.max[0], shape.min[1]], [shape.max[0], shape.max[1]], [shape.min[0], shape.max[1]]];
            const world = pts.map(([fx, fy]) => onMat(mat, fx, fy, OUTLINE_LIFT));
            const colour = colourOf(look, shape);
            const material = shape.status === "already_made"
                ? new THREE.LineDashedMaterial({ color: colour, dashSize: 8, gapSize: 6 })
                : new THREE.LineBasicMaterial({ color: colour });
            const outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(world.map((c) => toScene(...c))), material);
            if (shape.status === "already_made") outline.computeLineDistances();
            outline.userData.shape = { look: look.id, index: shape.index, status: shape.status };
            group.add(outline);
            if (shape.status === "made") continue;
            const outlineShape = new THREE.Shape(world.map((c) => new THREE.Vector2(c[0], c[1])));
            const flat = new THREE.ShapeGeometry(outlineShape);
            // ShapeGeometry lies in its own xy plane: carried into the site's frame at the outline's height.
            const pos = flat.getAttribute("position");
            for (let i = 0; i < pos.count; i++) {
                const v = toScene(pos.getX(i), pos.getY(i), world[0][2]);
                pos.setXYZ(i, v.x, v.y, v.z);
            }
            flat.computeBoundingSphere();
            const pick = new THREE.Mesh(flat, new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide }));
            pick.userData.pick = { host, look: look.id, index: shape.index };
            group.add(pick);
            pickables.push(pick);
        }
        return group;
    }

    // A camera looks down onto its host: from an apex over the middle to the
    // mat's corners (the host's top, or a square on the floor, with no look).
    function drawFrustum(host, mat) {
        let rect = mat;
        if (!rect) {
            if (host === FLOOR) {
                const p = floorPoint(madeNames());
                rect = { centre: [p[0] + FLOOR_UNSIZED_MM / 2, p[1], p[2]], width: FLOOR_UNSIZED_MM, depth: FLOOR_UNSIZED_MM };
            } else {
                const b = hostBounds(host);
                if (!b) return null;
                rect = { centre: [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, b.max[2]], width: b.max[0] - b.min[0], depth: b.max[1] - b.min[1] };
            }
        }
        const h = Math.min(900, Math.max(150, 0.6 * Math.max(rect.width, rect.depth)));
        const [cx, cy, cz] = rect.centre;
        const apex = toScene(cx, cy, cz + h);
        const corners = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]].map(([u, v]) => toScene(cx + u * rect.width, cy + v * rect.depth, cz + OUTLINE_LIFT));
        const pts = [];
        for (let i = 0; i < 4; i++) pts.push(apex, corners[i], corners[i], corners[(i + 1) % 4]);
        const lines = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: FRUSTUM_COLOR, transparent: true, opacity: 0.8 }));
        lines.userData.host = host;
        return lines;
    }

    function madeNames() { return attached ? Object.keys(attached.made || {}) : []; }

    function badgeText(host) {
        const cam = cameraAt(host);
        const look = drawnAt(host);
        const bits = [];
        if (host === FLOOR) bits.push("floor");
        if (cam) bits.push(`📷 ${cam.label || "camera"}`);
        if (look) {
            const mat = look.mat && look.mat.width;
            bits.push(`look: ${look.shapes.length} shape${look.shapes.length === 1 ? "" : "s"}${mat ? "" : " · unsized"}`);
        }
        return bits.join(" · ");
    }

    function badgePoint(host) {
        if (!hostInView(host)) return null;
        const g = groups.get(host);
        if (host === FLOOR) {
            if (g && g.mat) return toScene(g.mat.centre[0], g.mat.centre[1], g.mat.centre[2] + BADGE_LIFT);
            const p = floorPoint(madeNames());
            return toScene(p[0] + FLOOR_UNSIZED_MM / 2, p[1], p[2] + BADGE_LIFT);
        }
        const b = hostBounds(host);
        if (!b) return null;
        return toScene((b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, b.max[2] + BADGE_LIFT);
    }

    function clearDrawn() {
        for (const g of groups.values()) {
            for (const o of [g.mats, g.frustum]) {
                if (!o) continue;
                scene.remove(o);
                o.traverse((x) => { x.geometry?.dispose(); if (x.material) x.material.dispose(); });  // textures are kept
            }
        }
        groups.clear();
        pickables.length = 0;
    }

    function redraw() {
        clearDrawn();
        const wanted = new Set();
        for (const host of hosts()) {
            const look = drawnAt(host);
            const mat = matOf(look);
            const entry = { mats: null, frustum: null, look, mat };
            if (look && mat) { entry.mats = drawMat(host, look, mat); scene.add(entry.mats); }
            if (cameraAt(host)) { entry.frustum = drawFrustum(host, mat); if (entry.frustum) scene.add(entry.frustum); }
            groups.set(host, entry);
            const key = keyFor(host);
            wanted.add(key);
            let badge = anchors.get(key);
            if (!badge) {
                badge = document.createElement("div");
                badge.className = "world-badge place-mark";
                badge.dataset.host = host;
                badge.title = host === FLOOR ? "Select the floor" : `Select ${host}`;
                badge.addEventListener("click", () => onSelect(host));
                anchors.add(key, badge, () => badgePoint(host), { offset: { x: 0, y: -30 } });
            }
            const cam = cameraAt(host);
            if (cam) badge.dataset.camera = cam.id; else delete badge.dataset.camera;
            badge.classList.toggle("has-camera", !!cam);
            badge.classList.toggle("has-look", !!look);
            badge.textContent = badgeText(host);
        }
        for (const key of anchors.keys()) if (key.startsWith("place:") && !wanted.has(key)) anchors.remove(key);
        // A texture is kept while its look is pinned here, and no longer.
        const pinned = new Set(looks().map((l) => l.id));
        for (const [id, tex] of textures) if (!pinned.has(id)) { tex.dispose(); textures.delete(id); }
        if (chosen && !looks().some((l) => l.id === chosen.look && l.shapes.some((s) => s.index === chosen.index && s.status !== "made"))) chosen = null;
        sync();
    }

    // Mats at the top level only; a frustum while its host is in view.
    function sync() {
        const top = atTopLevel();
        for (const [host, g] of groups) {
            if (g.mats) g.mats.visible = top;
            if (g.frustum) g.frustum.visible = hostInView(host);
        }
    }

    // --- fetching: one request at a time, a second ask folded into one more ---------------
    // Asked while a fetch is under way, the answer is one more fetch after it,
    // shared by everyone who asked meanwhile: never two at once, never a pile.
    function fetchOnce() {
        const asked = generation, name = site;
        const p = (async () => {
            let answer = null;
            try {
                const r = await fetch(`${base}/sites/${encodeURIComponent(name)}/attached`);
                answer = r.ok ? await r.json() : null;
            } catch (e) { answer = null; }
            if (asked === generation) {
                attached = answer || { site: name, cameras: [], looks: [], made: {} };
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
            drawnPick.clear();
            clearDrawn();
            for (const tex of textures.values()) tex.dispose();
            textures.clear();
            for (const key of anchors.keys()) if (key.startsWith("place:")) anchors.remove(key);
            queued = null;
            inflight = null;
        }
        return refresh();
    }

    function visiblePickables() {
        return pickables.filter((m) => { for (let o = m; o; o = o.parent) if (!o.visible) return false; return true; });
    }

    return {
        load,
        refresh,
        sync,
        /* The meshes a click can land on, to raycast with the nodes' own. */
        pickables: visiblePickables,
        /* What a pick mesh stands for: { host, look, index } (index null: the mat). */
        picked(object) { return (object && object.userData && object.userData.pick) || null; },
        choose(lookId, index) {
            const look = looks().find((l) => l.id === lookId);
            const shape = look && look.shapes.find((s) => s.index === index);
            if (!shape || shape.status === "made") return false;
            chosen = { look: lookId, index };
            redraw();
            return true;
        },
        unchoose() { if (!chosen) return; chosen = null; redraw(); },
        chosen() { return chosen ? { ...chosen } : null; },
        attached() { return attached; },
        cameras,
        looksAt,
        drawnAt,
        cameraAt,
        madeRecord(piece) { return attached && attached.made ? attached.made[piece] || null : null; },
        /* A point of a drawn look's picture (fractions, y down) in scene coordinates. */
        scenePoint(lookId, fx, fy) {
            for (const g of groups.values()) {
                if (g.look && g.look.id === lookId && g.mat) return toScene(...onMat(g.mat, fx, fy, MAT_LIFT));
            }
            return null;
        },
        /* What is drawn, for tests and for the status line. */
        state() {
            return [...groups.entries()].map(([host, g]) => ({
                host,
                look: g.look ? g.look.id : null,
                mat: g.mats ? { visible: g.mats.visible, centre: g.mat.centre, width: g.mat.width, depth: g.mat.depth, sized: g.mat.sized } : null,
                outlines: g.mats ? g.mats.children.filter((o) => o.userData.shape).map((o) => ({ ...o.userData.shape, colour: o.material.color.getHex() })) : [],
                texture: g.look && textures.get(g.look.id) ? { ...textures.get(g.look.id).userData } : null,
                frustum: g.frustum ? { visible: g.frustum.visible } : null,
                camera: cameraAt(host) ? cameraAt(host).id : null,
            }));
        },
        destroy() {
            clearDrawn();
            for (const tex of textures.values()) tex.dispose();
            textures.clear();
            for (const key of anchors.keys()) if (key.startsWith("place:")) anchors.remove(key);
            site = null; attached = null;
        },
    };
}
