// The tour: the page's journeys (apothecary/journeys.py) a stage at a time, in a box over
// the page, and the one place a journey is chosen and stepped. Going to a stage takes the
// page there -- what it needs opened and chosen, the stage entered -- and a person
// explores it; one word is kept on the stage, under the name they give once: it works, or
// it is off with what is off (POST /tour/feedback, apothecary/tour.py). A word is of the
// build it was said of: said of an earlier one, it is shown as that and the stage waits
// again. The box has no words of its own: a stage's are its step's in journeys.py.
// Closed, its journey is left (`onShown(false)`); folded to its head, it is not.
//
// The box is in the browser's top layer, so no view or journey lays it out or covers
// it; it is dragged by its head, and folded to it by a double-click there. It stands
// over the world, so it is kept small: its head names the stage, what the page did and
// what to try are folded under one line, and what it says is only what is not so yet.
//
// `stage(journey, stageId, { reload })` is the page's: it resolves to `{ did: [...], said,
// refused }`. `reload` is true where no one pressed anything -- a reload found the box
// open, or the address named a stage -- and the page then starts nothing: a slice, a toolpath or shapes found are a
// person's press, and the stage says so.

import { setReason } from '/static/can.js';
import { stamp } from '/static/format.js';

const KEPT = 'apothecary.tour';

