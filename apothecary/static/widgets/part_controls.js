/* The part editor's controls: one for each parameter a part, a piece made from a
 * picture or a camera declares (apothecary/projects/parts/params.py's ParamField),
 * built the same way for each (the part-iteration plan of 2026-10-12, docs/plans/).
 *
 * A number is a slider and a number box beside it, the two kept in step: the
 * slider for the reach, the box for the exact value. Each steps on round numbers --
 * the step the field states (a SCAD customizer's `[1:0.5:20]`), one for an integer,
 * else a power of ten that crosses the range in a hundred to a thousand steps --
 * and the box takes any number typed, which the check then holds to the model. A
 * choice is a drop-down; a yes or no a tick; words a box; a vector a box for each of
 * its numbers, each captioned; a nested model a group of its own fields. The
 * field's description is its caption, and a unit it declares is shown beside its
 * number; where it declares none, nothing is.
 *
 * The page does the staging: every control calls onStage(name, value) with the
 * whole value of its field (a group's whole object, a vector's whole list), and the
 * page decides what that means. A control built here is updated in place by its
 * setValue(value), so the focus stays where a person left it while the numbers
 * round it change (an Apply, an undo, a restore).
 *
 *   buildParamControl(field, value, { onStage }) -> the field's element (.param),
 *       with setValue(value) on it.
 */

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// A number as it is shown: as short as it is, without the float noise arithmetic leaves.
export function shown(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value ?? "");
    return String(Number(n.toPrecision(12)));
}

// A value as words, for "was …": a list's numbers, a group's fields.
export function described(value) {
    if (Array.isArray(value)) return `[${value.map(described).join(", ")}]`;
    if (value && typeof value === "object") return Object.entries(value).map(([k, v]) => `${k} ${described(v)}`).join(", ");
    if (typeof value === "number") return shown(value);
    return String(value);
}

// Whether two staged values are the same: a list or a group by what is in it.
export function sameValue(a, b) {
    if ((a && typeof a === "object") || (b && typeof b === "object")) return JSON.stringify(a) === JSON.stringify(b);
    if (typeof a === "number" || typeof b === "number") return Number(a) === Number(b);
    return a === b;
}

// An integer, when the field says it is one (JSON Schema's word for it).
export const isInteger = (field) => field.type === "integer" || field.integer === true;

// A step a person counts in: a power of ten that crosses `span` in a hundred to a
// thousand steps.
export function roundStep(span) {
    if (!(span > 0) || !Number.isFinite(span)) return 1;
    return 10 ** Math.floor(Math.log10(span / 100) + 1e-9);
}

// The field's own step where it states one, one for an integer, else a round one.
export function stepOf(field) {
    if (Number(field.step) > 0) return Number(field.step);
    if (isInteger(field)) return 1;
    if (field.min !== null && field.min !== undefined && field.max !== null && field.max !== undefined) {
        return roundStep(Number(field.max) - Number(field.min));
    }
    return null;
}

const decimals = (step) => (String(step).split(".")[1] || "").length;
const onStep = (value, step) => Number((value).toFixed(Math.min(12, decimals(step) + 0)));

// The slider's ends, on its steps: the first step inside the field's range and the
// last, so every place the slider stops is a round number the model accepts.
function sliderEnds(field, step) {
    const min = Number(field.min), max = Number(field.max);
    const low = onStep(Math.ceil(min / step - 1e-9) * step, step);
    const high = onStep(Math.floor(max / step + 1e-9) * step, step);
    return low <= high ? [low, high] : [min, max];
}

// A vector's numbers, each named: across, along and up for two or three, else by place.
function axisNames(length) {
    return length <= 3 ? ["x", "y", "z"].slice(0, length) : Array.from({ length }, (_, i) => String(i + 1));
}

const isGroup = (field, value) => {
    const v = value ?? field.default;
    return v !== null && typeof v === "object" && !Array.isArray(v);
};

function unitHtml(field) {
    return field.unit ? `<span class="unit" title="${esc(field.name)} is in ${esc(field.unit)}">${esc(field.unit)}</span>` : "";
}

function headHtml(field) {
    const contested = (field.contested || []).length ? ' <span class="badge-contested">contested</span>' : "";
    const caption = field.description ? `<div class="caption">${esc(field.description)}</div>` : "";
    return `<div class="head"><span class="name">${esc(field.name)}${contested}</span><span class="val"></span></div>${caption}`;
}

