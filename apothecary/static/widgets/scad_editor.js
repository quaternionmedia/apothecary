/* The SCAD editor: a part's SCAD in CodeMirror 6, where the part editor's
 * read-only source stood in Selected (loop 2, the owner's answer of 2026-10-10,
 * docs/plans/ui-flows-2026-10-08.md).
 *
 * CodeMirror is vendored (apothecary/static/vendor/codemirror/, its README says
 * which packages and how to update them) and loaded the first time an editor
 * mounts, so a page that never opens one never loads it. The OpenSCAD mode is
 * this module's own, a stream tokenizer: comments, strings, numbers, the
 * language's words, its built-in modules and functions, and the special
 * variables ($fn and the rest). What OpenSCAD said of a line is marked on it,
 * as CodeMirror's lint marks a diagnostic: underlined, with a marker in the
 * gutter and the message on hover.
 *
 * The editor does not talk to the server. The page does: it is told when the
 * text changes (onChange), and what to do for each of the bar's buttons. The
 * bar holds the check's words (what OpenSCAD said, and what is next), the name a
 * Save keeps the variant under, Save, Float and Fullscreen; under the code, the
 * part's variants saved in git, each with what it changes and whether HEAD
 * already holds it. A part whose SCAD is not its own source (its geometry is
 * Python, or a made piece's few lines) is read-only, and has no name and no Save.
 *
 * OpenSCAD's own keys work inside it, and only there: F5 checks and draws
 * (onCheck), F6 and Ctrl+Enter render and draw (onApply), Ctrl+S saves a variant
 * (onSave). Outside it the browser's keys are the browser's.
 *
 * The page keeps a part's editor while another part is selected, so its text and
 * its undo come back with it: its root is taken out of the page and put back, and
 * rebind() points its callbacks at the page's newest. The name box names the
 * variant Save keeps; empty, Save keeps it under the name suggest() greyed in it.
 *
 * mountScadEditor(slot, options) renders into slot and resolves to the editor:
 *   options: { text, readOnly, editable, name, onChange(text), onSave(),
 *              onFloat(), onFullscreen(), onChoose(name), onCheck(), onApply(),
 *              onName(name), shownAs }
 *   editor:  { root, text(), setText(text), mark(messages), say(words, kind),
 *              name(), setName(name), suggest(name), showVariants(list),
 *              fullscreen(on), isFullscreen(), focus(), measure(), rebind(callbacks),
 *              destroy() }
 * variantChoices(list) is the markup of a list of saved variants to choose one
 * from, as the editor's own list and the page's short list under a part's
 * parameters both draw it; the page listens on the list.
 */

const MARKUP = `
<div class="scad-editor" tabindex="-1">
    <div class="scad-bar">
        <span class="scad-said" role="status"></span>
        <span class="scad-spacer"></span>
        <label class="scad-name-label" title="The name Save keeps this variant under, in git: letters, digits, _ . and -. Empty, the name greyed in it; a name already saved is asked about first">as <input type="text" id="scad-name" spellcheck="false" maxlength="64"></label>
        <button type="button" id="scad-save" title="Save: this SCAD and the numbers staged in the editor, committed to this part's own ref in git under the name beside it. Nothing in the checkout changes; merging it is yours to do (Ctrl+S in the editor; Part › Save)">Save</button>
        <button type="button" id="scad-float" title="Float the editor over the world, or put it back in Selected (Part › View › Float)">Float</button>
        <button type="button" id="scad-fullscreen" title="The editor over the whole page; Esc or this button puts it back (Part › View › Fullscreen)">Fullscreen</button>
    </div>
    <div class="scad-code"></div>
    <div class="scad-saved"></div>
</div>`;

// The modules, loaded once, the first time an editor mounts.
let loading = null;
function codemirror() {
    loading ??= Promise.all([
        import("@codemirror/state"),
        import("@codemirror/view"),
        import("@codemirror/language"),
        import("@codemirror/commands"),
        import("@codemirror/lint"),
        import("@lezer/highlight"),
    ]).then(([state, view, language, commands, lint, highlight]) => ({ state, view, language, commands, lint, highlight }));
    return loading;
}

