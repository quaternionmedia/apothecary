"""The two facets the page groups pieces by, and their colours: one vocabulary the ring, the
Site window's chips, the Layers window, the universe's clusters and the lanes read.

- **A Kind** is what a part is. It holds categories, the word a part's wrapper or its
  ``part.json`` gives it (``category``), so a part's kind is its category's. The universe
  groups by Kind.
- **A System** is the part of its place a site's piece serves. It holds a site's words, the
  ``category`` a site's node is given (``hierarchy.py``); a piece with no word of its own
  takes the nearest above it, so a machine's board is in its machine's System. A part
  standing loose in a site carries no word, and a site built round one part carries a
  kind's word (datum_core's ``enclosure``): each is grouped by its Kind instead. A site
  groups by System.

Each facet has at most eight values, a ring's cells (``menu.MOST_OPTIONS``), and a value
holds its words whole: no word is in two values of a facet.

**Colours are tokens** of ``static/tokens.css``: a kind's is ``--kind-<name>``, a System's
``--system-<name>``, the name in lower case with a dash for a space. A token may name
another (``var(--kind-machines)``) where a System is the same thing as a kind. A category's
colour is a shade of its kind's: the kind's lightness (CIE L*a*b*) stepped evenly across its
categories in the order the kind lists them, ``STEP`` apart and ``SPAN`` across at most, the
kind's own colour in the middle. A word of a System wears the System's colour.
``tests/test_facets.py`` holds each colour apart from the others, from the colours that mean
a state and from the shells' and the world's own, and at 3:1 against the page's ground.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

KIND = "kind"
SYSTEM = "system"

# A ring's cells: a facet with more values than this could not be one ring.
MOST_VALUES = 8

KINDS: Dict[str, Tuple[str, ...]] = {
    "Electronics": ("electrical", "electronics"),
    "Cameras": ("camera",),
    "Machines": ("machine",),
    "Motors": ("electromechanical",),
    "Test pieces": ("calibration", "coupon"),
    "Shop": ("dust", "tooling", "hardware", "storage"),
    "Housings": ("enclosure", "building"),
    "Things": ("appliance", "furniture", "cookie-cutter", "music", "rc", "misc"),
}

SYSTEMS: Dict[str, Tuple[str, ...]] = {
    "Building": ("wall",),
    "Furniture": ("furniture",),
    "Machines": ("machine",),
    "Mechanical": ("mechanical",),
    "Electrical": ("electrical",),
    "Plumbing": ("fluid",),
    "Lighting": ("lighting",),
    "Scenery": ("scenic",),
}

FACETS: Dict[str, Dict[str, Tuple[str, ...]]] = {KIND: KINDS, SYSTEM: SYSTEMS}

# How far apart a kind's categories are in lightness, and across how much at most.
STEP = 10.0
SPAN = 40.0

TOKENS = Path(__file__).resolve().parent / "static" / "tokens.css"


def _holder(facet: str, word: str) -> Optional[str]:
    for name, words in FACETS[facet].items():
        if word in words:
            return name
    return None


def kind_of(category: Optional[str]) -> Optional[str]:
    """The kind a part's category is in, or None for a word no kind holds."""
    return _holder(KIND, category) if category else None


def system_of(word: Optional[str]) -> Optional[str]:
    """The System a site's word is in, or None for a loose word."""
    return _holder(SYSTEM, word) if word else None


def token(facet: str, name: str) -> str:
    """The token that colours ``name`` of ``facet``: ``--kind-test-pieces``."""
    if name not in FACETS[facet]:
        raise KeyError(f"{name!r} is no {facet}: {', '.join(FACETS[facet])}")
    return f"--{facet}-{name.lower().replace(' ', '-')}"


def token_colour(variable: str, sheet: Optional[str] = None) -> str:
    """The colour ``static/tokens.css`` gives ``variable``, as ``#rrggbb``, following a
    ``var(--other)`` to the colour it names."""
    text = sheet if sheet is not None else TOKENS.read_text("utf-8")
    seen: List[str] = []
    while variable not in seen:
        seen.append(variable)
        found = re.search(rf"{re.escape(variable)}:\s*(#[0-9a-f]{{6}}|var\((--[a-z0-9-]+)\))", text)
        if found is None:
            raise LookupError(f"{variable} is not in {TOKENS}")
        if found.group(2) is None:
            return found.group(1)
        variable = found.group(2)
    raise LookupError(f"{variable} names itself through {' -> '.join(seen)}")


def colour(facet: str, name: str) -> str:
    """The colour of ``name`` of ``facet``, as its token says it."""
    return token_colour(token(facet, name))


# --- shades -------------------------------------------------------------------------------

_WHITE = (0.95047, 1.0, 1.08883)  # D65


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _encoded(linear: float) -> int:
    linear = max(0.0, min(1.0, linear))
    value = 12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1 / 2.4) - 0.055
    return math.floor(255 * value + 0.5)


