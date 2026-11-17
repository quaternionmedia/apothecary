"""One colour for each layer the world draws, the one table the server and the page read
(docs/viewer.md, "Layers").

A layer is named as the pick scope names it (``static/pick_scope.js``): ``shell:N``,
``category:NAME``, ``grid``, ``machine-buttons``, ``measure``. Its colour is used for what
it draws in the world -- a shell's rings, a category's pieces and the outline round its
cluster on a shell, the build volumes, the badges, the measurement -- and for its cells of
the ring and its row of the Layers window, so a person who sees a colour in one place knows
it in the others. The page is told the colours of the layers a site has, with the site
(``layer_colours``); the ring's cells carry theirs (``apothecary/menu.py``).

- **The world's own**: the alignment grid's, the colour the machines' build volumes are
  drawn in; the machines' buttons', the Machine group's own (``static/tokens.css``), since
  the badges it draws wear it; the measurement's.
- **A shell's**, by its number, innermost first, and from the first again past the last.
- **A category's**, written down below, or for a word nobody wrote down (a picture's word
  is whatever the vocabulary holds) taken from its name, the same every time.

Each colour written down is held apart from the others, from the colours that mean a
state and from the groups' (``tests/test_layer_colours.py``): the badges a machine wears
are the one place a layer and a group share a colour, being the same thing.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

GRID = "grid"
MACHINE_BUTTONS = "machine-buttons"
MEASURE = "measure"
SHELL = "shell:"
CATEGORY = "category:"

TOKENS = Path(__file__).resolve().parent / "static" / "tokens.css"


def _group_colour(variable: str) -> str:
    """A group's colour as ``static/tokens.css`` says it, so it is said once."""
    found = re.search(rf"{re.escape(variable)}:\s*(#[0-9a-f]{{6}})", TOKENS.read_text("utf-8"))
    if found is None:
        raise LookupError(f"{variable} is not in {TOKENS}")
    return found.group(1)


WORLD: Dict[str, str] = {
    # The machines' build volumes are drawn in it; the floor grid's lines stay the faint
    # greys a floor is drawn in.
    GRID: "#33ffdd",
    MACHINE_BUTTONS: _group_colour("--group-machine"),
    MEASURE: "#ff2fd0",
}

# Innermost first. Bright and saturated, apart from the categories' quieter colours, so
# a shell's rings are not read as a category's outline.
SHELLS: Tuple[str, ...] = ("#3d7eff", "#b06cff", "#ff4d94", "#f2f2f2", "#c8ff3e", "#0099ff")

# Written down, in the order the Site window's chips list them. The first seven are the
# sites' subsystems and the theatre's (theatre_site.py); the rest are the parts'
# categories, the universe's clusters, each chosen apart from every colour above it.
CATEGORIES: Dict[str, str] = {
    "wall": "#9c8f7a",
    "furniture": "#8a5a3c",
    "mechanical": "#5b7a99",
    "fluid": "#2f8fbf",
    "electrical": "#d8c11a",
    "lighting": "#e8a33a",
    "scenic": "#8f7bb5",
    "electromechanical": "#bb44aa",
    "machine": "#447744",
    "calibration": "#777700",
    "misc": "#bb4411",
    "enclosure": "#aa5566",
    "appliance": "#ff99ff",
    "music": "#117777",
    "electronics": "#00bb88",
    "storage": "#996611",
    "tooling": "#00ccee",
    "cookie-cutter": "#8866cc",
    "coupon": "#cc3344",
    "rc": "#88bb88",
    "hardware": "#eeaaaa",
    "camera": "#558800",
}


def _hsl(hue: float, saturation: float, lightness: float) -> str:
    """A colour from hue, saturation and lightness, each 0 to 1, written as the page
    always wrote it (each channel rounded half up)."""

    def channel(n: int) -> int:
        k = (n + hue * 12) % 12
        a = saturation * min(lightness, 1 - lightness)
        return math.floor(255 * (lightness - a * max(-1, min(k - 3, 9 - k, 1))) + 0.5)

    return "#{:02x}{:02x}{:02x}".format(channel(0), channel(8), channel(4))


def category_colour(name: str) -> str:
    """A category's colour: written down, else from its name -- its UTF-16 units folded
    as ``hash * 31 + unit`` in 32 bits, the hue that hash's remainder by 360, at 42 %
    saturation and 55 % lightness."""
    if name in CATEGORIES:
        return CATEGORIES[name]
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
    raise KeyError(f"{layer!r} names no layer: shell:N, category:NAME, {', '.join(WORLD)}")


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


def layers_in(site) -> Tuple[List[int], List[str]]:
    """The shells and the categories ``site``'s nodes are on, as the page reads them from
    its tree: every node beneath the root, a category inherited from the nearest node
    above that has one, a site's piece in the universe one node (what it is drawn as is
    no level). Shells innermost first; categories in the order the chips list them."""
    shells: Set[int] = set()
    categories: Set[str] = set()

    def visit(node, inherited: Optional[str]) -> None:
        own = _field(node, "category")
        category = own if own is not None else inherited
        if _field(node, "shell") is not None:
            shells.add(node.shell)
        if category:
            categories.add(category)
        if _field(node, "site_ref") is None:
            for child in _composed(node):
                visit(child, category)

    for child in _composed(site):
        visit(child, _field(site, "category"))
    return sorted(shells), _chip_order(categories)


def _chip_order(categories: Iterable[str]) -> List[str]:
    """Those written down first, in the order they are, then the rest by name."""
    present = set(categories)
    return [c for c in CATEGORIES if c in present] + sorted(present - set(CATEGORIES))


def _drawn_small(site) -> Set[str]:
    """The categories of the boxes a site's piece in the universe is drawn as."""
    found: Set[str] = set()

    def visit(node) -> None:
        if _field(node, "site_ref") is not None:
            found.update(box.category for box in _composed(node) if _field(box, "category"))
            return
        for child in _composed(node):
            visit(child)

    visit(site)
    return found


def layer_colours(site) -> Dict[str, str]:
    """Every colour the page draws ``site`` with, by layer: its shells, its categories --
    those of its nodes and those of the boxes a site's piece is drawn as -- in the chips'
    order, then the world's own."""
    shells, categories = layers_in(site)
    named = _chip_order([*categories, *_drawn_small(site)])
    return {
        **{f"{SHELL}{n}": shell_colour(n) for n in shells},
        **{f"{CATEGORY}{c}": category_colour(c) for c in named},
        **WORLD,
    }