// A number: its slider where it has a range, and its box, which steps where the
// slider stops and takes any number typed.
function numberHtml(field, value) {
    const step = stepOf(field);
    const bounded = field.min !== null && field.min !== undefined && field.max !== null && field.max !== undefined && step;
    const label = `${field.name}${field.unit ? `, ${field.unit}` : ""}`;
    const [low, high] = bounded ? sliderEnds(field, step) : [null, null];
    const ends = bounded ? ` min="${low}" max="${high}"` : "";
    const slider = bounded
        ? `<input type="range" class="param-slider"${ends} step="${step}" value="${esc(shown(value))}" aria-label="${esc(label)}, slider">`
        : "";
    return `<div class="num-row">${slider}`
        + `<input type="number" class="param-number"${ends} step="${step || "any"}" value="${esc(shown(value))}" aria-label="${esc(label)}">`
        + `${unitHtml(field)}</div>`;
}

function choiceOptions(field) {
    return field.options?.length
        ? field.options.map((o) => ({ value: o.value, label: o.label }))
        : (field.pattern?.match(/\w+/g) || []).map((w) => ({ value: w, label: w }));
}

function choiceHtml(field, options) {
    return `<select class="param-choice" aria-label="${esc(field.name)}">${options.map((o, i) => `<option value="${i}">${esc(o.label)}</option>`).join("")}</select>`;
}

function vectorHtml(field, numbers) {
    const names = axisNames(numbers.length);
    const step = Number(field.step) > 0 ? Number(field.step) : "any";
    const bound = (k) => (field[k] !== null && field[k] !== undefined ? ` ${k}="${field[k]}"` : "");
    return `<div class="vector">${numbers.map((n, i) => `<label class="coord"><span class="axis">${esc(names[i])}</span>`
        + `<input type="number" class="param-coord" data-index="${i}" step="${step}"${bound("min")}${bound("max")} value="${esc(shown(n))}" aria-label="${esc(field.name)} ${esc(names[i])}"></label>`).join("")}${unitHtml(field)}</div>`;
}

function candidatesHtml(field) {
    return (field.contested || []).map((c) => `<button type="button" class="cand" data-value="${esc(c.value)}" title="Stage ${esc(c.value)}, as ${esc(c.source)} has it"><b>${esc(shown(c.value))}</b><span class="src">${esc(c.source)}</span>${c.note ? `<span class="note">${esc(c.note)}</span>` : ""}</button>`).join("");
}

// A sub-field of a nested model, from what its default is: the server describes the
// group's fields no further, so a number gets a box, a yes or no a tick, words a box.
function subField(name, value) {
    if (typeof value === "boolean") return { name, type: "boolean", default: value, contested: [] };
    if (typeof value === "number") return { name, type: "number", default: value, contested: [] };
    if (Array.isArray(value)) return { name, type: "vector", default: value, contested: [] };
    if (value && typeof value === "object") return { name, type: "group", default: value, contested: [] };
    return { name, type: "text", default: value, contested: [] };
}

