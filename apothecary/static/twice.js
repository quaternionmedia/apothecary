/* Twice: a button whose press cannot be undone in the page asks to be pressed again.
 *
 * The rule (docs/plans/input-2026-10-12.md, "confirming by consequence"): what the
 * page can undo asks nothing; what it cannot -- a site rebuilt, a picture forgotten,
 * a camera removed, a board rebooted, a print abandoned -- is pressed twice, the
 * control itself saying "Again to ..." between the two; what heats, moves or
 * flashes a machine asks in a dialog; the emergency stop never asks. The ring asks
 * twice on its own wedge (ring.js); this is the same for a button.
 *
 * again(button, verb) answers whether this press is the second: the first turns the
 * button's words to "Again to <verb>" for AGAIN_MS and answers false; a press within
 * that answers true and puts the words back. No button (a call made for a choice
 * already confirmed): true.
 *
 * Plain ES module, no dependencies; it listens to nothing.
 */

export const AGAIN_MS = 6000;

export function again(button, verb, ms = AGAIN_MS) {
    if (!button) return true;
    const now = performance.now();
    const until = Number(button.dataset.againUntil || 0);
    if (until && now < until) {
        settle(button);
        return true;
    }
    if (!until) button.dataset.againWas = button.textContent;
    button.dataset.againUntil = String(now + ms);
    button.textContent = `Again to ${verb}`;
    button.classList.add("again");
    setTimeout(() => {
        if (button.isConnected && Number(button.dataset.againUntil || 0) <= performance.now() + 1) settle(button);
    }, ms);
    return false;
}

function settle(button) {
    if (button.dataset.againWas !== undefined) button.textContent = button.dataset.againWas;
    delete button.dataset.againUntil;
    delete button.dataset.againWas;
    button.classList.remove("again");
}
