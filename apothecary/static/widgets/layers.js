/* Layers: how deep a click in the world reaches, and which layers the world draws and
 * a click can select (docs/viewer.md, "Layers"). A window in the Site group, beside
 * the world, so Site's rows stay in view while it is open.
 *
 * Depth is a stepper: how many levels below the level in view are drawn and reached.
 * Each layer is a row with a Shown tick and a Selectable tick -- selectable only
 * within shown: ticking Selectable shows the layer, and hiding it clears the tick. The
 * parts have a row for each shell the loaded site has, the pieces a row for each
 * category (walls among them: Select walls in View is this row's Selectable), and the
 * world's own, the alignment grid, the machines' buttons and the measurement, only Shown.
 * With Measure shown, what it reads (the selection's size, the distance between two points,
 * the gap between two pieces, each with its source) is written below the rows as text.
 *
 * mountLayers(root, { scope, shells, categories }) draws the rows into root from the
 * pick scope (pick_scope.js) and keeps them as it changes; refresh() reads the shells
 * and categories again, as the page calls it when a site is drawn. The rows are this
 * window's own, drawn afresh each time, so one listener of each kind on the root
 * serves them all.
 */

import { GRID, MACHINE_BUTTONS, MEASURE, DEPTH_MAX, shellLayer, categoryLayer } from "/static/pick_scope.js";

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* The words a layer is named by: on its row and on the status line. */
export function layerLabel(id) {
    if (id === GRID) return "Alignment grid";
    if (id === MACHINE_BUTTONS) return "Machine buttons";
    if (id === MEASURE) return "Measure";
    if (id.startsWith("shell:")) return `Shell ${id.slice("shell:".length)}`;
    if (id.startsWith("category:")) return id.slice("category:".length);
    return id;
}

export function mountLayers(root, { scope, shells = () => [], categories = () => [], readings = () => [] }) {
    root.classList.add("layers-window");

    function row(id, label, hint, selectable) {
        const shown = scope.isShown(id);
        const tick = (kind, on) => `<input type="checkbox" class="layers-tick" data-layer="${esc(id)}" data-kind="${kind}"${on ? " checked" : ""} aria-label="${esc(label)}: ${kind}">`;
        return `<tr data-row="${esc(id)}"><th scope="row" title="${esc(hint)}">${esc(label)}</th>`
            + `<td>${tick("shown", shown)}</td><td>${selectable ? tick("selectable", scope.isSelectable(id)) : ""}</td></tr>`;
    }

    function section(title, rows) {
        if (!rows.length) return "";
        return `<tbody><tr class="layers-kind"><th scope="colgroup" colspan="3">${esc(title)}</th></tr>${rows.join("")}</tbody>`;
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
        return `<pre class="layers-reading" tabindex="0" aria-label="Measurements">${esc(lines.join("\n"))}</pre>`;
    }

    function paint() {
        const depth = scope.depth();
        const rows = shells();
        const last = rows.length - 1;
        const shellRows = rows.map((n, i) => {
            const note = rows.length > 1 ? (i === 0 ? " (innermost)" : i === last ? " (outermost)" : "") : "";
            return row(shellLayer(n), `${layerLabel(shellLayer(n))}${note}`, "The parts laid on this shell of the sphere", true);
        });
        const categoryRows = categories().map((c) => row(categoryLayer(c), layerLabel(categoryLayer(c)), c === "wall"
            ? "Walls: drawn faded; Selectable here is View > Select walls" : `The pieces of the ${c} category`, true));
        root.innerHTML = `<div class="layers-depth">
    <span class="layers-depth-label" title="How many levels below the level in view a click reaches and the world draws: 1 is the level's own pieces">Depth</span>
    <button type="button" class="layers-depth-less" data-act="depth-less" aria-label="One level less"${depth <= 1 ? " disabled" : ""}>-</button>
    <output class="layers-depth-value" aria-live="polite">${depth}</output>
    <button type="button" class="layers-depth-more" data-act="depth-more" aria-label="One level more"${depth >= DEPTH_MAX ? " disabled" : ""}>+</button>
</div>
<table class="layers-table"><thead><tr><th scope="col">Layer</th><th scope="col">Shown</th><th scope="col">Selectable</th></tr></thead>
${section("Parts, by shell", shellRows)}${section("Categories", categoryRows)}${section("The world", [
            row(GRID, layerLabel(GRID), "The floor grid and the machines' build volumes", false),
            row(MACHINE_BUTTONS, layerLabel(MACHINE_BUTTONS), "The badges a machine wears in the world", false),
            row(MEASURE, layerLabel(MEASURE), "While shown, a click in the world drops a point to measure between and selects nothing; the selection reads its size", false),
        ])}</table>
${reading()}
<div class="layers-reset"><button type="button" class="layers-reset-all" data-act="reset" title="Depth 1, every layer shown, every layer selectable but walls">Reset</button></div>`;
    }

    function onChange(event) {
        const box = event.target.closest && event.target.closest("input[data-layer]");
        if (!box) return;
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
