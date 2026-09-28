/* The loop's verbs at a host: a camera pinned, live, looked with; a picture
 * added, dropped or pasted, pinned, found, sized; a look drawn or unpinned; a
 * kept picture forgotten. No markup of its own: the ring is how each is asked
 * for (apothecary/menu.py builds the cells), the world is where each is seen
 * (picture_marks.js draws it), and the status bar is where each is said.
 *
 * A host is a root structure with a footprint, or the floor (""). A verb on a
 * host names it by the ring's target; a floor verb carries "@floor" after its
 * last colon. A verb about one look names the look.
 *
 * The browser's cameras are this origin's devices: a pin in cameras.json
 * names one by its deviceId, so a pin made in another browser is shown by its
 * label and can be moved or unpinned here, never opened. The stream exists
 * only while Live is on at its host; it stops when a Look is taken, when the
 * host is no longer selected, or when the site changes. A Look from Still
 * opens the pinned device, waits for its first frame and half a second more,
 * keeps the frame, and closes it again.
 *
 * mountPictures({ base, marks, world, log }):
 *   marks: the handle mountPictureMarks returned;
 *   world: siteName(), select(host), stepOut(), focusWidth(), openPanel(id),
 *          frameFloor(), rendered(), applySite(site) (the site as an answer
 *          carries it, drawn again: a re-scale may have rebuilt made pieces);
 *   log(text, kind): the page's status bar; kind "bad" is a refusal.
 */

export const FLOOR = "";
const FLOOR_MARK = "@floor";
const LOOK_SETTLE_MS = 500;     // after the first frame, before a still is kept
const PICTURES_FRESH_MS = 1500; // a pictures list this young is not asked for again
const FILE_MOST = 16 * 1024 * 1024;

