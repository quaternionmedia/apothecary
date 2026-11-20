/* Layers: how deep a click in the world reaches, and which layers the world draws and
 * a click can select (docs/viewer.md, "Layers"). A window in the Site group, beside
 * the world, so Site's rows stay in view while it is open.
 *
 * Depth is a stepper: how many levels below the level in view are drawn and reached.
 * Each layer is a row with a Shown tick and a Selectable tick -- selectable only
 * within shown: ticking Selectable shows the layer, and hiding it clears the tick. The
 * rows are those of what lies beneath the level in view (layers_world.js layersInView),
 * in the facets' order (apothecary/facets.py): the parts a row for each shell they are
 * on; a site's pieces a row for each System (the walls the Building System's: Select
 * walls in View is its row's Selectable); the parts a heading for each Kind, its ticks
 * set when every one of its categories is so, half set when some are, and acting on
 * them all, and a row for each of its categories beneath it; a row for each word neither
 * holds (a picture's); and the world's own, the alignment grid, the machines' buttons and
 * the measurement, only Shown.
 * With Measure shown, what it reads (the selection's size, the distance between two points,
 * the gap between two pieces, the diameter or wall under a click, each with its source) is
 * written below the rows as text.
 *
 * Each row wears its layer's colour (colourOf: the one table, static/layer_colours.js),
 * the colour the world draws the layer in and its cells of the ring wear: the legend. A
 * tick, the stepper and Reset each say in their title the address of the ring's cell that
 * does what they do (addressOf, given the action), as the page's buttons do.
 *
 * mountLayers(root, { scope, groups, colourOf, addressOf }) draws the rows into root from
 * the pick scope (pick_scope.js) and keeps them as it changes; refresh() reads the groups,
 * colours and addresses again, as the page calls it when a level is drawn or its ring is
 * resolved. The rows are this window's own, drawn afresh each
 * time, so one listener of each kind on the root serves them all.
 */

import { setReason } from "/static/can.js";
import { GRID, MACHINE_BUTTONS, MEASURE, WALL, DEPTH_MAX, shellLayer } from "/static/pick_scope.js";

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* The words a layer is named by: on its row and on the status line. */
export function layerLabel(id) {
    if (id === GRID) return "Alignment grid";
    if (id === MACHINE_BUTTONS) return "Machine buttons";
    if (id === MEASURE) return "Measure";
    if (id.startsWith("shell:")) return `Shell ${id.slice("shell:".length)}`;
    if (id.startsWith("category:")) return id.slice("category:".length);
    // A System's or a Kind's, its name: system:building, kind:test-pieces.
    if (id.startsWith("system:") || id.startsWith("kind:")) {
        const name = id.slice(id.indexOf(":") + 1).replace(/-/g, " ");
        return name.charAt(0).toUpperCase() + name.slice(1);
    }
    return id;
}

const NONE = { shells: [], systems: [], kinds: [], words: [] };

