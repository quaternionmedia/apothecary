// The tour over the page: a journey's stages (apothecary/journeys.py) in a box above the
// windows. A stage is put on by the page -- its machine's window opened, its piece
// chosen, its step entered -- and a person explores it there, then says how it is:
// as shown, or off with what is off (POST /tour/stages, apothecary/tour.py). The box is
// in the browser's top layer, so no view or journey lays it out or covers it; it is
// dragged by its head and folded to it. A prototype, on Make a thing.
//
// `stage(journey, stageId)` is the page's: it resolves to `{ did: [...], said, refused }`.
// `demo` says whether this is `apothecary serve --demo`, the one place a stage is put on.

const KEPT = 'apothecary.tour-pop';

const MARKUP = `
<header class="tour-pop-head" title="Drag to move">
  <span class="tour-pop-name"></span>
  <button type="button" data-do="fold" title="Fold to this bar, or unfold">▁</button>
  <button type="button" data-do="close" title="Close the tour: the page stays as it is">✕</button>
</header>
<div class="tour-pop-body">
  <ol class="tour-pop-stages"></ol>
  <h4 class="tour-pop-stage"></h4>
  <p class="tour-pop-hint"></p>
  <div class="tour-pop-row">
    <button type="button" class="tour-pop-put" data-do="put"></button>
  </div>
  <ul class="tour-pop-did"></ul>
  <p class="tour-pop-explore"></p>
  <p class="tour-pop-answer"></p>
  <input class="tour-pop-note" type="text" placeholder="What is off, if it is" aria-label="What is off">
  <div class="tour-pop-row">
    <button type="button" data-do="back">‹ Back</button>
    <span class="grow"></span>
    <button type="button" data-do="as-shown">✓ As shown</button>
    <button type="button" data-do="off">✗ Off</button>
    <button type="button" data-do="next">Next ›</button>
  </div>
</div>`;

function kept() {
    try { return JSON.parse(localStorage.getItem(KEPT)) || {}; } catch (e) { return {}; }
}
function keep(more) {
    try { localStorage.setItem(KEPT, JSON.stringify({ ...kept(), ...more })); } catch (e) { /* this browser keeps nothing */ }
}