// --- the OpenSCAD mode -------------------------------------------------------------

const KEYWORDS = new Set(["module", "function", "if", "else", "for", "let", "each", "intersection_for", "include", "use", "assert", "echo", "assign"]);
const ATOMS = new Set(["true", "false", "undef", "PI"]);
const BUILTINS = new Set([
    // solids and shapes
    "cube", "sphere", "cylinder", "polyhedron", "square", "circle", "polygon", "text", "import", "surface",
    // what is done to them
    "translate", "rotate", "scale", "resize", "mirror", "multmatrix", "color", "offset", "hull", "minkowski",
    "union", "difference", "intersection", "linear_extrude", "rotate_extrude", "projection", "render", "children",
    // functions
    "abs", "sign", "sin", "cos", "tan", "acos", "asin", "atan", "atan2", "floor", "round", "ceil", "ln", "log",
    "pow", "sqrt", "exp", "len", "min", "max", "norm", "cross", "concat", "lookup", "str", "chr", "ord", "search",
    "rands", "version", "version_num", "is_undef", "is_bool", "is_num", "is_string", "is_list", "is_function",
]);

function openscadMode() {
    return {
        name: "openscad",
        startState: () => ({ inComment: false, afterInclude: false }),
        copyState: (s) => ({ ...s }),
        token(stream, state) {
            if (state.inComment) {
                if (stream.skipTo("*/")) { stream.next(); stream.next(); state.inComment = false; } else stream.skipToEnd();
                return "comment";
            }
            if (stream.eatSpace()) return null;
            if (stream.match("//")) { stream.skipToEnd(); return "comment"; }
            if (stream.match("/*")) { state.inComment = true; return "comment"; }
            if (state.afterInclude && stream.match(/^<[^>]*>?/)) { state.afterInclude = false; return "string"; }
            state.afterInclude = false;
            if (stream.match(/^"(?:[^"\\]|\\.)*"?/)) return "string";
            if (stream.match(/^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/)) return "number";
            if (stream.match(/^\$[A-Za-z_]\w*/)) return "variableName.special";
            if (stream.match(/^[A-Za-z_]\w*/)) {
                const word = stream.current();
                if (word === "include" || word === "use") { state.afterInclude = true; return "keyword"; }
                if (KEYWORDS.has(word)) return "keyword";
                if (ATOMS.has(word)) return "atom";
                if (BUILTINS.has(word)) return "variableName.standard";
                return "variableName";
            }
            if (stream.match(/^[-+*/%^!<>=&|?:]+/)) return "operator";
            stream.next();
            return null;
        },
        languageData: { commentTokens: { line: "//", block: { open: "/*", close: "*/" } } },
    };
}

function theme(cm) {
    const { view, language, highlight } = cm;
    const t = highlight.tags;
    return [
        view.EditorView.theme({
            "&": { color: "#e2e2e2", backgroundColor: "#141414", fontSize: "12px", height: "100%" },
            ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", caretColor: "#9cdcfe" },
            ".cm-gutters": { backgroundColor: "#1b1b1b", color: "#777", border: "none" },
            ".cm-activeLine": { backgroundColor: "#1f2630" },
            ".cm-activeLineGutter": { backgroundColor: "#1f2630" },
            "&.cm-focused .cm-cursor": { borderLeftColor: "#9cdcfe" },
            "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "#264f78" },
            ".cm-lintRange-error": { backgroundColor: "#4a1f1f" },
            ".cm-lintRange-warning": { backgroundColor: "#3d3418" },
            ".cm-tooltip": { backgroundColor: "#222", color: "#eee", border: "1px solid #444" },
        }, { dark: true }),
        language.syntaxHighlighting(language.HighlightStyle.define([
            { tag: t.comment, color: "#6a9955" },
            { tag: t.keyword, color: "#c586c0" },
            { tag: t.atom, color: "#569cd6" },
            { tag: t.number, color: "#b5cea8" },
            { tag: t.string, color: "#ce9178" },
            { tag: t.operator, color: "#d4d4d4" },
            { tag: t.standard(t.variableName), color: "#dcdcaa" },
            { tag: t.special(t.variableName), color: "#4fc1ff" },
            { tag: t.variableName, color: "#9cdcfe" },
        ])),
    ];
}