// `shellLabel(n)`, where given, is what the world's sphere calls shell n (orbits.js
// shellLabel): a row says it in the same words.
export function mountLayers(root, { scope, groups = () => NONE, readings = () => [], colourOf = () => null, addressOf = () => null, shellLabel = null }) {
    root.classList.add("layers-window");

    // " · ⌗NN" for the cell that does what `action` does, or nothing.
    const taught = (action) => { const at = addressOf(action); return at ? ` · ⌗${at}` : ""; };

    // A layer's Shown or Selectable tick, or a Kind heading's over its categories
    // (`heading`): `on` true, false or "some", half set (data-mixed, made indeterminate
    // once drawn).
    function tick(id, label, kind, on, heading = false) {
        const said = heading ? `${label}: ${kind}, every one of its categories` : `${label}: ${kind}`;
        return `<input type="checkbox" class="layers-tick" data-layer="${esc(id)}" data-kind="${kind}"${heading ? ' data-heading="1"' : ""}${on === true ? " checked" : ""}${on === "some" ? ' data-mixed="1"' : ""} aria-label="${esc(said)}" title="${esc(`${said}${taught(`layer:${kind}:${id}`)}`)}">`;
    }

    // A row: a layer's, or (`heading`, a Kind) a heading over its categories' rows, which
    // are set in beneath it (`under`).
    function line(id, label, hint, ticks, { under = false, heading = false } = {}) {
        const colour = colourOf(id);
        const swatch = colour ? `<span class="layers-swatch" style="background: ${esc(colour)}"></span>` : "";
        const cls = heading ? "layers-heading" : under ? "layers-under" : "";
        return `<tr data-row="${esc(id)}"${cls ? ` class="${cls}"` : ""}${colour ? ` data-colour="${esc(colour)}"` : ""}><th scope="row" title="${esc(hint)}">${swatch}${esc(label)}</th>`
            + `<td>${ticks[0]}</td><td>${ticks[1] ?? ""}</td></tr>`;
    }

    function row(id, label, hint, selectable, under = false) {
        const ticks = [tick(id, label, "shown", scope.isShown(id))];
        if (selectable) ticks.push(tick(id, label, "selectable", scope.isSelectable(id)));
        return line(id, label, hint, ticks, { under });
    }

    // A Kind's heading: its ticks set when every one of its categories is so, half set
    // when some are.
    function heading(kind) {
        const ids = kind.words.map((word) => word.layer);
        const over = (has) => {
            const count = ids.filter(has).length;
            return count === ids.length ? true : count ? "some" : false;
        };
        return line(kind.layer, kind.name, `The parts of the ${kind.name} kind: its categories, beneath`, [
            tick(kind.layer, kind.name, "shown", over((id) => scope.isShown(id)), true),
            tick(kind.layer, kind.name, "selectable", over((id) => scope.isSelectable(id)), true),
        ], { heading: true });
    }

    function section(title, rows) {
        if (!rows.length) return "";
        return `<tbody><tr class="layers-section"><th scope="colgroup" colspan="3">${esc(title)}</th></tr>${rows.join("")}</tbody>`;
    }

    // Drawn afresh, so the focus is put back on the control a keyboard was on.
    function draw() {
        const was = root.contains(document.activeElement) ? document.activeElement : null;
        const at = was && (was.dataset.layer ? `[data-layer="${CSS.escape(was.dataset.layer)}"][data-kind="${was.dataset.kind}"]` : was.dataset.act ? `[data-act="${was.dataset.act}"]` : null);
        paint();
        const again = at && root.querySelector(at);
        if (again && !again.disabled) again.focus();
    }

    // What the measurement layer reads, as text to read and copy, each with its source.
    function reading() {
        const lines = scope.isShown(MEASURE) ? readings() : [];
        if (!lines.length) return "";
        const colour = colourOf(MEASURE);
        return `<pre class="layers-reading" tabindex="0" aria-label="Measurements"${colour ? ` style="color: ${esc(colour)}"` : ""}>${esc(lines.join("\n"))}</pre>`;
    }

    function paint() {
        const depth = scope.depth();
        const { shells: rows, systems, kinds, words } = { ...NONE, ...groups() };
        const last = rows.length - 1;
        const shellRows = rows.map((n, i) => {
            const note = rows.length > 1 ? (i === 0 ? " (innermost)" : i === last ? " (outermost)" : "") : "";
            return row(shellLayer(n), shellLabel ? shellLabel(n) : `${layerLabel(shellLayer(n))}${note}`, "The parts laid on this shell of the sphere", true);
        });
        const systemRows = systems.map((value) => row(value.layer, value.name, value.layer === WALL
            ? "Walls: drawn faded; Selectable here is View > Select walls" : `The pieces in the ${value.name} System`, true));
        const kindRows = kinds.flatMap((kind) => [heading(kind), ...kind.words.map((word) => row(word.layer, word.word, `The parts of the ${word.word} category, of the ${kind.name} kind`, true, true))]);
        const wordRows = words.map((word) => row(word.layer, word.word, `The pieces called ${word.word}, a word no System or Kind holds`, true));
        root.innerHTML = `<div class="layers-depth">
    <span class="layers-depth-label" title="How many levels below the level in view a click reaches and the world draws: 1 is the level's own pieces">Depth</span>
    <button type="button" class="layers-depth-less" data-act="depth-less" aria-label="One level less">-</button>
    <output class="layers-depth-value" aria-live="polite">${depth}</output>
    <button type="button" class="layers-depth-more" data-act="depth-more" aria-label="One level more">+</button>
</div>
<table class="layers-table"><thead><tr><th scope="col">Layer</th><th scope="col">Shown</th><th scope="col">Selectable</th></tr></thead>
${section("Parts, by shell", shellRows)}${section("Systems", systemRows)}${section("Kinds", kindRows)}${section("Words", wordRows)}${section("The world", [
            row(GRID, layerLabel(GRID), "The machines' build volumes, drawn in this colour, and the floor grid, drawn in the faint greys a floor wears: this layer shows or hides both", false),
            row(MACHINE_BUTTONS, layerLabel(MACHINE_BUTTONS), "The badges a machine wears in the world", false),
            row(MEASURE, layerLabel(MEASURE), "While shown, a click in the world drops a point to measure between and selects nothing, and reads the diameter or the wall under it; the selection reads its size", false),
        ])}</table>
<div class="layers-reset"><button type="button" class="layers-reset-all" data-act="reset" title="Depth 1, every layer shown, every layer selectable but walls${taught("layer:reset")}">Reset</button></div>
${reading()}`;
        for (const box of root.querySelectorAll("input[data-mixed]")) box.indeterminate = true;
        // The stepper at either end is greyed, saying why, as every control is (can.js).
        setReason(root.querySelector(".layers-depth-less"), depth <= 1 ? "the depth is 1, a click reaching the level's own pieces alone" : null, `One level less${taught("view:depth:less")}`);
        setReason(root.querySelector(".layers-depth-more"), depth >= DEPTH_MAX ? `the depth is ${DEPTH_MAX}, the deepest a click reaches` : null, `One level more${taught("view:depth:more")}`);
    }

    function onChange(event) {
        const box = event.target.closest && event.target.closest("input[data-layer]");
        if (!box) return;
        if (box.dataset.heading) {
            const kind = ({ ...NONE, ...groups() }).kinds.find((k) => k.layer === box.dataset.layer);
            const ids = kind ? kind.words.map((word) => word.layer) : [];
            if (box.dataset.kind === "shown") scope.setShownEach(ids, box.checked, box.dataset.layer);
            else scope.setSelectableEach(ids, box.checked, box.dataset.layer);
            return;
        }
        if (box.dataset.kind === "shown") scope.setShown(box.dataset.layer, box.checked);
        else scope.setSelectable(box.dataset.layer, box.checked);
    }
    function onClick(event) {
        const button = event.target.closest && event.target.closest("button[data-act]");
        if (!button) return;
        const act = button.dataset.act;
        if (act === "depth-less") scope.setDepth(scope.depth() - 1);
        else if (act === "depth-more") scope.setDepth(scope.depth() + 1);
        else if (act === "reset") scope.reset();
    }
    root.addEventListener("change", onChange);
    root.addEventListener("click", onClick);
    scope.onChange(draw);
    draw();
    return { refresh: draw };
}
