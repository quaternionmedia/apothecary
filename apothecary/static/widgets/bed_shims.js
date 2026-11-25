/* Bed shims: a printer's bed readings, how they differ, the shims that level it and its
 * range over the readings (docs/bed-shims.md). Four windows of the Machine's group,
 * closed until asked for: Runs, Differences, Fixes and History, of the printer whose
 * Machine is open.
 *
 * Everything shown is the server's (GET /bed/{site}/{printer}, apothecary/bed_shims.py's
 * `story`): the readings of the printer's pinned board, newest first; the newest heated
 * pair's shims; the pair's own difference, the floor; the newest pair less the pair before
 * it; and what the plane leaves, the bow. The page computes nothing the server computes.
 * It lays a grid out as a heatmap, back row on top as the bed lies, blue below and amber
 * above (the Bed mesh layer's two colours, machine_marks.js). It also draws the bed from
 * above with each screw where the printer's profile says it stands.
 *
 * Choosing a run draws it over the printer's bed in the world (`draw`). The shims are
 * drawn at their screws there whenever Fixes has them (`shims`). Make these hands the
 * shims to the printer's Print window, rendered at their thicknesses and sliced there
 * (`make`): nothing is printed, and ▶ Print is a person's.
 *
 * Fixes says what each shim fits: the hole its bed screw passes and the ring across, at
 * least the mount's face -- the printer's own once a person has kept them, else the
 * part's defaults, marked as defaults. Keep takes them from Parameters, where bed_shims
 * is chosen (its screw, M3 or M4, a hole typed over it, calipers' reading as the ring), and keeps
 * them as the printer's (PUT /bed/{site}/{printer}/mount): the state folder holds them
 * across a reload and a restart, and every slice of the shims after takes them.
 *
 * Above the runs, Probe hot: the bed heated to the filament's bed temperature (the Print
 * window's filament; a temperature typed over it) and held the seconds typed (90 by
 * default), then probed twice, a reading each, and turned off after -- the heated pair the
 * shims are computed from, in the Machine's own probe.
 *
 * mountBedShims({ runs, differences, fixes, history }, { base, printer, say, draw, shims, make, measured, probeHot, bedTemperature })
 *   printer(): { site, path } of the open Machine's printer, or null
 *   say(text, kind): the page's status line
 *   draw(record, newest): a reading drawn over the printer's bed in the world, and kept
 *   drawn until a reading newer than `newest` is taken
 *   shims(list, mount): each screw's shim drawn at its screw in the world, as wide as the
 *   mount's ring; null clears them
 *   make(params): the part bed_shims at `params` sliced for the printer; what it said
 *   stand(params): the shims stood on the site's bed_shims pieces, as an Apply would:
 *   drawn, shown in Parameters and made by a Slice or ⚒ Make of the part. Fixes asks it
 *   whenever the readings call for other shims than it last stood
 *   measured(): { screw, hole_d, outer_d } as Parameters holds them for bed_shims (hole_d
 *   null where none is typed over the screw's), or null
 *   probeHot(heat, soak): the open Machine's bed probed hot; { said } or { refused }
 *   bedTemperature(): the bed temperature of the filament its Print window holds, or null
 *   -> { load(), choose(id), act(verb), story() }
 *   act("make" | "keep" | "probe-hot"): Make these, Keep, Probe hot, as the ring's Panels ›
 *   Machine › Bed cells do them; what it did, or an Error saying why not.
 */

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LOW = [0x6f, 0xb3, 0xe8];   // the Bed mesh layer's blue, below
const HIGH = [0xe8, 0xb0, 0x4a];  // its amber, above
const MID = [0x3a, 0x3f, 0x3a];   // none either way, on a difference
const mm = (v, d = 3) => (typeof v === "number" ? v.toFixed(d) : "?");
const stamp = (at) => (at ? at.replace("T", " ").slice(0, 16) + " UTC" : "no time");

