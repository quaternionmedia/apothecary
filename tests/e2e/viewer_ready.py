"""When the viewer has drawn what it was asked to show, for a check or a screenshot."""

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


def _drag(page: Page, start: tuple, by: tuple, shift: bool = False) -> None:
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
    # Brought to the middle: a pan moves what is at the target's depth with the hand, so
    # it is repeated until the piece is there.
    for _ in range(4):
        spot = page.evaluate(SIGHTED, key)
        off = (spot["cx"] - spot["x"], spot["cy"] - spot["y"])
        if abs(off[0]) < 12 and abs(off[1]) < 12:  # a smaller drag is a click, a choice
            break
        _drag(page, (spot["cx"], spot["cy"]), off, shift=True)
    # The piece is on the line of sight now, nearer than the target: the wheel moves
    # the view along it, and stops at the nearest the orbit allows.
    spot = page.evaluate(SIGHTED, key)
    wanted = max(spot["nearest"], spot["toTarget"] - (spot["toPiece"] - distance))
    per_notch = 0.95 ** (spot["zoomSpeed"] * NOTCH / 100)
    notches = round(math.log(min(wanted / spot["toTarget"], 1.0)) / math.log(per_notch))
    page.mouse.move(spot["cx"], spot["cy"])
    for _ in range(notches):
        page.mouse.wheel(0, -NOTCH)


# An element of Selected scrolled to just under the stage bar, which stands over the top
# of the panel while it scrolls: scrolled to the panel's top, the element is under it.
UNDER_THE_STAGE_BAR = """(el) => {
    el.scrollIntoView({ block: 'start' });
    const bar = document.getElementById('stage-bar');
    let slot = el.parentElement;
    while (slot && slot.scrollHeight <= slot.clientHeight) slot = slot.parentElement;
    if (!slot || !bar || !bar.offsetParent) return;
    slot.scrollTop += el.getBoundingClientRect().top - bar.getBoundingClientRect().bottom - 6;
}"""
