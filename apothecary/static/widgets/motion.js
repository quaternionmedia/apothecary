/* Motion: a part's pieces moved through its motion, in a window of the Part group
 * (docs/airgap.md, The motion view; docs/parts-authoring.md, A part that moves).
 *
 * For the selected piece's part, when its wrapper declares a motion (BasePart.motion),
 * the window asks the server for the motion's table (GET /parts/{ref}/motion, motion/1:
 * apothecary/motion.py, sampled from the wrapper's own pose function), draws each piece
 * once through OpenSCAD as the part rests -- the still one and each that moves, alone,
 * in its own frame (world.loadPiece) -- hangs the moving ones from the still one, and
 * from then on only moves them: a slider over the motion's parameter, Play and Pause,
 * Back and Step a sample at a time, Reset. No OpenSCAD runs while it plays.
 *
 * A piece the table bends -- a flexure's leaves -- is drawn from the outlines the table
 * carries at each sample, extruded, taken point by point between two samples: the
 * model's geometry at that pose, not a simulation of the bending, which the window says.
 * Each gap the table follows is drawn as a mark where it is least, on each body, and
 * read as a number with its unit, both the nearest sample's as the server measured it:
 * the page computes no gap. What is bought (pins, inserts in pockets) is drawn in a
 * colour of its own while Bought is ticked, riding the piece it sits in; it is never in
 * a printed STL.
 *
 * Drawn, the part is framed once, looking along the axis its pieces turn about, a little
 * off it so its depth reads (world.frame); the still piece is drawn see-through, so what
 * moves inside it -- a rotor in its housing -- is seen; the moving pieces take its colour.
 *
 * Each button is a cell of the ring's Part › View › Motion (part:motion:*), and wears
 * its address in its title (world.addressOf); Play's says Pause while it plays. The
 * slider is no cell, and wears none.
 *
 * mountMotion(root, world) -> { act(verb), follow(), state(), table() }
 *   world: { base, selected() -> { key, ref, node, params } | null, loadPiece(node, ref,
 *   values, piece) -> Promise<{ mesh, measured }>, swap(node, object), meshOf(key),
 *   redraw(), shown(), addressOf(action), frame(object, along), view() }
 *   act: "open" | "play" | "back" | "step" | "reset" | "bought" -> Promise<{ said } |
 *   { refused }>
 */

import * as THREE from "three";
import { advance, gapsAt, outlinesAt, placeIn, poseAt, stepFrom } from "/static/part_motion.js";

// What is bought, drawn in a colour of its own; and where a gap is least, in the Part
// group's colour (static/tokens.css), the Motion window's: no layer's, so the
// measurement's magenta stays the measurement's.
const BOUGHT_COLOUR = 0x5f86b3;
const MARK_TOKEN = "--group-part";
const MARK_FALLBACK = "#a9c868";
// Seconds a motion's whole range takes while it plays.
const SPAN = 6;
// The still piece, seen through; and how far off the turning axis the part is framed from.
const STILL_OPACITY = 0.3;
const FRAME_TILT = (20 * Math.PI) / 180;

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const scene = (x, y, z) => new THREE.Vector3(x, z, -y);
const middle = (box) => [0, 1, 2].map((i) => (box.min_point[["x", "y", "z"][i]] + box.max_point[["x", "y", "z"][i]]) / 2);
const unit = (u) => (u === "deg" ? "°" : ` ${u}`);
const said = (v, u) => `${Number(v).toFixed(u === "deg" ? 1 : 2)}${unit(u)}`;

// The window's few rules, written once into the page by the first window mounted.
const STYLE = `
.motion-window { padding: 8px 10px; font-size: 13px; line-height: 1.4; }
.motion-window .motion-controls { display: flex; gap: 8px; align-items: center; margin: 6px 0; }
.motion-window .motion-at { flex: 1; min-width: 80px; }
.motion-window .motion-buttons { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.motion-window .motion-gaps { margin: 8px 0; padding-left: 18px; }
.motion-window .motion-gap-value { color: var(--group-part, #a9c868); }
.motion-window .motion-turned, .motion-window .motion-said { margin: 4px 0; opacity: 0.8; font-size: 12px; }`;