function blend(a, b, t) {
    return `rgb(${a.map((c, i) => Math.round(c + (b[i] - c) * t)).join(",")})`;
}
// A reading's colour: its least blue, its most amber.
const ofRange = (v, lo, hi) => blend(LOW, HIGH, hi > lo ? (v - lo) / (hi - lo) : 0.5);
// A difference's: blue below none, amber above, by the larger side.
function ofDifference(v, most) {
    if (!(most > 0)) return blend(MID, MID, 0);
    return v < 0 ? blend(MID, LOW, Math.min(1, -v / most)) : blend(MID, HIGH, Math.min(1, v / most));
}

/* A grid as a heatmap, rows from the front, so the last row is drawn on top. */
function heatmap(grid, colour, name) {
    if (!grid || !grid.length) return "";
    const cols = grid[0].length;
    const cells = [...grid].reverse().map((row) => row.map((v) =>
        `<div class="bed-cell" style="background:${colour(v)}" title="${esc(mm(v))} mm">${esc(v.toFixed(2))}</div>`).join("")).join("");
    return `<div class="bed-heat" data-heat="${esc(name)}" style="grid-template-columns:repeat(${cols},1fr)">${cells}</div>`;
}

function flatOf(grid) { return (grid || []).flat(); }

export function mountBedShims(sections, { base, printer, say, draw, shims, make, stand, measured, probeHot = null, bedTemperature = null }) {
    const el = sections;
    let story = null, chosen = null, error = null, loading = null, stood = null;
    // Probe hot above the runs, drawn once: what is typed there stays as the runs redraw.
    let runsList = null, hotC = null, soakS = null;
    if (el.runs) {
        el.runs.innerHTML = `<div class="bed-hot"><label for="bed-hot-c">probe hot</label>
            <input id="bed-hot-c" type="number" min="1" max="130" step="1" size="4" title="The bed's temperature to probe it at, °C: the Print window's filament's, typed over where another is wanted"> °C, held
            <input id="bed-soak" type="number" min="0" max="3600" step="10" size="5" value="90" title="How long the bed is held at temperature before it is probed, s, so the plate settles through"> s
            <button type="button" id="bed-probe-hot" class="warm" title="Heat the bed, hold it, then home and probe it twice, a reading each, and turn it off after: the heated pair the shims are computed from. Control must be armed">▤ Probe hot</button></div>
            <div class="bed-runs-list"></div>`;
        runsList = el.runs.querySelector(".bed-runs-list");
        hotC = el.runs.querySelector("#bed-hot-c");
        soakS = el.runs.querySelector("#bed-soak");
        hotC.addEventListener("input", () => { hotC.dataset.typed = hotC.value ? "1" : ""; });
    }

    const empty = (text) => `<p class="bed-empty">${esc(text)}</p>`;

    function renderRuns() {
        if (!el.runs) return;
        // The filament's bed temperature, until a person types another.
        const t = bedTemperature ? bedTemperature() : null;
        if (hotC && !hotC.dataset.typed && t !== null && document.activeElement !== hotC) hotC.value = String(t);
        if (error) { runsList.innerHTML = empty(error); return; }
        if (!story) { runsList.innerHTML = empty("Open a printer's Machine: these windows are of its bed."); return; }
        const runs = story.runs || [];
        const head = `<p class="bed-head" data-board="${esc(story.board)}">${esc(story.printer)}'s board ${esc(story.board)}: ${runs.length} reading${runs.length === 1 ? "" : "s"}, newest first. A run chosen is drawn over the bed in the world.</p>`;
        if (!runs.length) { runsList.innerHTML = head + empty("No reading yet: ▤ Probe hot above heats the bed, holds it and probes it twice; or heat it, let it soak, then ▤ Probe bed in the Machine's Bed level, twice."); return; }
        runsList.innerHTML = head + runs.map((r) => {
            const lo = Math.min(...flatOf(r.mesh)), hi = Math.max(...flatOf(r.mesh));
            const warm = r.heated === true ? "heated" : r.heated === false ? "cold" : "unknown";
            const temp = r.bed_c == null ? "bed temperature not read" : `bed ${r.bed_c} °C`;
            return `<div class="bed-run ${r.id === chosen ? "on" : ""}" data-id="${esc(r.id)}" data-heated="${warm}" role="button" tabindex="0">`
                + heatmap(r.mesh, (v) => ofRange(v, lo, hi), r.id)
                + `<div class="bed-run-words"><b>${esc(stamp(r.at))}</b> · ${esc(r.method)} · ${esc(temp)} <span class="bed-warm ${warm}">${esc(warm)}</span>`
                + ` · range <b>${esc(mm(r.range))}</b> mm${r.note ? `<br>${esc(r.note)}` : ""}</div></div>`;
        }).join("");
    }

    function renderDifferences() {
        if (!el.differences) return;
        if (error || !story) { el.differences.innerHTML = empty(error || "Open a printer's Machine: these windows are of its bed."); return; }
        const d = story.differences || {};
        const parts = [];
        const rep = d.repeatability;
        if (rep) {
            const most = Math.max(...flatOf(rep.mesh).map(Math.abs));
            parts.push(`<section class="bed-diff" data-diff="repeatability"><h4>Run 2 less run 1: the repeatability floor, <b>${esc(mm(rep.floor))}</b> mm</h4>`
                + `<p>${esc(rep.of[1])} less ${esc(rep.of[0])}, probed one after the other: what the probe does not repeat. A shim thinner than the most of it is none.</p>`
                + heatmap(rep.mesh, (v) => ofDifference(v, most), "repeatability") + "</section>");
        } else {
            parts.push(`<section class="bed-diff" data-diff="repeatability">${empty("No heated pair yet: probe twice, one after the other, the bed heated and soaked, for the floor.")}</section>`);
        }
        const after = d.after;
        if (after) {
            const most = Math.max(...flatOf(after.mesh).map(Math.abs));
            const f = flatOf(after.mesh);
            parts.push(`<section class="bed-diff" data-diff="after"><h4>After less before: <b>${esc(mm(Math.min(...f)))}..${esc(mm(Math.max(...f)))}</b> mm</h4>`
                + `<p>The newest heated pair (${esc(after.after.join(", "))}) less the pair before it (${esc(after.before.join(", "))}): what the shims fitted between them did, with the floor in it.</p>`
                + heatmap(after.mesh, (v) => ofDifference(v, most), "after") + "</section>");
        } else {
            parts.push(`<section class="bed-diff" data-diff="after">${empty("No pair after shims yet: fit them, heat and soak the bed, and probe twice again.")}</section>`);
        }
        const bow = d.bow;
        if (bow) {
            const most = Math.max(...flatOf(bow.mesh).map(Math.abs));
            const over = bow.bound != null && bow.range >= bow.bound;
            parts.push(`<section class="bed-diff" data-diff="bow" data-over="${over}"><h4>What the plane leaves: the bow, <b>${esc(mm(bow.range))}</b> mm across, which no shim fixes</h4>`
                + `<p>The levelled readings less the plane through them.${bow.bound != null ? ` The bound for a stored mesh is ${esc(bow.bound)} mm (measured.mesh_range_bound): ${over ? "the bow alone is over it, so no shim brings a reading under it" : "the bow is under it, once the bed is level"}.` : ""}</p>`
                + heatmap(bow.mesh, (v) => ofDifference(v, most), "bow") + "</section>");
        }
        el.differences.innerHTML = parts.join("");
    }

    function bedSvg(s) {
        const [vx, vy] = story.volume || [220, 220];
        const W = 220, H = Math.round((W * vy) / vx), k = W / vx;
        const X = (x) => (x * k).toFixed(1), Y = (y) => (H - y * k).toFixed(1);
        const a = s.grid;
        const marks = s.shims.map((sh) => {
            const kind = sh.printed != null ? "shim" : sh.none === "the highest" ? "highest" : "skipped";
            const words = sh.printed != null ? `${sh.printed.toFixed(1)} mm` : sh.none === "the highest" ? "none" : "skipped";
            const right = sh.x > vx / 2, up = sh.y > vy / 2;
            return `<g class="bed-screw ${kind}" data-screw="${esc(sh.label)}" data-printed="${esc(sh.printed ?? "")}">`
                + `<circle cx="${X(sh.x)}" cy="${Y(sh.y)}" r="5"/>`
                + `<text x="${X(sh.x)}" y="${Y(sh.y)}" dx="${right ? -8 : 8}" dy="${up ? 14 : -8}" text-anchor="${right ? "end" : "start"}">${esc(sh.label)} ${esc(words)}</text></g>`;
        }).join("");
        return `<svg class="bed-top" viewBox="-10 -10 ${W + 20} ${H + 20}" role="img" aria-label="The bed from above, each screw with its shim" xmlns="http://www.w3.org/2000/svg">`
            + `<rect class="bed-plate" x="0" y="0" width="${W}" height="${H}"/>`
            + `<rect class="bed-grid" x="${X(a.x[0])}" y="${Y(a.y[1])}" width="${((a.x[1] - a.x[0]) * k).toFixed(1)}" height="${((a.y[1] - a.y[0]) * k).toFixed(1)}"><title>${esc(`the probed grid, placed by ${a.from}`)}</title></rect>`
            + `<text class="bed-front" x="${W / 2}" y="${H + 9}" text-anchor="middle">front</text>`
            + marks + "</svg>";
    }

    function renderFixes() {
        if (!el.fixes) return;
        if (error || !story) { el.fixes.innerHTML = empty(error || "Open a printer's Machine: these windows are of its bed."); shims(null); return; }
        const m = story.mount;
        const mark = (kept) => (kept ? "" : ` <span class="bed-default" title="the part's default, not this printer's: measure it, set it in Parameters, then Keep">default</span>`);
        const mountLine = m
            ? `<p class="bed-mount" data-hole="${esc(m.hole_d)}" data-outer="${esc(m.outer_d)}" data-kept="${m.hole_kept && m.outer_kept}">Each shim fits a screw hole <b>${esc(m.hole_d)}</b> mm${m.hole_kept && m.screw ? ` (${esc(m.screw)})` : ""}${mark(m.hole_kept)} and a ring <b>${esc(m.outer_d)}</b> mm across${mark(m.outer_kept)}.`
                + ` <button type="button" id="bed-keep" title="Keep the screw hole and the ring Parameters holds for bed_shims as this printer's, measured: kept in the state folder, used by every slice of the shims after">⇩ Keep from Parameters</button></p>`
            : "";
        const s = story.shims;
        if (!s || s.error) { el.fixes.innerHTML = empty(s ? s.error : "No reading to level the bed by.") + mountLine; shims(null); return; }
        const reads = s.runs.map((r) => r.id).join(" and ");
        const lines = s.shims.map((sh) => {
            const what = sh.printed != null
                ? `shim <b>${esc(sh.printed.toFixed(1))}</b> mm (needs ${esc(mm(sh.thickness))})`
                : sh.none === "the highest" ? "none: the highest" : `skipped: ${esc(sh.none)} (needs ${esc(mm(sh.thickness))})`;
            return `<li data-screw="${esc(sh.label)}"><b>${esc(sh.label)}</b> ${esc(sh.name.replace("_", " "))}: plane ${esc((sh.plane >= 0 ? "+" : "") + mm(sh.plane))} mm, ${what}</li>`;
        }).join("");
        const cold = s.runs.some((r) => r.heated === false);
        const floor = s.floor == null ? "not known from one reading" : `${mm(s.floor)} mm`;
        el.fixes.innerHTML = `<p class="bed-head">From ${esc(reads)}${cold ? ` <span class="bed-warm cold">cold</span>: the bed is levelled at the temperature it prints at` : ""}. The highest corner gets none; each other what lifts it to the highest, rounded to a 0.1 mm layer; under one layer, or under the floor (${esc(floor)}), none.</p>`
            + bedSvg(s)
            + `<ul class="bed-shims">${lines}</ul>`
            + `<p class="bed-left">Left by rounding and the corners skipped: up to ${esc(mm(s.left))} mm between corners. Left by the plane: the bow, ${esc(mm(s.residual.range))} mm.</p>`
            + mountLine
            + (s.params ? `<p class="bed-stood">These stand on bed_shims, the piece on ${esc(story.printer)}'s bed: its Parameters show them, and a Slice or ⚒ Make of it makes them.</p>` : "")
            + (s.params
                ? `<p><button type="button" id="bed-make" title="bed_shims at these thicknesses, rendered and sliced for this printer in its Print window: nothing is printed, ▶ Print is a person's">⚒ Make these</button> <code>${esc(s.slice)}</code></p>`
                : `<p class="bed-empty">No corner needs a shim: the bed is as level as shims make it.</p>`);
        shims(s.shims, m);
        // The shims the readings call for stood on bed_shims, once per set: drawn on the
        // piece, in its Parameters, and what a Slice or ⚒ Make of it makes.
        const asked = s.params ? JSON.stringify(s.params) : null;
        if (asked && asked !== stood && stand) {
            stood = asked;
            stand(s.params).catch((e) => { stood = null; say(`Fixes: the shims were not stood on bed_shims: ${e.message}`, "error"); });
        }
    }

    function renderHistory() {
        if (!el.history) return;
        if (error || !story) { el.history.innerHTML = empty(error || "Open a printer's Machine: these windows are of its bed."); return; }
        const runs = [...(story.runs || [])].filter((r) => typeof r.range === "number").reverse();
        if (!runs.length) { el.history.innerHTML = empty("No reading yet."); return; }
        const W = 320, H = 160, L = 36, R = 8, T = 10, B = 24;
        const bound = story.bound;
        const top = Math.max(bound ?? 0, ...runs.map((r) => r.range)) * 1.1 || 1;
        const sx = (i) => L + (runs.length > 1 ? (i * (W - L - R)) / (runs.length - 1) : (W - L - R) / 2);
        const sy = (v) => H - B - (v / top) * (H - T - B);
        const ticks = [0, top / 2, top].map((v) => `<g class="tick"><line x1="${L}" x2="${W - R}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}"/><text x="${L - 4}" y="${sy(v).toFixed(1)}" dy="0.32em" text-anchor="end">${v.toFixed(2)}</text></g>`).join("");
        const rule = bound != null
            ? `<g class="bed-bound" data-bound="${esc(bound)}"><line x1="${L}" x2="${W - R}" y1="${sy(bound).toFixed(1)}" y2="${sy(bound).toFixed(1)}"/><text x="${W - R}" y="${sy(bound).toFixed(1)}" dy="-0.3em" text-anchor="end">bound ${esc(bound)} mm, a stored mesh</text></g>`
            : "";
        const points = runs.map((r, i) => {
            const warm = r.heated === true ? "heated" : "cold";
            return `<g class="bed-point ${warm} ${esc(r.method)}" data-id="${esc(r.id)}" data-range="${esc(r.range)}"><title>${esc(`${r.id}: ${mm(r.range)} mm, ${warm}, ${r.method}`)}</title><circle cx="${sx(i).toFixed(1)}" cy="${sy(r.range).toFixed(1)}" r="4"/></g>`;
        }).join("");
        el.history.innerHTML = `<p class="bed-head">Each reading's range, oldest on the left: <span class="bed-warm heated">heated</span> filled, <span class="bed-warm cold">cold</span> hollow, a read of the stored mesh ringed.</p>`
            + `<svg class="bed-history" viewBox="0 0 ${W} ${H}" role="img" aria-label="Each reading's range over the readings" xmlns="http://www.w3.org/2000/svg">${ticks}${rule}${points}<text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle">readings, oldest first</text></svg>`;
    }

    function render() { renderRuns(); renderDifferences(); renderFixes(); renderHistory(); }

    function choose(id) {
        const run = story && (story.runs || []).find((r) => r.id === id);
        if (!run) return false;
        chosen = id;
        draw({ ...run, machine: run.machine || "printer" }, story.runs[0].id);
        renderRuns();
        return true;
    }

    async function keep() {
        const at = printer();
        if (!at) throw new Error("open a printer's Machine: a mount is kept for it");
        const given = measured();
        if (!given) throw new Error("nothing in Parameters: choose bed_shims, its screw chosen and the mount's outer diameter typed, then Keep");
        const body = { outer_d: given.outer_d, ...(given.screw ? { screw: given.screw } : {}), ...(given.hole_d ? { hole_d: given.hole_d } : {}) };
        const r = await fetch(`${base}/bed/${encodeURIComponent(at.site)}/${encodeURIComponent(at.path)}/mount`, {
            method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        const answer = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof answer.detail === "string" ? answer.detail : `the server answered ${r.status}`);
        await load();
        return `${at.path}'s shims fit a ${answer.said}`;
    }

    // Probe hot: the temperature and the hold typed, the open Machine's bed probed hot.
    async function hot() {
        const heat = Number(hotC && hotC.value), soak = Number(soakS && soakS.value);
        if (!(heat > 0 && heat <= 130)) throw new Error("type the bed's temperature in °C, at most 130: the Print window's filament's is filled in when it is known");
        if (!(soak >= 0 && soak <= 3600)) throw new Error("type how long the bed is held, 0 to 3600 s");
        if (!probeHot) throw new Error("open a printer's Machine: its bed is probed there");
        const done = await probeHot(heat, soak);
        if (done.refused) throw new Error(done.refused);
        return done.said;
    }

    async function act(verb) {
        if (verb === "keep") return keep();
        if (verb === "probe-hot") return hot();
        if (verb !== "make") throw new Error(`no such act: ${verb}`);
        const s = story && story.shims;
        if (!s || s.error || !s.params) throw new Error(s && s.error ? s.error : "no shim to make: Fixes has none");
        return make(s.params);
    }

    async function onRunsClick(ev) {
        if (ev.target.closest("#bed-probe-hot")) {
            try { say(`Probe hot: ${await hot()}`, "success"); } catch (e) { say(`Probe hot: ${e.message}`, "error"); }
            return;
        }
        const run = ev.target.closest(".bed-run");
        if (run) choose(run.dataset.id);
    }
    function onRunsKey(ev) {
        const run = ev.key === "Enter" && ev.target.closest(".bed-run");
        if (run) choose(run.dataset.id);
    }
    async function onFixesClick(ev) {
        const button = ev.target.closest("#bed-make, #bed-keep");
        if (!button) return;
        const [verb, word] = button.id === "bed-keep" ? ["keep", "Keep"] : ["make", "Make these"];
        button.disabled = true;
        try { say(`${word}: ${await act(verb)}`, "success"); } catch (e) { say(`${word}: ${e.message}`, "error"); }
        button.disabled = false;
    }
    el.runs.addEventListener("click", onRunsClick);
    el.runs.addEventListener("keydown", onRunsKey);
    el.fixes.addEventListener("click", onFixesClick);
    // A reading kept by the Machine (Probe bed, Probe hot): the runs asked for again.
    const onLeveled = () => { if (printer()) load(); };
    window.addEventListener("apothecary:leveled", onLeveled);

    async function load() {
        const at = printer();
        if (!at) { story = null; error = null; render(); return null; }
        if (loading) return loading;
        loading = (async () => {
            try {
                const r = await fetch(`${base}/bed/${encodeURIComponent(at.site)}/${encodeURIComponent(at.path)}`);
                const body = await r.json().catch(() => ({}));
                if (!r.ok) { story = null; error = body.detail || `the server answered ${r.status}`; }
                else { story = body; error = null; if (!chosen || !(story.runs || []).some((x) => x.id === chosen)) chosen = story.runs?.[0]?.id ?? null; }
            } catch (e) { story = null; error = e.message; }
            render();
            return story;
        })();
        try { return await loading; } finally { loading = null; }
    }

    render();
    return { load, choose, act, story: () => story };
}
