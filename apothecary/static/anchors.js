/* Anchors: HTML fixed to a point in the world.
 *
 * A layer over the canvas holds elements, each bound to a function that
 * answers a point in the scene (three.js coordinates). Every frame the
 * point is projected through the camera and the element moved with a
 * transform. An anchor behind the camera or well outside the canvas is
 * hidden; one whose point is behind something in the scene is dimmed
 * (class `behind`), tested with a ray every few frames rather than every
 * one. The layer does not take the pointer; its children do.
 *
 * Badges are anchors too, and the layer is where they keep out of each
 * other's way, once for every badge. A badge is a small icon at its thing's
 * own spot; its words are a card (its `.badge-words` child) shown while the
 * pointer is on it or while its thing is selected. Two badges that would
 * overlap on screen step aside, side by side; three or more merge into one
 * count (×3), whose card lists each of them, until the view comes close
 * enough to part them. Open cards never overlap each other, nor what the page
 * asks to keep clear (keepClear: its hint bar, its depth ladder), and keep
 * EDGE_PX clear of the layer's edges. A badge's size is read once (and again
 * when what it says changes), an open card's each frame: there are at most a
 * few.
 *
 * Written here rather than fetched: the vendored three.js carries no
 * CSS2DRenderer, and nothing is fetched from a website while a person is
 * using the tool (static/vendor/three/README.md).
 */

import * as THREE from "three";

const MARGIN_PX = 80;       // an anchor this far outside the canvas is hidden
const OCCLUSION_EVERY = 6;  // frames between occlusion tests
const GAP_PX = 4;           // between two badges stepped aside
const MERGE_AT = 3;         // this many badges in one another's way merge into a count
const EDGE_PX = 10;         // an open card keeps this far from the layer's edges
const CARD_GAP_PX = 6;      // between two open cards, and between a card and its badge
const CLUSTER_W = 34;       // a count's width (its CSS width)
const LINGER_MS = 400;      // a card stays open this long after the pointer leaves, to be reached

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// A drawn badge's box, from its bottom centre (where its point is) and its size.
const boxOf = (x, y, w, h) => ({ l: x - w / 2, r: x + w / 2, t: y - h, b: y });
const meets = (a, b, gap) => a.l < b.r + gap && b.l < a.r + gap && a.t < b.b + gap && b.t < a.b + gap;

