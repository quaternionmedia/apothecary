/* The loop's verbs: a camera's device chosen, live, a picture taken; a picture
 * added, dropped or pasted and pinned at a place as a view; its shapes found;
 * the view sized, drawn or unpinned; a kept picture forgotten. No markup of its
 * own: the ring is how each is asked for (apothecary/menu.py builds the cells),
 * the world is where each is seen (picture_marks.js draws it), and the status
 * bar is where each is said -- every step's message naming the step after it: a
 * camera's device chosen names Take picture, a picture taken or pinned names Find
 * shapes, shapes found name Make.
 *
 * Taking and finding are two steps. Take picture, a drop, a paste, Picture ›
 * Add and Picture › Folder pin a view and find nothing; Picture › Find shapes
 * runs a finder on the view drawn at a place.
 *
 * A place is a host, a root structure with a footprint, or the floor (""). A
 * verb on a place names it by the ring's target; a floor verb carries "@floor"
 * after its last colon. A verb about one view names the view. A camera is a part
 * of the site (camera_1, ...): its verbs are its own ring's, naming it by the
 * ring's target, and Camera › Add here and Remove are the server's.
 *
 * A camera's device is one of this browser's cameras, by the id the browser gave
 * it: a camera whose device another browser chose shows its label and is never
 * opened here. The stream exists only while the camera is Live; it stops at
 * Still, when a picture is taken (the picture is then what is shown), when the
 * camera goes, or when the site changes. Take picture with no stream open opens
 * the device, waits for its first frame and half a second more, keeps the frame,
 * and closes it again. The picture lies where the camera looks.
 *
 * The first time, the browser has to be asked: a camera's Device offers Allow
 * until the browser's cameras are named. Allow asks once and flows on -- one
 * camera is chosen at once, several reopen the ring at Device to choose from --
 * and a refusal says what to do. A yes given elsewhere (the address bar) is
 * noticed where the browser reports it, and the cameras are named again as a
 * ring opens, so Device lists them.
 *
 * The picture chosen in Pictures (choose(path)) is told to every ring as
 * chosen_picture: Picture › Folder's eighth cell pins it when it is older than
 * the seven newest the cell's ring holds, and marks its own cell when it is
 * among them.
 *
 * mountPictures({ base, marks, world, log }):
 *   marks: the handle mountPictureMarks returned;
 *   world: siteName(), select(path), stepOut(), focusWidth(), openPanel(id),
 *          frameFloor(), rendered(), reopenRing(path, into, at),
 *          applySite(site) (the site as an answer carries it, drawn again);
 *   log(text, kind): the page's status bar; kind "bad" is a refusal.
 */

export const FLOOR = "";
const FLOOR_MARK = "@floor";
const FRAME_SETTLE_MS = 500;     // after the first frame, before a still is kept
const PICTURES_FRESH_MS = 1500; // a pictures list this young is not asked for again
const FILE_MOST = 16 * 1024 * 1024;

