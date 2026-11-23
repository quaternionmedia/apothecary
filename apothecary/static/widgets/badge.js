/* Badge: a face or a word engraved in a plate, composed in a window of the Part group
 * (parts/badge; docs/viewer.md, The Badge window).
 *
 * For the badge selected -- a piece built from parts/badge: in the universe, where every
 * part stands, or in any site that holds one -- its numbers are its editor's (Part ›
 * Edit), and the window stages them there and applies them, so the world draws what is
 * composed. A face is chosen of six, each drawn after its emoji, or the word, staged as
 * its kind and face and drawn at once. The word is typed and its font chosen, or a
 * face's diameter set, with the controls the Parameters window builds
 * (part_controls.js), staged there too and drawn once they rest. ⚒ Print and ⚒ Cut make
 * the badge drawn on the first printer or router of any site that makes it, as ⚒ Make
 * does, that machine's site opened with the variant drawn: ⚒ Cut is greyed for a word,
 * which the router does not cut, saying why.
 *
 * Each face's button, and the word's, is a cell of the badge's ring, Part › View › Badge,
 * and wears its address in its title; ⚒ Print and ⚒ Cut do what a part's Slice and
 * Toolpath cells do, on the first machine of each kind that makes it, as ⚒ Make does.
 *
 * mountBadge(root, world) -> { follow(), refresh(), act(verb), state() }
 *   follow: the badge selected, its editor opened and read; refresh: what that editor has
 *   staged read again, nothing opened (the window brought forward).
 *   world: { selected() -> { key, ref } | null,
 *            editor(key) -> Promise<{ fields, staged } | null>, the part's editor opened on it,
 *            staged(key) -> {...} | null, what its editor has staged, where it is open,
 *            stage(key, name, value) -> Promise, a value staged as its control in Parameters
 *            stages it, once the editor is there to take it,
 *            apply(key) -> Promise<{ said } | { refused }>,
 *            make(key, kind) -> Promise<{ said } | { refused }>,
 *            controlFor(field, value, onStage) -> element, the Parameters window's control,
 *            addressOf(action) -> string | null, say(text, kind) }
 *   act: "face:<name>" | "word" | "make:printer" | "make:router" -> Promise<{ said } | { refused }>
 */

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// The part this window composes; its faces in their order, each with its emoji, then the
// word; what of a face and of a word it shows of the part's numbers (the rest are in
// Parameters).
export const PART = "badge";
export const CHOICES = [
    ["open", "😮", "Open"], ["smile", "🙂", "Smile"], ["neutral", "😐", "Neutral"],
    ["wink", "😉", "Wink"], ["frown", "🙁", "Frown"], ["grin", "😀", "Grin"], ["word", "✎", "Word"],
];
const SHOWN = { face: ["diameter"], word: ["text", "font", "text_size"] };
// The router does not cut a word, in the part's own words (parts/badge's Refused).
export const NOT_CUT = "a word is printed, not cut: its letters are a font's outlines, which the router's one end mill cannot follow -- choose a face to cut, or make the word on a printer";
// How long the controls rest before what is staged is drawn.
const REST_MS = 700;

const STYLE = `
.badge-window { padding: 8px 10px; font-size: 13px; line-height: 1.4; }
.badge-window .badge-faces { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.badge-window .badge-face { font-size: 18px; min-width: 2.2em; }
.badge-window .badge-face[aria-pressed="true"] { outline: 2px solid var(--group-part, #a9c868); }
.badge-window .badge-fields .param { margin: 4px 0; }
.badge-window .badge-makes { display: flex; gap: 8px; margin: 8px 0 4px; }
.badge-window .badge-said { margin: 4px 0; opacity: 0.85; font-size: 12px; }`;