export function mountPictures({ base = "", marks, world, log }) {
    const say = (text, kind = "") => { if (log) log(text, kind); };
    const state = { cameras: [], asked: false, live: null, pictures: [], picturesAt: 0 };
    let picturesInflight = null;

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const where = (host) => (host === FLOOR ? "the floor" : host);
    const siteUrl = () => `/sites/${encodeURIComponent(world.siteName())}`;

    // --- this browser's cameras ---------------------------------------------------------
    async function listCameras() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) { state.cameras = []; return []; }
        const all = await navigator.mediaDevices.enumerateDevices();
        const video = all.filter((d) => d.kind === "videoinput");
        // Until the browser is allowed, a camera has no name and (often) no id.
        state.asked = video.some((d) => d.label);
        state.cameras = video.filter((d) => d.deviceId).map((d, i) => ({ id: d.deviceId, label: d.label || `camera ${i + 1}` }));
        return state.cameras;
    }
    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
        navigator.mediaDevices.addEventListener("devicechange", () => listCameras().catch(() => {}));
    }
    const ready = listCameras().catch(() => {});
    const mine = (id) => state.cameras.find((c) => c.id === id) || null;

    async function allow() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("this browser has no cameras to offer");
        const probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        for (const t of probe.getTracks()) t.stop();
        await listCameras();
        say(`${state.cameras.length} camera(s) allowed: Camera › Pin here names them`);
    }

    async function pinCamera(host, id) {
        const cam = mine(id);
        const answer = await api(`/cameras/${encodeURIComponent(id)}`, {
            method: "PUT",
            body: JSON.stringify({ label: cam ? cam.label : "camera", site: world.siteName(), path: host }),
        });
        await marks.refresh();
        const replaced = answer.replaced && answer.replaced.length ? `, in place of ${answer.replaced.length} pinned there before` : "";
        say(`${cam ? cam.label : "camera"} pinned at ${where(host)}${replaced}`);
    }

    async function unpinCamera(host) {
        const cam = marks.cameraAt(host);
        if (!cam) throw new Error(`no camera is pinned at ${where(host)}`);
        if (state.live && state.live.host === host) still();
        await api(`/cameras/${encodeURIComponent(cam.id)}`, { method: "DELETE" });
        await marks.refresh();
        say(`${cam.label || "camera"} unpinned from ${where(host)}; its looks stay`);
    }

    function pinnedHere(host) {
        const cam = marks.cameraAt(host);
        if (!cam) throw new Error(`no camera is pinned at ${where(host)}: Camera › Pin here`);
        if (!mine(cam.id)) throw new Error(`${cam.label || "that camera"} is another browser's: pin one of this browser's here`);
        return cam;
    }

    // --- streams: live on the mat, or opened for one frame --------------------------------
    function videoFor(stream) {
        const video = document.createElement("video");
        video.muted = true; video.playsInline = true; video.autoplay = true;
        video.style.cssText = "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none";
        document.body.appendChild(video);
        const loaded = new Promise((resolve) => video.addEventListener("loadeddata", () => resolve(), { once: true }));
        video.srcObject = stream;
        video.play().catch(() => {});
        return { video, loaded };
    }
    async function open(id) {
        return navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: id } }, audio: false });
    }
    function close(stream, video) {
        for (const t of stream.getTracks()) t.stop();
        if (video) { video.srcObject = null; video.remove(); }
    }

    async function goLive(host) {
        const cam = pinnedHere(host);
        still();
        const stream = await open(cam.id);
        const { video, loaded } = videoFor(stream);
        state.live = { host, id: cam.id, stream, video };
        await loaded;
        if (!state.live || state.live.video !== video) return;
        marks.setLive(host, video);
        say(`${cam.label} is live on ${where(host)}: Look keeps a frame and finds what is in it`);
    }
    function still() {
        if (!state.live) return false;
        const { stream, video } = state.live;
        state.live = null;
        close(stream, video);
        marks.setLive(null, null);
        return true;
    }

    function grab(video) {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        if (!canvas.width || !canvas.height) return Promise.reject(new Error("the camera gave no frame"));
        canvas.getContext("2d").drawImage(video, 0, 0);
        return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("no frame"))), "image/png"));
    }
    async function frame(cam) {
        if (state.live && state.live.id === cam.id) return grab(state.live.video);
        const stream = await open(cam.id);
        const { video, loaded } = videoFor(stream);
        try {
            await loaded;
            await new Promise((resolve) => setTimeout(resolve, LOOK_SETTLE_MS));
            return await grab(video);
        } finally { close(stream, video); }
    }

    async function keepBlob(blob, { name, kept = "capture", host = null, camera = null }) {
        const q = new URLSearchParams({ name, kept });
        if (host !== null) { q.set("site", world.siteName()); q.set("host", host); }
        if (camera) q.set("camera", camera);
        const r = await fetch(`${base}/photos/pictures?${q}`, { method: "POST", body: blob, headers: { "Content-Type": blob.type || "application/octet-stream" } });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        state.picturesAt = 0;
        return body;
    }

    function found(look) {
        const n = look.shapes.length;
        const sized = look.mat && look.mat.width ? `, ${Math.round(look.mat.width)} mm across` : "; give its width in Selected";
        return `${n} shape${n === 1 ? "" : "s"} found at ${where(look.host)}${look.left_out ? ` (${look.left_out} left out)` : ""}${sized}`;
    }
    async function drawNew(host, look) {
        await marks.refresh();
        marks.draw(host, look.id);
        world.select(host);
    }

    // Look: a frame kept with its camera and host, found, pinned; Live ends.
    async function look(host) {
        const cam = pinnedHere(host);
        const blob = await frame(cam);
        still();
        const kept = await keepBlob(blob, { name: cam.id, host, camera: cam.id });
        if (!kept.look) throw new Error(`kept ${kept.path}, and not pinned: ${kept.not_pinned || "refused"}`);
        await drawNew(host, kept.look);
        say(found(kept.look));
        return kept.look;
    }
    // Keep: the frame is kept on this machine, and nothing more.
    async function keep(host) {
        const cam = pinnedHere(host);
        const kept = await keepBlob(await frame(cam), { name: cam.id });
        say(`kept ${kept.path} on this machine; Picture › Folder pins it at a place`);
        return kept;
    }

    // --- pictures from this machine --------------------------------------------------------
    // Several at once: each kept under uploads/ and pinned as its own look, found
    // one after another; the last is drawn, and every refusal is named.
    async function addFiles(files, host) {
        const chosen = [...(files || [])];
        if (!chosen.length) return [];
        world.stepOut();
        const pinned = [], refused = [];
        for (const file of chosen) {
            if (file.size > FILE_MOST) { refused.push(`${file.name}: larger than 16 MB`); continue; }
            try {
                const kept = await keepBlob(file, { name: file.name, kept: "upload", host });
                if (kept.look) pinned.push(kept.look); else refused.push(`${file.name}: kept, not pinned: ${kept.not_pinned}`);
            } catch (e) { refused.push(`${file.name}: ${e.message}`); }
        }
        if (pinned.length) await drawNew(host, pinned[pinned.length - 1]);
        const last = pinned.length ? `; ${found(pinned[pinned.length - 1])}` : "";
        say(`${pinned.length} picture(s) pinned at ${where(host)}${last}` + (refused.length ? ` -- refused: ${refused.join("; ")}` : ""), refused.length && !pinned.length ? "bad" : "");
        return pinned;
    }
    function pickFiles(host) {
        const input = document.createElement("input");
        input.type = "file"; input.multiple = true;
        input.accept = "image/png,image/jpeg,image/gif,image/webp,image/bmp,image/tiff";
        input.addEventListener("change", () => addFiles(input.files, host).catch((e) => say(e.message, "bad")));
        input.click();
    }
    async function paste(blob, host) {
        const at = new Date();
        const stamp = at.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "");
        const file = new File([blob], `${stamp}-paste.png`, { type: blob.type || "image/png" });
        return addFiles([file], host);
    }
    async function pinPicture(host, picture, finder = null) {
        const body = { host, picture };
        if (finder) body.finder = finder;
        const drawn = marks.drawnAt(host);
        if (finder && drawn && drawn.camera) body.camera = drawn.camera;
        const lookNow = await api(`${siteUrl()}/looks`, { method: "POST", body: JSON.stringify(body) });
        await drawNew(host, lookNow);
        say(found(lookNow));
        return lookNow;
    }

    // --- the drawn look --------------------------------------------------------------------
    function drawnHere(host) {
        const drawn = marks.drawnAt(host);
        if (!drawn) throw new Error(`no look is pinned at ${where(host)}`);
        return drawn;
    }
    function drawLook(host, id) {
        if (!marks.draw(host, id)) { say(`no look ${id} at ${where(host)}`, "bad"); return false; }
        const drawn = marks.drawnAt(host);
        world.rendered();
        say(`drawing ${drawn.picture} at ${where(host)}`);
        return true;
    }
    async function unpinLook(host) {
        const drawn = drawnHere(host);
        await api(`${siteUrl()}/looks/${encodeURIComponent(drawn.id)}`, { method: "DELETE" });
        await marks.refresh();
        say(`unpinned ${drawn.picture} from ${where(host)}; the picture and any pieces made stay`);
    }
    async function forget(host) {
        const drawn = drawnHere(host);
        await api(`/photos/pictures/${drawn.picture.split("/").map(encodeURIComponent).join("/")}`, { method: "DELETE" });
        state.picturesAt = 0;
        await marks.refresh();
        say(`forgot ${drawn.picture}: its looks are unpinned, every site's; pieces made from it stay`);
    }
    async function purge() {
        const pictures = await picturesNow(true);
        const kept = pictures.filter((p) => p.kept);
        if (!kept.length) throw new Error("nothing kept from the browser to forget");
        if (!confirm(`Forget every picture the browser put here? ${kept.length} kept picture(s) go; the folder's own (${pictures.length - kept.length}) stay.`)) return null;
        const gone = await api("/photos/pictures", { method: "DELETE" });
        state.picturesAt = 0;
        await marks.refresh();
        say(`forgot ${gone.forgotten.length} kept picture(s); ${gone.left} of the folder's own stay`);
        return gone;
    }

    // The one width: a look's scale. With a shape chosen on the drawn look, the
    // number is that shape's long side; otherwise the picture's width. At a host
    // with a camera and no look, it is the camera's width for its next look.
    async function setWidth(host, mm) {
        if (!(mm > 0)) throw new Error("a width is a number of millimetres, more than nothing");
        const drawn = marks.drawnAt(host);
        if (!drawn) {
            const cam = marks.cameraAt(host);
            if (!cam) throw new Error(`nothing at ${where(host)} to size`);
            await api(`/cameras/${encodeURIComponent(cam.id)}`, { method: "PUT", body: JSON.stringify({ label: cam.label || "camera", site: world.siteName(), path: host, mm_across: mm }) });
            await marks.refresh();
            say(`${cam.label || "camera"}: its next look is ${mm} mm across`);
            return;
        }
        const chosen = marks.chosen();
        const byShape = chosen && chosen.look === drawn.id;
        const body = byShape ? { known_index: chosen.index, mm } : { mm_across: mm };
        const sized = await api(`${siteUrl()}/looks/${encodeURIComponent(drawn.id)}/scale`, { method: "PUT", body: JSON.stringify(body) });
        // Pieces made from the look whose sides nobody stated were rebuilt at the
        // new width: the site is drawn as it is now (which fetches the marks too).
        const rebuilt = sized.rebuilt || [];
        if (rebuilt.length && sized.site && world.applySite) await world.applySite(sized.site);
        else await marks.refresh();
        if (byShape) marks.choose(drawn.id, chosen.index);
        const followed = rebuilt.length ? `; ${rebuilt.length} made piece(s) rebuilt at that width: ${rebuilt.join(", ")}` : "";
        say(`${drawn.picture}: ${Math.round(sized.mm_across)} mm across${byShape ? `, from shape ${chosen.index}'s long side` : ""}${followed}; Picture › Make makes its shapes`);
    }

    // --- what the ring is told -------------------------------------------------------------
    function picturesNow(fresh = false) {
        if (!fresh && Date.now() - state.picturesAt < PICTURES_FRESH_MS) return Promise.resolve(state.pictures);
        if (!picturesInflight) {
            picturesInflight = api("/photos/pictures")
                .then((list) => { state.pictures = list; state.picturesAt = Date.now(); return list; })
                .catch(() => state.pictures)
                .finally(() => { picturesInflight = null; });
        }
        return picturesInflight;
    }
    // The Picture context for the place a ring stands on: a host, or "" the floor.
    async function context(host, { fresh = false } = {}) {
        const [pictures] = await Promise.all([picturesNow(fresh), ready]);
        const keptPaths = new Set(pictures.filter((p) => p.kept).map((p) => p.path));
        const cam = host === null ? null : marks.cameraAt(host);
        const looks = host === null ? [] : [...marks.looksAt(host)].reverse();
        const drawn = host === null ? null : marks.drawnAt(host);
        return {
            cameras: state.cameras.map((c) => ({ id: c.id, label: c.label })),
            asked: state.asked,
            pictures: pictures.map((p) => p.path),
            here: {
                camera: cam ? { id: cam.id, label: cam.label || "camera" } : null,
                live: !!(state.live && state.live.host === host),
                looks: looks.map((l) => ({
                    id: l.id,
                    picture: l.picture,
                    finder: l.finder,
                    sized: !!(l.mat && l.mat.width),
                    kept: keptPaths.has(l.picture) || /^(captures|uploads)\//.test(l.picture),
                    shapes: l.shapes.map((s) => ({ index: s.index, word: s.word, status: s.status })),
                })),
                drawn: drawn ? drawn.id : null,
            },
        };
    }

    // --- the ring's verbs --------------------------------------------------------------------
    // The host a verb is about: "@floor" after its last colon, else the ring's node.
    function hostOf(intent) {
        if (intent.action.endsWith(`:${FLOOR_MARK}`)) return FLOOR;
        const target = intent.context && intent.context.targets && intent.context.targets[0];
        return intent.context && intent.context.pointing === "node" && target ? target : FLOOR;
    }
    const bare = (action) => action.replace(new RegExp(`:${FLOOR_MARK}$`), "");

    // A camera or picture verb the page carries; false for one it does not.
    async function carry(intent) {
        const action = bare(intent.action);
        const host = hostOf(intent);
        if (!action.startsWith("camera:") && !action.startsWith("picture:") && action !== "fit") return false;
        // A floor verb selects the floor, so Selected shows what it acts on.
        if (intent.action.endsWith(`:${FLOOR_MARK}`)) world.select(host);
        const [, verb, ...rest] = action.split(":");
        const arg = rest.join(":");
        if (action === "fit") { world.frameFloor(); say("the floor, framed"); return true; }
        switch (`${action.split(":")[0]}:${verb}`) {
            case "camera:allow": await allow(); return true;
            case "camera:pin": await pinCamera(host, arg); return true;
            case "camera:unpin": await unpinCamera(host); return true;
            case "camera:live": await goLive(host); return true;
            case "camera:still": if (still()) say(`${where(host)}: still again`); return true;
            case "camera:look": await look(host); return true;
            case "camera:keep": await keep(host); return true;
            case "camera:gather": return false;  // the camera panel's report, until gathering leaves core
            case "picture:add": pickFiles(host); say(`choose pictures to pin at ${where(host)}`); return true;
            case "picture:pin": world.stepOut(); await pinPicture(host, arg); return true;
            case "picture:find": await pinPicture(host, drawnHere(host).picture, arg); return true;
            case "picture:draw": {
                const lookAt = marks.attached() && marks.attached().looks.find((l) => l.id === arg);
                if (!lookAt) throw new Error(`no look ${arg} in this site`);
                world.select(lookAt.host);
                drawLook(lookAt.host, arg);
                return true;
            }
            case "picture:size": world.focusWidth(); say("type a width in Selected, in millimetres"); return true;
            case "picture:unpin": await unpinLook(host); return true;
            case "picture:forget": await forget(host); return true;
            case "picture:purge": await purge(); return true;
            case "picture:kept": world.openPanel("kept"); say("the other kept pictures are in Kept"); return true;
            case "picture:looks": world.openPanel("selected"); say("every look here is a row in Selected: click one to draw it"); return true;
            default: return false;
        }
    }

    // A selection elsewhere, a site change, a step out of the level: Live ends.
    function selectionChanged(host) {
        if (state.live && state.live.host !== host) still();
    }

    return {
        ready, state, listCameras, allow, pinCamera, unpinCamera, goLive, still, look, keep,
        addFiles, pickFiles, paste, pinPicture, drawLook, unpinLook, forget, purge, setWidth,
        context, carry, selectionChanged, picturesNow,
        live: () => (state.live ? state.live.host : null),
        destroy() { still(); },
    };
}
