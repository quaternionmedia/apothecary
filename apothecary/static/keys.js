/* Keys: the one check every shortcut of the page asks, and how a key is named.
 *
 * A shortcut acts unless the focus takes that key itself (docs/plans/
 * input-2026-10-12.md, "keys act where they belong"):
 *
 * - a box typed in, a drop-down or editable text (the SCAD editor) takes every
 *   key: a person is typing there, and no shortcut acts;
 * - a slider takes the arrows, Page Up and Page Down, Home and End;
 * - a button, a link, a tick-box or a fold's summary takes Enter and Space.
 *
 * Page Up and Page Down step a level only while the world has the keys (the
 * canvas has the focus, or nothing has it and the last press was in the world);
 * anywhere else they scroll, as the browser does. Ctrl, Alt, Meta or Shift held
 * rules Backspace out.
 *
 * A shortcut is named by the key it prints, with its modifiers: "m", "Shift+m",
 * "PageDown", "Ctrl+s". A letter is named in lower case with Shift said, so Caps
 * Lock changes nothing; another printed character carries its Shift in itself
 * ("?", "~"). A shortcut is matched by that name, and by the key's position on a
 * US keyboard as well (KeyM for "m"), so a layout that prints something else
 * there still reaches it.
 *
 * Plain ES module, no dependencies; it listens to nothing.
 */

const MODIFIER_KEYS = new Set(["Control", "Alt", "AltGraph", "Shift", "Meta", "OS", "CapsLock", "Dead", "Unidentified", "Process"]);
// Input types that are not typed in: a slider, a tick-box, a button.
const NOT_TYPED = /^(range|checkbox|radio|button|submit|reset|color|file|image)$/;
const SLIDER_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End"]);
const PRESS_KEYS = new Set(["Enter", " "]);

/* Whether `el` is somewhere a person types: a text box, a number box, a text area, a
 * drop-down (its letters choose), or editable text. */
export function typing(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT") return true;
    return tag === "INPUT" && !NOT_TYPED.test(el.type);
}

/* Whether the focused element takes this key itself. */
export function takes(el, key) {
    if (!el || el.nodeType !== 1 || el === document.body) return false;
    if (typing(el)) return true;
    if (el.tagName === "INPUT" && el.type === "range") return SLIDER_KEYS.has(key);
    if (/^(BUTTON|A|SUMMARY)$/.test(el.tagName) || (el.tagName === "INPUT" && NOT_TYPED.test(el.type))) return PRESS_KEYS.has(key);
    return false;
}

/* The one check: whether a shortcut may act on this key press. Never while typing;
 * never on a key the focus takes; a modifier held rules Backspace out. */
export function mayAct(event, focus = document.activeElement) {
    if (!event || event.isComposing) return false;
    if (event.key === "Backspace" && (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey)) return false;
    return !takes(focus, event.key);
}

const LETTER = /^[a-z]$/i;

/* A key pressed, as a shortcut names it; a modifier pressed alone is no shortcut: null. */
export function comboOf(e) {
    const key = e && e.key;
    if (!key || MODIFIER_KEYS.has(key)) return null;
    const letter = LETTER.test(key);
    const named = key.length > 1;
    const parts = [];
    if (e.ctrlKey) parts.push("Ctrl");
    if (e.altKey) parts.push("Alt");
    if ((named || letter) && e.shiftKey) parts.push("Shift");
    if (e.metaKey) parts.push("Meta");
    parts.push(key === " " ? "Space" : letter ? key.toLowerCase() : key);
    return parts.join("+");
}

/* The same press by where the key is, Shift always said: "Shift+KeyM". */
export function codeComboOf(e) {
    if (!e || !e.code || MODIFIER_KEYS.has(e.key)) return null;
    const parts = [];
    if (e.ctrlKey) parts.push("Ctrl");
    if (e.altKey) parts.push("Alt");
    if (e.shiftKey) parts.push("Shift");
    if (e.metaKey) parts.push("Meta");
    parts.push(e.code);
    return parts.join("+");
}

// A printed key's place on a US keyboard, Shift said where it prints the character.
const US_CODES = {
    "`": "Backquote", "~": "Shift+Backquote", "-": "Minus", "=": "Equal", "[": "BracketLeft", "]": "BracketRight",
    "\\": "Backslash", ";": "Semicolon", "'": "Quote", ",": "Comma", ".": "Period", "/": "Slash", "?": "Shift+Slash",
    Space: "Space",
};

/* Where a shortcut's key sits on a US keyboard, as codeComboOf names a press there. */
export function codeOfCombo(combo) {
    if (!combo) return null;
    const parts = combo.split("+");
    const key = combo.endsWith("++") ? "+" : parts.pop();
    const mods = combo.endsWith("++") ? parts.slice(0, -2) : parts;
    let code;
    if (LETTER.test(key)) code = `Key${key.toUpperCase()}`;
    else if (/^[0-9]$/.test(key)) code = `Digit${key}`;
    else if (US_CODES[key]) code = US_CODES[key];
    else if (key.length > 1) code = key;  // PageDown, F2, Enter: their own codes
    else return null;
    const shifted = code.startsWith("Shift+");
    if (shifted) code = code.slice("Shift+".length);
    const order = ["Ctrl", "Alt", "Shift", "Meta"].filter((m) => mods.includes(m) || (m === "Shift" && shifted));
    return [...order, code].join("+");
}

/* Whether a press is this shortcut: by the key it printed, or by where the key is. */
export function matches(e, combo) {
    if (!combo) return false;
    if (comboOf(e) === combo) return true;
    const code = codeOfCombo(combo);
    return !!code && codeComboOf(e) === code;
}

/* The world's own keys: whether Page Up and Page Down step a level now. `world` is
 * the canvas; `lastPressInWorld` whether the last press landed in the world. */
export function worldHasKeys(world, lastPressInWorld) {
    const focus = document.activeElement;
    if (focus === world) return true;
    return (!focus || focus === document.body) && !!lastPressInWorld;
}