export function mountMotion(root, world) {
    if (!document.getElementById("motion-window-style")) {
        const style = document.createElement("style");
        style.id = "motion-window-style";
        style.textContent = STYLE;
        document.head.append(style);
    }
    const motionEl = root;
    motionEl.classList.add("motion-window");
    let subject = null;  // { key, ref, params, node }
    let table = null;
    let built = null;  // { key, still, moving: { name: { object, centre } }, bent, marks, bought, stillCentre }
    let state = { value: 0, cycle: 0, way: 1 };
    let playing = false, frame = null, last = 0, busy = null;
    let showBought = true, note = "";
    let framed = null;  // the key of the part last framed: framed once, when first drawn

    const taught = (action) => { const at = world.addressOf ? world.addressOf(action) : null; return at ? ` · ⌗${at}` : ""; };
    // Play's tip says what a press does now: Pause while it plays.
    const playTip = () => `${playing ? "Pause" : "Play"}${taught("part:motion:play")}`;

    function paint() {
        if (!subject) {
            motionEl.innerHTML = `<p class="section-empty motion-none">${esc(note || "Select a part whose pieces move -- the rolling rotor, the flexure rotor, the cycloidal disc -- and its motion plays here.")}</p>`;
            return;
        }
        if (!table) {
            motionEl.innerHTML = `<p class="section-empty motion-none">${esc(note || `${subject.ref}: asking for its motion…`)}</p>`;
            return;
        }
        const [lo, hi] = table.range;
        const gaps = gapsAt(table, state.value);
        const turned = table.pieces.filter((p) => p.drawn).map((p) => `${p.label} turned ${said(poseAt(table, p, state.value, state.cycle)[2], "deg")}`);
        motionEl.innerHTML = `
            <div class="motion-head"><strong>${esc(subject.ref)}</strong>: its ${esc(table.label)} from ${lo} to ${hi}${esc(unit(table.unit))}, ${table.samples.length} samples</div>
            <div class="motion-controls">
              <input type="range" class="motion-at" min="${lo}" max="${hi}" step="any" value="${state.value}" aria-label="${esc(table.label)}" title="${esc(`${table.label}: drag through the motion; Back and Step move a sample at a time`)}">
              <span class="motion-value">${esc(table.label)} ${esc(said(state.value, table.unit))}${table.cyclic && state.cycle ? `, cycle ${state.cycle}` : ""}</span>
            </div>
            <div class="motion-buttons">
              <button type="button" class="motion-play" data-motion="play" title="${esc(playTip())}">${playing ? "⏸ Pause" : "▶ Play"}</button>
              <button type="button" class="motion-back" data-motion="back" title="${esc(`The sample before${taught("part:motion:back")}`)}">◀ Back</button>
              <button type="button" class="motion-step" data-motion="step" title="${esc(`The sample after${taught("part:motion:step")}`)}">Step ▶</button>
              <button type="button" class="motion-reset" data-motion="reset" title="${esc(`Back to ${lo}${unit(table.unit)}${taught("part:motion:reset")}`)}">Reset</button>
              <label title="${esc(`What is bought -- pins, inserts in pockets -- drawn in a colour of its own; never in a printed STL${taught("part:motion:bought")}`)}"><input type="checkbox" class="motion-bought"${showBought ? " checked" : ""}> Bought</label>
            </div>
            <ul class="motion-gaps">${gaps.map((g) => `<li data-gap="${esc(g.name)}"><span class="motion-gap-label">${esc(g.label)}</span>: least <strong class="motion-gap-value">${esc(said(g.least, g.unit))}</strong> at ${esc(table.label)} ${esc(said(g.at, table.unit))}${g.marks.length > 1 ? `, ${g.marks.length} places` : ""}</li>`).join("")}</ul>
            <p class="motion-turned">${esc(turned.join("; "))}</p>
            <p class="motion-said">Each gap is the server's at the sample nearest, measured from the outlines (apothecary/gap_geometry.py); between two samples the pieces are taken in proportion, at most ${esc(table.interpolation.error_mm.toFixed(4))} mm from where the part's own pose puts them. ${esc(table.note)}${table.bent.length ? " The bent pieces are drawn from the model's outline at each sample, not simulated." : ""} No force, torque or flux is computed.</p>`;
    }

    // Only what changes while it plays, so a control under the pointer is not drawn afresh.
    function refresh() {
        if (!table || !motionEl.querySelector(".motion-at")) { paint(); return; }
        const at = motionEl.querySelector(".motion-at");
        if (document.activeElement !== at) at.value = String(state.value);
        motionEl.querySelector(".motion-value").textContent = `${table.label} ${said(state.value, table.unit)}${table.cyclic && state.cycle ? `, cycle ${state.cycle}` : ""}`;
        for (const g of gapsAt(table, state.value)) {
            const row = motionEl.querySelector(`[data-gap="${CSS.escape(g.name)}"]`);
            if (row) row.innerHTML = `<span class="motion-gap-label">${esc(g.label)}</span>: least <strong class="motion-gap-value">${esc(said(g.least, g.unit))}</strong> at ${esc(table.label)} ${esc(said(g.at, table.unit))}${g.marks.length > 1 ? `, ${g.marks.length} places` : ""}`;
        }
        const turned = table.pieces.filter((p) => p.drawn).map((p) => `${p.label} turned ${said(poseAt(table, p, state.value, state.cycle)[2], "deg")}`);
        motionEl.querySelector(".motion-turned").textContent = turned.join("; ");
        const play = motionEl.querySelector(".motion-play");
        play.textContent = playing ? "⏸ Pause" : "▶ Play";
        play.title = playTip();
    }

    // ---- the pieces, drawn once -----------------------------------------------------

    function cylinder(insert, centre, material) {
        const [z0, z1] = insert.z;
        const mesh = new THREE.Mesh(new THREE.CylinderGeometry(insert.diameter / 2, insert.diameter / 2, z1 - z0, 32), material);
        mesh.position.copy(scene(insert.at[0] - centre[0], insert.at[1] - centre[1], (z0 + z1) / 2 - centre[2]));
        mesh.name = `bought:${insert.name}`;
        return mesh;
    }

    function extruded(outline, z0, z1, still) {
        const shape = new THREE.Shape(outline.map(([x, y]) => new THREE.Vector2(x, y)));
        const geometry = new THREE.ExtrudeGeometry(shape, { depth: z1 - z0, bevelEnabled: false });
        geometry.rotateX(-Math.PI / 2);  // the site's z up is three.js's y
        geometry.translate(-still[0], z0 - still[2], still[1]);
        return geometry;
    }

    // The pieces of `asked`'s part drawn and hung together, or null where the window moved
    // off `asked` while they were drawn: nothing of them is swapped into the world then.
    async function build(asked) {
        const node = asked.node;
        const values = (piece) => ({ ...table.params, [table.piece_param]: piece });
        const drawn = table.pieces.filter((p) => p.drawn);
        const [still, ...moving] = await Promise.all([
            world.loadPiece(node, asked.ref, values(table.still.piece), table.still.piece),
            ...drawn.map((p) => world.loadPiece(node, asked.ref, values(p.piece), p.piece)),
        ]);
        if (subject !== asked) {
            for (const { mesh } of [still, ...moving]) mesh?.traverse((o) => { o.geometry?.dispose(); o.material?.dispose?.(); });
            return null;
        }
        if (!still.measured || moving.some((m) => !m.measured)) throw new Error("a piece came back without its measured box");
        const stillCentre = middle(still.measured);
        const group = still.mesh;
        const edges = group.getObjectByName("edges");
        // The still piece seen through, the moving ones solid. The page colours the part's
        // own material (the still piece's): each moving piece takes its colour from it as
        // it is drawn, so they are coloured, faded and selected with the part.
        const solid = group.material, ghost = solid.clone();
        Object.assign(ghost, { transparent: true, opacity: STILL_OPACITY, depthWrite: false });
        group.material = ghost;
        const follows = () => {
            solid.color.copy(ghost.color);
            if (solid.emissive && ghost.emissive) solid.emissive.copy(ghost.emissive);
        };
        const out = { key: asked.key, group, stillCentre, moving: {}, bent: [], marks: new THREE.Group(), bought: [] };
        const boughtMaterial = new THREE.MeshPhongMaterial({ color: BOUGHT_COLOUR });
        const seat = (holder, insert, centre) => {
            const mesh = cylinder(insert, centre, boughtMaterial);
            holder.add(mesh);
            out.bought.push(mesh);
        };
        for (const insert of table.still.inserts) seat(group, insert, stillCentre);
        table.pieces.forEach((p) => {
            let object, centre;
            const k = drawn.indexOf(p);
            if (k >= 0) {
                object = moving[k].mesh;
                centre = middle(moving[k].measured);
                object.material.dispose();
                object.material = solid;
                object.onBeforeRender = follows;
                const own = object.getObjectByName("edges");
                if (own && edges) { own.material.dispose(); own.material = edges.material; }
            } else {
                object = new THREE.Group();  // bought and not printed: only what it carries
                centre = [0, 0, 0];
            }
            object.quaternion.identity();
            object.name = `piece:${p.piece}`;
            for (const insert of p.inserts) seat(object, insert, centre);
            group.add(object);
            out.moving[p.piece] = { object, centre };
        });
        for (const b of table.bent) {
            const mesh = new THREE.Mesh(new THREE.BufferGeometry(), solid);
            mesh.onBeforeRender = follows;
            mesh.name = `bent:${b.name}`;
            group.add(mesh);
            out.bent.push({ b, meshes: [mesh] });
        }
        out.marks.name = "motion-marks";
        group.add(out.marks);
        // A click on a moving piece is a click on the part, as a machine's pieces are.
        const hit = group.raycast.bind(group);
        group.raycast = (raycaster, hits) => {
            hit(raycaster, hits);
            for (const { object } of Object.values(out.moving)) {
                if (!object.isMesh) continue;
                const from = hits.length;
                THREE.Mesh.prototype.raycast.call(object, raycaster, hits);
                for (let h = from; h < hits.length; h++) hits[h].object = group;
            }
        };
        group.userData.motion = { ref: asked.ref, param: table.param };
        world.swap(node, group);
        return out;
    }

    function pose() {
        if (!built || !table) return;
        for (const p of table.pieces) {
            const { object, centre } = built.moving[p.piece];
            const at = placeIn(poseAt(table, p, state.value, state.cycle), centre, built.stillCentre);
            object.position.set(...at.position);
            object.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), at.angle);
        }
        for (const { b, meshes } of built.bent) {
            const [z0, z1] = b.z;
            const parts = outlinesAt(table, b, state.value).map((o) => extruded(o, z0, z1, built.stillCentre));
            meshes[0].geometry.dispose();
            meshes[0].geometry = parts.length ? merged(parts) : new THREE.BufferGeometry();
        }
        for (const m of built.bought) m.visible = showBought;
        drawMarks();
        world.redraw();
    }

    // Several extrusions as one geometry: each leaf's triangles one after another.
    function merged(parts) {
        const positions = [], normals = [];
        for (const g of parts) {
            const flat = g.index ? g.toNonIndexed() : g;
            positions.push(...flat.attributes.position.array);
            flat.computeVertexNormals();
            normals.push(...flat.attributes.normal.array);
            g.dispose();
        }
        const out = new THREE.BufferGeometry();
        out.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        out.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
        return out;
    }

    function drawMarks() {
        const group = built.marks;
        for (const child of [...group.children]) { group.remove(child); child.geometry?.dispose(); child.material?.dispose(); }
        const c = built.stillCentre;
        const reach = Math.max(...table.pieces.map((p) => p.reach || 1), 1);
        const size = Math.max(0.4, reach * 0.015);
        const colour = getComputedStyle(document.documentElement).getPropertyValue(MARK_TOKEN).trim() || MARK_FALLBACK;
        // The least of each gap drawn whole, its other places (a pin each) fainter.
        for (const g of gapsAt(table, state.value)) {
            g.marks.forEach((m, k) => {
                const look = { color: colour, depthTest: false, transparent: true, opacity: k === 0 ? 1 : 0.55 };
                for (const [p, r] of [[m.on, size], [m.to, size * 0.7]]) {
                    const dot = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 8), new THREE.MeshBasicMaterial(look));
                    dot.position.copy(scene(p[0] - c[0], p[1] - c[1], g.z - c[2]));
                    dot.renderOrder = 10;
                    dot.name = `mark:${g.name}`;
                    group.add(dot);
                }
                const line = new THREE.Line(
                    new THREE.BufferGeometry().setFromPoints([scene(m.on[0] - c[0], m.on[1] - c[1], g.z - c[2]), scene(m.to[0] - c[0], m.to[1] - c[1], g.z - c[2])]),
                    new THREE.LineBasicMaterial(look),
                );
                line.renderOrder = 10;
                group.add(line);
            });
        }
    }

    // ---- what is moved, and when ----------------------------------------------------

    // The selected piece's part, when it has a motion: its table asked for, its pieces
    // drawn once. Again only when the subject, its values or its drawing changed. What
    // comes back for a subject the window has since moved off (the selection changed while
    // it was asked for) is dropped: the window is already on the piece selected now.
    async function prepare() {
        const chosen = world.selected();
        const same = chosen && subject && chosen.key === subject.key && JSON.stringify(chosen.params) === JSON.stringify(subject.params);
        if (!chosen) { subject = null; table = null; built = null; note = ""; paint(); return { refused: "Nothing is selected: select a part whose pieces move" }; }
        if (!same) { stop(); subject = chosen; table = null; built = null; state = { value: 0, cycle: 0, way: 1 }; note = ""; paint(); }
        const asked = subject;
        const dropped = () => ({ refused: `${asked.ref}: the selection moved on before its motion was drawn`, dropped: true });
        if (!table) {
            const q = encodeURIComponent(JSON.stringify(asked.params || {}));
            const r = await fetch(`${world.base}/parts/${encodeURIComponent(asked.ref)}/motion?params=${q}`);
            if (subject !== asked) return dropped();
            if (!r.ok) {
                const detail = await r.json().then((b) => b.detail).catch(() => r.statusText);
                if (subject !== asked) return dropped();
                note = r.status === 404 ? `${asked.ref} declares no motion: its pieces do not move against one another.` : `${asked.ref}: ${detail}`;
                paint();
                return { refused: note };
            }
            const answer = await r.json();
            if (subject !== asked) return dropped();
            table = answer;
            state = { value: table.range[0], cycle: 0, way: 1 };
            paint();
        }
        if (!built || world.meshOf(asked.key) !== built.group) {
            note = `${asked.ref}: drawing its pieces once…`;
            let made;
            try {
                made = await build(asked);
            } catch (error) {
                if (subject !== asked) return dropped();
                built = null;
                note = `${asked.ref}'s pieces could not be drawn: ${error.message}`;
                paint();
                return { refused: note };
            }
            if (!made || subject !== asked) return dropped();
            built = made;
            note = "";
            paint();
            pose();
            if (framed !== subject.key) { framed = subject.key; framePart(); }
        }
        return { said: `${subject.ref}: its ${table.label}, ${table.samples.length} samples` };
    }

    // The part framed looking down the axis its pieces turn about (its own up), tilted
    // FRAME_TILT towards where the view already is, so the turning reads and its depth too.
    function framePart() {
        if (!world.frame || !built) return;
        const group = built.group;
        group.updateWorldMatrix(true, true);
        const axis = new THREE.Vector3(0, 1, 0).applyQuaternion(group.getWorldQuaternion(new THREE.Quaternion())).normalize();
        const view = world.view ? world.view().normalize() : new THREE.Vector3(1, 0, 0);
        let side = view.clone().addScaledVector(axis, -view.dot(axis));
        if (side.lengthSq() < 1e-6) {
            const across = Math.abs(axis.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
            side = across.addScaledVector(axis, -across.dot(axis));
        }
        side.normalize();
        world.frame(group, axis.multiplyScalar(Math.cos(FRAME_TILT)).addScaledVector(side, Math.sin(FRAME_TILT)));
    }

    function tick(now) {
        if (!playing) return;
        const seconds = last ? Math.min(0.1, (now - last) / 1000) : 0;
        last = now;
        state = advance(table, state, seconds, SPAN);
        pose();
        refresh();
        frame = requestAnimationFrame(tick);
    }
    function start() { if (playing) return; playing = true; last = 0; frame = requestAnimationFrame(tick); }
    function stop() { playing = false; if (frame) cancelAnimationFrame(frame); frame = null; }

    async function act(verb) {
        // One act at a time: a second press while the pieces are being drawn waits for it.
        if (busy) await busy.catch(() => null);
        const done = (async () => {
            const ready = await prepare();
            if (ready.refused) return ready;
            const [lo] = table.range;
            if (verb === "open") return ready;
            if (verb === "play") { if (playing) stop(); else start(); refresh(); return { said: `${subject.ref}: ${playing ? "playing" : "paused at"} ${table.label} ${said(state.value, table.unit)}` }; }
            if (verb === "step" || verb === "back") {
                stop();
                state = { ...state, value: stepFrom(table, state.value, verb === "step" ? 1 : -1) };
            } else if (verb === "reset") {
                stop();
                state = { value: lo, cycle: 0, way: 1 };
            } else if (verb === "bought") {
                showBought = !showBought;
            } else {
                return { refused: `Motion has no ${verb}` };
            }
            pose();
            paint();
            const g = gapsAt(table, state.value)[0];
            return { said: `${subject.ref}: ${table.label} ${said(state.value, table.unit)}${g ? `, ${g.label} ${said(g.least, g.unit)}` : ""}${verb === "bought" ? (showBought ? "; what is bought drawn" : "; what is bought hidden") : ""}` };
        })();
        busy = done;
        return done;
    }

    function clicked(ev) {
        const button = ev.target.closest("[data-motion]");
        if (button) act(button.dataset.motion);
    }
    function scrubbed(ev) {
        if (!ev.target.classList.contains("motion-at") || !table) return;
        stop();
        state = { ...state, value: Number(ev.target.value) };
        pose();
        refresh();
    }
    function ticked(ev) {
        if (ev.target.classList.contains("motion-bought")) act("bought");
    }
    motionEl.addEventListener("click", (ev) => clicked(ev));
    motionEl.addEventListener("input", (ev) => scrubbed(ev));
    motionEl.addEventListener("change", (ev) => ticked(ev));

    // The selection moved on: the window follows it, and stops what was playing. Its
    // pieces are drawn only while the window is shown, or when a verb asks.
    function follow() {
        const chosen = world.selected();
        if (chosen && subject && chosen.key === subject.key) return;
        stop();
        subject = null; table = null; built = null; note = ""; framed = null;
        if (chosen && world.shown()) act("open"); else paint();
    }

    paint();
    return {
        act, follow,
        state: () => ({ ...state, playing, bought: showBought, ref: subject?.ref ?? null, drawn: Boolean(built) }),
        table: () => table,
    };
}
