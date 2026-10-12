"""When the viewer has drawn what it was asked to show, for a check or a screenshot."""

from contextlib import contextmanager

from playwright.sync_api import Page

FRAMES = """(n) => new Promise((done) => {
    const step = () => (n-- > 0 ? requestAnimationFrame(step) : done());
    step();
})"""

# What the page animates and then stops animating -- the hint bar's 0.6 s fade, a
# badge's fade in or out, a fold turning -- finished: a picture taken half way through
# one differs from run to run. One that never ends (a spinner) is not waited for.
STILL = """() => Promise.all(
    document.getAnimations()
        .filter((a) => a.effect && a.effect.getComputedTiming().endTime !== Infinity)
        .map((a) => a.finished.catch(() => null))
)"""

# The view at rest: the orbit controls ease a turn or a zoom out over many frames
# after the hand has stopped, so the camera is watched until two frames in a row
# leave it where it was (or a few seconds of frames have passed).
CAMERA_AT_REST = """() => new Promise((done) => {
    const v = window.fractalViewer;
    if (!v || !v.camera) return done();
    let last = null, still = 0, frames = 0;
    const look = () => {
        const now = [...v.camera.matrixWorld.elements, ...v.orbitControls.target.toArray()].join(',');
        still = now === last ? still + 1 : 0;
        last = now;
        if (still >= 2 || ++frames > 300) return done();
        requestAnimationFrame(look);
    };
    look();
})"""

# anchors.js tests whether a badge is behind something every 6 frames.
OCCLUSION_TESTED = 7


def settled(page: Page, frames: int = 2) -> None:
    """Wait until the level on screen has its geometry, the camera is at rest, nothing is
    part way through an animation, and `frames` frames have drawn it. On a page that is
    not the viewer (a picture, a JSON answer) only the frames are waited for."""
    page.evaluate("() => window.fractalViewer ? window.fractalViewer.waveDone : null")
    page.evaluate(CAMERA_AT_REST)
    # The badges' occlusion tested where the camera came to rest, and what that faded.
    page.evaluate(FRAMES, OCCLUSION_TESTED)
    page.evaluate(STILL)
    page.evaluate(FRAMES, frames)


# Where a piece's middle is, on the page and from the camera, beside the middle of the
# world, how far the orbit's target is, and which way round each lies from the target
# (radians about the vertical, as the orbit measures its own turn): its bounds' centre
# (Z up) through the camera (three.js's Y up).
SIGHTED = """(key) => {
    const v = window.fractalViewer;
    const node = v.renderNodeByKey[key] || v.nodeByPath(key);
    const b = node && node.world_bounds;
    if (!b) return null;
    const centre = v.camera.position.clone().set(
        (b.min[0] + b.max[0]) / 2, (b.min[2] + b.max[2]) / 2, (b.min[1] + b.max[1]) / 2);
    const p = centre.clone().project(v.camera);
    const r = v.canvas.getBoundingClientRect();
    const t = v.orbitControls.target, c = v.camera.position;
    return { x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height,
             cx: r.left + r.width / 2, cy: r.top + r.height / 2, top: r.top, high: r.height,
             toPiece: c.distanceTo(centre), toTarget: c.distanceTo(t),
             camera: Math.atan2(c.x - t.x, c.z - t.z), piece: Math.atan2(centre.x - t.x, centre.z - t.z),
             apart: Math.hypot(centre.x - t.x, centre.z - t.z),
             nearest: v.orbitControls.minDistance, zoomSpeed: v.orbitControls.zoomSpeed,
             rotateSpeed: v.orbitControls.rotateSpeed };
}"""

# One notch of a mouse wheel, as Chromium reports it, and what it does to the orbit's
# distance (OrbitControls: 0.95 to the zoom speed times the notch over a hundred).
NOTCH = 120


