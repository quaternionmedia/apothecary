"""One colour for each layer the world draws, the one table the server and the page read
(docs/viewer.md, "Layers").

A layer is named as the pick scope names it (``static/pick_scope.js``): ``shell:N``,
``system:NAME``, ``category:NAME``, ``kind:NAME`` (a heading over its categories' layers,
``facets.py``), ``grid``, ``machine-buttons``, ``measure``. Its colour is used for what it
draws in the world -- a shell's rings, a System's or a category's pieces, the outline round
a cluster on a shell, the build volumes, the badges, the measurement -- and for its cells of
the ring and its row of the Layers window, so a person who sees a colour in one place knows
it in the others. The page is told the colours of the layers a site has, with the site
(``layer_colours``); the ring's cells carry theirs (``apothecary/menu.py``).

- **The world's own**: the alignment grid's, the colour the machines' build volumes are
  drawn in; the machines' buttons', the Machine group's own (``static/tokens.css``), since
  the badges it draws wear it; the measurement's.
- **A shell's**, by its number, innermost first, and from the first again past the last.
- **A System's, a Kind's and a category's** are the facets' (``facets.py``, their tokens):
  a category a shade of its kind's. A word neither facet holds (a picture's word is
  whatever the vocabulary holds) takes a colour from its name, the same every time.

The shells' and the world's own are held apart from each other, from the colours that mean
a state and from the groups' (``tests/test_layer_colours.py``), and the facets' from them
(``tests/test_facets.py``): the badges a machine wears are the one place a layer and a
group share a colour, being the same thing.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .facets import CATEGORY_LAYER as CATEGORY
from .facets import SYSTEM, category_shade, facets_of, layer_of, named
from .facets import colour as facet_colour

GRID = "grid"
MACHINE_BUTTONS = "machine-buttons"
MEASURE = "measure"
SHELL = "shell:"

TOKENS = Path(__file__).resolve().parent / "static" / "tokens.css"


def _token(variable: str) -> str:
    """A colour as ``static/tokens.css`` says it, so it is said once."""
    found = re.search(rf"{re.escape(variable)}:\s*(#[0-9a-f]{{6}})", TOKENS.read_text("utf-8"))
    if found is None:
        raise LookupError(f"{variable} is not in {TOKENS}")
    return found.group(1)


WORLD: Dict[str, str] = {
    # The machines' build volumes are drawn in it; the floor grid's lines stay the faint
    # greys a floor is drawn in.
    GRID: "#33ffdd",
    MACHINE_BUTTONS: _token("--group-machine"),
    MEASURE: "#ff2fd0",
}

# Innermost first. Bright and saturated, apart from the facets' quieter colours, so
# a shell's rings are not read as a cluster's outline; and none the measurement's hue,
# which is drawn over them.
SHELLS: Tuple[str, ...] = ("#3d7eff", "#b06cff", "#ff6a00", "#f2f2f2", "#c8ff3e", "#0099ff")


def _hsl(hue: float, saturation: float, lightness: float) -> str:
    """A colour from hue, saturation and lightness, each 0 to 1, written as the page
    always wrote it (each channel rounded half up)."""

    def channel(n: int) -> int:
        k = (n + hue * 12) % 12
        a = saturation * min(lightness, 1 - lightness)
        return math.floor(255 * (lightness - a * max(-1, min(k - 3, 9 - k, 1))) + 0.5)

    return "#{:02x}{:02x}{:02x}".format(channel(0), channel(8), channel(4))


def category_colour(name: str) -> str:
    """A category's colour: a shade of its kind's (``facets.category_shade``), else, for a
    word no kind holds, from its name -- its UTF-16 units folded as ``hash * 31 + unit``
    in 32 bits, the hue that hash's remainder by 360, at 42 % saturation and 55 %
    lightness."""
    shade = category_shade(name)
    if shade is not None:
        return shade
    folded = 0
    units = name.encode("utf-16-le")
    for i in range(0, len(units), 2):
        folded = (folded * 31 + int.from_bytes(units[i : i + 2], "little")) % 2**32
    return _hsl((folded % 360) / 360, 0.42, 0.55)


def shell_colour(n: int) -> str:
    """Shell ``n``'s colour, innermost first, from the first again past the last."""
    return SHELLS[n % len(SHELLS)]


def colour_of(layer: str) -> str:
    """The colour of the layer named ``layer``."""
    if layer in WORLD:
        return WORLD[layer]
    if layer.startswith(SHELL):
        return shell_colour(int(layer[len(SHELL) :]))
    if layer.startswith(CATEGORY):
        return category_colour(layer[len(CATEGORY) :])
    value = named(layer)
    if value is not None:
        return facet_colour(*value)
    raise KeyError(
        f"{layer!r} names no layer: shell:N, system:NAME, kind:NAME, category:NAME, "
        f"{', '.join(WORLD)}"
    )


# A node is read for what it holds: a site's tree is Assemblies, and anything else handed
# in for one (a stand-in a test builds) gives what it has and nothing it lacks.
def _composed(node) -> list:
    return [
        *getattr(node, "children", ()),
        *getattr(node, "additions", ()),
        *getattr(node, "subtractions", ()),
    ]


def _field(node, name: str):
    return getattr(node, name, None)


def shells_in(site) -> List[int]:
    """The shells ``site``'s nodes are on, innermost first, as the page reads them from its
    tree: every node beneath the root, a site's piece in the universe one node (what it is
    drawn as is no level)."""
    shells: Set[int] = set()

    def visit(node) -> None:
        if _field(node, "shell") is not None:
            shells.add(node.shell)
        if _field(node, "site_ref") is None:
            for child in _composed(node):
                visit(child)

    for child in _composed(site):
        visit(child)
    return sorted(shells)


def _drawn_small(site) -> List[str]:
    """The layers of the boxes a site's piece in the universe is drawn as: each box's in
    its own site, by its word."""
    found: List[str] = []

    def visit(node) -> None:
        if _field(node, "site_ref") is not None:
            for box in _composed(node):
                layer = layer_of(SYSTEM, _field(box, "category"), None)
                if layer is not None and layer not in found:
                    found.append(layer)
            return
        for child in _composed(node):
            visit(child)

    visit(site)
    return found


def layer_colours(
    site, part_category: Callable[[str], Optional[str]] = lambda _: None
) -> Dict[str, str]:
    """Every colour the page draws ``site`` with, by layer: its shells; then, as the facets
    list them (``facets.facets_of``), each value and each kind its pieces are grouped by,
    a heading, and its words' layers; the words neither holds; the layers of the boxes a
    site's piece in the universe is drawn as; then the world's own."""
    sent = facets_of(site, part_category)
    found: Dict[str, str] = {f"{SHELL}{n}": shell_colour(n) for n in shells_in(site)}
    for group in (*sent["values"], *sent["kinds"]):
        found[group["layer"]] = group["colour"]
        for word in group["words"]:
            found.setdefault(word["layer"], word["colour"])
    for word in sent["loose"]:
        found.setdefault(word["layer"], colour_of(word["layer"]))
    for layer in _drawn_small(site):
        found.setdefault(layer, colour_of(layer))
    return {**found, **WORLD}
