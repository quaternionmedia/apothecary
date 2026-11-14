// The tour: what the roadmap claims (docs/ROADMAP.md), a stop at a time, in a box over the
// page. A stop is a stage of a journey (apothecary/journeys.py) or a walkthrough page.
// A stage is put on by the page -- what it needs opened, chosen and made, the stage
// entered -- and a person explores it there; a page is read, with the steps its
// test recorded. Either way one word is kept on the stop: as shown, or off with what
// is off (POST /tour/answers, apothecary/tour.py). The box has no words of its own: a
// stop's are the journey's or the page's.
//
// The box is in the browser's top layer, so no view or journey lays it out or covers
// it; it is dragged by its head, and folded to it by a double-click there. It stands
// over the world, so it is kept small: its head names the stop, what the page did and
// what to try are folded under one line, and what it says is only what is not so yet.
//
// `stage(journey, stageId)` is the page's: it resolves to `{ did: [...], said, refused }`.
// `demo` says whether this is `apothecary serve --demo`, the one place a stage is put on.

const KEPT = 'apothecary.tour';

const MARKUP = `
<header class="tour-pop-head" title="Drag to move; double-click to fold to this bar, or unfold">
  <span class="tour-pop-title"></span>
  <span class="tour-pop-name"></span>
  <button type="button" class="tour-pop-close" data-do="close" title="Close the tour: the page stays as it is">✕</button>
</header>
<div class="tour-pop-body">
  <select class="tour-pop-lines" aria-label="The roadmap's lines"></select>
  <ol class="tour-pop-stops"></ol>
  <p class="tour-pop-words"><span class="tour-pop-said"></span>
    <button type="button" class="tour-pop-put" data-do="put" aria-label="Put the page here">↻</button>
    <a class="tour-pop-page" target="_blank" rel="noopener">its page</a></p>
  <p class="tour-pop-explore"></p>
  <details class="tour-pop-more">
    <summary></summary>
    <ul class="tour-pop-did"></ul>
    <ul class="tour-pop-tries"></ul>
  </details>
  <p class="tour-pop-answer"></p>
  <div class="tour-pop-row">
    <button type="button" class="tour-pop-back" data-do="back" aria-label="Back" title="The stop before">‹</button>
    <input class="tour-pop-note" type="text" placeholder="What is off" aria-label="What is off" title="What is off at this stop: ✗ Off, or Enter, keeps it">
    <button type="button" class="tour-pop-as-shown" data-do="as-shown" title="The page does what this stop shows: kept, and on to the next">✓ As shown</button>
    <button type="button" class="tour-pop-off" data-do="off" title="This stop is off, with what the field says: kept, and on to the next">✗ Off</button>
    <button type="button" class="tour-pop-next" data-do="next" aria-label="Next" title="The next stop">›</button>
  </div>
</div>`;

function kept() {
    try { return JSON.parse(localStorage.getItem(KEPT)) || {}; } catch (e) { return {}; }
}
function keep(more) {
    try { localStorage.setItem(KEPT, JSON.stringify({ ...kept(), ...more })); } catch (e) { /* this browser keeps nothing */ }
}
const el = (tag, props = {}, ...kids) => {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...kids);
    return node;
};