# The page selects what a press lands on, a press on a selected camera's ring turns the
# camera, and one on a selected piece's arrows moves it: a hand framing the view presses
# where none of that is -- on the floor, a wall or the sky, clear of the selection's
# arrows and of anything standing over the world -- nearest the point it aimed for.
FREE_SPOT = """([x0, y0]) => {
    const v = window.fractalViewer, r = v.canvas.getBoundingClientRect();
    let near = null;
    const chosen = v.selectedName && v.meshByName[v.selectedName];
    if (chosen) {
        const p = v.camera.position.clone();
        chosen.getWorldPosition(p);
        p.project(v.camera);
        near = { x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height };
    }
    const free = (x, y) => {
        if (x < r.left + 12 || x > r.right - 12 || y < r.top + 12 || y > r.bottom - 12) return false;
        if (document.elementFromPoint(x, y) !== v.canvas) return false;
        if (near && Math.hypot(x - near.x, y - near.y) < 140) return false;
        const at = { clientX: x, clientY: y, button: 0 };
        return !v.raycastPick(at) && !v.cameraHandleAt(at);
    };
    for (let d = 0; d < 1200; d += 12) {
        for (let a = 0; a < 24; a++) {
            const x = x0 + d * Math.cos(a * Math.PI / 12), y = y0 + d * Math.sin(a * Math.PI / 12);
            if (free(x, y)) return [x, y];
        }
    }
    return null;
}"""


def _drag(page: Page, aim: tuple, by: tuple, shift: bool = False) -> None:
    start = page.evaluate(FREE_SPOT, list(aim))
    assert start, "nowhere in the world to press that is not a piece"
    page.mouse.move(*start)
    if shift:
        page.keyboard.down("Shift")
    page.mouse.down()
    page.mouse.move(start[0] + by[0], start[1] + by[1], steps=16)
    page.mouse.up()
    if shift:
        page.keyboard.up("Shift")
    settled(page)


def by_hand(page: Page, key: str, distance: float) -> None:
    """Frame a piece as a person does, with the controls the hint bar names. A drag turns
    the view round until the piece stands between it and the middle of the orbit (the
    wheel only ever moves towards that middle), Shift+drag brings the piece to the middle
    of the world, and the wheel brings the view to about ``distance`` mm from it. No
    camera is moved behind the page's back; how far to drag and how many notches to turn
    are worked out here, as a hand works them out by eye.

    The orbit's easing is off while it frames: it changes how the view gets there, over
    hundreds of frames of software GL after each drag, and not where it ends."""
    settled(page)
    page.evaluate(EASING, False)
    try:
        _by_hand(page, key, distance)
    finally:
        page.evaluate(EASING, True)
    settled(page)


# The orbit's easing, off or as it was.
EASING = """(on) => {
    const orbit = window.fractalViewer.orbitControls;
    if (!on) { window.__easing = orbit.enableDamping; orbit.enableDamping = false; }
    else if (window.__easing !== undefined) { orbit.enableDamping = window.__easing; }
}"""