export function mountBadge(root, world) {
    if (!document.getElementById("badge-window-style")) {
        const style = document.createElement("style");
        style.id = "badge-window-style";
        style.textContent = STYLE;
        document.head.append(style);
    }
    const badgeEl = root;
    badgeEl.classList.add("badge-window");
    let subject = null;  // { key, ref }
    let staged = {};     // the editor's staged numbers, as last read
    let fields = [];     // the part's fields, as its editor describes them
    let note = "";
    let resting = null;
    let reading = null;  // the badge's editor being read, as follow() reads it
    let painted = null;  // the kind the controls were drawn for

    const taught = (action) => { const at = world.addressOf ? world.addressOf(action) : null; return at ? ` · ⌗${at}` : ""; };
    const kind = () => (staged.kind === "word" ? "word" : "face");
    const chosen = () => (kind() === "word" ? "word" : staged.face || "smile");
    const said = (text) => { note = text || ""; const el = badgeEl.querySelector(".badge-said"); if (el) el.textContent = note; };

    function head() {
        return kind() === "word"
            ? `the word ${esc(staged.text ?? "")}, in ${esc(staged.font ?? "")}: printed`
            : `a face, ${esc((CHOICES.find(([n]) => n === chosen()) || [])[1] || "")} ${esc(chosen())}: printed, or cut on the router`;
    }

    function paint() {
        if (!subject) {
            badgeEl.innerHTML = `<p class="section-empty badge-none">${esc(note || "Select the badge -- parts/badge, in the universe where every part stands -- and compose it here: a face, or a word.")}</p>`;
            return;
        }
        const word = kind() === "word";
        painted = kind();
        badgeEl.innerHTML = `
            <div class="badge-head"><strong>${esc(subject.key)}</strong>: <span class="badge-what">${head()}</span></div>
            <div class="badge-faces" role="group" aria-label="A face, or the word">${CHOICES.map(([name, emoji, label]) => `<button type="button" class="badge-face" data-face="${name}" aria-pressed="${chosen() === name}" aria-label="${esc(label)}" title="${esc(`${label}: staged and drawn${taught(name === "word" ? "part:badge:word" : `part:badge:face:${name}`)}`)}">${emoji}</button>`).join("")}</div>
            <div class="badge-fields"></div>
            <div class="badge-makes">${[["printer", "⚒ Print", "sliced"], ["router", "⚒ Cut", "its toolpath written"]].map(([machine, label, how]) => `<button type="button" class="badge-make" data-make="${machine}"${machine === "router" && word ? ` disabled title="${esc(`Disabled: ${NOT_CUT}`)}"` : ` title="${esc(`The badge drawn, made on the first ${machine} of any site that makes it, as ⚒ Make does: that site opened, the variant drawn chosen under makes and ${how}; ▶ is yours`)}"`}>${label}</button>`).join("")}</div>
            <p class="badge-said">${esc(note)}</p>`;
        const host = badgeEl.querySelector(".badge-fields");
        for (const name of SHOWN[kind()]) {
            const field = fields.find((f) => f.name === name);
            if (field) host.append(world.controlFor(field, staged[name], (n, value) => staging(n, value)));
        }
    }

    // The badge selected followed, its editor opened and read when it is another.
    // What waits to be drawn is the badge's it was staged on: another selected, it is let go.
    async function follow() {
        const now = world.selected();
        if (!now || now.ref !== PART) {
            const was = subject;
            subject = null;
            rest(null);
            const next = now ? `${now.key} is built from ${now.ref || "no part"}: the Badge window composes parts/badge` : "";
            const stale = was || next !== note || !badgeEl.querySelector(".badge-none");
            note = next;
            if (stale) paint();
            return;
        }
        // The badge followed already, or being read: done once its numbers are read.
        if (subject && subject.key === now.key) return reading;
        rest(null);
        subject = now;
        reading = read();
        await reading;
    }

    // The draw waiting for the controls to rest: set, or let go (``null``).
    function rest(work) {
        clearTimeout(resting);
        resting = work ? setTimeout(() => { resting = null; work(); }, REST_MS) : null;
    }

    // The editor's fields and what it has staged, read again, and drawn.
    async function read() {
        const editor = subject ? await world.editor(subject.key) : null;
        if (!subject) return;
        if (!editor) { note = `${subject.key}: its numbers did not open`; paint(); return; }
        staged = { ...editor.staged };
        fields = editor.fields || [];
        paint();
    }

    // A value staged from the window's controls, as Parameters stages it; drawn once they
    // rest, or by the caller (``now``).
    async function staging(name, value, { now = false } = {}) {
        if (!subject) return;
        staged[name] = value;
        const key = subject.key;
        const done = world.stage(key, name, value);
        const what = badgeEl.querySelector(".badge-what");
        if (what) what.innerHTML = head();
        rest(null);
        await done;
        if (now || subject?.key !== key) return;
        rest(async () => {
            const done = await world.apply(key);
            if (subject?.key === key && !done.superseded) said(done.refused || done.said);
        });
    }

    // What the editor has staged, read again without opening anything: the controls drawn
    // again only for another kind, so one being typed in keeps its place.
    function refresh() {
        if (!subject) return;
        const now = world.staged(subject.key);
        if (!now) return;
        staged = now;
        if (painted !== kind()) { paint(); return; }
        const what = badgeEl.querySelector(".badge-what");
        if (what) what.innerHTML = head();
        for (const button of badgeEl.querySelectorAll(".badge-face")) button.setAttribute("aria-pressed", String(button.dataset.face === chosen()));
    }

    async function act(verb) {
        if (!subject) return { refused: "the Badge window composes the badge selected: select parts/badge, in the universe" };
        const [what, name] = verb.split(":");
        if (what === "face" || what === "word") {
            // The kind, then the face where it is one, staged as Parameters stages them,
            // then drawn now rather than once the controls rest.
            if (what === "face" && !CHOICES.some(([n]) => n === name && n !== "word")) return { refused: `the badge has no face ${name}` };
            const key = subject.key;
            rest(null);
            await staging("kind", what === "word" ? "word" : "face", { now: true });
            if (what === "face") await staging("face", name, { now: true });
            const done = await world.apply(key);
            // A newer choice stopped this one's render: that one says what is drawn.
            if (done.superseded || subject?.key !== key) return done;
            await read();
            const named = what === "word" ? "the word" : `${(CHOICES.find(([n]) => n === name) || [])[1]} ${name}`;
            const answer = done.refused ? done : { said: `${key}: ${named} drawn` };
            said(answer.refused || answer.said);
            return answer;
        }
        if (what === "make") {
            if (name === "router" && kind() === "word") return { refused: NOT_CUT };
            // What is typed and not yet drawn is drawn first, so what is made is what the
            // window says.
            const key = subject.key;
            if (resting) {
                rest(null);
                const drawn = await world.apply(key);
                if (drawn.refused) return drawn;
                if (subject?.key !== key) return { refused: `${key} is no longer selected: nothing made` };
            }
            return world.make(key, name);
        }
        return { refused: `the Badge window has no ${verb}` };
    }

    async function clicked(ev) {
        const button = ev.target.closest("button[data-face], button[data-make]");
        if (!button || button.disabled) return;
        const face = button.dataset.face;
        const done = await act(face ? (face === "word" ? "word" : `face:${face}`) : `make:${button.dataset.make}`);
        // ⚒ Make says what it did, and the slice or toolpath after it says what it made:
        // said again here, its first words would stand over the newer. A choice a newer
        // one stopped leaves the newer to speak.
        if (done.superseded || (!face && !done.refused)) return;
        world.say(done.refused || done.said || "", done.refused ? "error" : "success");
    }
    badgeEl.addEventListener("click", (ev) => clicked(ev));

    paint();
    return { follow, refresh, act, state: () => ({ key: subject?.key ?? null, chosen: subject ? chosen() : null, staged: { ...staged } }) };
}
