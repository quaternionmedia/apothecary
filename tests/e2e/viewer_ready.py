"""When the viewer has drawn what it was asked to show, for a check or a screenshot."""

from playwright.sync_api import Page

FRAMES = """(n) => new Promise((done) => {
    const step = () => (n-- > 0 ? requestAnimationFrame(step) : done());
    step();
})"""

# anchors.js tests whether a badge is behind something every 6 frames.
OCCLUSION_TESTED = 7


def settled(page: Page, frames: int = 2) -> None:
    """Wait until the level on screen has its geometry and `frames` frames have drawn it."""
    page.evaluate("() => window.fractalViewer.waveDone")
    page.evaluate(FRAMES, frames)