export function mountAnchors({ container, canvas, camera, scene, keepClear = () => [] }) {
    const layer = document.createElement("div");
    layer.className = "anchor-layer";
    layer.style.cssText = "position:absolute;inset:0;overflow:hidden;pointer-events:none;";
    container.appendChild(layer);
    const anchors = new Map();
    const clusters = new Map();  // the members' keys, joined -> { el, keys }
    const raycaster = new THREE.Raycaster();
    const v = new THREE.Vector3();
    const dir = new THREE.Vector3();
    let frame = 0;

    // The transform gizmo's handles and its (unrendered) picking plane are
    // meshes too, and the plane spans the whole scene: a badge would be
    // dimmed by it whenever the plane lay between the camera and the point,
    // which is most of the time. Nothing of the gizmo is in the way, nor is a
    // mesh drawn to be seen through (a faded wall, userData.passThrough).
    function inTheWay(object) {
        for (let o = object; o; o = o.parent) {
            if (o.isTransformControls || o.isTransformControlsGizmo || o.isTransformControlsPlane) return false;
        }
        return !object.userData.passThrough;
    }

    function occluded(point, ignore) {
        // A ray from the camera to the point: anything it hits first is in the way.
        dir.copy(point).sub(camera.position);
        const distance = dir.length();
        if (distance === 0) return false;
        raycaster.set(camera.position, dir.normalize());
        raycaster.far = distance - 1;
        const hits = raycaster.intersectObjects(scene.children, true);
        return hits.some((h) => h.object.isMesh && h.object.visible && inTheWay(h.object) && !(ignore && ignore(h.object)));
    }

    // A badge's size, read when it is first shown and after what it says changed;
    // and its border, which its card is placed inside.
    function sizeOf(a) {
        if (a.size) return a.size;
        const w = a.el.offsetWidth, h = a.el.offsetHeight;
        if (!w || !h) return { w: 24, h: 22, bx: 1, by: 1 };
        a.size = { w, h, bx: a.el.clientLeft, by: a.el.clientTop };
        return a.size;
    }
    const hovered = (x, now) => x.hover || now < x.hoverOff;

    // Who keeps out of whose way: each shown badge alone, then any two groups
    // whose drawn boxes meet joined and laid out again, until none meet. One
    // badge stands at its point; two step aside, side by side about their middle,
    // each at its own height; three or more are one count at their middle.
    function layout(shown) {
        let groups = shown.map((a) => place({ members: [a] }));
        for (let changed = true; changed && groups.length > 1;) {
            changed = false;
            outer: for (let i = 0; i < groups.length; i++) {
                for (let j = i + 1; j < groups.length; j++) {
                    if (!meets(groups[i].box, groups[j].box, GAP_PX)) continue;
                    const joined = place({ members: [...groups[i].members, ...groups[j].members] });
                    groups = groups.filter((_, k) => k !== i && k !== j);
                    groups.push(joined);
                    changed = true;
                    break outer;
                }
            }
        }
        return groups;
    }
    function place(group) {
        const m = group.members;
        if (m.length === 1) {
            const a = m[0], { w, h } = sizeOf(a);
            a.drawn = { x: a.want.x, y: a.want.y };
            group.box = boxOf(a.want.x, a.want.y, w, h);
            return group;
        }
        const x = m.reduce((s, a) => s + a.want.x, 0) / m.length;
        const y = m.reduce((s, a) => s + a.want.y, 0) / m.length;
        if (m.length >= MERGE_AT) {
            group.at = { x, y };
            group.box = boxOf(x, y, CLUSTER_W, sizeOf(m[0]).h);
            return group;
        }
        const ordered = [...m].sort((a, b) => a.want.x - b.want.x || (a.key < b.key ? -1 : 1));
        const total = ordered.reduce((s, a) => s + sizeOf(a).w, 0) + GAP_PX * (ordered.length - 1);
        let left = x - total / 2;
        group.box = null;
        for (const a of ordered) {
            const { w, h } = sizeOf(a);
            a.drawn = { x: left + w / 2, y: a.want.y };
            const box = boxOf(a.drawn.x, a.drawn.y, w, h);
            group.box = group.box ? { l: Math.min(group.box.l, box.l), r: Math.max(group.box.r, box.r), t: Math.min(group.box.t, box.t), b: Math.max(group.box.b, box.b) } : box;
            left += w + GAP_PX;
        }
        return group;
    }

    // A count standing for several badges: its card lists each, and a row's
    // click is that badge's click. Kept while the same badges are merged.
    function clusterFor(keys) {
        const id = keys.join("\u0000");
        let c = clusters.get(id);
        if (c) return c;
        const el = document.createElement("div");
        el.className = "world-badge cluster";
        el.style.cssText = "position:absolute;left:0;top:0;pointer-events:auto;";
        el.innerHTML = `<span class="badge-icon">×${keys.length}</span><div class="badge-words"></div>`;
        el.setAttribute("aria-label", "Badges standing close together: zoom in to part them");
        el.addEventListener("click", (ev) => {
            const row = ev.target.closest(".cluster-row");
            const a = row && anchors.get(row.dataset.anchor);
            if (a) a.el.click();
        });
        el.addEventListener("pointerenter", () => { c.hover = true; });
        el.addEventListener("pointerleave", () => { c.hover = false; c.hoverOff = performance.now() + LINGER_MS; });
        layer.appendChild(el);
        c = { el, keys, hover: false, hoverOff: 0, said: null };
        clusters.set(id, c);
        return c;
    }
    function fillCluster(c, open) {
        const rows = c.keys.map((k) => {
            const a = anchors.get(k);
            const icon = a.el.querySelector(".badge-icon"), words = a.el.querySelector(".badge-words");
            return `<div class="cluster-row${a.selected && a.selected() ? " selected" : ""}" data-anchor="${esc(k)}"><span class="badge-icon">${icon ? icon.innerHTML : ""}</span> ${words ? words.innerHTML : ""}</div>`;
        }).join("");
        if (open && rows !== c.said) { c.el.querySelector(".badge-words").innerHTML = rows; c.said = rows; }
    }

    // What else stands over the world and is not to be covered (keepClear: the
    // hint bar, the depth ladder), as boxes in the layer's pixels; a thing hidden
    // or faded out is not in the way.
    function furniture() {
        if (!keepClear) return [];
        const base = layer.getBoundingClientRect();
        return keepClear().filter((el) => el && !el.hidden && el.offsetWidth && parseFloat(getComputedStyle(el).opacity) > 0.05).map((el) => {
            const r = el.getBoundingClientRect();
            return { l: r.left - base.left, r: r.right - base.left, t: r.top - base.top, b: r.bottom - base.top };
        });
    }

    // The open cards, placed one after another: above the badge, else below,
    // right or left of it, each kept EDGE_PX inside the layer; the first place
    // that meets no card already placed (nor the furniture), else above what it
    // meets.
    function placeCards(open, w, h) {
        const placed = open.length ? furniture() : [];
        const cardsFrom = placed.length;
        for (const { el, card, box, border } of open) {
            el.classList.add("open");
            card.style.maxWidth = `${Math.max(120, w - 2 * EDGE_PX)}px`;
            const cw = card.offsetWidth, ch = card.offsetHeight;
            const cx = (box.l + box.r) / 2, cy = (box.t + box.b) / 2;
            const clamp = (p) => ({
                l: Math.max(EDGE_PX, Math.min(w - EDGE_PX - cw, p.l)),
                t: Math.max(EDGE_PX, Math.min(h - EDGE_PX - ch, p.t)),
            });
            const tries = [
                { l: cx - cw / 2, t: box.t - CARD_GAP_PX - ch },
                { l: cx - cw / 2, t: box.b + CARD_GAP_PX },
                { l: box.r + CARD_GAP_PX, t: cy - ch / 2 },
                { l: box.l - CARD_GAP_PX - cw, t: cy - ch / 2 },
            ].map(clamp).map((p) => ({ l: p.l, t: p.t, r: p.l + cw, b: p.t + ch }));
            let at = tries.find((p) => !placed.some((q) => meets(p, q, CARD_GAP_PX)));
            if (!at) {
                // Nowhere beside its badge is clear: above whatever it meets, as far
                // up as it has to go, but never past the top edge.
                at = tries[0];
                for (let moved = true; moved;) {
                    moved = false;
                    for (const q of placed) {
                        if (!meets(at, q, CARD_GAP_PX) || q.t - CARD_GAP_PX - ch < EDGE_PX) continue;
                        at = { ...at, t: q.t - CARD_GAP_PX - ch, b: q.t - CARD_GAP_PX };
                        moved = true;
                    }
                }
            }
            placed.push(at);
            // The card is placed inside its badge's border: from there, to where it goes.
            card.style.transform = `translate(${(at.l - box.l - border.x).toFixed(1)}px, ${(at.t - box.t - border.y).toFixed(1)}px)`;
        }
        return placed.slice(cardsFrom);
    }

    let lastCards = [];
    function update() {
        frame += 1;
        const w = canvas.clientWidth, h = canvas.clientHeight;
        if (!w || !h) return;
        const testOcclusion = frame % OCCLUSION_EVERY === 0;
        const shown = [];
        for (const a of anchors.values()) {
            const point = a.point();
            a.drawn = null;
            if (!point) { a.el.hidden = true; a.at = null; continue; }
            v.copy(point).project(camera);
            const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h;
            const visible = v.z < 1 && x > -MARGIN_PX && x < w + MARGIN_PX && y > -MARGIN_PX && y < h + MARGIN_PX;
            a.el.hidden = !visible;
            if (!visible) { a.at = null; continue; }
            a.at = { x, y };
            a.want = { x: x + a.offset.x, y: y + a.offset.y };
            if (testOcclusion && a.occlude) a.el.classList.toggle("behind", occluded(point, a.ignore));
            shown.push(a);
        }
        const groups = layout(shown);
        const open = [], wanted = new Set(), now = performance.now();
        for (const g of groups) {
            if (g.members.length >= MERGE_AT) {
                const keys = g.members.map((a) => a.key).sort();
                const c = clusterFor(keys);
                wanted.add(keys.join("\u0000"));
                for (const a of g.members) { a.el.classList.add("merged"); a.el.classList.remove("aside", "open"); a.drawn = { ...g.at }; }
                c.el.hidden = false;
                c.el.classList.toggle("behind", g.members.every((a) => a.el.classList.contains("behind")));
                c.el.style.transform = `translate(${g.at.x.toFixed(1)}px, ${g.at.y.toFixed(1)}px) translate(-50%, -100%)`;
                const selected = g.members.some((a) => a.selected && a.selected());
                const isOpen = hovered(c, now) || selected;
                fillCluster(c, isOpen);
                if (isOpen) open.push({ el: c.el, card: c.el.querySelector(".badge-words"), box: g.box, border: { x: 1, y: 1 }, selected });
                else c.el.classList.remove("open");
                continue;
            }
            for (const a of g.members) {
                a.el.classList.remove("merged");
                a.el.classList.toggle("aside", g.members.length > 1);
                a.el.style.transform = `translate(${a.drawn.x.toFixed(1)}px, ${a.drawn.y.toFixed(1)}px) translate(-50%, -100%)`;
                const card = a.el.querySelector(".badge-words");
                const selected = !!(a.selected && a.selected());
                a.el.classList.toggle("selected", selected);
                if (card && card.textContent.trim() && (hovered(a, now) || selected)) {
                    const { w: bw, h: bh, bx, by } = sizeOf(a);
                    open.push({ el: a.el, card, box: boxOf(a.drawn.x, a.drawn.y, bw, bh), border: { x: bx, y: by }, selected });
                } else a.el.classList.remove("open");
            }
        }
        for (const [id, c] of clusters) if (!wanted.has(id)) { c.el.remove(); clusters.delete(id); }
        // The selected thing's card first, so the one being looked at holds its place.
        open.sort((p, q) => Number(q.selected) - Number(p.selected));
        lastCards = placeCards(open, w, h);
    }

    function markHover(a) {
        a.el.addEventListener("pointerenter", () => { a.hover = true; });
        a.el.addEventListener("pointerleave", () => { a.hover = false; a.hoverOff = performance.now() + LINGER_MS; });
    }

    return {
        layer,
        /* Bind `el` to `point()` (a THREE.Vector3 in scene coordinates, or
         * null to hide). `offset` is in pixels; the element's bottom centre
         * sits on the point. `selected()` says whether its thing is selected,
         * which opens its card; `ignore(mesh)` names a mesh that never dims it
         * (the one its thing is inside). */
        add(key, el, point, { offset = { x: 0, y: -6 }, occlude = true, selected = null, ignore = null } = {}) {
            this.remove(key);
            el.style.position = "absolute";
            el.style.left = "0";
            el.style.top = "0";
            el.style.pointerEvents = "auto";
            el.hidden = true;
            el.dataset.anchor = key;
            layer.appendChild(el);
            const a = { key, el, point, offset, occlude, selected, ignore, at: null, want: null, drawn: null, size: null, hover: false, hoverOff: 0 };
            markHover(a);
            anchors.set(key, a);
            return el;
        },
        /* A badge: an element of class `world-badge` (and `className`) holding
         * its icon and its words, bound as add() binds one. The caller listens
         * to it and says what it says (say). */
        badge(key, point, { className = "", title = "", ...options } = {}) {
            const el = document.createElement("div");
            el.className = `world-badge${className ? ` ${className}` : ""}`;
            if (title) el.title = title;
            el.innerHTML = '<span class="badge-icon"></span><div class="badge-words"></div>';
            return this.add(key, el, point, options);
        },
        /* What a badge says: its icon, and its words as markup (escaped by the caller). */
        say(key, { icon, words }) {
            const a = anchors.get(key);
            if (!a) return false;
            const iconEl = a.el.querySelector(".badge-icon"), wordsEl = a.el.querySelector(".badge-words");
            if (iconEl && iconEl.textContent !== icon) { iconEl.textContent = icon; a.size = null; }
            if (wordsEl && wordsEl.innerHTML !== words) wordsEl.innerHTML = words;
            return true;
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
        /* Where an anchor's point was last projected, in canvas pixels (null when hidden) -- for tests. */
        at(key) { const a = anchors.get(key); return a && a.at ? { ...a.at } : null; },
        /* Where its badge was last drawn: its box in canvas pixels, whether it
         * stepped aside, and the count it merged into (null when it did not). */
        drawn(key) {
            const a = anchors.get(key);
            if (!a || !a.at || !a.drawn) return null;
            const { w, h } = sizeOf(a);
            const merged = a.el.classList.contains("merged");
            const cluster = merged ? [...clusters.values()].find((c) => c.keys.includes(key)) : null;
            return { ...boxOf(a.drawn.x, a.drawn.y, merged ? CLUSTER_W : w, h), aside: a.el.classList.contains("aside"), merged: cluster ? cluster.keys.length : null };
        },
        /* The open cards as last placed, in canvas pixels -- for tests. */
        cards() { return lastCards.map((c) => ({ ...c })); },
        update,
        clear() { for (const key of [...anchors.keys()]) this.remove(key); },
        destroy() { this.clear(); layer.remove(); },
    };
}
