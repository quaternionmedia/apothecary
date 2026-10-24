"""When the viewer has drawn what it was asked to show, for a check or a screenshot."""

from playwright.sync_api import Page, expect

# Gives the viewer a `waveDone` promise (its latest wave of geometry loads) when it
# has none of its own. Installed with page.add_init_script, before the page's script
# assigns window.fractalViewer, so the first wave is caught too.
WAVE_DONE = """
Object.defineProperty(window, 'fractalViewer', {
    configurable: true,
    set(viewer) {
        Object.defineProperty(window, 'fractalViewer', { value: viewer, writable: true });
        if ('waveDone' in viewer) return;
        const wave = viewer.scheduleWaveLoad;
        viewer.waveDone = Promise.resolve();
        viewer.scheduleWaveLoad = function (nodes) {
            const done = wave.call(this, nodes);
            if (done) this.waveDone = done;
            return done;
        };
    },
});
"""

FRAMES = """(n) => new Promise((done) => {
    const step = () => (n-- > 0 ? requestAnimationFrame(step) : done());
    step();
})"""

# anchors.js tests whether a badge is behind something every 6 frames.
OCCLUSION_TESTED = 7


def settled(page: Page, frames: int = 2) -> None:
    """Wait until the level on screen has its geometry and `frames` frames have drawn it."""
    if page.evaluate("() => !!window.fractalViewer && 'waveDone' in window.fractalViewer"):
        page.evaluate("() => window.fractalViewer.waveDone")
    else:
        expect(page.locator("#status")).to_contain_text("Loaded")
    page.evaluate(FRAMES, frames)
