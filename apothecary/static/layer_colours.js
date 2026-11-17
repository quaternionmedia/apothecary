/* The colours of the layers the site in view has, as the server sends them with it
 * (apothecary/layer_colours.py, the one table): a shell's rings, a category's pieces and
 * its cluster's outline, the build volumes, the badges, the measurement, and each one's
 * cells of the ring and row of the Layers window. Read here, never written here.
 *
 *   takeLayerColours(payload)   the colours a site's payload carries, in place of the last
 *   layerHex(id)                a layer's colour as "#rrggbb", or null
 *   layerColour(id, fallback)   the same as a number, for three.js, or `fallback`
 *   categoriesInOrder()         the categories it has a colour for, in the order the
 *                               Site window's chips list them (those written down first)
 *
 * Plain ES module, no dependencies, so node can hold it (tests/test_layer_colours_page.py).
 */

const colours = new Map();

export function takeLayerColours(payload) {
    if (!payload || !payload.layer_colours) return false;
    colours.clear();
    for (const [id, hex] of Object.entries(payload.layer_colours)) {
        if (/^#[0-9a-f]{6}$/.test(hex)) colours.set(id, hex);
    }
    return true;
}

export function layerHex(id) {
    return colours.get(id) ?? null;
}

export function layerColour(id, fallback) {
    const hex = colours.get(id);
    return hex ? parseInt(hex.slice(1), 16) : fallback;
}

export function categoriesInOrder() {
    return [...colours.keys()].filter((id) => id.startsWith("category:")).map((id) => id.slice("category:".length));
}
