/* Anchors: HTML fixed to a point in the world.
 *
 * A layer over the canvas holds elements, each bound to a function that
 * answers a point in the scene (three.js coordinates). Every frame the
 * point is projected through the camera and the element moved with a
 * transform -- no layout is read, so a dozen anchors cost nothing a person
 * can notice. An anchor behind the camera or well outside the canvas is
 * hidden; one whose point is behind something in the scene is dimmed
 * (class `behind`), tested with a ray every few frames rather than every
 * one. The layer does not take the pointer; its children do.
 *
 * Written here rather than fetched: the vendored three.js carries no
 * CSS2DRenderer, and nothing is fetched from a website while a person is
 * using the tool (static/vendor/three/README.md).
 */

import * as THREE from "three";

const MARGIN_PX = 80;       // an anchor this far outside the canvas is hidden
const OCCLUSION_EVERY = 6;  // frames between occlusion tests

export function mountAnchors({ container, canvas, camera, scene }) {
    const layer = document.createElement("div");
    layer.className = "anchor-layer";
    layer.style.cssText = "position:absolute;inset:0;overflow:hidden;pointer-events:none;";
    container.appendChild(layer);
    const anchors = new Map();
    const raycaster = new THREE.Raycaster();
    const v = new THREE.Vector3();
    const dir = new THREE.Vector3();
    let frame = 0;

    function occluded(point) {
        // A ray from the camera to the point: anything it hits first is in the way.
        dir.copy(point).sub(camera.position);
        const distance = dir.length();
        if (distance === 0) return false;
        raycaster.set(camera.position, dir.normalize());
        raycaster.far = distance - 1;
        const hits = raycaster.intersectObjects(scene.children, true);
        return hits.some((h) => h.object.isMesh && h.object.visible);
    }

    function update() {
        frame += 1;
        const w = canvas.clientWidth, h = canvas.clientHeight;
        if (!w || !h) return;
        const testOcclusion = frame % OCCLUSION_EVERY === 0;
        for (const a of anchors.values()) {
            const point = a.point();
            if (!point) { a.el.hidden = true; a.at = null; continue; }
            v.copy(point).project(camera);
            const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h;
            const visible = v.z < 1 && x > -MARGIN_PX && x < w + MARGIN_PX && y > -MARGIN_PX && y < h + MARGIN_PX;
            a.el.hidden = !visible;
            if (!visible) { a.at = null; continue; }
            a.at = { x, y };
            a.el.style.transform = `translate(${(x + a.offset.x).toFixed(1)}px, ${(y + a.offset.y).toFixed(1)}px) translate(-50%, -100%)`;
            if (testOcclusion && a.occlude) a.el.classList.toggle("behind", occluded(point));
        }
    }

    return {
        layer,
        /* Bind `el` to `point()` (a THREE.Vector3 in scene coordinates, or
         * null to hide). `offset` is in pixels; the element's bottom centre
         * sits on the point. */
        add(key, el, point, { offset = { x: 0, y: -6 }, occlude = true } = {}) {
            this.remove(key);
            el.style.position = "absolute";
            el.style.left = "0";
            el.style.top = "0";
            el.style.pointerEvents = "auto";
            el.hidden = true;
            el.dataset.anchor = key;
            layer.appendChild(el);
            anchors.set(key, { el, point, offset, occlude, at: null });
            return el;
        },
        remove(key) {
            const a = anchors.get(key);
            if (!a) return false;
            a.el.remove();
            anchors.delete(key);
            return true;
        },
        get(key) { return anchors.get(key) ? anchors.get(key).el : null; },
        has(key) { return anchors.has(key); },
        keys() { return [...anchors.keys()]; },
        /* Where an anchor was last drawn, in canvas pixels (null when hidden) -- for tests. */
        at(key) { const a = anchors.get(key); return a && a.at ? { ...a.at } : null; },
        update,
        clear() { for (const key of [...anchors.keys()]) this.remove(key); },
        destroy() { this.clear(); layer.remove(); },
    };
}