def _by_hand(page: Page, key: str, distance: float) -> None:
    import math

    spot = page.evaluate(SIGHTED, key)
    assert spot, f"{key} is not on screen"
    # Turned round about the vertical: OrbitControls turns 2π × rotateSpeed per canvas
    # height dragged, and a drag to the right turns the view the other way round.
    if spot["apart"] > 1:
        # No further round than it takes to stand within 60 degrees of the piece's side
        # of the target, so the view keeps as much of where it looked from as it can.
        apart = (spot["piece"] - spot["camera"] + math.pi) % (2 * math.pi) - math.pi
        turn = math.copysign(max(0.0, abs(apart) - math.radians(60)), apart)
        across = -turn * spot["high"] / (2 * math.pi * spot["rotateSpeed"])
        while abs(across) > 1:
            step = max(-300.0, min(300.0, across))
            _drag(page, (spot["cx"] - step / 2, spot["top"] + 30), (step, 0))
            across -= step
    # Brought nearer in rounds, as an eye corrects as it closes in: the piece to the
    # middle, then the wheel half of the way, then again. A piece a little off the line
    # of sight far away is far off it close to.
    per_notch = 0.95 ** (spot["zoomSpeed"] * NOTCH / 100)
    for _ in range(8):
        spot = _to_the_middle(page, key)
        # The piece is on the line of sight now, nearer than the target: the wheel moves
        # the view along it, and stops at the nearest the orbit allows.
        wanted = max(spot["nearest"], spot["toTarget"] - (spot["toPiece"] - distance))
        notches = round(math.log(min(wanted / spot["toTarget"], 1.0)) / math.log(per_notch))
        if notches <= 0:
            break
        # Over the world, not over what stands in front of it: a piece's badge stands at
        # its middle, which is the middle of the world now, and takes the wheel there.
        # The orbit moves towards its middle wherever the pointer is.
        over = page.evaluate(FREE_SPOT, [spot["cx"], spot["cy"]])
        assert over, "nowhere over the world to turn the wheel"
        page.mouse.move(*over)
        for _ in range(notches if notches <= 3 else (notches + 1) // 2):
            page.mouse.wheel(0, -NOTCH)
        settled(page)


def _to_the_middle(page: Page, key: str) -> dict:
    """Shift+drag until the piece is in the middle of the world, to the pixel. A pan
    moves what is at the target's depth with the hand, and what is nearer further, so
    each drag is shortened by how much nearer the piece is."""
    for _ in range(6):
        spot = page.evaluate(SIGHTED, key)
        off = (spot["cx"] - spot["x"], spot["cy"] - spot["y"])
        if abs(off[0]) < 0.5 and abs(off[1]) < 0.5:
            break
        nearer = spot["toPiece"] / spot["toTarget"]
        _drag(page, (spot["cx"], spot["cy"]), (off[0] * nearer, off[1] * nearer), shift=True)
    return page.evaluate(SIGHTED, key)


# An element of Selected scrolled to just under the stage bar, which stands over the top
# of the panel while it scrolls: scrolled to the panel's top, the element is under it.
UNDER_THE_STAGE_BAR = """(el) => {
    el.scrollIntoView({ block: 'start' });
    const bar = document.getElementById('stage-bar');
    let slot = el.parentElement;
    while (slot && slot.scrollHeight <= slot.clientHeight) slot = slot.parentElement;
    if (!slot) return;
    // The bar stands over the panel's top only while what it heads is in view.
    const shown = slot.getBoundingClientRect(), b = bar && bar.offsetParent ? bar.getBoundingClientRect() : null;
    const under = b && b.bottom > shown.top + 1 && b.top < shown.bottom ? b.bottom : shown.top;
    slot.scrollTop += el.getBoundingClientRect().top - under - 6;
}"""


# Whether Site is folded to its title.
SITE_FOLDED = """(folded) => document.querySelector(".panel[data-panel='site']")
    .classList.contains('collapsed') === folded"""

# The part's editor from its stage bar down: the bar at the top of Selected.
STAGE_BAR_AT_THE_TOP = (
    "() => document.getElementById('stage-bar').scrollIntoView({ block: 'start' })"
)

# A marked line of the SCAD editor made the first its code shows.
MARKED_LINE_FIRST = """(line) => {
    const code = line.closest('.cm-scroller');
    code.scrollTop += line.getBoundingClientRect().top - code.getBoundingClientRect().top - 4;
}"""


@contextmanager
def site_folded(page: Page):
    """Site folded to its title by its ▾ while a picture is taken, as a person folds it
    to give Selected the rail; unfolded again after, so its rows are there to press."""
    fold = page.locator(".panel[data-panel='site'] .panel-collapse")
    fold.click()
    page.wait_for_function(SITE_FOLDED, arg=True)
    try:
        yield
    finally:
        fold.click()
        page.wait_for_function(SITE_FOLDED, arg=False)
