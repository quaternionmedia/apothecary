// The tour: the page's journeys (apothecary/journeys.py) a stage at a time, in a box over
// the page. Going to a stage takes the page there -- what it needs opened and chosen, the
// stage entered -- and a person explores it; one word is kept on the stage, under the
// name they give once: it works, or it is off with what is off (POST /tour/feedback,
// apothecary/tour.py). A word is of the build it was said of: said of an earlier one,
// it is shown as that and the stage waits again. The box has no words of its own: a
// stage's are the ones its journey's rail shows.
//
// The box is in the browser's top layer, so no view or journey lays it out or covers
// it; it is dragged by its head, and folded to it by a double-click there. It stands
// over the world, so it is kept small: its head names the stage, what the page did and
// what to try are folded under one line, and what it says is only what is not so yet.
//
// `stage(journey, stageId)` is the page's: it resolves to `{ did: [...], said, refused }`.

const KEPT = 'apothecary.tour';

const MARKUP = `
<header class="tour-pop-head" title="Drag to move; double-click to fold to this bar, or unfold">
  <span class="tour-pop-title"></span>
  <span class="tour-pop-name"></span>
  <button type="button" class="tour-pop-close" data-do="close" title="Close the tour: the page stays as it is">✕</button>
</header>
<div class="tour-pop-body">
  <select class="tour-pop-journeys" aria-label="Journeys"></select>
  <ol class="tour-pop-stages"></ol>
  <p class="tour-pop-words"><span class="tour-pop-said"></span>
    <button type="button" class="tour-pop-put" data-do="put" aria-label="Take the page here" title="Take the page here again: opens and chooses what this stage needs, and enters it">↻</button>
    <a class="tour-pop-page" target="_blank" rel="noopener" title="The walkthrough page that goes through this stage, in a tab">its page</a></p>
  <details class="tour-pop-more">
    <summary></summary>
    <ul class="tour-pop-did"></ul>
    <p class="tour-pop-needs"></p>
    <ul class="tour-pop-tries"></ul>
  </details>
  <p class="tour-pop-feedback"></p>
  <label class="tour-pop-who">as <input class="tour-pop-by" type="text" placeholder="your name" aria-label="Your name" maxlength="80" title="The name your words are kept under: asked once, and kept by this browser"></label>
  <div class="tour-pop-row">
    <button type="button" class="tour-pop-back" data-do="back" aria-label="Back" title="The stage before">‹</button>
    <input class="tour-pop-note" type="text" placeholder="What is off" aria-label="What is off" title="What is off at this stage: ✗ Off, or Enter, keeps it">
    <button type="button" class="tour-pop-works" data-do="works" title="This stage does what it says: kept, and on to the next">✓ Works</button>
    <button type="button" class="tour-pop-off" data-do="off" title="Something here is off, as the field says: kept, and on to the next">✗ Off</button>
    <button type="button" class="tour-pop-next" data-do="next" aria-label="Next" title="The next stage">›</button>
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

export function mountTourPopover({ base = '', stage, onShown = () => {} }) {
    const box = el('div', { className: 'tour-pop', id: 'tour-pop' });
    box.setAttribute('popover', 'manual');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Tour');
    box.innerHTML = MARKUP;
    document.body.append(box);
    const $ = (sel) => box.querySelector(sel);
    // Every stage in the journeys' order, each knowing its journey.
    const state = { journeys: [], stages: [], at: 0, busy: false, did: null };

    // What the page did and what to try, folded or open as a person left it.
    const more = $('.tour-pop-more');
    more.open = Boolean(kept().more);
    // Opened, it grows: placed again, so it stays whole on the page.
    more.addEventListener('toggle', () => { keep({ more: more.open }); if (box.matches(':popover-open')) place(); });

    // The name a word is kept under: asked once, kept by this browser.
    const who = $('.tour-pop-by');
    who.value = kept().by || '';
    who.addEventListener('change', function named() { keep({ by: who.value.trim() }); });

    const here = () => state.stages[state.at];
    const journeyOf = (s) => state.journeys[s.of];

    function place() {
        const { x, y } = kept();
        const w = box.offsetWidth || 352, h = box.offsetHeight || 200;
        const left = Math.min(Math.max(4, x ?? 16), window.innerWidth - w - 4);
        // Whole on the page however much it says: it grows upward from where it was left.
        const top = Math.max(4, Math.min(y ?? window.innerHeight - h - 48, window.innerHeight - h - 8));
        box.style.left = `${left}px`;
        box.style.top = `${top}px`;
    }

    // A word counts for the build it was said of: one of an earlier build is worn
    // dimmed, and its stage is among those still waiting.
    const now = (s) => (s.feedback?.current ? s.feedback : null);
    const mark = (s) => (s.feedback ? `${s.feedback.verdict === 'off' ? 'off' : 'works'}${s.feedback.current ? '' : ' earlier'}` : '');
    const count = (stages) => {
        const said = stages.filter(now).length, off = stages.filter((s) => now(s)?.verdict === 'off').length;
        return `${said}/${stages.length}${off ? ` · ${off} off` : ''}`;
    };

    function render() {
        const at = here();
        if (!at) return;
        const journey = journeyOf(at);
        const said = state.stages.filter(now).length, off = state.stages.filter((s) => now(s)?.verdict === 'off').length;
        const earlier = state.stages.filter((s) => s.feedback && !s.feedback.current).length;
        const name = $('.tour-pop-name');
        name.textContent = count(state.stages);
        name.title = `${said} of ${state.stages.length} stages have a word on this build, ${off} off${earlier ? `; ${earlier} more were said of an earlier build` : ''}`;

        const journeys = $('.tour-pop-journeys');
        journeys.replaceChildren(...state.journeys.map((j, i) => el('option', { value: String(i), textContent: `${j.name} · ${count(j.stages)}` })));
        journeys.value = String(at.of);

        $('.tour-pop-stages').replaceChildren(...journey.stages.map((s, i) => {
            const b = el('button', { type: 'button', className: mark(s), textContent: `${i + 1} ${s.title}`, title: s.words });
            b.dataset.stage = s.id;
            if (s.id === at.id) b.setAttribute('aria-current', 'step');
            return el('li', {}, b);
        }));

        $('.tour-pop-title').textContent = `${journey.name} · ${journey.stages.indexOf(at) + 1}. ${at.title}`;
        $('.tour-pop-said').textContent = `${at.words[0].toUpperCase()}${at.words.slice(1)}.`;
        $('.tour-pop-put').disabled = state.busy;
        const page = $('.tour-pop-page');
        page.hidden = !at.tries.length;
        if (at.tries.length) page.href = `${base}/walkthrough/${at.tries[0].page}`;
        box.classList.toggle('busy', state.busy);

        // What the page did to get here, then what it said, or what the stage needs
        // first, apart from what was done; and what there is to try:
        // each step's heading, a link to its picture where it has one, and each page
        // that shows the same thing whole, a link to the page. Folded under one line,
        // and open where the stage needs something first, which a person has to read.
        const needs = state.did?.refused ? state.did.said : '';
        const done = state.did ? [...state.did.did, !needs && state.did.said].filter(Boolean) : [];
        $('.tour-pop-did').replaceChildren(...done.map((t) => el('li', { textContent: t })));
        $('.tour-pop-needs').textContent = needs;
        $('.tour-pop-tries').replaceChildren(...at.tries.map((t) => {
            const text = t.heading;
            const href = t.index === null ? `${base}/walkthrough/${t.page}` : t.picture && `${base}/walkthrough/${t.picture}`;
            if (!href) return el('li', { textContent: text, title: t.words });
            const a = el('a', { textContent: text, href, target: '_blank', rel: 'noopener', title: t.words });
            return el('li', { className: t.index === null ? 'whole' : '' }, a);
        }));
        more.hidden = !done.length && !needs && !at.tries.length;
        if (needs) more.open = true;
        $('.tour-pop-more summary').textContent = needs
            ? 'This stage needs something first'
            : [done.length && 'what the page did', at.tries.length && `${at.tries.length} to try`].filter(Boolean).join(' · ');

        const f = at.feedback;
        $('.tour-pop-feedback').textContent = f
            ? `${f.verdict === 'off' ? `✗ Off: ${f.note}` : '✓ Works'} -- said${f.by ? ` by ${f.by}` : ''} ${new Date(f.at).toLocaleString()}${f.current ? '' : `, of an earlier build${f.commit ? ` (${f.commit})` : ''}: this stage waits for a word again`}`
            : '';
        $('.tour-pop-back').disabled = state.at === 0;
        $('.tour-pop-next').disabled = state.at >= state.stages.length - 1;
        if (box.matches(':popover-open')) place();
    }

    async function read() {
        const doc = await fetch(`${base}/tour`).then((r) => r.json());
        const id = here()?.id;
        state.journeys = doc.journeys;
        state.stages = doc.journeys.flatMap((j, i) => j.stages.map((s) => Object.assign(s, { of: i })));
        if (id) state.at = Math.max(0, state.stages.findIndex((s) => s.id === id));
    }

    async function put() {
        const at = here();
        if (!at || state.busy) return;
        state.busy = true; state.did = null; render();
        try { state.did = await stage(at.journey, at.stage); }
        catch (e) { state.did = { did: [], said: `The page did not get here: ${e.message || e}`, refused: true }; }
        state.busy = false; render();
    }

    async function go(at, { putOn = true } = {}) {
        if (at < 0 || at >= state.stages.length) return;
        state.at = at; state.did = null;
        keep({ stage: here().id });
        render();
        if (putOn) await put();
    }

    async function say(verdict) {
        const at = here();
        const note = $('.tour-pop-note').value, by = who.value.trim();
        if (!by) {
            $('.tour-pop-feedback').textContent = 'Not kept: say who you are, once, in the field below.';
            who.focus();
            return;
        }
        const r = await fetch(`${base}/tour/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage: at.id, verdict, note, by }),
        });
        if (!r.ok) {
            const why = (await r.json().catch(() => ({}))).detail || r.statusText;
            $('.tour-pop-feedback').textContent = `Not kept: ${why}.`;
            return;
        }
        $('.tour-pop-note').value = '';
        await read();
        if (state.at < state.stages.length - 1) await go(state.at + 1);
        else render();
    }

    const api = {
        isOpen: () => box.matches(':popover-open'),
        async open() {
            await read();
            const was = state.stages.findIndex((s) => s.id === kept().stage);
            const first = state.stages.findIndex((s) => !now(s));
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
            if (verb === 'works') return say('works');
            if (verb === 'off') return say('off');
            if (verb === 'by') return void who.focus();
            if (verb === 'page') { const page = here().tries[0]?.page; if (page) window.open(`${base}/walkthrough/${page}`, '_blank', 'noopener'); }
        },
        // The rail moved in the page: the box shows that stage, and puts nothing on.
        follow(journeyId, stageId) {
            if (!api.isOpen() || state.busy) return;
            const at = state.stages.findIndex((s) => s.journey === journeyId && s.stage === stageId);
            if (at >= 0 && at !== state.at) { state.at = at; state.did = null; keep({ stage: here().id }); render(); }
        },
        wasOpen: () => Boolean(kept().open),
    };

    box.addEventListener('click', (e) => {
        const b = e.target.closest('button');
        if (!b) return;
        if (b.dataset.stage) return void go(state.stages.findIndex((s) => s.id === b.dataset.stage));
        api.act(b.dataset.do);
    });
    // A journey chosen: its first stage, the page taken there.
    const tourJourneys = $('.tour-pop-journeys');
    tourJourneys.addEventListener('change', function chosen() {
        const first = state.stages.findIndex((s) => s.of === Number(tourJourneys.value));
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
    const noteField = $('.tour-pop-note');
    noteField.addEventListener('keydown', (e) => { if (e.key === 'Enter') api.act('off'); });
    window.addEventListener('resize', () => { if (api.isOpen()) place(); });
    return api;
}