const MARKUP = `
<header class="tour-pop-head" title="Drag to move; double-click to fold to this bar, or unfold">
  <span class="tour-pop-title"></span>
  <span class="tour-pop-name"></span>
  <button type="button" class="tour-pop-close" data-do="close" title="Close the tour and leave its journey: the windows stay where they are">✕</button>
</header>
<div class="tour-pop-body">
  <select class="tour-pop-journeys" aria-label="Journeys"></select>
  <ol class="tour-pop-stages"></ol>
  <p class="tour-pop-words"><span class="tour-pop-said"></span>
    <button type="button" class="tour-pop-put" data-do="put" aria-label="Take the page here" title="Take the page here again: opens and chooses what this stage needs, and enters it">↻</button>
    <a class="tour-pop-page" target="_blank" rel="noopener" title="The walkthrough page that goes through this stage, at the step it names first, in a tab">its page</a></p>
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

export function mountTourPopover({ base = '', stage, onShown = () => {}, settled = () => {} }) {
    const box = el('div', { className: 'tour-pop', id: 'tour-pop' });
    box.setAttribute('popover', 'manual');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Tour');
    box.innerHTML = MARKUP;
    document.body.append(box);
    const $ = (sel) => box.querySelector(sel);
    // Every stage in the journeys' order, each knowing its journey.
    const state = { journeys: [], stages: [], at: 0, busy: false, did: null, after: null };

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
    // Where a thing to try is: a step on its walkthrough page, its words and picture
    // together under the page's bar, or a page whole.
    const pageOf = (t) => `${base}/walkthrough/${t.page}${t.anchor ? `#${t.anchor}` : ''}`;

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
    // Each stage with a word on any build counts, so a deploy loses no progress; those
    // said of an earlier build are counted apart, and wait for a word again.
    const count = (stages) => {
        const said = stages.filter((s) => s.feedback).length;
        const earlier = stages.filter((s) => s.feedback && !s.feedback.current).length;
        const off = stages.filter((s) => s.feedback?.verdict === 'off').length;
        return `${said}/${stages.length}${earlier ? ` · ${earlier} earlier` : ''}${off ? ` · ${off} off` : ''}`;
    };

    function render() {
        const at = here();
        if (!at) return;
        const journey = journeyOf(at);
        const said = state.stages.filter((s) => s.feedback).length, off = state.stages.filter((s) => s.feedback?.verdict === 'off').length;
        const earlier = state.stages.filter((s) => s.feedback && !s.feedback.current).length;
        const name = $('.tour-pop-name');
        name.textContent = count(state.stages);
        name.title = `${said} of ${state.stages.length} stages have a word, ${off} off${earlier ? `; ${earlier} of them said of an earlier build, each waiting for a word on this one` : ''}`;

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
        if (at.tries.length) page.href = pageOf(at.tries[0]);
        box.classList.toggle('busy', state.busy);

        // What the page did to get here, then what it said, or what the stage needs
        // first, apart from what was done; and what there is to try:
        // each step's heading, a link to the step on its page, and each page that shows
        // the same thing whole, a link to the page. Folded under one line, and open
        // where the stage needs something first, which a person has to read.
        const needs = state.did?.refused ? state.did.said : '';
        const done = state.did ? [...state.did.did, !needs && state.did.said].filter(Boolean) : [];
        $('.tour-pop-did').replaceChildren(...done.map((t) => el('li', { textContent: t })));
        $('.tour-pop-needs').textContent = needs;
        $('.tour-pop-tries').replaceChildren(...at.tries.map((t) => {
            const a = el('a', { textContent: t.heading, href: pageOf(t), target: '_blank', rel: 'noopener', title: t.words });
            return el('li', { className: t.index === null ? 'whole' : '' }, a);
        }));
        more.hidden = !done.length && !needs && !at.tries.length;
        if (needs) more.open = true;
        $('.tour-pop-more summary').textContent = needs
            ? 'This stage needs something first'
            : [done.length && 'what the page did', at.tries.length && `${at.tries.length} to try`].filter(Boolean).join(' · ');

        const f = at.feedback;
        $('.tour-pop-feedback').textContent = f
            ? `${f.verdict === 'off' ? `✗ Off: ${f.note}` : '✓ Works'} -- said${f.by ? ` by ${f.by}` : ''} ${stamp(f.at)}${f.current ? '' : `, of an earlier build${f.commit ? ` (${f.commit})` : ''}: this stage waits for a word again`}`
            : '';
        setReason($('.tour-pop-back'), state.at === 0 ? 'this is the journey\'s first stage' : null, 'The stage before');
        setReason($('.tour-pop-next'), state.at >= state.stages.length - 1 ? 'this is the journey\'s last stage' : null, 'The next stage');
        if (box.matches(':popover-open')) place();
    }

    async function read() {
        const doc = await fetch(`${base}/tour`).then((r) => r.json());
        const id = here()?.id;
        state.journeys = doc.journeys;
        state.stages = doc.journeys.flatMap((j, i) => j.stages.map((s) => Object.assign(s, { of: i })));
        if (id) state.at = Math.max(0, state.stages.findIndex((s) => s.id === id));
    }

    async function put({ reload = false } = {}) {
        const at = here();
        if (!at || state.busy) return;
        state.busy = true; state.did = null; state.after = null; render();
        try { state.did = await stage(at.journey, at.stage, { reload }); }
        catch (e) { state.did = { did: [], said: `The page did not get here: ${e.message || e}`, refused: true }; }
        state.busy = false; render();
        // The box at the size what it says gives it: the page frames around it again.
        settled();
        // A window chosen on the way was another stage's: followed now the page is here.
        const after = state.after;
        state.after = null;
        if (after) api.follow(after.journey, after.stage);
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

    // Where a reload finds the box open, the page is taken to its stage as the stage's
    // ↻ does: the box holds what a person was doing, the page does not, and the box
    // never stands over a page it is not true of. No one pressed anything, so nothing is
    // started on the way: what only a job brings, the box says ↻ does. An address that
    // names a journey's stage opens the box on it the same way (`openOn`).
    let opening = Promise.resolve();
    const api = {
        isOpen: () => box.matches(':popover-open'),
        open() { return (opening = api.opened()); },
        restage: async () => { await opening; if (api.isOpen()) await put({ reload: true }); },
        async openOn(journeyId, stageId) {
            await opening;
            if (!api.isOpen()) await api.open();
            const at = state.stages.findIndex((s) => s.journey === journeyId && s.stage === stageId);
            if (at < 0) return;
            state.at = at; state.did = null;
            keep({ stage: here().id });
            render();
            await put({ reload: true });
        },
        async opened() {
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
            if (verb === 'page') { const first = here().tries[0]; if (first) window.open(pageOf(first), '_blank', 'noopener'); }
        },
        // A window chosen in the page is another stage's: the box shows that stage, and
        // puts nothing on. While the page is on its way to a stage, it is kept until then.
        follow(journeyId, stageId) {
            if (!api.isOpen()) return;
            if (state.busy) { state.after = { journey: journeyId, stage: stageId }; return; }
            const at = state.stages.findIndex((s) => s.journey === journeyId && s.stage === stageId);
            if (at >= 0 && at !== state.at) { state.at = at; state.did = null; keep({ stage: here().id }); render(); }
        },
        wasOpen: () => Boolean(kept().open),
        isFolded: () => box.classList.contains('folded'),
        // Folded to its head (`on`) or not, kept as a person's double-click keeps it.
        fold(on) { box.classList.toggle('folded', on); keep({ folded: on }); place(); },
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