export function mountTourPopover({ base = '', demo = false, stage, onShown = () => {} }) {
    const box = el('div', { className: 'tour-pop', id: 'tour-pop' });
    box.setAttribute('popover', 'manual');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Tour');
    box.innerHTML = MARKUP;
    document.body.append(box);
    const $ = (sel) => box.querySelector(sel);
    // Every stop in the roadmap's order, each knowing its line.
    const state = { lines: [], stops: [], at: 0, busy: false, did: null };

    // What the page did and what to try, folded or open as a person left it.
    const more = $('.tour-pop-more');
    more.open = Boolean(kept().more);
    // Opened, it grows: placed again, so it stays whole on the page.
    more.addEventListener('toggle', () => { keep({ more: more.open }); if (box.matches(':popover-open')) place(); });

    const here = () => state.stops[state.at];
    const lineOf = (stop) => state.lines[stop.line];

    function place() {
        const { x, y } = kept();
        const w = box.offsetWidth || 352, h = box.offsetHeight || 200;
        const left = Math.min(Math.max(4, x ?? 16), window.innerWidth - w - 4);
        // Whole on the page however much it says: it grows upward from where it was left.
        const top = Math.max(4, Math.min(y ?? window.innerHeight - h - 48, window.innerHeight - h - 8));
        box.style.left = `${left}px`;
        box.style.top = `${top}px`;
    }

    const mark = (stop) => (stop.answer ? (stop.answer.verdict === 'off' ? 'off' : 'as-shown') : '');
    const count = (stops) => {
        const said = stops.filter((s) => s.answer).length, off = stops.filter((s) => s.answer?.verdict === 'off').length;
        return `${said}/${stops.length}${off ? ` · ${off} off` : ''}`;
    };

    function render() {
        const stop = here();
        if (!stop) return;
        const line = lineOf(stop);
        const said = state.stops.filter((s) => s.answer).length, off = state.stops.filter((s) => s.answer?.verdict === 'off').length;
        const name = $('.tour-pop-name');
        name.textContent = `${said}/${state.stops.length}${off ? ` · ${off} off` : ''}`;
        name.title = `The tour: ${said} of ${state.stops.length} stops said, ${off} off`;

        const lines = $('.tour-pop-lines');
        lines.replaceChildren();
        let group = null;
        state.lines.forEach((l, i) => {
            if (!group || group.label !== l.group) { group = el('optgroup', { label: l.group }); lines.append(group); }
            const text = l.shown_by_nothing ? `${l.text} · shown by nothing` : `${l.text} · ${count(l.stops)}`;
            group.append(el('option', { value: String(i), textContent: text, disabled: l.shown_by_nothing }));
        });
        lines.value = String(stop.line);

        $('.tour-pop-stops').replaceChildren(...line.stops.map((s, i) => {
            const b = el('button', { type: 'button', className: mark(s), textContent: s.kind === 'stage' ? `${i + 1} ${s.title}` : s.number, title: s.kind === 'stage' ? s.words : s.title });
            b.dataset.stop = s.id;
            if (s.id === stop.id) b.setAttribute('aria-current', 'step');
            return el('li', {}, b);
        }));

        const isStage = stop.kind === 'stage';
        $('.tour-pop-title').textContent = isStage
            ? `${stop.journey_name} · ${line.stops.indexOf(stop) + 1}. ${stop.title}`
            : `${stop.number} — ${stop.title}`;
        $('.tour-pop-said').textContent = isStage ? `${stop.words[0].toUpperCase()}${stop.words.slice(1)}.` : stop.words;

        const put = $('.tour-pop-put');
        put.hidden = !isStage;
        put.disabled = state.busy || !demo || !stop.put_on;
        box.classList.toggle('busy', state.busy);
        put.title = demo
            ? 'Put the page here again: opens and chooses what this stage needs, and enters it'
            : 'Only on the demo (apothecary serve --demo): here, do what the stage says in the page';
        const page = $('.tour-pop-page');
        page.hidden = isStage;
        if (!isStage) page.href = `${base}/walkthrough/${stop.page}`;

        // What the page did to stand here, then what it said; and what its tests
        // recorded: each step's heading, a link to its picture where it has one, and each
        // page that shows it whole, a link to the page. Folded under one line, and open
        // where the page refused, which is what a person has to read.
        const done = state.did ? [...state.did.did, state.did.said].filter(Boolean) : [];
        const did = $('.tour-pop-did');
        did.className = `tour-pop-did${state.did?.refused ? ' refused' : ''}`;
        did.replaceChildren(...done.map((t) => el('li', { textContent: t })));
        $('.tour-pop-tries').replaceChildren(...stop.tries.map((t) => {
            const text = t.heading;
            const href = t.index === null ? `${base}/walkthrough/${t.page}` : t.picture && `${base}/walkthrough/${t.picture}`;
            if (!href) return el('li', { textContent: text, title: t.words });
            const a = el('a', { textContent: text, href, target: '_blank', rel: 'noopener', title: t.words });
            return el('li', { className: t.index === null ? 'whole' : '' }, a);
        }));
        more.hidden = !done.length && !stop.tries.length;
        if (state.did?.refused) more.open = true;
        $('.tour-pop-more summary').textContent = state.did?.refused
            ? 'The page was not put here'
            : [done.length && 'what the page did', stop.tries.length && `${stop.tries.length} to try`].filter(Boolean).join(' · ');

        // Said only where it is not so: a page is read, and off the demo nothing is put on.
        $('.tour-pop-explore').textContent = isStage
            ? (demo ? '' : 'This is not the demo, so the tour puts nothing on: do what the stage says in the page, then say how it is.')
            : 'Shown only: a page is read, not put on.';
        const a = stop.answer;
        $('.tour-pop-answer').textContent = a
            ? `${a.verdict === 'off' ? `✗ Off: ${a.note}` : '✓ As shown'} -- said ${new Date(a.at).toLocaleString()} against ${a.commit || 'an unknown commit'}${a.changed ? ' with changes' : ''}`
            : '';
        $('.tour-pop-back').disabled = state.at === 0;
        $('.tour-pop-next').disabled = state.at >= state.stops.length - 1;
        if (box.matches(':popover-open')) place();
    }

    async function read() {
        const doc = await fetch(`${base}/tour`).then((r) => r.json());
        const id = here()?.id;
        state.lines = doc.lines;
        state.stops = doc.lines.flatMap((l, i) => l.stops.map((s) => Object.assign(s, { line: i })));
        if (id) state.at = Math.max(0, state.stops.findIndex((s) => s.id === id));
    }

    async function put() {
        const stop = here();
        if (!demo || !stop || stop.kind !== 'stage' || !stop.put_on || state.busy) return;
        state.busy = true; state.did = null; render();
        try { state.did = await stage(stop.journey, stop.stage); }
        catch (e) { state.did = { did: [], said: `The stage was not put on: ${e.message || e}`, refused: true }; }
        state.busy = false; render();
    }

    async function go(at, { putOn = true } = {}) {
        if (at < 0 || at >= state.stops.length) return;
        state.at = at; state.did = null;
        keep({ stop: here().id });
        render();
        if (putOn) await put();
    }

    async function say(verdict) {
        const stop = here();
        const note = $('.tour-pop-note').value;
        const r = await fetch(`${base}/tour/answers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stop: stop.id, verdict, note }),
        });
        if (!r.ok) {
            const why = (await r.json().catch(() => ({}))).detail || r.statusText;
            $('.tour-pop-answer').textContent = `Not kept: ${why}.`;
            return;
        }
        $('.tour-pop-note').value = '';
        await read();
        if (state.at < state.stops.length - 1) await go(state.at + 1);
        else render();
    }

    const api = {
        isOpen: () => box.matches(':popover-open'),
        async open() {
            await read();
            const was = state.stops.findIndex((s) => s.id === kept().stop);
            const first = state.stops.findIndex((s) => !s.answer && lineOf(s).ticked);
            state.at = was >= 0 ? was : Math.max(0, first);
            box.classList.toggle('folded', Boolean(kept().folded));
            box.showPopover();
            render(); place();
            keep({ open: true });
            onShown(true);
        },
        close() { box.hidePopover(); keep({ open: false }); onShown(false); },
        toggle() { return api.isOpen() ? api.close() : api.open(); },
        // What the box's buttons do, for the ring's Panels › Windows › Tour cells.
        async act(verb) {
            if (verb === 'toggle') return api.toggle();
            if (!api.isOpen()) await api.open();
            if (verb === 'close') return api.close();
            if (verb === 'fold') { box.classList.toggle('folded'); keep({ folded: box.classList.contains('folded') }); return; }
            if (verb === 'put') return put();
            if (verb === 'back') return go(state.at - 1);
            if (verb === 'next') return go(state.at + 1);
            if (verb === 'as-shown') return say('as shown');
            if (verb === 'off') return say('off');
            if (verb === 'page') { const s = here(); const page = s.kind === 'page' ? s.page : s.tries[0]?.page; if (page) window.open(`${base}/walkthrough/${page}`, '_blank', 'noopener'); }
        },
        // The rail moved in the page: the box shows that stage, and puts nothing on.
        follow(journeyId, stageId) {
            if (!api.isOpen() || state.busy) return;
            const at = state.stops.findIndex((s) => s.kind === 'stage' && s.journey === journeyId && s.stage === stageId);
            if (at >= 0 && at !== state.at) { state.at = at; state.did = null; keep({ stop: here().id }); render(); }
        },
        wasOpen: () => Boolean(kept().open),
    };

    box.addEventListener('click', (e) => {
        const b = e.target.closest('button');
        if (!b) return;
        if (b.dataset.stop) return void go(state.stops.findIndex((s) => s.id === b.dataset.stop));
        api.act(b.dataset.do);
    });
    // A line chosen: its first stop, put on where it can be.
    const tourLines = $('.tour-pop-lines');
    tourLines.addEventListener('change', function chosen() {
        const first = state.stops.findIndex((s) => s.line === Number(tourLines.value));
        if (first >= 0) go(first);
    });

    // Dragged by its head, kept where it was left.
    const head = $('.tour-pop-head');
    head.addEventListener('pointerdown', (e) => {
        if (e.target.closest('button')) return;
        const dx = e.clientX - box.offsetLeft, dy = e.clientY - box.offsetTop;
        head.setPointerCapture(e.pointerId);
        const move = (m) => { keep({ x: m.clientX - dx, y: m.clientY - dy }); place(); };
        const up = () => { head.removeEventListener('pointermove', move); head.removeEventListener('pointerup', up); };
        head.addEventListener('pointermove', move);
        head.addEventListener('pointerup', up);
    });
    head.addEventListener('dblclick', (e) => { if (!e.target.closest('button')) api.act('fold'); });
    $('.tour-pop-note').addEventListener('keydown', (e) => { if (e.key === 'Enter') api.act('off'); });
    window.addEventListener('resize', () => { if (api.isOpen()) place(); });
    return api;
}