def lab(hex_colour: str) -> Tuple[float, float, float]:
    """CIE L*a*b* (D65) of a ``#rrggbb`` colour."""
    r, g, b = (_linear(int(hex_colour[i : i + 2], 16) / 255) for i in (1, 3, 5))
    xyz = (
        (r * 0.4124 + g * 0.3576 + b * 0.1805) / _WHITE[0],
        r * 0.2126 + g * 0.7152 + b * 0.0722,
        (r * 0.0193 + g * 0.1192 + b * 0.9505) / _WHITE[2],
    )
    fx, fy, fz = (t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in xyz)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def from_lab(lightness: float, a: float, b: float) -> str:
    """A ``#rrggbb`` colour from CIE L*a*b* (D65), each channel clipped to what sRGB holds."""
    fy = (lightness + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def inverse(t: float) -> float:
        return t**3 if t**3 > 0.008856 else (t - 16 / 116) / 7.787

    x, y, z = inverse(fx) * _WHITE[0], inverse(fy), inverse(fz) * _WHITE[2]
    r = 3.2406 * x - 1.5372 * y - 0.4986 * z
    g = -0.9689 * x + 1.8758 * y + 0.0415 * z
    bl = 0.0557 * x - 0.2040 * y + 1.0570 * z
    return "#{:02x}{:02x}{:02x}".format(_encoded(r), _encoded(g), _encoded(bl))


def shades(base: str, count: int) -> List[str]:
    """``count`` shades of ``base``: its lightness stepped evenly, ``STEP`` apart and ``SPAN``
    across at most, ``base`` in the middle."""
    step = min(STEP, SPAN / (count - 1)) if count > 1 else 0.0
    lightness, a, b = lab(base)
    return [from_lab(lightness + step * (i - (count - 1) / 2), a, b) for i in range(count)]


def category_shade(category: str) -> Optional[str]:
    """A part's category's colour, a shade of its kind's; None for a word no kind holds."""
    kind = kind_of(category)
    if kind is None:
        return None
    words = KINDS[kind]
    return shades(colour(KIND, kind), len(words))[words.index(category)]


# --- a site's pieces ---------------------------------------------------------------------


def _composed(node) -> list:
    return [
        *getattr(node, "children", ()),
        *getattr(node, "additions", ()),
        *getattr(node, "subtractions", ()),
    ]


def _pieces(site) -> Iterator[Tuple[str, object, Optional[str]]]:
    """Every node beneath ``site``'s root with its dotted path and its word: its own, else
    the nearest above it that has one. A site's piece in the universe is one node: what it
    is drawn as is no level (``layer_colours.layers_in`` reads a tree the same way)."""

    def visit(
        node, path: str, inherited: Optional[str]
    ) -> Iterator[Tuple[str, object, Optional[str]]]:
        own = getattr(node, "category", None)
        word = own if own is not None else inherited
        yield path, node, word
        if getattr(node, "site_ref", None) is None:
            for child in _composed(node):
                yield from visit(child, f"{path}.{child.name}", word)

    for child in _composed(site):
        yield from visit(child, child.name, getattr(site, "category", None))


def facet_of(site) -> str:
    """The facet ``site`` is grouped by: Kind in the universe, whose pieces lie on its
    shells, and System in a site, whose pieces lie on none."""
    on_shells = any(getattr(node, "shell", None) is not None for _, node, _ in _pieces(site))
    return KIND if on_shells else SYSTEM


def kind_and_system(
    by: str, word: Optional[str], part_category: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """A piece's Kind and System, from its word (its own or inherited) and, for a piece
    that is a part, its part's category. In the universe a piece has its part's kind and
    no System. In a site it has its word's System, and its part's kind where it is a part;
    a piece whose word no System holds is grouped by its kind, its part's or, where its
    word is a kind's category (datum_core's tray, an enclosure), its word's."""
    if by == KIND:
        return kind_of(part_category or word), None
    system = system_of(word)
    if part_category:
        return kind_of(part_category), system
    return (kind_of(word) if system is None else None), system


def kinds_and_systems(
    site, part_category: Callable[[str], Optional[str]] = lambda _: None
) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """Each piece of ``site`` by its dotted path: its Kind and its System
    (``kind_and_system``), ``part_category`` giving a part's category by its name."""
    by = facet_of(site)
    found: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for path, node, word in _pieces(site):
        ref = getattr(node, "part_ref", None)
        found[path] = kind_and_system(by, word, part_category(ref) if ref else None)
    return found


# --- what a site is sent ------------------------------------------------------------------


def _value(facet: str, name: str, words_present: Iterable[str]) -> Dict[str, object]:
    words = FACETS[facet][name]
    own = colour(facet, name)
    tints = shades(own, len(words)) if facet == KIND else [own] * len(words)
    here = set(words_present)
    return {
        "name": name,
        "token": token(facet, name),
        "colour": own,
        "words": [{"word": w, "colour": tints[i]} for i, w in enumerate(words) if w in here],
    }


def facets_of(
    site, part_category: Callable[[str], Optional[str]] = lambda _: None
) -> Dict[str, object]:
    """What the page groups ``site``'s pieces by, sent with it beside ``layer_colours``:

    - ``by``, the facet: ``kind`` in the universe, ``system`` in a site;
    - ``values``, each of its values the site has, in the vocabulary's order, with its
      token, its colour and its words the site has, each with its colour;
    - ``loose``, the words the site has that no value holds, by name;
    - ``kinds``, in a site, the kinds its pieces with no System are grouped by, each as a
      value is, its words the categories those pieces are of.

    ``part_category`` gives a part's category by its name, for a piece that is a part."""
    by = facet_of(site)
    words: set = set()
    loose_kinds: Dict[str, set] = {}
    for _, node, word in _pieces(site):
        if word:
            words.add(word)
        ref = getattr(node, "part_ref", None)
        category = part_category(ref) if ref else None
        kind, system = kind_and_system(by, word, category)
        if by == SYSTEM and system is None and kind is not None:
            loose_kinds.setdefault(kind, set()).add(category or word)
    values = [_value(by, name, words) for name, held in FACETS[by].items() if words & set(held)]
    kinds = [_value(KIND, name, loose_kinds[name]) for name in KINDS if name in loose_kinds]
    return {
        "by": by,
        "values": values,
        "loose": sorted(w for w in words if _holder(by, w) is None),
        "kinds": kinds,
    }