export function mountTourPopover({ base = '', demo = false, stage, onShown = () => {} }) {
    const box = document.createElement('div');
    box.className = 'tour-pop';
    box.id = 'tour-pop';
    box.setAttribute('popover', 'manual');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Tour');
    box.innerHTML = MARKUP;
    document.body.append(box);
    const $ = (sel) => box.querySelector(sel);
    const state = { journeys: [], journey: null, at: 0, busy: false, did: null };

    const journey = () => state.journeys.find((j) => j.id === state.journey) || state.journeys[0];
    const here = () => journey()?.stages[state.at];

    function place() {
        const { x, y } = kept();
        const w = box.offsetWidth || 352, h = box.offsetHeight || 300;
        const left = Math.min(Math.max(4, x ?? 16), window.innerWidth - w - 4);
        // Whole on the page however much it says: it grows upward from where it was left.
        const top = Math.max(4, Math.min(y ?? window.innerHeight - h - 48, window.innerHeight - h - 8));
        box.style.left = `${left}px`;
        box.style.top = `${top}px`;
    }

    function render() {
        const j = journey(), s = here();
        if (!j || !s) return;
        const answered = j.stages.filter((x) => x.answer).length;
        $('.tour-pop-name').textContent = `Tour · ${j.name} · ${answered} of ${j.stages.length} said`;
        const list = $('.tour-pop-stages');
        list.replaceChildren(...j.stages.map((x, i) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.dataset.at = String(i);
            b.textContent = `${i + 1} ${x.label}`;
            b.title = x.hint;
            if (i === state.at) b.setAttribute('aria-current', 'step');
            if (x.answer) b.className = x.answer.verdict === 'off' ? 'off' : 'as-shown';
            const li = document.createElement('li');
            li.append(b);
            return li;
        }));
        $('.tour-pop-stage').textContent = `${state.at + 1}. ${s.label}`;
        $('.tour-pop-hint').textContent = `${s.hint[0].toUpperCase()}${s.hint.slice(1)}.`;
        const put = $('.tour-pop-put');
        const on = Object.values(j.staged_on || {}).join(' and ');
        put.disabled = state.busy || !demo || !on;
        put.textContent = state.busy ? 'Putting the page here…' : 'Put the page here';
        put.title = demo
            ? `Opens and chooses what this stage needs (${on}), and enters it`
            : 'Only on the demo (apothecary serve --demo): here, do what the stage says in the page';
        const did = $('.tour-pop-did');
        did.className = `tour-pop-did${state.did?.refused ? ' refused' : ''}`;
        did.replaceChildren(...(state.did ? [...state.did.did, state.did.said].filter(Boolean) : []).map((t) => {
            const li = document.createElement('li');
            li.textContent = t;
            return li;
        }));
        $('.tour-pop-explore').textContent = demo
            ? 'Explore this stage in the page, then say how it is.'
            : 'This is not the demo, so the tour puts nothing on: do what the stage says in the page, then say how it is.';
        const a = s.answer;
        $('.tour-pop-answer').textContent = a
            ? `${a.verdict === 'off' ? `✗ Off: ${a.note}` : '✓ As shown'} -- said ${new Date(a.at).toLocaleString()} against ${a.commit || 'an unknown commit'}${a.changed ? ' with changes' : ''}`
            : 'Not said yet.';
        $('[data-do="back"]').disabled = state.at === 0;
        $('[data-do="next"]').disabled = state.at >= j.stages.length - 1;
        if (box.matches(':popover-open')) place();
    }

    async function read() {
        const doc = await fetch(`${base}/tour/journeys`).then((r) => r.json());
        state.journeys = doc.journeys;
        if (!state.journey) state.journey = kept().journey || doc.journeys[0]?.id;
    }

    async function put() {
        const j = journey(), s = here();
        if (!demo || !j || !s || state.busy) return;
        state.busy = true; state.did = null; render();
        try { state.did = await stage(j.id, s.id); }
        catch (e) { state.did = { did: [], said: `The stage was not put on: ${e.message || e}`, refused: true }; }
        state.busy = false; render();
    }

    async function go(at, { putOn = true } = {}) {
        const j = journey();
        if (!j || at < 0 || at >= j.stages.length) return;
        state.at = at; state.did = null;
        keep({ journey: j.id, at });
        render();
        if (putOn && demo) await put();
    }

    async function say(verdict) {
        const j = journey(), s = here();
        const note = $('.tour-pop-note').value;
        const r = await fetch(`${base}/tour/stages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ journey: j.id, stage: s.id, verdict, note }),
        });
        if (!r.ok) {
            const why = (await r.json().catch(() => ({}))).detail || r.statusText;
            $('.tour-pop-answer').textContent = `Not kept: ${why}.`;
            return;
        }
        $('.tour-pop-note').value = '';
        await read();
        if (state.at < j.stages.length - 1) await go(state.at + 1);
        else render();
    }

    box.addEventListener('click', (e) => {
        const b = e.target.closest('button');
        if (!b) return;
        if (b.dataset.at) return void go(Number(b.dataset.at));
        const verb = b.dataset.do;
        if (verb === 'close') return void api.close();
        if (verb === 'fold') { box.classList.toggle('folded'); keep({ folded: box.classList.contains('folded') }); return; }
        if (verb === 'put') return void put();
        if (verb === 'back') return void go(state.at - 1);
        if (verb === 'next') return void go(state.at + 1);
        if (verb === 'as-shown') return void say('as shown');
        if (verb === 'off') return void say('off');
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
    window.addEventListener('resize', () => { if (box.matches(':popover-open')) place(); });

    const api = {
        isOpen: () => box.matches(':popover-open'),
        async open({ putOn = false } = {}) {
            await read();
            const j = journey();
            const first = j ? j.stages.findIndex((s) => !s.answer) : 0;
            state.at = Math.min(kept().at ?? (first < 0 ? 0 : first), (j?.stages.length || 1) - 1);
            box.classList.toggle('folded', Boolean(kept().folded));
            box.showPopover();
            render(); place();
            keep({ open: true });
            onShown(true);
            if (putOn && demo) await put();
        },
        close() { box.hidePopover(); keep({ open: false }); onShown(false); },
        toggle() { return api.isOpen() ? api.close() : api.open(); },
        // The rail moved in the page: the box shows that stage, and puts nothing on.
        follow(journeyId, stageId) {
            const j = journey();
            if (!api.isOpen() || !j || j.id !== journeyId) return;
            const at = j.stages.findIndex((s) => s.id === stageId);
            if (at >= 0 && at !== state.at && !state.busy) { state.at = at; state.did = null; keep({ at }); render(); }
        },
        wasOpen: () => Boolean(kept().open),
    };
    return api;
}