// --- what the bar and the lists show ------------------------------------------------

function esc(v) {
    return String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function when(iso) {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "";
    return new Date(t).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function numbers(params) {
    const shown = Object.entries(params ?? {}).map(([k, v]) => `${k} ${Array.isArray(v) ? `[${v.join(", ")}]` : v}`);
    return shown.length ? shown.join(", ") : "its own numbers";
}

/* A list of saved variants to choose one from: each a button naming it, when it
 * was saved and with what numbers; with `full`, also whether HEAD holds it and,
 * folded, what it changes. */
export function variantChoices(list, { full = false, chosen = null } = {}) {
    if (!list || !list.length) return `<span class="empty">no variants saved yet: Save keeps one in git</span>`;
    return list.map((v) => {
        const head = v.merged ? `<span class="in-head" title="HEAD already holds it: merged">in HEAD</span>` : `<span class="not-in-head" title="Not merged: git merge ${esc(v.ref)} makes it the part's source">not merged</span>`;
        const changes = full && v.diff !== null && v.diff !== undefined
            ? `<details class="variant-diff"><summary>what it changes</summary><pre>${v.diff ? esc(v.diff) : "nothing: its SCAD is the part's own"}</pre></details>`
            : "";
        return `<div class="saved-row${v.name === chosen ? " chosen" : ""}" data-variant="${esc(v.name)}">`
            + `<button type="button" class="saved-variant" data-variant="${esc(v.name)}" title="Draw ${esc(v.name)}: its SCAD in the editor and its numbers staged, rendered (Part › Variants › ${esc(v.name)})">${esc(v.name)}</button>`
            + `<span class="saved-when">${esc(when(v.date))}</span>${full ? head : ""}`
            + `<div class="saved-numbers">${esc(numbers(v.params))}</div>${changes}</div>`;
    }).join("");
}

// --- the editor --------------------------------------------------------------------

export async function mountScadEditor(slot, options = {}) {
    const { text = "", readOnly = false, editable = !readOnly, name = "", shownAs = null } = options;
    // What the page is told, through one object it can point elsewhere (rebind).
    const on = {};
    for (const key of ["onChange", "onSave", "onFloat", "onFullscreen", "onChoose", "onCheck", "onApply", "onName"]) on[key] = options[key];
    slot.innerHTML = MARKUP;
    const root = slot.querySelector(".scad-editor");
    const said = root.querySelector(".scad-said");
    const nameBox = root.querySelector("#scad-name");
    const saveBtn = root.querySelector("#scad-save");
    const floatBtn = root.querySelector("#scad-float");
    const fullBtn = root.querySelector("#scad-fullscreen");
    const savedList = root.querySelector(".scad-saved");
    nameBox.value = name;
    for (const el of [nameBox.parentElement, saveBtn]) el.hidden = !editable;
    savedList.hidden = !editable;
    saveBtn.onclick = () => on.onSave && on.onSave();
    floatBtn.onclick = () => on.onFloat && on.onFloat();
    fullBtn.onclick = () => on.onFullscreen && on.onFullscreen();
    nameBox.oninput = () => on.onName && on.onName(nameBox.value);
    savedList.onclick = (ev) => {
        const b = ev.target.closest(".saved-variant");
        if (b && on.onChoose) on.onChoose(b.dataset.variant);
    };
    // Escape, with the editor over the page, puts it back: the editor holds the
    // focus while it is there (its root takes it when nothing in it does).
    root.onkeydown = (ev) => {
        if (ev.key === "Escape" && root.classList.contains("fullscreen")) {
            ev.preventDefault();
            ev.stopPropagation();
            if (on.onFullscreen) on.onFullscreen();
        }
    };

    const cm = await codemirror();
    const { state, view, language, commands, lint } = cm;
    const listen = view.EditorView.updateListener.of((update) => {
        if (update.docChanged && on.onChange) on.onChange(update.state.doc.toString());
    });
    // OpenSCAD's keys, ahead of the editor's own: each is taken, so F5 does not reload
    // the page nor Ctrl+S save it, while the editor has the focus.
    const take = (call) => () => { if (on[call]) on[call](); return true; };
    const openscadKeys = view.keymap.of([
        { key: "F5", run: take("onCheck"), preventDefault: true },
        { key: "F6", run: take("onApply"), preventDefault: true },
        { key: "Mod-Enter", run: take("onApply"), preventDefault: true },
        { key: "Mod-s", run: take("onSave"), preventDefault: true },
    ]);
    const editorView = new view.EditorView({
        parent: root.querySelector(".scad-code"),
        state: state.EditorState.create({
            doc: text,
            extensions: [
                view.lineNumbers(),
                view.highlightActiveLine(),
                view.highlightActiveLineGutter(),
                view.drawSelection(),
                commands.history(),
                language.indentOnInput(),
                language.bracketMatching(),
                language.StreamLanguage.define(openscadMode()),
                lint.lintGutter(),
                openscadKeys,
                view.keymap.of([...commands.defaultKeymap, ...commands.historyKeymap, commands.indentWithTab]),
                state.EditorState.readOnly.of(readOnly),
                view.EditorView.editable.of(!readOnly),
                ...theme(cm),
                listen,
            ],
        }),
    });

    const editor = {
        root,
        view: editorView,
        marked: [],
        text: () => editorView.state.doc.toString(),
        // The text replaced, as a person replacing it would: one undoable change.
        setText(next) {
            if (next === editorView.state.doc.toString()) return;
            editorView.dispatch({ changes: { from: 0, to: editorView.state.doc.length, insert: next } });
        },
        /* What OpenSCAD said, marked on the lines it names: those of this file
         * (shownAs, the part's SCAD as the API names it) or of no file at all. */
        mark(messages) {
            const doc = editorView.state.doc;
            const diagnostics = [];
            for (const m of messages ?? []) {
                if (!m.line || (m.file && shownAs && m.file !== shownAs)) continue;
                const line = doc.line(Math.min(Math.max(1, m.line), doc.lines));
                diagnostics.push({
                    from: line.from,
                    to: Math.max(line.to, line.from),
                    severity: m.level === "error" ? "error" : "warning",
                    message: m.message,
                });
            }
            editorView.dispatch(lint.setDiagnostics(editorView.state, diagnostics));
            // What is marked, by line: for a reader of the page (a test among them).
            editor.marked = diagnostics.map((d) => ({ line: doc.lineAt(d.from).number, severity: d.severity, message: d.message }));
            const first = diagnostics.find((d) => d.severity === "error") ?? diagnostics[0];
            if (first) editorView.dispatch({ effects: view.EditorView.scrollIntoView(first.from, { y: "nearest" }) });
            return diagnostics.length;
        },
        say(words, kind = "") {
            said.textContent = words;
            said.className = `scad-said ${kind}`;
        },
        name: () => nameBox.value.trim(),
        setName(next) { nameBox.value = next; },
        suggest(next) { nameBox.placeholder = next || ""; },
        showVariants(list, chosen = null) { savedList.innerHTML = `<div class="code-header">Saved variants</div>${variantChoices(list, { full: true, chosen })}`; },
        fullscreen(on) {
            root.classList.toggle("fullscreen", on);
            fullBtn.textContent = on ? "Exit fullscreen" : "Fullscreen";
            if (on) root.focus();
            editorView.requestMeasure();
        },
        isFullscreen: () => root.classList.contains("fullscreen"),
        floated(on) { floatBtn.textContent = on ? "Dock" : "Float"; editorView.requestMeasure(); },
        focus() { editorView.focus(); },
        measure() { editorView.requestMeasure(); },
        rebind(callbacks) { Object.assign(on, callbacks); },
        destroy() { editorView.destroy(); root.remove(); },
    };
    return editor;
}