export function buildParamControl(field, value, { onStage }) {
    const wrap = document.createElement("div");
    wrap.className = "param" + ((field.contested || []).length ? " is-contested" : "");
    wrap.dataset.field = field.name;
    const group = isGroup(field, value);
    const options = choiceOptions(field);
    const kind = group ? "group" : (field.type === "enum" || field.options?.length) && options.length ? "enum"
        : field.type === "integer" ? "number" : field.type;
    wrap.dataset.kind = kind;

    if (kind === "group") {
        // A nested model: its own fields, in a group headed by its name and caption.
        const current = { ...(field.default || {}), ...(value || {}) };
        wrap.classList.add("param-group-wrap");
        wrap.innerHTML = `<fieldset class="param-group"><legend><span class="name">${esc(field.name)}</span><span class="val"></span></legend>${field.description ? `<div class="caption">${esc(field.description)}</div>` : ""}</fieldset>`;
        const set = wrap.querySelector("fieldset");
        const parts = {};
        for (const [key, sub] of Object.entries(current)) {
            parts[key] = buildParamControl(subField(key, sub), sub, {
                onStage: (name, next) => {
                    current[name] = next;
                    onStage(field.name, { ...current });
                },
            });
            parts[key].classList.add("sub");
            set.appendChild(parts[key]);
        }
        wrap.setValue = (next) => {
            Object.assign(current, next || {});
            for (const [key, part] of Object.entries(parts)) part.setValue(current[key]);
        };
        wrap._input = Object.values(parts)[0]?._input ?? null;
        return wrap;
    }

    wrap.innerHTML = headHtml(field);
    const val = wrap.querySelector(".val");

    if (kind === "enum") {
        wrap.insertAdjacentHTML("beforeend", choiceHtml(field, options));
        const select = wrap.querySelector(".param-choice");
        const set = (v) => {
            const at = options.findIndex((o) => String(o.value) === String(v));
            if (at >= 0) select.value = String(at);
            val.textContent = options[at]?.label ?? String(v ?? "");
        };
        select.onchange = () => {
            const chosen = options[Number(select.value)];
            val.textContent = chosen.label;
            onStage(field.name, chosen.value);
        };
        set(value);
        wrap.setValue = set;
        wrap._input = select;
    } else if (kind === "boolean") {
        wrap.insertAdjacentHTML("beforeend", `<input type="checkbox" class="param-tick" aria-label="${esc(field.name)}">`);
        const tick = wrap.querySelector(".param-tick");
        const set = (v) => { tick.checked = Boolean(v); val.textContent = tick.checked ? "yes" : "no"; };
        tick.onchange = () => { set(tick.checked); onStage(field.name, tick.checked); };
        set(value);
        wrap.setValue = set;
        wrap._input = tick;
    } else if (kind === "vector") {
        const numbers = Array.isArray(value) ? [...value] : [...(field.default ?? [])];
        wrap.insertAdjacentHTML("beforeend", vectorHtml(field, numbers));
        const boxes = [...wrap.querySelectorAll(".param-coord")];
        let current = numbers;
        for (const box of boxes) {
            box.oninput = () => {
                const n = Number(box.value);
                if (box.value === "" || !Number.isFinite(n)) return;
                current = [...current];
                current[Number(box.dataset.index)] = n;
                onStage(field.name, current);
            };
        }
        wrap.setValue = (next) => {
            current = Array.isArray(next) ? [...next] : current;
            boxes.forEach((box, i) => { if (Number(box.value) !== Number(current[i]) || box.value === "") box.value = shown(current[i]); });
        };
        wrap._input = boxes[0] ?? null;
    } else if (kind === "number") {
        wrap.insertAdjacentHTML("beforeend", numberHtml(field, value));
        const slider = wrap.querySelector(".param-slider");
        const box = wrap.querySelector(".param-number");
        const contested = () => {
            for (const button of wrap.querySelectorAll(".cand")) button.classList.toggle("active", Number(button.dataset.value) === Number(box.value));
        };
        // The slider says where it stopped; the box says it exactly.
        if (slider) {
            slider.oninput = () => {
                box.value = shown(slider.value);
                contested();
                onStage(field.name, Number(slider.value));
            };
        }
        // A number typed: staged as typed, the slider following as near as its steps go.
        box.oninput = () => {
            const n = Number(box.value);
            if (box.value === "" || !Number.isFinite(n)) return;
            if (slider) slider.value = String(n);
            contested();
            onStage(field.name, n);
        };
        wrap.setValue = (next) => {
            const n = Number(next);
            if (Number(box.value) !== n || box.value === "") box.value = shown(next);
            if (slider) slider.value = String(n);
            contested();
        };
        wrap.contested = contested;
        wrap._input = slider || box;
    } else {
        wrap.insertAdjacentHTML("beforeend", `<input type="text" class="param-text" aria-label="${esc(field.name)}">`);
        const box = wrap.querySelector(".param-text");
        box.value = value ?? "";
        box.oninput = () => onStage(field.name, box.value);
        wrap.setValue = (next) => { if (box.value !== String(next ?? "")) box.value = next ?? ""; };
        wrap._input = box;
    }

    // The candidates the part's sources disagree about: one press stages one.
    if ((field.contested || []).length) {
        wrap.insertAdjacentHTML("beforeend", candidatesHtml(field));
        for (const button of wrap.querySelectorAll(".cand")) {
            button.onclick = () => {
                const chosen = Number.isFinite(Number(button.dataset.value)) && button.dataset.value !== "" ? Number(button.dataset.value) : button.dataset.value;
                wrap.setValue(chosen);
                onStage(field.name, chosen);
            };
        }
        wrap.contested?.();
    }
    return wrap;
}

// Which control in `host` holds the focus, by its field and what it is, so the same
// one can take it again when the controls are built afresh.
export function focusedControl(host) {
    const el = document.activeElement;
    if (!el || !host.contains(el)) return null;
    const param = el.closest(".param[data-field]");
    if (!param) return null;
    const path = [];
    for (let p = param; p && p !== host; p = p.parentElement?.closest(".param[data-field]")) path.unshift(p.dataset.field);
    return { path, kind: el.className, index: el.dataset.index ?? null };
}

export function refocus(host, was) {
    if (!was) return false;
    let scope = host;
    for (const name of was.path) {
        scope = [...scope.querySelectorAll(".param[data-field]")].find((p) => p.dataset.field === name) || null;
        if (!scope) return false;
    }
    const selector = `.${was.kind.split(" ")[0]}${was.index !== null ? `[data-index="${was.index}"]` : ""}`;
    const el = scope.querySelector(selector);
    if (!el) return false;
    el.focus();
    return true;
}
