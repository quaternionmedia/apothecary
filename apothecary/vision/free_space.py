"""The free space on a structure's top: what rests on it, and where a picture fits clear of it.

One reading of a surface, shared by the two things that need it. Pinning a picture
at a host lays it where the widest picture of its shape fits in the part of the top
nothing stands on, and keeps that place (``views.View.offset``). Reading a view back
names, for each shape found in it, what standing on the host its footprint overlaps:
a flag, never a refusal -- Make still makes it, and the site's layout check then
holds the piece like any other.

Rectangles are the site's frame, in millimetres, upright (x and y), as footprints are.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

from typing import AbstractSet, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from ..hierarchy import Assembly

RESTING_MM = 0.5  # an underside this near a top rests on it


class Area(NamedTuple):
    """An upright rectangle of the site's frame: its low and high x and y, in mm."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def depth(self) -> float:
        return self.y1 - self.y0

    @property
    def centre(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def overlaps(self, other: "Area") -> bool:
        """Whether the two have an area in common; edges that only touch do not."""
        return (
            self.x0 < other.x1 and other.x0 < self.x1 and self.y0 < other.y1 and other.y0 < self.y1
        )


class Fit(NamedTuple):
    """Where a picture is laid on a top: its middle, and the widest it can be there
    clear of what stands on the top."""

    centre: Tuple[float, float]
    width: float


def footprint(node: Assembly) -> Optional[Area]:
    """A structure's footprint in the site's frame, or None when it has no bounds."""
    b = node.world_bounds()
    if b is None:
        return None
    return Area(b.min_point.x, b.min_point.y, b.max_point.x, b.max_point.y)


def resting_on(
    site: Assembly, host: str, leave_out: AbstractSet[str] = frozenset()
) -> List[Tuple[str, Area]]:
    """The site's root structures resting on ``host``'s top, each with its footprint:
    its underside at the top's height and its footprint over some of the top. What
    stands beside the host, or hangs above it, is not on it; ``leave_out`` names what
    is not counted (a site's made pieces and cameras, which belong to its pictures)."""
    node = next((c for c in site.children if c.name == host), None)
    top = footprint(node) if node is not None else None
    if top is None:
        return []
    height = node.world_bounds().max_point.z
    resting = []
    for other in site.children:
        if other.name == host or other.name in leave_out:
            continue
        b = other.world_bounds()
        if b is None or abs(b.min_point.z - height) > RESTING_MM:
            continue
        area = footprint(other)
        if area is not None and area.overlaps(top):
            resting.append((other.name, area))
    return resting


def overlapping(area: Area, standing: Iterable[Tuple[str, Area]]) -> List[str]:
    """The names of what ``area`` overlaps, in the order given."""
    return [name for name, other in standing if area.overlaps(other)]


def _clear(top: Area, standing: Sequence[Area]) -> List[Area]:
    """Every rectangle of the top, its sides on the top's edges or what stands on it,
    that nothing standing overlaps."""
    xs = sorted(
        {top.x0, top.x1, *(min(max(v, top.x0), top.x1) for s in standing for v in (s.x0, s.x1))}
    )
    ys = sorted(
        {top.y0, top.y1, *(min(max(v, top.y0), top.y1) for s in standing for v in (s.y0, s.y1))}
    )
    clear = []
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1 :]:
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1 :]:
                    candidate = Area(x0, y0, x1, y1)
                    if any(candidate.overlaps(s) for s in standing):
                        break  # a deeper one overlaps it too
                    clear.append(candidate)
    return clear


def fit(top: Area, standing: Sequence[Area], tallness: float) -> Fit:
    """The widest picture ``tallness`` deep for its width that fits on ``top`` clear of
    ``standing``, centred in the clear rectangle that holds it; of two as wide, the
    one nearer the top's middle. With nothing clear, the top's own middle and width."""

    def widest(area: Area) -> float:
        return min(area.width, area.depth / tallness)

    middle = top.centre
    best: Optional[Tuple[float, float, Area]] = None
    for area in _clear(top, standing):
        width = widest(area)
        away = (area.centre[0] - middle[0]) ** 2 + (area.centre[1] - middle[1]) ** 2
        if best is None or (width, -away) > (best[0], -best[1]):
            best = (width, away, area)
    if best is None or best[0] <= 0:
        return Fit(centre=middle, width=widest(top))
    return Fit(centre=best[2].centre, width=best[0])