export function mountPictures({ base = "", marks, world, log }) {
    const say = (text, kind = "") => { if (log) log(text, kind); };
    const state = { cameras: [], asked: false, live: null, pictures: [], picturesAt: 0, chosen: null };
    let picturesInflight = null;

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const where = (host) => (host === FLOOR ? "the floor" : host);
    // A verb's place on the ring, as a person reads it: the floor's are under the
    // canvas ring's Pictures › Floor.
    const ringPath = (host, verb) => `${host === FLOOR ? "Pictures › Floor › " : ""}${verb}`;
    const siteUrl = () => `/sites/${encodeURIComponent(world.siteName())}`;
    const cameraUrl = (name) => `${siteUrl()}/cameras/${encodeURIComponent(name)}`;

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
    // The camera allowed (or refused) for this site in the address bar: the
    // browser says so here, where it can, and the cameras are named again.
    if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: "camera" })
            .then((status) => status.addEventListener("change", () => listCameras().catch(() => {})))
            .catch(() => {});
    }
    const ready = listCameras().catch(() => {});
    const mine = (id) => state.cameras.find((c) => c.id === id) || null;

    // A camera part as the world has it, or a refusal naming what to do.
    function cameraNamed(name) {
        const cam = marks.camera(name);
        if (!cam) throw new Error(`no camera ${name} in this site`);
        return cam;
    }
    // A camera whose device is this browser's: the device, or a refusal that says why not.
    function deviceOf(name) {
        const cam = cameraNamed(name);
        if (!cam.device) throw new Error(`${name} has no device yet: Device, on its ring, says which of this browser's cameras it is`);
        if (!mine(cam.device.id)) throw new Error(`${name}'s device is another browser's (${cam.device.label}): choose one of this browser's under its Device`);
        return cam.device;
    }

    // Allow: the browser is asked once. It answers with its prompt, or with what
    // the address bar holds for this site. Its yes flows on: one camera is chosen
    // as this camera's device at once; several reopen the ring at Device, where
    // the ring stood, so the choice is made without another trip.
    async function allow(name, at = null) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error("this browser has no cameras to offer");
        let probe;
        try {
            probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } catch (e) {
            const said = e && e.message ? ` (${e.message})` : "";
            if (e && e.name === "NotAllowedError") {
                throw new Error(`the browser refused the camera${said}: answer its prompt, or allow the camera for this site in the address bar, then ${name}'s Device again`);
            }
            throw new Error(`this browser offered no camera it could use${said || (e && e.name ? ` (${e.name})` : "")}`);
        }
        for (const t of probe.getTracks()) t.stop();
        await listCameras();
        const n = state.cameras.length;
        if (!n) throw new Error("the browser allowed a camera and then named none: this browser offered no camera it could use");
        if (n === 1) { await chooseDevice(name, state.cameras[0].id, { allowed: true }); return; }
        say(`${n} cameras allowed: choose which is ${name}`);
        if (world.reopenRing) world.reopenRing(name, "camera:device", at);
    }

    // Device › one of this browser's cameras: this camera is that one, and no
    // other camera is (the server takes it off any other).
    async function chooseDevice(name, id, { allowed = false } = {}) {
        const device = mine(id);
        const answer = await api(`${cameraUrl(name)}/device`, {
            method: "PUT",
            body: JSON.stringify({ id, label: device ? device.label : "camera" }),
        });
        if (state.live && state.live.camera !== name && state.live.id === id) still();
        await marks.refresh();
        const from = (answer.taken_from || []).map((c) => (c.site === world.siteName() ? c.name : `${c.site}'s ${c.name}`));
        const taken = from.length ? `, taken off ${from.join(", ")}` : "";
        say(`${name} is ${device ? device.label : "that camera"}${allowed ? ", allowed" : ""}${taken}: Take picture (P) keeps a frame where it looks`);
    }

    // --- streams: live where the camera looks, or opened for one frame -------------------
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

    async function goLive(name) {
        const device = deviceOf(name);
        still();
        const stream = await open(device.id);
        const { video, loaded } = videoFor(stream);
        state.live = { camera: name, id: device.id, stream, video };
        await loaded;
        if (!state.live || state.live.video !== video) return;
        marks.setLive(name, video);
        if (world.rendered) world.rendered();
        say(`${name} is live where it looks: Take picture (P) keeps a frame`);
    }
    function still() {
        if (!state.live) return false;
        const { stream, video, camera } = state.live;
        state.live = null;
        close(stream, video);
        if (marks.liveAt() === camera) marks.setLive(null, null);
        if (world.rendered) world.rendered();
        return true;
    }

    function grab(video) {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        if (!canvas.width || !canvas.height) return Promise.reject(new Error("the camera gave no frame"));
        canvas.getContext("2d").drawImage(video, 0, 0);
        return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("no frame"))), "image/png"));
    }
    async function frame(device) {
        if (state.live && state.live.id === device.id) return grab(state.live.video);
        const stream = await open(device.id);
        const { video, loaded } = videoFor(stream);
        try {
            await loaded;
            await new Promise((resolve) => setTimeout(resolve, FRAME_SETTLE_MS));
            return await grab(video);
        } finally { close(stream, video); }
    }

    async function keepBlob(blob, { name, kept = "capture", host = null, camera = null }) {
        const q = new URLSearchParams({ name, kept });
        if (host !== null || camera !== null) q.set("site", world.siteName());
        if (host !== null) q.set("host", host);
        if (camera) q.set("camera", camera);
        const r = await fetch(`${base}/photos/pictures?${q}`, { method: "POST", body: blob, headers: { "Content-Type": blob.type || "application/octet-stream" } });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        state.picturesAt = 0;
        return body;
    }

    // What a view pinned is, and the step after it: Find shapes.
    function pinned(view) {
        if (view.host === null) return `${view.picture}: ${view.camera} was looking at a wall or the sky, so it lies nowhere and is drawn on the camera; aim the camera down and Take picture again`;
        const by = view.camera ? `${view.camera}'s picture lies on ${where(view.host)}` : `${view.picture} pinned at ${where(view.host)} as a view`;
        return `${by}: ${ringPath(view.host, "Picture › Find shapes")} finds what is in it`;
    }
    // What Find shapes found, and the step after it: Make, once the view has a width.
    function found(view) {
        const n = view.shapes.length;
        const left = view.left_out ? ` (${view.left_out} left out)` : "";
        if (!n) return `no shapes found in ${view.picture} at ${where(view.host)} by ${view.finder}: take or pin another picture here`;
        const make = ringPath(view.host, "Picture › Make");
        const next = view.mat && view.mat.width
            ? `, ${Math.round(view.mat.width)} mm across: ${make} makes them pieces`
            : `: type the picture's width in Selected (${ringPath(view.host, "Picture › Size")}), then ${make} makes them pieces`;
        return `${n} shape${n === 1 ? "" : "s"} found at ${where(view.host)}${left}${next}`;
    }
    async function drawNew(host, view, select = true) {
        await marks.refresh();
        if (host !== null) marks.draw(host, view.id);
        if (select) world.select(host);
    }

    // Take picture: a frame from the camera's device, kept and laid where the
    // camera looks as its view; nothing found in it yet; Live ends.
    async function takePicture(name) {
        const device = deviceOf(name);
        const blob = await frame(device);
        still();
        const kept = await keepBlob(blob, { name, camera: name });
        if (!kept.view) throw new Error(`kept ${kept.path}, and not pinned: ${kept.not_pinned || "refused"}`);
        // The camera stays selected: its picture is drawn where it landed.
        await drawNew(kept.view.host, kept.view, false);
        if (world.rendered) world.rendered();
        say(pinned(kept.view));
        return kept.view;
    }
    // Find shapes: a finder reads the view drawn here. On a view another finder
    // searched already, its shapes are a new view, drawn in its place.
    async function findShapes(host, finder) {
        const drawn = drawnHere(host);
        const body = finder ? { finder } : {};
        const view = await api(`${siteUrl()}/views/${encodeURIComponent(drawn.id)}/find`, { method: "POST", body: JSON.stringify(body) });
        await drawNew(host, view);
        say(found(view));
        return view;
    }

    // --- pictures from this machine --------------------------------------------------------
    // Several at once: each kept under uploads/ and pinned as its own view, one
    // after another; the last is drawn, and every refusal is named.
    async function addFiles(files, host) {
        const chosen = [...(files || [])];
        if (!chosen.length) return [];
        world.stepOut();
        const views = [], refused = [];
        for (const file of chosen) {
            if (file.size > FILE_MOST) { refused.push(`${file.name}: larger than 16 MB`); continue; }
            try {
                const kept = await keepBlob(file, { name: file.name, kept: "upload", host });
                if (kept.view) views.push(kept.view); else refused.push(`${file.name}: kept, not pinned: ${kept.not_pinned}`);
            } catch (e) { refused.push(`${file.name}: ${e.message}`); }
        }
        if (views.length) await drawNew(host, views[views.length - 1]);
        const next = views.length ? ` as views: ${ringPath(host, "Picture › Find shapes")} finds what is in the one drawn` : "";
        say(`${views.length} picture(s) pinned at ${where(host)}${next}` + (refused.length ? ` -- refused: ${refused.join("; ")}` : ""), refused.length && !views.length ? "bad" : "");
        return views;
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
    // Picture › Folder: a picture already under the root, pinned here as a view.
    async function pinPicture(host, picture) {
        const view = await api(`${siteUrl()}/views`, { method: "POST", body: JSON.stringify({ host, picture }) });
        await drawNew(host, view);
        say(pinned(view));
        return view;
    }

    // --- the drawn view --------------------------------------------------------------------
    function drawnHere(host) {
        const drawn = marks.drawnAt(host);
        if (!drawn) throw new Error(`no view is pinned at ${where(host)}`);
        return drawn;
    }
    function drawView(host, id) {
        if (!marks.draw(host, id)) { say(`no view ${id} at ${where(host)}`, "bad"); return false; }
        const drawn = marks.drawnAt(host);
        world.rendered();
        say(`drawing ${drawn.picture} at ${where(host)}`);
        return true;
    }
    async function unpinView(host) {
        const drawn = drawnHere(host);
        await api(`${siteUrl()}/views/${encodeURIComponent(drawn.id)}`, { method: "DELETE" });
        await marks.refresh();
        say(`unpinned ${drawn.picture} from ${where(host)}; the picture stays in the folder, and any pieces made from it stay`);
    }
    async function forget(host) {
        const drawn = drawnHere(host);
        await api(`/photos/pictures/${drawn.picture.split("/").map(encodeURIComponent).join("/")}`, { method: "DELETE" });
        state.picturesAt = 0;
        await marks.refresh();
        say(`forgot ${drawn.picture}: its views are unpinned, every site's; pieces made from it stay`);
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

    // The one width: a view's scale. With a shape chosen on the drawn view, the
    // number is that shape's long side; otherwise the picture's width. On a
    // camera's picture, the first width typed teaches the camera its lens, and its
    // other pictures nobody sized follow it.
    async function setWidth(host, mm) {
        if (!(mm > 0)) throw new Error("a width is a number of millimetres, more than nothing");
        const drawn = marks.drawnAt(host);
        if (!drawn) throw new Error(`nothing at ${where(host)} to size`);
        const chosen = marks.chosen();
        const byShape = chosen && chosen.view === drawn.id;
        const body = byShape ? { known_index: chosen.index, mm } : { mm_across: mm };
        const sized = await api(`${siteUrl()}/views/${encodeURIComponent(drawn.id)}/scale`, { method: "PUT", body: JSON.stringify(body) });
        // Pieces made from the view (or, a lens taught, from its camera's other
        // pictures) whose sides nobody stated were rebuilt: the site is drawn as it
        // is now (which fetches the marks too).
        const rebuilt = sized.rebuilt || [];
        if (rebuilt.length && sized.site && world.applySite) await world.applySite(sized.site);
        else await marks.refresh();
        if (byShape) marks.choose(drawn.id, chosen.index);
        const followed = rebuilt.length ? `; ${rebuilt.length} made piece(s) rebuilt at that width: ${rebuilt.join(", ")}` : "";
        const taught = sized.taught ? `; ${sized.taught} learned its lens from it, and its other pictures nobody sized follow` : "";
        const next = sized.finder === null
            ? `${ringPath(host, "Picture › Find shapes")} finds its shapes, then Make makes them pieces`
            : sized.shapes.length ? `${ringPath(host, "Picture › Make")} makes its shapes pieces` : "it holds no shapes to make";
        say(`${drawn.picture}: ${Math.round(sized.mm_across)} mm across${byShape ? `, from shape ${chosen.index}'s long side` : ""}${taught}${followed}; ${next}`);
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
    // The Picture context for what a ring stands on: a place (a host, or "" the
    // floor) or a camera. A camera's device is the server's to tell its ring.
    async function context(target, { fresh = false } = {}) {
        const [pictures] = await Promise.all([picturesNow(fresh), ready]);
        // Not yet named as a ring opens: the browser may have been allowed since
        // (the address bar, or a yes it did not report), so ask it again.
        if (fresh && !state.asked) await listCameras().catch(() => {});
        const keptPaths = new Set(pictures.filter((p) => p.kept).map((p) => p.path));
        const views = target === null ? [] : [...marks.viewsAt(target)].reverse();
        const drawn = target === null ? null : marks.drawnAt(target);
        return {
            cameras: state.cameras.map((c) => ({ id: c.id, label: c.label })),
            asked: state.asked,
            pictures: pictures.map((p) => p.path),
            chosen_picture: state.chosen,
            here: {
                live: !!(state.live && state.live.camera === target),
                views: views.map((l) => ({
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
    // What a verb is about: "@floor" after its last colon, else the ring's node (a
    // host or a camera).
    function targetOf(intent) {
        if (intent.action.endsWith(`:${FLOOR_MARK}`)) return FLOOR;
        const target = intent.context && intent.context.targets && intent.context.targets[0];
        return intent.context && intent.context.pointing === "node" && target ? target : FLOOR;
    }
    const bare = (action) => action.replace(new RegExp(`:${FLOOR_MARK}$`), "");

    // A camera or picture verb the page carries; false for one it does not (the
    // server's: Add here and Remove, Make, Drop, a made piece's Word).
    async function carry(intent) {
        const action = bare(intent.action);
        const target = targetOf(intent);
        if (!action.startsWith("camera:") && !action.startsWith("picture:") && action !== "fit") return false;
        // A floor verb selects the floor, so Selected shows what it acts on.
        if (intent.action.endsWith(`:${FLOOR_MARK}`)) world.select(target);
        const [, verb, ...rest] = action.split(":");
        const arg = rest.join(":");
        if (action === "fit") { world.frameFloor(); say("the floor, framed"); return true; }
        switch (`${action.split(":")[0]}:${verb}`) {
            case "camera:allow": await allow(target, intent.at || null); return true;
            case "camera:device": await chooseDevice(target, arg); return true;
            case "camera:live": await goLive(target); return true;
            case "camera:still": if (still()) say(`${target}: still again`); return true;
            case "camera:take-picture": await takePicture(target); return true;
            case "picture:add": pickFiles(target); say(`choose pictures to pin at ${where(target)}`); return true;
            case "picture:pin": world.stepOut(); await pinPicture(target, arg); return true;
            case "picture:find": await findShapes(target, arg); return true;
            case "picture:draw": {
                const viewAt = marks.attached() && marks.attached().views.find((l) => l.id === arg);
                if (!viewAt) throw new Error(`no view ${arg} in this site`);
                world.select(viewAt.host);
                drawView(viewAt.host, arg);
                return true;
            }
            case "picture:size": world.focusWidth(); say("type a width in Selected, in millimetres"); return true;
            case "picture:unpin": await unpinView(target); return true;
            case "picture:forget": await forget(target); return true;
            case "picture:purge": await purge(); return true;
            // Folder's eighth leaf: every picture is a row of Pictures; one chosen there
            // is this cell the next time, Pin and its name.
            case "picture:more": world.openPanel("pictures"); say(`every picture is in Pictures: choose one there, and Folder's last cell pins it at ${where(target)} as a view`); return true;
            case "picture:views": world.openPanel("selected"); say("every view here is a row in Selected: click one to draw it"); return true;
            default: return false;
        }
    }

    // The picture chosen in Pictures, or none (null): told to every ring after.
    function choose(path) { state.chosen = path || null; return state.chosen; }

    // A camera removed: its stream, if it was live, ends with it.
    function cameraGone(name) { if (state.live && state.live.camera === name) still(); }

    return {
        ready, state, listCameras, allow, chooseDevice, goLive, still, takePicture,
        findShapes, addFiles, pickFiles, paste, pinPicture, drawView, unpinView, forget, purge, setWidth,
        context, carry, cameraGone, picturesNow, choose,
        chosen: () => state.chosen,
        live: () => (state.live ? state.live.camera : null),
        liveVideo: (name) => (state.live && state.live.camera === name ? state.live.stream : null),
        isMine: (id) => !!mine(id),
        destroy() { still(); },
    };
}
