"""When the viewer has drawn what it was asked to show, for a check or a screenshot."""

from playwright.sync_api import Page

FRAMES = """(n) => new Promise((done) => {
    const step = () => (n-- > 0 ? requestAnimationFrame(step) : done());
    step();
})"""

# The hint bar fades over 0.6 s once a few things are done: a picture taken while it
# fades catches it half way, and differs from run to run.
HINT_STILL = """() => Promise.all(
    (document.getElementById('viewer-hint')?.getAnimations() || [])
        .map((a) => a.finished.catch(() => null))
)"""

# anchors.js tests whether a badge is behind something every 6 frames.
OCCLUSION_TESTED = 7


def settled(page: Page, frames: int = 2) -> None:
    """Wait until the level on screen has its geometry, the hint bar is not fading, and
    `frames` frames have drawn it."""
    page.evaluate("() => window.fractalViewer.waveDone")
    page.evaluate(HINT_STILL)
    page.evaluate(FRAMES, frames)
